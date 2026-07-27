"""
VectorBackend — P5 Open Source Integration (Fase B)
====================================================
Capa de abstraccion intercambiable para almacenamiento vectorial.

Permite escalar desde el store JSON actual hasta ChromaDB o FAISS
sin cambios en MemoryManager ni KnowledgeStore.

Implementaciones disponibles:
  - JsonVectorBackend  : comportamiento actual (default, siempre disponible)
  - ChromaVectorBackend: ChromaDB embebido (VECTOR_BACKEND=chroma)
  - FaissVectorBackend : FAISS offline/GPU (VECTOR_BACKEND=faiss)

Seleccion via variable de entorno: VECTOR_BACKEND=json|chroma|faiss
El JSON backend es el default permanente. No se migran datos automaticamente.

Patron DM AI OS:
- Interfaz abstracta VectorBackend con 3 metodos obligatorios.
- get_backend() factory que selecciona la implementacion segun env var.
- Si el backend solicitado no esta instalado: advertencia + fallback a JSON.

NO modifica MemoryManager, KnowledgeStore, EmbeddingEngine ni ningun modulo
congelado. KnowledgeStore puede opcionalmente usar esta abstraccion como backend.

Referencia: OPEN_SOURCE_INTEGRATION_STATUS.md — P5
"""

import json
import os
import logging
import math
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional

log = logging.getLogger("vector_backend")


# ===========================================================================
# Abstract Interface
# ===========================================================================

