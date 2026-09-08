"""
System information tool.

This module provides a tool for gathering system information.
"""

import datetime
import os
import platform
import subprocess

from nlsh.tools.base import BaseTool


class SystemInfo(BaseTool):
    """Provides OS, kernel, architecture, datetime, and shell context."""

    def get_context(self):
        """Get system information.

        Returns:
            str: Formatted system information.
        """
        system_info = []

        # Operating system information
        system_info.append(f"OS: {platform.system()}")
        system_info.append(f"OS Release: {platform.release()}")

        # Distribution information (for Linux)
        if platform.system() == "Linux":
            try:
                # Use /etc/os-release as the primary source
                if os.path.exists("/etc/os-release"):
                    with open("/etc/os-release") as f:
                        for line in f:
                            if line.startswith("PRETTY_NAME="):
                                distro = line.split("=")[1].strip().strip('"')
                                system_info.append(f"Distribution: {distro}")
                                break
            except:  # noqa: E722
                pass

        # macOS version
        if platform.system() == "Darwin":
            mac_ver = platform.mac_ver()
            system_info.append(f"macOS Version: {mac_ver[0]}")

        # Architecture information
        system_info.append(f"Architecture: {platform.machine()}")

        # Python information (can be useful for commands that involve Python)
        system_info.append(
            f"Python: {platform.python_version()} ({platform.python_implementation()})"
        )

        # Current date/time with timezone (helps with relative-date commands)
        now = datetime.datetime.now().astimezone()
        tz_name = now.tzname() or ""
        utc_offset = now.strftime("%z")
        formatted_offset = f"UTC{utc_offset[:3]}:{utc_offset[3:]}" if utc_offset else "UTC"
        tz_label = f"{tz_name} ({formatted_offset})" if tz_name else formatted_offset
        system_info.append(
            f"Current datetime: {now.strftime('%Y-%m-%d %H:%M (%a)')}, timezone: {tz_label}"
        )

        # Shell and, if cheaply obtainable, its version
        shell_name = self.config.get_shell()
        shell_line = f"Shell: {shell_name}"
        shell_path = os.environ.get("SHELL")
        if shell_path:
            try:
                result = subprocess.run(  # noqa: S603
                    [shell_path, "--version"],
                    capture_output=True,
                    timeout=1,
                    text=True,
                )
                first_line = result.stdout.strip().splitlines()[0] if result.stdout else ""
                if first_line:
                    shell_line = f"Shell: {shell_name} ({first_line})"
            except Exception:  # noqa: BLE001
                pass
        system_info.append(shell_line)

        return "\n".join(system_info)
