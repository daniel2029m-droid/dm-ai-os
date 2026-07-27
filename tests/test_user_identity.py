import pytest
from src.users.identity_manager import identity_manager
from src.users.user_profile import UserProfile

def test_user_profile_crud():
    profile = identity_manager.get_profile("daniel")
    assert profile is not None
    assert "Daniel" in profile.name  # Acepta 'Daniel' o 'Daniel Morales'
    assert "Spanish" in profile.preferences.get("language", "")

    # Update preference
    res = identity_manager.update_preference("theme", "dark", user_id="daniel")
    assert res is True

    updated_profile = identity_manager.get_profile("daniel")
    assert updated_profile.preferences.get("theme") == "dark"