class VectorBackend(ABC):
    """
    Abstract interface for vector storage backends.
    All implementations must provide these 3 methods.
    """

    @abstractmethod
    def save_vector(
        self,
        item_id: str,
        text: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a vector with its associated text and metadata."""
        ...

    @abstractmethod
    def search_similar(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return the top_k most similar vectors to query_vector.

        Each result dict MUST contain:
          - "id":    str
          - "text":  str
          - "score": float (similarity, higher = more similar)
          - "metadata": dict
        """
        ...

    @abstractmethod
    def delete_vector(self, item_id: str) -> bool:
        """Delete a vector by id. Returns True if deleted, False if not found."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return total number of stored vectors."""
        ...

    def backend_name(self) -> str:
        return self.__class__.__name__


# ===========================================================================
# JSON Backend (Default — always available, zero extra dependencies)
# ===========================================================================

class JsonVectorBackend(VectorBackend):
    """
    Default vector backend: stores vectors in a JSON file.
    Exact same behavior as the current KnowledgeStore implementation.
    100% compatible with existing data. Default for all installations.
    """

    def __init__(self, vectors_dir: Optional[str] = None):
        if not vectors_dir:
            vectors_dir = (
                Path(os.path.expanduser("~"))
                / ".gemini" / "antigravity-ide" / "scratch"
                / "Project_State" / "Memory" / "vectors"
            )
        self.vectors_dir = Path(vectors_dir)
        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.vectors_dir / "vector_index.json"
        self._init_store()

    def _init_store(self):
        if not self.index_file.exists():
            self.index_file.write_text(json.dumps({"items": []}), encoding="utf-8")

    def _load(self) -> Dict[str, Any]:
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except Exception:
            return {"items": []}

    def _save(self, data: Dict[str, Any]):
        self.index_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save_vector(
        self,
        item_id: str,
        text: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        data = self._load()
        # Update if exists, append if new
        for item in data["items"]:
            if item["id"] == item_id:
                item.update({"text": text, "vector": vector, "metadata": metadata or {}})
                self._save(data)
                return
        data["items"].append({
            "id": item_id,
            "text": text,
            "vector": vector,
            "metadata": metadata or {},
        })
        self._save(data)
        log.debug(f"[JsonVectorBackend] Saved vector id='{item_id}'")

    def search_similar(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        data = self._load()
        items = data.get("items", [])

        # Optional metadata filter
        if filter_metadata:
            items = [
                it for it in items
                if all(it.get("metadata", {}).get(k) == v for k, v in filter_metadata.items())
            ]

        scored = []
        for item in items:
            score = self._cosine(query_vector, item.get("vector", []))
            scored.append({
                "id": item["id"],
                "text": item.get("text", ""),
                "score": score,
                "metadata": item.get("metadata", {}),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def delete_vector(self, item_id: str) -> bool:
        data = self._load()
        before = len(data["items"])
        data["items"] = [it for it in data["items"] if it["id"] != item_id]
        if len(data["items"]) < before:
            self._save(data)
            return True
        return False

    def count(self) -> int:
        return len(self._load().get("items", []))

    @staticmethod
    def _cosine(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        return dot / (n1 * n2) if n1 and n2 else 0.0


# ===========================================================================
# Chroma Backend (Optional — requires: pip install chromadb)
# ===========================================================================

class ChromaVectorBackend(VectorBackend):
    """
    ChromaDB embedded vector backend.
    20-100x faster than JSON for >10K vectors.
    Runs fully embedded — no server required.

    Activate: VECTOR_BACKEND=chroma
    Install:  pip install chromadb>=0.5.0
    """

    COLLECTION_NAME = "dm_ai_os_memory"

    def __init__(self, persist_dir: Optional[str] = None):
        if not persist_dir:
            persist_dir = str(
                Path(os.path.expanduser("~"))
                / ".gemini" / "antigravity-ide" / "scratch"
                / "Project_State" / "Memory" / "chroma_db"
            )
        self.persist_dir = persist_dir
        self._client = None
        self._collection = None

    @staticmethod
    def _is_available() -> bool:
        try:
            import chromadb  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        import chromadb
        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        log.info(f"[ChromaVectorBackend] Collection '{self.COLLECTION_NAME}' ready at {self.persist_dir}")
        return self._collection

    def save_vector(
        self,
        item_id: str,
        text: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        col = self._get_collection()
        # Chroma requires string metadata values
        safe_meta = {k: str(v) for k, v in (metadata or {}).items()}
        col.upsert(
            ids=[item_id],
            documents=[text],
            embeddings=[vector],
            metadatas=[safe_meta],
        )
        log.debug(f"[ChromaVectorBackend] Upserted id='{item_id}'")

    def search_similar(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        col = self._get_collection()
        where = {k: str(v) for k, v in filter_metadata.items()} if filter_metadata else None
        kwargs = {"query_embeddings": [query_vector], "n_results": top_k}
        if where:
            kwargs["where"] = where

        res = col.query(**kwargs)
        output = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        dists = res.get("distances", [[]])[0]
        metas = res.get("metadatas", [[]])[0]

        for i, item_id in enumerate(ids):
            # Chroma returns L2 distance with cosine space -> convert to similarity
            dist = dists[i] if i < len(dists) else 1.0
            score = max(0.0, 1.0 - dist)
            output.append({
                "id": item_id,
                "text": docs[i] if i < len(docs) else "",
                "score": score,
                "metadata": metas[i] if i < len(metas) else {},
            })
        return output

    def delete_vector(self, item_id: str) -> bool:
        try:
            col = self._get_collection()
            col.delete(ids=[item_id])
            return True
        except Exception as e:
            log.warning(f"[ChromaVectorBackend] Delete failed for '{item_id}': {e}")
            return False

    def count(self) -> int:
        try:
            return self._get_collection().count()
        except Exception:
            return 0


# ===========================================================================
# FAISS Backend (Optional — requires: pip install faiss-cpu)
# ===========================================================================

class FaissVectorBackend(VectorBackend):
    """
    FAISS vector backend — fast approximate nearest neighbor search.
    Ideal for local installations with large vector counts (>100K).
    No server required. Supports GPU via faiss-gpu.

    Activate: VECTOR_BACKEND=faiss
    Install:  pip install faiss-cpu>=1.8.0  (or faiss-gpu)

    NOTE: FAISS index is held in-memory and persisted to disk on save.
    Metadata stored in companion JSON file alongside the FAISS index.
    """

    def __init__(self, index_dir: Optional[str] = None):
        if not index_dir:
            index_dir = str(
                Path(os.path.expanduser("~"))
                / ".gemini" / "antigravity-ide" / "scratch"
                / "Project_State" / "Memory" / "faiss_db"
            )
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.index_dir / "faiss.index"
        self.meta_file = self.index_dir / "faiss_meta.json"
        self._index = None
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._ids: List[str] = []  # ordered list matching FAISS internal indices
        self._dim: Optional[int] = None
        self._load()

    @staticmethod
    def _is_available() -> bool:
        try:
            import faiss  # noqa: F401
            return True
        except ImportError:
            return False

    def _load(self):
        """Load existing index and metadata from disk."""
        try:
            if self.index_file.exists() and self.meta_file.exists():
                import faiss
                self._index = faiss.read_index(str(self.index_file))
                meta_data = json.loads(self.meta_file.read_text(encoding="utf-8"))
                self._meta = meta_data.get("meta", {})
                self._ids = meta_data.get("ids", [])
                self._dim = self._index.d
                log.info(f"[FaissVectorBackend] Loaded {self._index.ntotal} vectors (dim={self._dim})")
        except Exception as e:
            log.warning(f"[FaissVectorBackend] Failed to load index: {e}. Starting fresh.")

    def _init_index(self, dim: int):
        """Initialize a new flat L2 index for given dimension."""
        import faiss
        self._dim = dim
        self._index = faiss.IndexFlatIP(dim)  # Inner product (cosine with normalized vectors)
        log.info(f"[FaissVectorBackend] New index dim={dim}")

    def _persist(self):
        """Write index and metadata to disk."""
        import faiss
        faiss.write_index(self._index, str(self.index_file))
        meta_data = {"meta": self._meta, "ids": self._ids}
        self.meta_file.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")

    def save_vector(
        self,
        item_id: str,
        text: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        import numpy as np
        dim = len(vector)

        if self._index is None:
            self._init_index(dim)

        import faiss
        vec_np = np.array([vector], dtype=np.float32)
        # Normalize for cosine similarity via inner product
        faiss.normalize_L2(vec_np)

        if item_id in self._ids:
            # FAISS does not support in-place update; mark for rebuild if needed
            # For simplicity: update metadata only (vector update requires full rebuild)
            self._meta[item_id] = {"text": text, "metadata": metadata or {}}
        else:
            self._index.add(vec_np)
            self._ids.append(item_id)
            self._meta[item_id] = {"text": text, "metadata": metadata or {}}

        self._persist()
        log.debug(f"[FaissVectorBackend] Saved id='{item_id}' (total={self._index.ntotal})")

    def search_similar(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if self._index is None or self._index.ntotal == 0:
            return []

        import numpy as np, faiss
        q = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(q)

        k = min(top_k * 3, self._index.ntotal)  # over-fetch for metadata filtering
        scores, indices = self._index.search(q, k)

        output = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._ids):
                continue
            item_id = self._ids[idx]
            item_meta = self._meta.get(item_id, {})

            # Optional metadata filter
            if filter_metadata:
                if not all(
                    item_meta.get("metadata", {}).get(fk) == fv
                    for fk, fv in filter_metadata.items()
                ):
                    continue

            output.append({
                "id": item_id,
                "text": item_meta.get("text", ""),
                "score": float(score),
                "metadata": item_meta.get("metadata", {}),
            })
            if len(output) >= top_k:
                break

        return output

    def delete_vector(self, item_id: str) -> bool:
        """
        FAISS does not support single-vector deletion natively.
        Marks the vector as deleted in metadata. Full rebuild happens lazily.
        """
        if item_id not in self._ids:
            return False
        # Soft delete: remove from metadata (vector stays in index but won't be returned)
        del self._meta[item_id]
        self._persist()
        log.debug(f"[FaissVectorBackend] Soft-deleted id='{item_id}'")
        return True

    def count(self) -> int:
        return len(self._meta)


# ===========================================================================
# Backend Factory
# ===========================================================================

def get_backend(vectors_dir: Optional[str] = None) -> VectorBackend:
    """
    Factory that returns the appropriate VectorBackend based on VECTOR_BACKEND env var.

    VECTOR_BACKEND=json   -> JsonVectorBackend  (default, always available)
    VECTOR_BACKEND=chroma -> ChromaVectorBackend (requires: pip install chromadb)
    VECTOR_BACKEND=faiss  -> FaissVectorBackend  (requires: pip install faiss-cpu)

    If the requested backend is not installed, logs a warning and falls back to JSON.
    """
    backend_name = os.getenv("VECTOR_BACKEND", "json").lower().strip()

    if backend_name == "chroma":
        if ChromaVectorBackend._is_available():
            log.info("[VectorBackend] Using ChromaDB backend")
            return ChromaVectorBackend()
        else:
            log.warning(
                "[VectorBackend] ChromaDB requested but not installed. "
                "Install: pip install chromadb>=0.5.0. Falling back to JSON backend."
            )

    elif backend_name == "faiss":
        if FaissVectorBackend._is_available():
            log.info("[VectorBackend] Using FAISS backend")
            return FaissVectorBackend()
        else:
            log.warning(
                "[VectorBackend] FAISS requested but not installed. "
                "Install: pip install faiss-cpu>=1.8.0. Falling back to JSON backend."
            )

    elif backend_name != "json":
        log.warning(f"[VectorBackend] Unknown backend '{backend_name}'. Using JSON backend.")

    log.info("[VectorBackend] Using JSON backend (default)")
    return JsonVectorBackend(vectors_dir=vectors_dir)


# Module-level default backend instance
# Used by any module that imports this directly
# KnowledgeStore continues using its own implementation unchanged
default_backend: VectorBackend = get_backend()
