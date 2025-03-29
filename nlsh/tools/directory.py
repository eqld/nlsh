"""
Directory listing tool.

This module provides a tool for listing files in the current directory.
"""

import os
import stat
from datetime import datetime

from nlsh.tools.base import BaseTool


class DirLister(BaseTool):
    """Lists non-hidden files in current directory with basic metadata."""
    
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
                
            try:
                stats = entry.stat()
                size = stats.st_size
                modified = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                
                # Determine file type
                file_type = "Directory" if entry.is_dir() else "File"
                if entry.is_file():
                    # Check if file is executable
                    if stats.st_mode & stat.S_IXUSR:
                        file_type = "Executable"
                
                files.append({
                    'name': entry.name,
                    'type': file_type,
                    'size': size,
                    'modified': modified
                })
            except (PermissionError, FileNotFoundError):
                # Skip files we can't access
                continue
        
        # Sort files by name
        files.sort(key=lambda x: x['name'])
        
        # Format file information
        for file in files:
            size_str = self._format_size(file['size'])
            result.append(f"- {file['name']} ({file['type']}, {size_str}, modified: {file['modified']})")
        
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
