"""
System information tool.

This module provides a tool for gathering system information.
"""

import os
import platform
import sys

from nlsh.tools.base import BaseTool


class SystemInfo(BaseTool):
    """Provides OS, kernel, and architecture context."""
    
    def get_context(self):
        """Get system information.
        
        Returns:
            str: Formatted system information.
        """
        system_info = []
        
        # Operating system information
        system_info.append(f"OS: {platform.system()}")
        system_info.append(f"OS Version: {platform.version()}")
        system_info.append(f"OS Release: {platform.release()}")
        
        # Distribution information (for Linux)
        if platform.system() == "Linux":
            try:
                # Use /etc/os-release as the primary source
                if os.path.exists("/etc/os-release"):
                    with open("/etc/os-release", "r") as f:
                        for line in f:
                            if line.startswith("PRETTY_NAME="):
                                distro = line.split("=")[1].strip().strip('"')
                                system_info.append(f"Distribution: {distro}")
                                break
            except:
                pass
        
        # macOS version
        if platform.system() == "Darwin":
            mac_ver = platform.mac_ver()
            system_info.append(f"macOS Version: {mac_ver[0]}")
        
        # Windows version
        if platform.system() == "Windows":
            win_ver = sys.getwindowsversion()
            system_info.append(f"Windows Build: {win_ver.build}")
        
        # Architecture information
        system_info.append(f"Architecture: {platform.machine()}")
        system_info.append(f"Processor: {platform.processor()}")
        
        # Python information (can be useful for commands that involve Python)
        system_info.append(f"Python Version: {platform.python_version()}")
        system_info.append(f"Python Implementation: {platform.python_implementation()}")
        
        return "\n".join(system_info)
