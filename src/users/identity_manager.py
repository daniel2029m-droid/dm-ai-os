import sqlite3
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from .user_profile import UserProfile

log = logging.getLogger("identity_manager")

class IdentityManager:
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_dir = Path(os.path.expanduser("~")) / ".gemini" / "antigravity-ide" / "scratch" / "Project_State" / "Storage"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "users.db")
            
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT,
                    data_json TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            
        # Ensure default user 'daniel' exists with full name Daniel Morales
        profile = self.get_profile("daniel")
        if not profile or profile.name != "Daniel Morales":
            default_profile = UserProfile(user_id="daniel", name="Daniel Morales")
            self.save_profile(default_profile)

    def get_profile(self, user_id: str = "daniel") -> Optional[UserProfile]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                data = json.loads(row[0])
                return UserProfile.from_dict(data)
        return None

    def save_profile(self, profile: UserProfile) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            data_str = json.dumps(profile.to_dict(), ensure_ascii=False)
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, name, data_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (profile.user_id, profile.name, data_str))
            conn.commit()
            log.info(f"[IdentityManager] Saved profile for user: {profile.user_id}")
            return True

    def update_preference(self, key: str, value: Any, user_id: str = "daniel") -> bool:
        profile = self.get_profile(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id)
        profile.preferences[key] = value
        return self.save_profile(profile)

identity_manager = IdentityManager()
