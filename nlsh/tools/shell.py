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
        
        # Format the history
        if history:
            result = ["Recent command history:"]
            for cmd in history[:self.MAX_HISTORY_ENTRIES]:
                result.append(f"- {cmd}")
            return "\n".join(result)
        else:
            return "Could not retrieve command history."
    
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
