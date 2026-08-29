"""
CreativeMemoryManager — Pattern extraction, prompt genome mapping, and performance attribution for DM AI OS v1.5.1.
Transforms CreativeManifestV2 execution lineage and ContentPerformanceEvent telemetry into structured creative intelligence.
"""
import sqlite3
import os
import json
import time
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

from ..storage.storage_layer import storage
from ..storage.content_metrics_store import content_metrics_store, ContentMetricsStore

log = logging.getLogger("creative_memory")

# ─── Prompt Genome Rule Catalog ───────────────────────────────────────────────

GENOME_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "STYLE": {
        "photorealistic": ["photorealistic", "photo", "hyperrealistic", "realistic", "raw photo"],
        "cinematic": ["cinematic", "film still", "35mm", "movie scene", "hollywood"],
        "cyberpunk": ["cyberpunk", "neo-tokyo", "futuristic", "sci-fi", "high-tech"],
        "watercolor": ["watercolor", "aquarelle", "watercolour", "fluid paint"],
        "anime": ["anime", "manga", "studio ghibli", "cel shading", "makoto shinkai"],
        "minimalist": ["minimalist", "minimalism", "clean design", "simple background"],
        "oil_painting": ["oil painting", "canvas", "classic art", "brushstrokes"],
        "3d_render": ["3d render", "octane render", "unreal engine", "raytracing", "cgi"]
    },
    "HOOK": {
        "close_up_portrait": ["close-up", "portrait", "face shot", "headshot", "macro face"],
        "hero_shot": ["hero shot", "epic pose", "triumphant", "low angle view", "commanding"],
        "dynamic_action": ["action shot", "running", "jumping", "motion blur", "fast paced", "explosion"],
        "pov_perspective": ["pov", "first person", "point of view", "viewer perspective"],
        "visual_contrast": ["contrast", "light and dark", "duality", "split lighting", "bichromatic"]
    },
    "COMPOSITION": {
        "centered": ["centered", "center composition", "symmetry", "symmetrical"],
        "wide_angle": ["wide angle", "panoramic", "landscape view", "vista", "expansive"],
        "rule_of_thirds": ["rule of thirds", "off-center", "dynamic framing"],
        "macro": ["macro", "extreme close-up", "detailed texture", "microscopic"],
        "isometric": ["isometric", "orthographic", "diorama", "miniature view"]
    },
    "LIGHTING": {
        "neon": ["neon", "neon glow", "cyber glow", "fluorescent", "led light"],
        "golden_hour": ["golden hour", "sunset light", "warm sun", "dusk glow"],
        "volumetric": ["volumetric", "god rays", "crepuscular rays", "foggy light", "hazy beams"],
        "studio_lighting": ["studio lighting", "softbox", "rim light", "three point lighting"],
        "dramatic_shadows": ["dramatic shadows", "chiaroscuro", "noir", "dark shadow", "silhouette"]
    }
}


