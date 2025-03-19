"""
Configuration handling for nlsh.

This module provides functionality for loading and managing configuration.
"""

import os
import re
from pathlib import Path
import yaml


class Config:
    """Configuration manager for nlsh."""
    
    # Default configuration
    DEFAULT_CONFIG = {
        "shell": "bash",  # Default shell
        "backends": [
            {
                "name": "openai",
                "url": "https://api.openai.com/v1",
                "api_key": "",  # Will be populated from environment variable
                "model": "gpt-3.5-turbo"
            }
        ],
        "default_backend": 0,
        "tools": {
            "enabled": [
                "DirLister",
                "EnvInspector",
                "SystemInfo"
            ]
        }
    }
    
    def __init__(self, config_path=None):
        """Initialize configuration.
        
        Args:
            config_path: Optional path to configuration file.
                If not provided, will look in default locations.
        """
        self.config = self.DEFAULT_CONFIG.copy()
        
        # Load configuration from file
        config_file = self._find_config_file(config_path)
        if config_file:
            self._load_config_file(config_file)
            
        # Apply environment variable overrides
        self._apply_env_overrides()
    
    def _find_config_file(self, config_path=None):
        """Find configuration file.
        
        Args:
            config_path: Optional explicit path to configuration file.
            
        Returns:
            Path object to configuration file, or None if not found.
        """
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            return None
            
        # Check default locations
        # 1. ~/.nlsh/config.yml
        home_config = Path.home() / ".nlsh" / "config.yml"
        if home_config.exists():
            return home_config
            
        # 2. ~/.config/nlsh/config.yml
        xdg_config = Path.home() / ".config" / "nlsh" / "config.yml"
        if xdg_config.exists():
            return xdg_config
            
        # No config file found
        return None
    
    def _load_config_file(self, config_file):
        """Load configuration from file.
        
        Args:
            config_file: Path to configuration file.
        """
        try:
            with open(config_file, 'r') as f:
                file_config = yaml.safe_load(f)
                
            # Update configuration with values from file
            if file_config:
                self._update_config(self.config, file_config)
        except Exception as e:
            print(f"Error loading configuration file: {e}")
    
    def _update_config(self, base_config, new_config):
        """Recursively update configuration.
        
        Args:
            base_config: Base configuration to update.
            new_config: New configuration values.
        """
        for key, value in new_config.items():
            if isinstance(value, dict) and key in base_config and isinstance(base_config[key], dict):
                # Recursively update nested dictionaries
                self._update_config(base_config[key], value)
            else:
                # Update value
                base_config[key] = value
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration."""
        # Override shell
        if "NLSH_SHELL" in os.environ:
            self.config["shell"] = os.environ["NLSH_SHELL"]
            
        # Override default backend
        if "NLSH_DEFAULT_BACKEND" in os.environ:
            try:
                self.config["default_backend"] = int(os.environ["NLSH_DEFAULT_BACKEND"])
            except ValueError:
                pass
                
        # Apply API keys from environment variables
        for i, backend in enumerate(self.config["backends"]):
            # Check for backend-specific API key
            env_var_name = f"NLSH_BACKEND_{i}_API_KEY"
            if env_var_name in os.environ:
                backend["api_key"] = os.environ[env_var_name]
                
            # Check for named API key
            if backend["name"]:
                env_var_name = f"{backend['name'].upper()}_API_KEY"
                if env_var_name in os.environ:
                    backend["api_key"] = os.environ[env_var_name]
                    
            # Handle environment variable references in API key
            if isinstance(backend["api_key"], str) and backend["api_key"].startswith("$"):
                env_var = backend["api_key"][1:]
                backend["api_key"] = os.environ.get(env_var, "")
    
    def get_shell(self):
        """Get configured shell.
        
        Returns:
            str: Shell name.
        """
        return self.config["shell"]
    
    def get_backend(self, index=None):
        """Get backend configuration.
        
        Args:
            index: Optional backend index. If not provided, uses default_backend.
            
        Returns:
            dict: Backend configuration.
        """
        if index is None:
            index = self.config["default_backend"]
            
        try:
            return self.config["backends"][index]
        except IndexError:
            # Fall back to first backend if index is invalid
            return self.config["backends"][0] if self.config["backends"] else None
    
    def get_enabled_tools(self):
        """Get list of enabled tools.
        
        Returns:
            list: List of enabled tool names.
        """
        return self.config["tools"]["enabled"]
