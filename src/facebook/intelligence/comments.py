"""
Comment Intelligence
====================
Download/store comments and run sentiment, topic, question, intent,
spam detection, plus clustering of recurring requests.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..database import FacebookDatabase, facebook_db

log = logging.getLogger("facebook.intelligence.comments")

# Lightweight lexicons (ES + EN) — production heuristic layer; LLM enrichment optional
_POS = {
    "excelente", "genial", "amor", "love", "great", "awesome", "gracias", "thanks",
    "hermoso", "hermosa", "beautiful", "increible", "increíble", "fire", "top",
    "me gusta", "best", "perfecto", "wonderful", "amazing", "feliz", "happy",
}
_NEG = {
    "malo", "mala", "horrible", "odio", "hate", "terrible", "peor", "worst",
    "basura", "scam", "estafa", "fake", "mentira", "boring", "aburrido",
    "spam", "basura", "asco", "disgusting", "nunca", "never",
}
_QUESTION_RE = re.compile(
    r"(\?|¿|^(how|what|when|where|why|who|cu[aá]nto|c[oó]mo|qu[eé]|cu[aá]ndo|d[oó]nde|por qu[eé]|qui[eé]n)\b)",
    re.I | re.M,
)
_SPAM_PATTERNS = [
    re.compile(r"(https?://|wa\.me|bit\.ly|t\.me/)", re.I),
    re.compile(r"(crypto|forex|nft|giveaway|gana dinero|make money fast|dm me|inbox me)", re.I),
    re.compile(r"(.)\1{6,}"),  # repeated chars
    re.compile(r"(buy now|compra ya|click here|haz clic)", re.I),
]
_INTENT_RULES: List[Tuple[str, re.Pattern]] = [
    ("purchase", re.compile(r"(precio|price|comprar|buy|costo|cu[aá]nto cuesta|order|pedido)", re.I)),
    ("support", re.compile(r"(ayuda|help|soporte|support|problema|issue|no funciona|broken)", re.I)),
    ("collaboration", re.compile(r"(colab|collab|partnership|sponsor|publicidad)", re.I)),
    ("request_content", re.compile(r"(quiero ver|make a|haz un|tutorial|more of|m[aá]s de esto|please post)", re.I)),
    ("complaint", re.compile(r"(queja|complaint|estafa|scam|reembolso|refund|molesto|angry)", re.I)),
    ("praise", re.compile(r"(me encanta|love this|amazing|incre[ií]ble|great job|excelente trabajo)", re.I)),
    ("question", re.compile(r"(\?|¿)", re.I)),
]

_TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "pricing": ["precio", "price", "costo", "barato", "caro", "discount", "descuento"],
    "shipping": ["envío", "envio", "shipping", "delivery", "entrega"],
    "quality": ["calidad", "quality", "durability", "material"],
    "tutorial": ["tutorial", "cómo", "como", "how to", "paso a paso"],
    "product": ["producto", "product", "item", "modelo"],
    "schedule": ["horario", "schedule", "cuando", "cuándo", "when do you"],
    "music": ["música", "musica", "song", "canción", "cancion", "audio"],
    "ai": ["ai", "ia", "inteligencia artificial", "midjourney", "prompt", "higgsfield"],
}


class CommentIntelligence:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db

    def ingest_comments(
        self,
        page_id: str,
        comments: List[Dict[str, Any]],
        analyze: bool = True,
    ) -> Dict[str, Any]:
        stored = 0
        analyzed = 0
        for raw in comments:
            c = dict(raw)
            if analyze:
                labels = self.analyze_text(c.get("body") or c.get("text") or "")
                c.update(labels)
                analyzed += 1
            try:
                self.db.upsert_comment(page_id, c)
                stored += 1
            except Exception as e:
                log.warning("[CommentIntel] upsert failed: %s", e)
        clusters = self.cluster_recurring_requests(page_id) if analyze else []
        return {
            "status": "success",
            "stored": stored,
            "analyzed": analyzed,
            "clusters": clusters,
        }

    def analyze_text(self, text: str) -> Dict[str, Any]:
        body = (text or "").strip()
        lower = body.lower()
        sentiment, score = self._sentiment(lower)
        topics = self._topics(lower)
        is_question = bool(_QUESTION_RE.search(body))
        intent = self._intent(lower, is_question)
        is_spam = self._is_spam(body, lower)
        return {
            "sentiment": sentiment,
            "sentiment_score": score,
            "topics": topics,
            "is_question": is_question,
            "intent": intent,
            "is_spam": is_spam,
        }

    def analyze_stored(self, page_id: str, limit: int = 1000) -> Dict[str, Any]:
        comments = self.db.list_comments(page_id, limit=limit)
        updated = 0
        for c in comments:
            if c.get("sentiment") and c.get("intent"):
                continue
            labels = self.analyze_text(c.get("body") or "")
            c.update(labels)
            self.db.upsert_comment(page_id, c)
            updated += 1
        clusters = self.cluster_recurring_requests(page_id)
        summary = self.summary(page_id)
        return {"status": "success", "updated": updated, "clusters": clusters, "summary": summary}

    def summary(self, page_id: str) -> Dict[str, Any]:
        comments = self.db.list_comments(page_id, limit=5000)
        if not comments:
            return {"total": 0}
        sentiments = Counter(c.get("sentiment") or "unknown" for c in comments)
        intents = Counter(c.get("intent") or "other" for c in comments)
        questions = sum(1 for c in comments if c.get("is_question"))
        spam = sum(1 for c in comments if c.get("is_spam"))
        topic_counter: Counter = Counter()
        for c in comments:
            topics = c.get("topics") or []
            if isinstance(topics, str):
                try:
                    import json
                    topics = json.loads(topics)
                except Exception:
                    topics = [topics]
            for t in topics:
                topic_counter[t] += 1
        return {
            "total": len(comments),
            "sentiments": dict(sentiments),
            "intents": dict(intents),
            "questions": questions,
            "spam": spam,
            "top_topics": topic_counter.most_common(10),
            "positive_ratio": sentiments.get("positive", 0) / max(len(comments), 1),
            "negative_ratio": sentiments.get("negative", 0) / max(len(comments), 1),
        }

    def cluster_recurring_requests(self, page_id: str, min_size: int = 2) -> List[Dict[str, Any]]:
        """
        Cluster recurring request-like comments by normalized token signature.
        Updates cluster_id on matching comments.
        """
        comments = self.db.list_comments(page_id, limit=5000)
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for c in comments:
            body = (c.get("body") or "").strip()
            if not body:
                continue
            intent = c.get("intent")
            is_q = c.get("is_question")
            if intent not in ("request_content", "purchase", "question", "support") and not is_q:
                continue
            if c.get("is_spam"):
                continue
            sig = self._normalize_signature(body)
            if len(sig) < 8:
                continue
            buckets[sig].append(c)

        clusters = []
        for sig, members in buckets.items():
            if len(members) < min_size:
                continue
            cluster_id = "cl_" + hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]
            for m in members:
                m["cluster_id"] = cluster_id
                # preserve analysis fields
                self.db.upsert_comment(page_id, m)
            clusters.append({
                "cluster_id": cluster_id,
                "size": len(members),
                "signature": sig[:120],
                "sample": members[0].get("body", "")[:200],
                "intent": members[0].get("intent"),
            })
        clusters.sort(key=lambda x: x["size"], reverse=True)
        return clusters

    def enrich_with_llm(self, page_id: str, sample_limit: int = 30) -> Dict[str, Any]:
        """Optional local-LLM batch enrichment for ambiguous comments."""
        comments = [c for c in self.db.list_comments(page_id, limit=500) if not c.get("sentiment")]
        comments = comments[:sample_limit]
        if not comments:
            return {"status": "success", "enriched": 0}

        try:
            from src.providers.capability_selector import capability_selector
        except Exception as e:
            return {"status": "error", "message": str(e)}

        enriched = 0
        for c in comments:
            body = (c.get("body") or "")[:500]
            prompt = (
                f"Analiza este comentario de Facebook y responde SOLO en JSON con claves "
                f"sentiment (positive|neutral|negative), intent, topics (lista), is_spam (bool), is_question (bool):\n"
                f"\"{body}\""
            )
            raw = capability_selector.generate(
                prompt=prompt,
                capability="reasoning",
                system_prompt="Eres un analista de comentarios de redes sociales. Responde JSON válido.",
            )
            parsed = _try_json(raw)
            if not parsed:
                # Keep heuristic
                labels = self.analyze_text(body)
                c.update(labels)
            else:
                c["sentiment"] = parsed.get("sentiment") or c.get("sentiment")
                c["intent"] = parsed.get("intent") or c.get("intent")
                c["topics"] = parsed.get("topics") or c.get("topics") or []
                c["is_spam"] = bool(parsed.get("is_spam", c.get("is_spam")))
                c["is_question"] = bool(parsed.get("is_question", c.get("is_question")))
            self.db.upsert_comment(page_id, c)
            enriched += 1
        return {"status": "success", "enriched": enriched}

    # ── Internals ────────────────────────────────────────────────────────────

    def _sentiment(self, lower: str) -> Tuple[str, float]:
        pos = sum(1 for w in _POS if w in lower)
        neg = sum(1 for w in _NEG if w in lower)
        total = pos + neg
        if total == 0:
            return "neutral", 0.0
        score = (pos - neg) / total
        if score > 0.2:
            return "positive", score
        if score < -0.2:
            return "negative", score
        return "neutral", score

    def _topics(self, lower: str) -> List[str]:
        found = []
        for topic, kws in _TOPIC_KEYWORDS.items():
            if any(k in lower for k in kws):
                found.append(topic)
        return found

    def _intent(self, lower: str, is_question: bool) -> str:
        for name, pattern in _INTENT_RULES:
            if pattern.search(lower):
                return name
        return "question" if is_question else "other"

    def _is_spam(self, body: str, lower: str) -> bool:
        if len(body) > 800 and body.count("http") > 2:
            return True
        return any(p.search(body) for p in _SPAM_PATTERNS)

    @staticmethod
    def _normalize_signature(text: str) -> str:
        t = text.lower()
        t = re.sub(r"https?://\S+", "", t)
        t = re.sub(r"[^a-záéíóúñü0-9\s]", " ", t)
        tokens = [w for w in t.split() if len(w) > 2]
        # Drop very common stopwords
        stop = {"que", "the", "and", "para", "con", "por", "una", "los", "las", "del", "this", "that", "you", "me"}
        tokens = [w for w in tokens if w not in stop]
        return " ".join(sorted(set(tokens))[:12])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _try_json(text: str) -> Optional[Dict[str, Any]]:
    import json
    if not text:
        return None
    text = text.strip()
    # Extract fenced or raw JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
