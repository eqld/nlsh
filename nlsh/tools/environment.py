"""
Environment variables inspection tool.

This module provides a tool for inspecting environment variables.
"""

import os

from nlsh.tools.base import BaseTool


class EnvInspector(BaseTool):
    """Reports a minimal, safe subset of environment variables."""

    # Only these variables are ever sent to the LLM.
    WHITELIST = [
        "SHELL",
        "TERM",
        "LANG",
        "LC_ALL",
        "EDITOR",
        "PAGER",
        "HOME",
        "PWD",
        "TMPDIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "VIRTUAL_ENV",
        "CONDA_DEFAULT_ENV",
    ]
    MAX_PATH_ENTRIES = 15

    def get_context(self):
        """Get a whitelisted subset of environment variables.

        Only variables listed in ``WHITELIST`` are ever included, plus a
        capped preview of ``PATH`` entries. No other environment variables
        are inspected or sent to the LLM.

        Returns:
            str: Formatted environment variables information.
        """
        lines = ["Environment (whitelisted):"]
        for key in self.WHITELIST:
            value = os.environ.get(key)
            if value:
                lines.append(f"{key}={value}")

        path = os.environ.get("PATH", "")
        entries = [e for e in path.split(os.pathsep) if e]
        shown = entries[: self.MAX_PATH_ENTRIES]
        lines.append(f"PATH entries ({len(entries)} total, first {len(shown)} shown):")
        lines.extend(f"- {e}" for e in shown)

        return "\n".join(lines)
