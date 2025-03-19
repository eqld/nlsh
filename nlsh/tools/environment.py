"""
Environment variables inspection tool.

This module provides a tool for inspecting environment variables.
"""

import os
import re

from nlsh.tools.base import BaseTool


class EnvInspector(BaseTool):
    """Reports environment variables for compatibility checks."""
    
    # List of sensitive environment variable patterns to filter out
    SENSITIVE_ENV_PATTERNS = [
        r'.*TOKEN.*',
        r'.*SECRET.*',
        r'.*PASSWORD.*',
        r'.*KEY.*',
        r'.*CREDENTIAL.*',
        r'.*AUTH.*',
    ]
    
    # List of important environment variables to always include
    IMPORTANT_ENV_VARS = [
        'PATH',
        'SHELL',
        'HOME',
        'USER',
        'LANG',
        'LC_ALL',
        'TERM',
        'EDITOR',
        'PAGER',
        'PWD',
    ]
    
    def get_context(self):
        """Get environment variables information.
        
        Returns:
            str: Formatted environment variables information.
        """
        env_info = ["Environment Variables:"]
        
        # Get all environment variables
        env_vars = dict(os.environ)
        
        # Filter out sensitive information
        filtered_env = {}
        for key, value in env_vars.items():
            # Always include important variables
            if key in self.IMPORTANT_ENV_VARS:
                filtered_env[key] = value
                continue
                
            # Filter out sensitive variables
            if any(re.match(pattern, key, re.IGNORECASE) for pattern in self.SENSITIVE_ENV_PATTERNS):
                filtered_env[key] = "[REDACTED]"
            else:
                filtered_env[key] = value
        
        # Get shell information
        shell = filtered_env.get('SHELL', 'Unknown')
        env_info.append(f"Current shell: {shell}")
        
        # Add PATH information (useful for command availability)
        path = filtered_env.get('PATH', '')
        path_entries = path.split(os.pathsep)
        env_info.append("PATH entries:")
        for entry in path_entries:
            if entry:  # Skip empty entries
                env_info.append(f"- {entry}")
        
        # Add other important environment variables
        env_info.append("\nOther important environment variables:")
        for key in sorted(self.IMPORTANT_ENV_VARS):
            if key != 'PATH' and key in filtered_env:  # PATH already handled above
                env_info.append(f"{key}={filtered_env[key]}")
        
        # Add remaining environment variables
        env_info.append("\nAdditional environment variables:")
        for key in sorted(filtered_env.keys()):
            if key not in self.IMPORTANT_ENV_VARS:
                env_info.append(f"{key}={filtered_env[key]}")
        
        return "\n".join(env_info)
