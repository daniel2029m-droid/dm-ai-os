import pytest
import os
from unittest.mock import patch

@pytest.fixture(autouse=True, scope="session")
def disable_auth_for_tests():
    """
    Globally disable authentication during tests so we don't have to 
    inject API keys into hundreds of existing test client calls.
    Tests that specifically need to test auth can unmock this.
    """
    mock_config = {
        "require_auth": False,
        "auth_mode": "none",
        "allowed_bearer_tokens": ["dm-secret-key-v1"],
        "allowed_api_keys": ["dm-secret-key-v1"]
    }
    
    with patch("src.api.openai_compat.auth_middleware._load_security_config", return_value=mock_config), \
         patch("src.api.auth.load_security_config", return_value=mock_config):
        yield
