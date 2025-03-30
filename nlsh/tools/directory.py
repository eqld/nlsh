"""
Directory listing tool.

This module provides a tool for listing files in the current directory.
"""

import os
import stat
import shlex
from datetime import datetime
from typing import Dict, List

from nlsh.tools.base import BaseTool


class DirLister(BaseTool):
    """Lists non-hidden files in current directory with basic metadata."""
    
    def _sanitize_path(self, path: str) -> str:
        """Sanitize a file path to prevent command injection.
        
        Args:
            path: File path to sanitize.
            
        Returns:
            str: Sanitized file path.
        """
        # Use shlex.quote to escape special characters
        return shlex.quote(path)
    
    def _format_file_info(self, entry: os.DirEntry) -> Dict[str, str]:
        """Format file information safely.
        
        Args:
            entry: Directory entry.
            
        Returns:
            Dict[str, str]: Formatted file information.
        """
        try:
            stats = entry.stat()
            return {
                'name': self._sanitize_path(entry.name),
                'type': ("Directory" if entry.is_dir() else 
                        "Executable" if entry.is_file() and stats.st_mode & stat.S_IXUSR else 
                        "File"),
                'size': self._format_size(stats.st_size),
                'modified': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            }
        except (PermissionError, FileNotFoundError):
            return None
    
    def get_context(self):
        """Get a listing of files in the current directory.
        
        Returns:
            str: Formatted directory listing.
        """
        current_dir = os.getcwd()
        result = [f"Current directory: {current_dir}"]
        result.append("Files:")
        
        # Get all non-hidden files in the current directory
        files = []
        for entry in os.scandir(current_dir):
            # Skip hidden files (those starting with .)
            if entry.name.startswith('.'):
                continue
                
            file_info = self._format_file_info(entry)
            if file_info:
                files.append(file_info)
        
        # Sort files by name
        files.sort(key=lambda x: x['name'])
        
        # Format file information
        for file in files:
            result.append(f"- {file['name']} ({file['type']}, {file['size']}, modified: {file['modified']})")
        
        return "\n".join(result)
    
    def _format_size(self, size_bytes):
        """Format file size in a human-readable format.
        
        Args:
            size_bytes: File size in bytes.
            
        Returns:
            str: Formatted file size.
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024 or unit == 'TB':
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
