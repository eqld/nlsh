"""
Directory listing tool.

This module provides a tool for listing files in the current directory.
"""

import os
import shlex
import stat
from typing import Any, Optional

from nlsh.tools.base import BaseTool
from nlsh.tools.common import format_size, scan_visible_entries


class DirLister(BaseTool):
    """Lists non-hidden files in current directory with basic metadata."""

    MAX_ENTRIES = 50

    def _sanitize_path(self, path: str) -> str:
        """Sanitize a file path to prevent command injection.

        Args:
            path: File path to sanitize.

        Returns:
            str: Sanitized file path.
        """
        # Use shlex.quote to escape special characters
        return shlex.quote(path)

    def _format_file_info(self, entry: os.DirEntry) -> Optional[dict[str, Any]]:
        """Format file information safely.

        Args:
            entry: Directory entry.

        Returns:
            Optional[dict[str, Any]]: Formatted file information (``is_dir`` is
                a bool, the other values are strings), or None if the entry
                cannot be stat'ed.
        """
        try:
            stats = entry.stat()
            is_dir = entry.is_dir()
            return {
                "name": self._sanitize_path(entry.name),
                "is_dir": is_dir,
                "type": (
                    "Directory"
                    if is_dir
                    else (
                        "Executable" if entry.is_file() and stats.st_mode & stat.S_IXUSR else "File"
                    )
                ),
                "size": format_size(stats.st_size),
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
        try:
            entries = scan_visible_entries(current_dir)
        except OSError:
            return f"Current directory: {current_dir}\n(unable to list directory contents)"

        for entry in entries:
            file_info = self._format_file_info(entry)
            if file_info:
                files.append(file_info)

        # Directories first, then files, each group alphabetical
        dirs = sorted((f for f in files if f["is_dir"]), key=lambda x: x["name"])
        non_dirs = sorted((f for f in files if not f["is_dir"]), key=lambda x: x["name"])
        ordered = dirs + non_dirs

        total = len(ordered)
        shown = ordered[: self.MAX_ENTRIES]

        # Format file information
        for file in shown:
            result.append(f"- {file['name']} ({file['type']}, {file['size']})")

        if total > self.MAX_ENTRIES:
            remaining = total - self.MAX_ENTRIES
            result.append(f"... and {remaining} more entries (listing truncated)")

        return "\n".join(result)