class CreativeMemoryManager:
    """
    Analyzes creative manifests, correlates them with audience performance metrics,
    extracts prompt genome patterns, and maintains evidence-based performance scores.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        min_pattern_samples: int = 3,
        high_confidence_lift_threshold: float = 5.0,
        underperforming_lift_threshold: float = -5.0,
        metrics_store: Optional[ContentMetricsStore] = None,
        job_store = None
    ):
        if not db_path:
            db_dir_env = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
            if db_dir_env:
                db_dir = os.path.join(db_dir_env, "Storage")
            elif os.getenv("VERCEL"):
                db_dir = "/tmp/Project_State/Storage"
            else:
                db_dir = os.path.join(
                    os.path.expanduser("~"),
                    ".gemini", "antigravity-ide", "scratch", "Project_State", "Storage"
                )
            db_path = os.path.join(db_dir, "knowledge.db")

        self.db_path = db_path
        self.min_pattern_samples = min_pattern_samples
        self.high_confidence_lift_threshold = high_confidence_lift_threshold
        self.underperforming_lift_threshold = underperforming_lift_threshold
        self.metrics_store = metrics_store or ContentMetricsStore(db_path=self.db_path)
        self.job_store = job_store or storage.job_store
        self._db_initialized = False

    def _ensure_db(self):
        if self._db_initialized:
            return
        db_dir = os.path.dirname(self.db_path)
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception:
            db_dir = "/tmp/Project_State/Storage"
            os.makedirs(db_dir, exist_ok=True)
            self.db_path = os.path.join(db_dir, "knowledge.db")

        self._init_db()
        self._db_initialized = True

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS creative_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    pattern_type TEXT NOT NULL,
                    descriptor TEXT NOT NULL,
                    avg_performance_score REAL DEFAULT 0.0,
                    sample_count INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_patterns_type ON creative_patterns(pattern_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_patterns_score ON creative_patterns(avg_performance_score);")
            conn.commit()

    def extract_prompt_genome(
        self,
        prompt: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[str]]:
        """
        Deterministically extracts structured genome descriptors from prompt text.
        Returns a dictionary mapping pattern categories (STYLE, HOOK, COMPOSITION, LIGHTING) to detected descriptors.
        """
        if not prompt or not isinstance(prompt, str):
            return {cat: [] for cat in GENOME_KEYWORDS}

        prompt_clean = prompt.lower()
        genome: Dict[str, List[str]] = {}

        for category, descriptors in GENOME_KEYWORDS.items():
            detected = []
            for desc_name, keywords in descriptors.items():
                for kw in keywords:
                    pattern = r"\b" + re.escape(kw) + r"\b"
                    if re.search(pattern, prompt_clean):
                        detected.append(desc_name)
                        break
            genome[category] = detected

        return genome

    def get_global_baseline(self) -> float:
        """Calculates the global average performance score across all recorded metrics."""
        self._ensure_db()
        if hasattr(self, "metrics_store") and self.metrics_store:
            self.metrics_store._ensure_db()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT AVG(performance_score) FROM content_metrics WHERE performance_score IS NOT NULL")
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return round(float(row[0]), 2)
        except sqlite3.OperationalError:
            pass
        return 0.0

    def analyze_job(self, job_id: str) -> Dict[str, Any]:
        """
        Correlates a specific job's manifest with its recorded performance metrics and extracts its pattern genome.
        """
        self._ensure_db()
        job = self.job_store.get_job(job_id)
        metrics = self.metrics_store.get_metrics_by_job(job_id)

        if not job and not metrics:
            return {"job_id": job_id, "status": "NOT_FOUND", "error": "Job and metrics not found."}

        prompt = job.get("prompt", "") if job else ""
        if not prompt and metrics:
            # Fallback check on manifest file
            manifest_file = storage.artifacts_dir / f"creative_manifest_{job_id}.json"
            if manifest_file.exists():
                try:
                    m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    prompt = m_data.get("prompt", "")
                except Exception:
                    pass

        genome = self.extract_prompt_genome(prompt)

        avg_score = 0.0
        if metrics:
            valid_scores = [m["performance_score"] for m in metrics if m.get("performance_score") is not None]
            if valid_scores:
                avg_score = round(sum(valid_scores) / len(valid_scores), 2)

        return {
            "job_id": job_id,
            "status": "ANALYZED",
            "prompt": prompt,
            "genome": genome,
            "metrics_count": len(metrics),
            "avg_performance_score": avg_score
        }

    def refresh_patterns(self) -> Dict[str, Any]:
        """
        Scans all performance metrics in content_metrics, joins with jobs/manifests,
        aggregates pattern performance by descriptor, and updates the creative_patterns table.
        """
        self._ensure_db()
        all_metrics = self.metrics_store.list_metrics(limit=5000)
        if not all_metrics:
            return {"status": "NO_METRICS", "patterns_updated": 0, "global_baseline": 0.0}

        global_baseline = self.get_global_baseline()

        # Group metrics by job_id to calculate average score per job
        job_scores: Dict[str, List[float]] = {}
        for m in all_metrics:
            j_id = m.get("job_id")
            score = m.get("performance_score")
            if j_id and score is not None:
                job_scores.setdefault(j_id, []).append(float(score))

        # Map patterns to list of job scores
        pattern_aggregates: Dict[Tuple[str, str], List[float]] = {}

        for j_id, scores in job_scores.items():
            job_avg_score = sum(scores) / len(scores)
            job = self.job_store.get_job(j_id)
            prompt = job.get("prompt", "") if job else ""
            if not prompt:
                manifest_file = storage.artifacts_dir / f"creative_manifest_{j_id}.json"
                if manifest_file.exists():
                    try:
                        m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                        prompt = m_data.get("prompt", "")
                    except Exception:
                        pass

            genome = self.extract_prompt_genome(prompt)
            for cat, descriptors in genome.items():
                for desc in descriptors:
                    key = (cat, desc)
                    pattern_aggregates.setdefault(key, []).append(job_avg_score)

        # Write aggregated patterns to creative_patterns
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        updated_count = 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for (p_type, descriptor), scores in pattern_aggregates.items():
                p_id = f"pat_{p_type.lower()}_{descriptor.lower()}"
                sample_count = len(scores)
                avg_score = round(sum(scores) / sample_count, 2)

                cursor.execute("""
                    INSERT INTO creative_patterns (
                        pattern_id, pattern_type, descriptor, avg_performance_score, sample_count, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(pattern_id) DO UPDATE SET
                        avg_performance_score = excluded.avg_performance_score,
                        sample_count = excluded.sample_count,
                        last_updated = excluded.last_updated
                """, (p_id, p_type, descriptor, avg_score, sample_count, now))
                updated_count += 1

            conn.commit()

        log.info(f"[CreativeMemoryManager] Refreshed {updated_count} creative patterns against baseline {global_baseline}")
        return {
            "status": "SUCCESS",
            "patterns_updated": updated_count,
            "global_baseline": global_baseline
        }

    def get_pattern(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single pattern entry with evidence classification."""
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM creative_patterns WHERE pattern_id = ?", (pattern_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._enrich_pattern(dict(row), self.get_global_baseline())

    def _enrich_pattern(self, pattern: Dict[str, Any], global_baseline: float) -> Dict[str, Any]:
        """Calculates lift, evidence confidence, and classification status."""
        score = pattern.get("avg_performance_score", 0.0)
        count = pattern.get("sample_count", 0)
        lift = round(score - global_baseline, 2)

        if count < self.min_pattern_samples:
            classification = "LOW_CONFIDENCE"
        elif lift >= self.high_confidence_lift_threshold:
            classification = "OUTPERFORMING"
        elif lift <= self.underperforming_lift_threshold:
            classification = "UNDERPERFORMING"
        else:
            classification = "NEUTRAL"

        pattern["lift"] = lift
        pattern["global_baseline"] = global_baseline
        pattern["classification"] = classification
        pattern["is_reliable_evidence"] = (count >= self.min_pattern_samples)
        return pattern

    def get_top_patterns(self, category: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves highest-performing patterns with statistical lift."""
        self._ensure_db()
        baseline = self.get_global_baseline()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if category:
                cursor.execute(
                    "SELECT * FROM creative_patterns WHERE pattern_type = ? ORDER BY avg_performance_score DESC LIMIT ?",
                    (category.upper(), limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM creative_patterns ORDER BY avg_performance_score DESC LIMIT ?",
                    (limit,)
                )
            return [self._enrich_pattern(dict(r), baseline) for r in cursor.fetchall()]

    def get_underperforming_patterns(self, category: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves lowest-performing patterns."""
        self._ensure_db()
        baseline = self.get_global_baseline()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if category:
                cursor.execute(
                    "SELECT * FROM creative_patterns WHERE pattern_type = ? ORDER BY avg_performance_score ASC LIMIT ?",
                    (category.upper(), limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM creative_patterns ORDER BY avg_performance_score ASC LIMIT ?",
                    (limit,)
                )
            return [self._enrich_pattern(dict(r), baseline) for r in cursor.fetchall()]

# Global singleton
creative_memory = CreativeMemoryManager()
