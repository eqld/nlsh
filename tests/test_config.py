"""
Tests for the configuration module.
"""

import os
import tempfile
from pathlib import Path
import yaml

import pytest

from nlsh.config import Config


def test_default_config():
    """Test that default configuration is loaded when no file is provided."""
    config = Config()
    assert config.get_shell() == "bash"
    assert len(config.get_enabled_tools()) > 0
    assert config.get_backend() is not None


def test_config_from_file():
    """Test loading configuration from a file."""
    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as temp:
        yaml.dump({
            "shell": "zsh",
            "tools": {
                "enabled": ["DirLister", "SystemInfo"]
            }
        }, temp)
    
    try:
        # Load config from the temporary file
        config = Config(temp.name)
        
        # Check that values from the file were loaded
        assert config.get_shell() == "zsh"
        assert set(config.get_enabled_tools()) == {"DirLister", "SystemInfo"}
    finally:
        # Clean up the temporary file
        os.unlink(temp.name)


def test_env_override():
    """Test that environment variables override configuration values."""
    # Set environment variables
    os.environ["NLSH_SHELL"] = "fish"
    
    try:
        # Load config
        config = Config()
        
        # Check that environment variable overrides default
        assert config.get_shell() == "fish"
    finally:
        # Clean up environment
        del os.environ["NLSH_SHELL"]


def test_backend_selection():
    """Test backend selection."""
    config = Config()
    
    # Default backend
    default_backend = config.get_backend()
    assert default_backend is not None
    
    # Specific backend (if multiple are defined)
    if len(config.config["backends"]) > 1:
        backend_1 = config.get_backend(1)
        assert backend_1 is not None
        assert backend_1 != default_backend
