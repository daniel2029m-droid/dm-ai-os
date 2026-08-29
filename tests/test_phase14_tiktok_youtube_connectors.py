"""
Unit tests for TikTokConnector and YouTubeConnector (Fase 14.5/14.6)
"""

import pytest
from pathlib import Path
from src.specialists.tiktok_connector import TikTokConnector, _SESSIONS_ROOT as TT_ROOT, TikTokConnectorError
from src.specialists.youtube_connector import YouTubeConnector, _SESSIONS_ROOT as YT_ROOT, YouTubeConnectorError


class TestTikTokConnectorOffline:
    """Offline unit tests for TikTokConnector."""

    def test_import_and_session_root(self):
        assert TikTokConnector is not None
        assert TT_ROOT is not None

    def test_session_state_path(self):
        connector = TikTokConnector(user_id="daniel")
        assert connector._state_file == TT_ROOT / "tiktok_daniel" / "storage_state.json"

    def test_no_playwright_raises_error(self, monkeypatch):
        monkeypatch.setattr("src.specialists.tiktok_connector.PLAYWRIGHT_AVAILABLE", False)
        with pytest.raises(TikTokConnectorError, match="playwright is not installed"):
            TikTokConnector(user_id="test")


class TestYouTubeConnectorOffline:
    """Offline unit tests for YouTubeConnector."""

    def test_import_and_session_root(self):
        assert YouTubeConnector is not None
        assert YT_ROOT is not None

    def test_session_state_path(self):
        connector = YouTubeConnector(user_id="daniel")
        assert connector._state_file == YT_ROOT / "youtube_daniel" / "storage_state.json"

    def test_no_playwright_raises_error(self, monkeypatch):
        monkeypatch.setattr("src.specialists.youtube_connector.PLAYWRIGHT_AVAILABLE", False)
        with pytest.raises(YouTubeConnectorError, match="playwright is not installed"):
            YouTubeConnector(user_id="test")
