from typing import List, Dict, Any, Optional
from .embedding_engine import embedding_engine
from .long_term_memory import long_term_memory
from .knowledge_store import knowledge_store
from src.users.identity_manager import identity_manager

class MemoryRetriever:
    def __init__(self):
        pass

    def retrieve_relevant_memories(self, query: str, top_k: int = 5, min_score: float = 0.05) -> List[Dict[str, Any]]:
        if not query:
            return []

        query_vector = embedding_engine.generate_embedding(query)
        memories = long_term_memory.get_all()
        if not memories:
            return []

        scored_memories = []
        query_words = set(w.lower() for w in query.split() if len(w) > 2)

        for mem in memories:
            mem_vector = mem.get("embedding")
            if not mem_vector:
                mem_vector = embedding_engine.generate_embedding(mem["content"])

            score = embedding_engine.cosine_similarity(query_vector, mem_vector)
            
            # Simple keyword boost if exact match or word overlap
            mem_lower = mem["content"].lower()
            if query.lower() in mem_lower or any(w in mem_lower for w in query_words):
                score += 0.35

            if score >= min_score:
                scored_memories.append({
                    "id": mem["id"],
                    "content": mem["content"],
                    "category": mem["category"],
                    "importance": mem["importance"],
                    "score": round(score, 4),
                    "created_at": mem["created_at"]
                })

        scored_memories.sort(key=lambda x: x["score"], reverse=True)
        if not scored_memories and memories:
            # Fallback to returning top_k memories if any memory exists
            return [{
                "id": m["id"],
                "content": m["content"],
                "category": m["category"],
                "importance": m["importance"],
                "score": 0.1,
                "created_at": m["created_at"]
            } for m in memories[:top_k]]

        return scored_memories[:top_k]

    def build_context_prompt(self, user_id: str = "daniel", current_query: str = "") -> str:
        profile = identity_manager.get_profile(user_id)
        user_name = profile.name if profile else "User"
        prefs = profile.preferences if profile else {}

        context_lines = [
            f"[User Profile] Name: {user_name} | Preferred Language: {prefs.get('language', 'Spanish')}",
            f"Content Style: {prefs.get('content_style', 'AI Automation')} | Tools: {', '.join(prefs.get('favorite_tools', []))}"
        ]

        if current_query:
            relevant = self.retrieve_relevant_memories(current_query, top_k=3)
            if relevant:
                context_lines.append("[Relevant Long-Term Memories]")
                for m in relevant:
                    context_lines.append(f"- ({m['category']}) {m['content']}")

        return "\n".join(context_lines)

memory_retriever = MemoryRetriever()
