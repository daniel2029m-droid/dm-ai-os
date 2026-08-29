"""
Unit tests for InstagramConnector (Fase 14.4)
"""

import pytest
from pathlib import Path
from src.specialists.instagram_connector import InstagramConnector, _SESSIONS_ROOT, InstagramConnectorError


class TestInstagramConnectorOffline:
    """Offline unit tests for InstagramConnector without opening real browser."""

    def test_import_and_session_root(self):
        assert InstagramConnector is not None
        assert _SESSIONS_ROOT is not None

    def test_session_state_path(self):
        connector = InstagramConnector(user_id="daniel")
        assert connector._state_file == _SESSIONS_ROOT / "instagram_daniel" / "storage_state.json"

    def test_no_playwright_raises_error(self, monkeypatch):
        monkeypatch.setattr("src.specialists.instagram_connector.PLAYWRIGHT_AVAILABLE", False)
        with pytest.raises(InstagramConnectorError, match="playwright is not installed"):
            InstagramConnector(user_id="test")
