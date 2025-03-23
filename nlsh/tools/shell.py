"""
Shell history inspection tool.

This module provides a tool for analyzing recent command history.
"""

import os
import re
import subprocess
from pathlib import Path

from nlsh.tools.base import BaseTool


class ShellHistoryInspector(BaseTool):
    """Analyzes recent command history to avoid redundant suggestions."""
    
    # Maximum number of history entries to analyze
    MAX_HISTORY_ENTRIES = 50
    
    # History file paths for different shells
    HISTORY_FILES = {
        "bash": "~/.bash_history",
        "zsh": "~/.zsh_history",
        "fish": "~/.local/share/fish/fish_history",
        "powershell": "~/.config/powershell/PSReadLine/ConsoleHost_history.txt"
    }
    
    # List of sensitive patterns to filter out from shell history
    SENSITIVE_PATTERNS = [
        # Similar to EnvInspector patterns but case-insensitive
        r'.*token.*',
        r'.*secret.*',
        r'.*password.*',
        r'.*key.*',
        r'.*credential.*',
        r'.*auth.*',
        
        # Additional patterns for personal identifiable information
        r'.*export.*=.*',  # Environment variable exports that might contain secrets
        r'.*set.*=.*',     # Windows/PowerShell variable setting
        
        # Email addresses
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        
        # Phone numbers (various formats)
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # US/Canada: 123-456-7890
        r'\b\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,4}\b',  # International
        
        # Credit/Debit card numbers
        r'\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b',  # 16-digit card
        r'\b\d{4}[-.\s]?\d{6}[-.\s]?\d{5}\b',  # 15-digit card
        
        # Social Security Numbers (US)
        r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b',
        
        # Passport numbers, ID numbers, etc. (various formats)
        r'\bpassport\s*[:=]?\s*\w+\b',
        r'\bid\s*[:=]?\s*\w+\b',
        r'\bssn\s*[:=]?\s*[\w-]+\b',
        r'\blicense\s*[:=]?\s*\w+\b',
        
        # Bank account numbers (various formats)
        r'\baccount\s*[:=]?\s*\d+\b',
        r'\biban\s*[:=]?\s*[A-Za-z0-9\s]+\b',
        r'\bsort\s*code\s*[:=]?\s*\d+\b',
        r'\brouting\s*[:=]?\s*\d+\b',
        
        # API keys and tokens (common formats)
        r'\b[a-zA-Z0-9_-]{32,}\b',  # Long alphanumeric strings
        r'\b[a-zA-Z0-9]{8}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{12}\b',  # UUID format
        
        # AWS-specific patterns
        r'\bAKIA[0-9A-Z]{16}\b',  # AWS Access Key ID
        r'\b[a-zA-Z0-9/+]{40}\b',  # AWS Secret Access Key
        
        # OAuth tokens
        r'\b[a-zA-Z0-9_-]{24}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27}\b',  # JWT format
        r'\bgho_[a-zA-Z0-9_-]{36}\b',  # GitHub token
        r'\bxox[pbar]-[0-9]{12}-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{32}\b',  # Slack token
    ]
    
    def get_context(self):
        """Get recent command history.
        
        Returns:
            str: Formatted command history.
        """
        shell = self.config.get_shell()
        history = []
        
        # Try to get history from the history command first
        history = self._get_history_from_command(shell)
        
        # If that fails, try to read from history file
        if not history:
            history = self._get_history_from_file(shell)
        
        # Filter out sensitive commands
        filtered_history = self._filter_sensitive_commands(history)
        
        # Format the history
        if filtered_history:
            result = ["Recent command history:"]
            for cmd in filtered_history[:self.MAX_HISTORY_ENTRIES]:
                result.append(f"- {cmd}")
            return "\n".join(result)
        else:
            return "Could not retrieve command history."
    
    def _filter_sensitive_commands(self, commands):
        """Filter out commands that might contain sensitive information.
        
        Args:
            commands: List of command strings.
            
        Returns:
            list: Filtered list of commands.
        """
        if not commands:
            return []
            
        filtered = []
        for cmd in commands:
            # Skip empty commands
            if not cmd.strip():
                continue
                
            # Check if command matches any sensitive pattern
            if any(re.search(pattern, cmd, re.IGNORECASE) for pattern in self.SENSITIVE_PATTERNS):
                continue
                
            # Command is safe, add it to filtered list
            filtered.append(cmd)
            
        return filtered
    
    def _get_history_from_command(self, shell):
        """Get history using shell's history command.
        
        Args:
            shell: Shell name.
            
        Returns:
            list: List of recent commands.
        """
        try:
            if shell == "bash" or shell == "zsh":
                # For bash and zsh, use the history command
                output = subprocess.check_output(
                    ["history", str(self.MAX_HISTORY_ENTRIES)],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                # Parse the output
                commands = []
                for line in output.splitlines():
                    # Remove the history number and leading whitespace
                    match = re.match(r'^\s*\d+\s+(.+)$', line)
                    if match:
                        commands.append(match.group(1))
                    else:
                        # If the pattern doesn't match, just add the whole line
                        commands.append(line.strip())
                
                return commands
                
            elif shell == "fish":
                # For fish, use the history command
                output = subprocess.check_output(
                    ["fish", "-c", f"history | head -n {self.MAX_HISTORY_ENTRIES}"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                return [line.strip() for line in output.splitlines()]
                
            elif shell == "powershell":
                # For PowerShell, use Get-History
                output = subprocess.check_output(
                    ["powershell", "-Command", f"Get-History -Count {self.MAX_HISTORY_ENTRIES} | Select-Object -ExpandProperty CommandLine"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                return [line.strip() for line in output.splitlines()]
                
        except (subprocess.SubprocessError, FileNotFoundError):
            # If the command fails, return an empty list
            return []
    
    def _get_history_from_file(self, shell):
        """Get history by reading the history file.
        
        Args:
            shell: Shell name.
            
        Returns:
            list: List of recent commands.
        """
        if shell not in self.HISTORY_FILES:
            return []
            
        history_file = os.path.expanduser(self.HISTORY_FILES[shell])
        if not os.path.exists(history_file):
            return []
            
        try:
            with open(history_file, 'r', errors='ignore') as f:
                content = f.readlines()
                
            commands = []
            
            if shell == "bash":
                # Bash history is just a list of commands
                commands = [line.strip() for line in content]
                
            elif shell == "zsh":
                # Zsh history has a more complex format with timestamps
                for line in content:
                    # Extract the command part (after the first semicolon)
                    parts = line.split(';', 1)
                    if len(parts) > 1:
                        commands.append(parts[1].strip())
                    else:
                        commands.append(line.strip())
                        
            elif shell == "fish":
                # Fish history is stored in a more complex format
                # This is a simplified parser
                for line in content:
                    if ': cmd: ' in line:
                        cmd = line.split(': cmd: ', 1)[1].strip()
                        commands.append(cmd)
                        
            elif shell == "powershell":
                # PowerShell history is just a list of commands
                commands = [line.strip() for line in content]
                
            # Reverse the list to get most recent commands first
            commands.reverse()
            
            return commands[:self.MAX_HISTORY_ENTRIES]
            
        except Exception:
            # If reading the file fails, return an empty list
            return []
