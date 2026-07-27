from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional

@dataclass
class UserProfile:
    user_id: str = "daniel"
    name: str = "Daniel Morales"
    preferences: Dict[str, Any] = field(default_factory=lambda: {
        "language": "Spanish",
        "content_style": "AI automation",
        "favorite_tools": ["Ollama", "n8n", "CapCut"]
    })
    projects: List[str] = field(default_factory=lambda: ["Multi-Agent AI Platform"])
    goals: List[str] = field(default_factory=lambda: ["Automate AI workflows locally"])
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        return cls(
            user_id=data.get("user_id", "daniel"),
            name=data.get("name", "Daniel"),
            preferences=data.get("preferences", {}),
            projects=data.get("projects", []),
            goals=data.get("goals", []),
            metadata=data.get("metadata", {})
        )
