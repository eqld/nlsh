"""Tool availability probe."""

import shutil

from nlsh.tools.base import BaseTool


class ToolAvailability(BaseTool):
    """Reports which common CLI tools are available on PATH."""

    COMMON_TOOLS = [
        "git", "docker", "kubectl", "curl", "wget", "jq", "yq",
        "make", "tar", "zip", "unzip", "gzip", "rg", "fd", "fzf",
        "awk", "sed", "grep", "find", "xargs", "sort", "uniq",
        "python3", "node", "npm", "go", "cargo", "brew", "apt", "yum",
        "systemctl", "ps", "lsof", "netstat", "ss", "rsync", "ssh", "scp",
    ]

    def get_context(self):
        """Get a list of common CLI tools available on PATH.

        Returns:
            str: Formatted list of available CLI tools.
        """
        available = [t for t in self.COMMON_TOOLS if shutil.which(t)]
        return "Available CLI tools: " + ", ".join(available)
