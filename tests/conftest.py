"""Shared pytest fixtures for the nlsh test suite.

The autouse `isolated_env` fixture is critical: without it, a developer's
real ``~/.nlsh/config.yml`` or environment variables (API keys, NLSH_*
overrides) would leak into the tests and make them non-hermetic.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from nlsh.config import Config


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Prevent tests from seeing the developer's real config/env."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in list(os.environ):
        if var.startswith("NLSH_") or var.endswith("_API_KEY"):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)


@pytest.fixture
def config(tmp_path):
    """Config loaded from a minimal valid YAML file."""
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        "shell: bash\n"
        "backends:\n"
        "  - name: test-backend\n"
        "    url: http://localhost:9999/v1\n"
        "    api_key: dummy-key\n"
        "    model: test-model\n"
        "default_backend: 0\n"
    )
    return Config(str(cfg))


def make_chat_response(content, tool_calls=None):
    """Build an object mimicking openai chat.completions.create() response.

    Mirrors the shapes `nlsh/backends.py` actually reads off the response:
    ``response.choices[0].message.content`` and
    ``response.choices[0].message.tool_calls``.
    """
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, delta=None)
    return SimpleNamespace(choices=[choice])


@pytest.fixture
def mock_openai_client():
    """AsyncMock client with .chat.completions.create."""
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=make_chat_response("ls -la"))
    return client
