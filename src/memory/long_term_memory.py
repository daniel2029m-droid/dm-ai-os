import sqlite3
import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

log = logging.getLogger("long_term_memory")

class LongTermMemory:
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_dir_env = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
            if db_dir_env:
                db_dir = Path(db_dir_env) / "Memory"
            elif os.getenv("VERCEL"):
                db_dir = Path("/tmp/Project_State/Memory")
            else:
                db_dir = Path(os.path.expanduser("~")) / ".gemini" / "antigravity-ide" / "scratch" / "Project_State" / "Memory"
            db_path = str(db_dir / "memory.db")
            
        self.db_path = db_path
        self._db_initialized = False

    def _ensure_db(self):
        """Lazy database creation and schema setup."""
        if self._db_initialized:
            return
        db_dir = Path(self.db_path).parent
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            db_dir = Path("/tmp/Project_State/Memory")
            db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(db_dir / "memory.db")

        self._init_db()
        self._db_initialized = True

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    importance REAL DEFAULT 1.0,
                    embedding_json TEXT,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM memories")
            count = cursor.fetchone()[0]
            if count == 0:
                default_memories = [
                    ("Soy DM AI OS, un sistema operativo autónomo de inteligencia artificial basado en BrainPipeline.", "identity", 1.0),
                    ("Mi núcleo cognitivo es BrainPipeline. Grok Build es únicamente un cliente externo. Opero mediante memoria, herramientas MCP y agentes autónomos.", "identity", 1.0),
                    ("Grok Build es solamente un cliente de terminal que se conecta a DM AI OS a través de la OpenAI Compatibility Layer.", "system", 1.0),
                    ("El usuario principal es Daniel Morales (CEO / Lead Engineer).", "user", 1.0),
                    ("Daniel Morales es el desarrollador principal y creador de DM AI OS.", "user", 1.0),
                    ("Daniel Morales es CEO y Lead Engineer del proyecto DM AI OS. Es el arquitecto del sistema BrainPipeline.", "user", 1.0),
                    ("Daniel Morales diseñó la arquitectura de múltiples agentes autónomos que componen DM AI OS.", "user", 1.0),
                    ("Daniel prefiere arquitectura Multi-Agent basada en eventos. Su idioma preferido es el español.", "user", 1.0),
                    ("El núcleo principal de inteligencia es BrainPipeline, el cual orquesta agentes y memoria.", "architecture", 1.0),
                    ("El sistema DM AI OS opera con modelos Ollama locales: dm-autonomous-brain, dm-reasoner, dm-fast, dm-memory, dm-browser, dm-research, dm-media, dm-facebook.", "architecture", 1.0),
                ]
                for content, category, importance in default_memories:
                    cursor.execute("""
                        INSERT INTO memories (content, category, importance, embedding_json, metadata_json)
                        VALUES (?, ?, ?, '[]', '{}')
                    """, (content, category, importance))
                conn.commit()
                log.info("[LongTermMemory] Seeded default core system memories.")

            # Ensure Daniel Morales identity memories always exist
            self._ensure_daniel_memories(cursor)
            conn.commit()

    def _ensure_daniel_memories(self, cursor) -> None:
        """Ensure core Daniel Morales memories always exist in the DB (idempotent, no duplicates)."""
        required_daniel_memories = [
            ("El usuario principal es Daniel Morales (CEO / Lead Engineer), creador de DM AI OS.", "user", 1.0),
            ("Daniel Morales es el desarrollador principal y arquitecto del sistema BrainPipeline y DM AI OS.", "user", 1.0),
            ("Daniel Morales diseñó la arquitectura multi-agente de DM AI OS con memoria persistente y herramientas MCP.", "user", 1.0),
            ("Daniel Morales prefiere arquitecturas basadas en agentes autónomos. Su idioma preferido es el español.", "user", 1.0),
            ("Daniel Morales es CEO de dmoralesllc. Trabaja en IA, automatización y agentes locales con Ollama.", "user", 1.0),
        ]
        for content, category, importance in required_daniel_memories:
            cursor.execute("SELECT COUNT(*) FROM memories WHERE content = ?", (content,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO memories (content, category, importance, embedding_json, metadata_json)
                    VALUES (?, ?, ?, '[]', '{}')
                """, (content, category, importance))
                log.info(f"[LongTermMemory] Ensured memory: '{content[:60]}...'")

    def store(self, content: str, category: str = "general", importance: float = 1.0, embedding: Optional[List[float]] = None, metadata: Optional[Dict[str, Any]] = None) -> int:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memories (content, category, importance, embedding_json, metadata_json)
                VALUES (?, ?, ?, ?, ?)
            """, (
                content,
                category,
                importance,
                json.dumps(embedding or []),
                json.dumps(metadata or {})
            ))
            conn.commit()
            return cursor.lastrowid

    def get_all(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT id, content, category, importance, embedding_json, metadata_json, created_at FROM memories WHERE category = ? ORDER BY id DESC", (category,))
            else:
                cursor.execute("SELECT id, content, category, importance, embedding_json, metadata_json, created_at FROM memories ORDER BY id DESC")
                
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "content": r[1],
                    "category": r[2],
                    "importance": r[3],
                    "embedding": json.loads(r[4]) if r[4] else [],
                    "metadata": json.loads(r[5]) if r[5] else {},
                    "created_at": r[6]
                }
                for r in rows
            ]

    def forget(self, memory_id: int) -> bool:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    def clear_all(self):
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories")
            conn.commit()

long_term_memory = LongTermMemory()
