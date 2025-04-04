"""
Configuration handling for nlsh.

This module provides functionality for loading and managing configuration.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml


class ConfigValidationError(Exception):
    """Configuration validation error."""
    pass


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
                "model": "gpt-3.5-turbo",
                "timeout": 120.0,  # Default timeout in seconds
                "is_reasoning_model": False  # Flag to identify reasoning models
            }
        ],
        "default_backend": 0,
        "nlgc": {
            "include_full_files": True  # Whether nlgc includes full file content by default
        }
    }
    
    def __init__(self, config_path: Optional[str] = None) -> None:
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
    
    def _find_config_file(self, config_path: Optional[str] = None) -> Optional[Path]:
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
    
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate configuration structure and values.
        
        Args:
            config: Configuration dictionary to validate.
            
        Raises:
            ConfigValidationError: If configuration is invalid.
        """
        # Validate shell
        if not isinstance(config.get("shell"), str):
            raise ConfigValidationError("Shell must be a string")
        if config["shell"] not in ["bash", "zsh", "fish", "powershell"]:
            raise ConfigValidationError("Shell must be one of: bash, zsh, fish, powershell")
            
        # Validate backends
        if not isinstance(config.get("backends"), list):
            raise ConfigValidationError("Backends must be a list")
        if not config["backends"]:
            raise ConfigValidationError("At least one backend must be configured")
            
        for i, backend in enumerate(config["backends"]):
            if not isinstance(backend, dict):
                raise ConfigValidationError(f"Backend {i} must be an object")
            required_fields = ["name", "url", "model"]
            for field in required_fields:
                if field not in backend:
                    raise ConfigValidationError(f"Backend {i} missing required field: {field}")
            
            # Validate API key format and environment variables
            if "api_key" in backend and isinstance(backend["api_key"], str):
                if backend["api_key"].startswith("$"):
                    env_var = backend["api_key"][1:]
                    api_key = os.environ.get(env_var)
                    if not api_key:
                        raise ConfigValidationError(
                            f"Required environment variable {env_var} for backend {backend['name']} is not set"
                        )
                    if len(api_key.strip()) < 8:  # Basic validation for API key length
                        raise ConfigValidationError(
                            f"API key from environment variable {env_var} for backend {backend['name']} appears invalid (too short)"
                        )
            
            # Validate timeout
            if "timeout" in backend:
                try:
                    timeout = float(backend["timeout"])
                    if timeout <= 0:
                        raise ConfigValidationError(f"Backend {i} timeout must be positive")
                except ValueError:
                    raise ConfigValidationError(f"Backend {i} timeout must be a number")

        # Validate nlgc section (optional)
        if "nlgc" in config:
            if not isinstance(config["nlgc"], dict):
                raise ConfigValidationError("nlgc section must be an object")
            if "include_full_files" in config["nlgc"]:
                if not isinstance(config["nlgc"]["include_full_files"], bool):
                    raise ConfigValidationError("nlgc.include_full_files must be a boolean")

    def _load_config_file(self, config_file: str) -> None:
        """Load and validate configuration from file."""
        try:
            with open(config_file, 'r') as f:
                file_config = yaml.safe_load(f)
                
            # Validate configuration
            if file_config:
                self._validate_config(file_config)
                self._update_config(self.config, file_config)
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ConfigValidationError(f"Error loading config file: {e}")
    
    def _update_config(self, base_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
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
    
    def _apply_env_overrides(self) -> None:
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
            if "api_key" in backend and isinstance(backend["api_key"], str):
                if backend["api_key"].startswith("$"):
                    env_var = backend["api_key"][1:]
                    api_key = os.environ.get(env_var, "")
                    if not api_key:
                        raise ConfigValidationError(
                            f"Environment variable {env_var} for backend {backend['name']} API key is empty"
                        )
                    backend["api_key"] = api_key
        
        # Override nlgc settings
        if "NLSH_NLGC_INCLUDE_FULL_FILES" in os.environ:
            env_val = os.environ["NLSH_NLGC_INCLUDE_FULL_FILES"].lower()
            if env_val in ["true", "1", "yes"]:
                self.config.setdefault("nlgc", {})["include_full_files"] = True
            elif env_val in ["false", "0", "no"]:
                self.config.setdefault("nlgc", {})["include_full_files"] = False

    def get_shell(self) -> str:
        """Get configured shell.
        
        Returns:
            str: Shell name.
        """
        return self.config["shell"]
    
    def get_backend(self, index: Optional[int] = None) -> Optional[Dict[str, Any]]:
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

    def get_nlgc_config(self) -> Dict[str, Any]:
        """Get nlgc specific configuration.
        
        Returns:
            dict: nlgc configuration dictionary.
        """
        # Return the nlgc section, falling back to default if not present
        return self.config.get("nlgc", self.DEFAULT_CONFIG["nlgc"])
