"""
Prompt Intelligence
===================
Learn which prompts monetize best, rank prompts, generate optimized variants.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import FacebookDatabase, facebook_db

log = logging.getLogger("facebook.intelligence.prompts")


class PromptIntelligence:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db

    def rebuild_from_content(self, page_id: str) -> Dict[str, Any]:
        """Aggregate all content with prompts into prompt_intel rankings."""
        posts = self.db.list_content(page_id, limit=5000)
        buckets: Dict[str, Dict[str, Any]] = {}
        for p in posts:
            prompt = (p.get("prompt") or "").strip()
            if not prompt:
                continue
            ph = _prompt_hash(prompt)
            b = buckets.setdefault(ph, {
                "prompt_text": prompt,
                "prompt_hash": ph,
                "ai_model": p.get("ai_model"),
                "character_id": p.get("character_id"),
                "style": p.get("style"),
                "sample_count": 0,
                "total_revenue": 0.0,
                "total_reach": 0.0,
                "total_views": 0.0,
                "rpm_sum": 0.0,
                "eng_sum": 0.0,
                "rpm_n": 0,
                "eng_n": 0,
            })
            b["sample_count"] += 1
            b["total_revenue"] += float(p.get("revenue") or 0)
            b["total_reach"] += float(p.get("reach") or 0)
            b["total_views"] += float(p.get("views") or 0)
            if p.get("rpm") is not None:
                b["rpm_sum"] += float(p["rpm"])
                b["rpm_n"] += 1
            if p.get("engagement_rate") is not None:
                b["eng_sum"] += float(p["engagement_rate"])
                b["eng_n"] += 1
            if p.get("ai_model"):
                b["ai_model"] = p.get("ai_model")
            if p.get("character_id"):
                b["character_id"] = p.get("character_id")
            if p.get("style"):
                b["style"] = p.get("style")

        stored = 0
        for ph, b in buckets.items():
            avg_rpm = (b["rpm_sum"] / b["rpm_n"]) if b["rpm_n"] else (
                (b["total_revenue"] / b["total_views"] * 1000.0) if b["total_views"] else 0.0
            )
            avg_eng = (b["eng_sum"] / b["eng_n"]) if b["eng_n"] else 0.0
            score = self._score(
                sample_count=b["sample_count"],
                total_revenue=b["total_revenue"],
                avg_rpm=avg_rpm,
                avg_engagement=avg_eng,
                total_views=b["total_views"],
            )
            self.db.upsert_prompt_intel(page_id, {
                "prompt_text": b["prompt_text"],
                "prompt_hash": ph,
                "ai_model": b.get("ai_model"),
                "character_id": b.get("character_id"),
                "style": b.get("style"),
                "sample_count": b["sample_count"],
                "total_revenue": b["total_revenue"],
                "total_reach": b["total_reach"],
                "total_views": b["total_views"],
                "avg_rpm": avg_rpm,
                "avg_engagement": avg_eng,
                "score": score,
            })
            stored += 1
        return {"status": "success", "prompts_ranked": stored}

    def rank(self, page_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self.rebuild_from_content(page_id)
        return self.db.rank_prompts(page_id, limit=limit)

    def best_monetizing(self, page_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        ranked = self.rank(page_id, limit=limit * 2)
        # Prefer revenue + rpm
        ranked.sort(
            key=lambda r: (float(r.get("total_revenue") or 0) * 2 + float(r.get("avg_rpm") or 0)),
            reverse=True,
        )
        return ranked[:limit]

    def generate_variants(
        self,
        page_id: str,
        prompt_text: Optional[str] = None,
        n: int = 5,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate optimized prompt variants based on top-performing prompts.
        Uses local LLM when available; always returns deterministic structural variants.
        """
        top = self.best_monetizing(page_id, limit=5)
        base = prompt_text
        if not base and top:
            base = top[0].get("prompt_text")
        if not base:
            return {"status": "error", "message": "No base prompt available. Provide prompt_text or ingest content with prompts."}

        structural = self._structural_variants(base, top)
        llm_variants: List[str] = []
        if use_llm:
            llm_variants = self._llm_variants(base, top, n=n)

        # Dedupe preserving order
        seen = set()
        variants = []
        for v in llm_variants + structural:
            key = v.strip().lower()
            if key and key not in seen and key != base.strip().lower():
                seen.add(key)
                variants.append(v.strip())
            if len(variants) >= n:
                break

        # Persist on matching prompt intel row
        ph = _prompt_hash(base)
        existing = None
        for row in self.db.rank_prompts(page_id, limit=100):
            if row.get("prompt_hash") == ph or row.get("prompt_text") == base:
                existing = row
                break
        record = {
            "prompt_text": base,
            "prompt_hash": ph,
            "variants": variants,
            "sample_count": (existing or {}).get("sample_count", 0),
            "total_revenue": (existing or {}).get("total_revenue", 0),
            "total_reach": (existing or {}).get("total_reach", 0),
            "total_views": (existing or {}).get("total_views", 0),
            "avg_rpm": (existing or {}).get("avg_rpm", 0),
            "avg_engagement": (existing or {}).get("avg_engagement", 0),
            "score": (existing or {}).get("score", 0),
            "ai_model": (existing or {}).get("ai_model"),
            "character_id": (existing or {}).get("character_id"),
            "style": (existing or {}).get("style"),
        }
        self.db.upsert_prompt_intel(page_id, record)

        return {
            "status": "success",
            "base_prompt": base,
            "variants": variants,
            "informed_by": [
                {"prompt": t.get("prompt_text"), "score": t.get("score"), "revenue": t.get("total_revenue")}
                for t in top[:3]
            ],
            "generated_at": _now(),
        }

    def _structural_variants(self, base: str, top: List[Dict[str, Any]]) -> List[str]:
        styles = []
        for t in top:
            if t.get("style"):
                styles.append(t["style"])
        extras = [
            f"{base}, cinematic lighting, ultra detailed, 4k",
            f"{base}, viral social media composition, high contrast",
            f"Professional commercial photo: {base}",
            f"{base} — emotional storytelling, golden hour",
            f"Close-up portrait style: {base}, shallow depth of field",
        ]
        if styles:
            extras.append(f"{base}, style: {styles[0]}")
        # Extract common winning tokens from top prompts
        tokens = self._winning_tokens(top)
        if tokens:
            extras.append(f"{base}, emphasizing {', '.join(tokens[:4])}")
        return extras

    def _llm_variants(self, base: str, top: List[Dict[str, Any]], n: int = 5) -> List[str]:
        try:
            from src.providers.capability_selector import capability_selector
        except Exception:
            return []

        examples = "\n".join(
            f"- (rev={t.get('total_revenue')}, rpm={t.get('avg_rpm')}): {t.get('prompt_text')}"
            for t in top[:3]
        )
        prompt = (
            f"Eres un experto en prompts de generación de imagen/video para Facebook Reels que monetizan.\n"
            f"Prompt base:\n{base}\n\n"
            f"Prompts top por ingresos:\n{examples or '(sin historial)'}\n\n"
            f"Genera {n} variantes optimizadas para mayor RPM y engagement. "
            f"Una variante por línea, sin numeración ni explicaciones."
        )
        raw = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Devuelve solo las variantes de prompt, una por línea.",
        )
        if not raw or "offline" in raw.lower() or "unreachable" in raw.lower():
            return []
        lines = []
        for line in raw.splitlines():
            line = re.sub(r"^\s*[\d\-\*\.]+\s*", "", line).strip()
            if len(line) > 15:
                lines.append(line)
        return lines[:n]

    @staticmethod
    def _winning_tokens(top: List[Dict[str, Any]]) -> List[str]:
        counts: Dict[str, int] = defaultdict(int)
        stop = {"the", "and", "with", "for", "a", "an", "de", "la", "el", "en", "un", "una", "y", "con"}
        for t in top:
            text = (t.get("prompt_text") or "").lower()
            for tok in re.findall(r"[a-záéíóúñü]{4,}", text):
                if tok not in stop:
                    counts[tok] += 1
        return [w for w, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]]

    @staticmethod
    def _score(
        sample_count: int,
        total_revenue: float,
        avg_rpm: float,
        avg_engagement: float,
        total_views: float,
    ) -> float:
        # Bayesian-ish shrink for low sample counts
        conf = min(sample_count, 10) / 10.0
        raw = (
            total_revenue * 2.0
            + avg_rpm * 1.5
            + avg_engagement * 50.0
            + (total_views / 1000.0) * 0.1
        )
        return round(raw * (0.4 + 0.6 * conf), 4)


def _prompt_hash(text: str) -> str:
    norm = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
