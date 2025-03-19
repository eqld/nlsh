"""
System tools for enhancing LLM context.

This module provides various tools that gather system information
to enhance the context provided to the LLM.
"""

from nlsh.tools.base import BaseTool
from nlsh.tools.directory import DirLister
from nlsh.tools.environment import EnvInspector
from nlsh.tools.system import SystemInfo
from nlsh.tools.shell import ShellHistoryInspector
from nlsh.tools.process import ProcessSniffer
from nlsh.tools.network import NetworkInfo

# Register all available tools
AVAILABLE_TOOLS = {
    "DirLister": DirLister,
    "EnvInspector": EnvInspector,
    "SystemInfo": SystemInfo,
    "ShellHistoryInspector": ShellHistoryInspector,
    "ProcessSniffer": ProcessSniffer,
    "NetworkInfo": NetworkInfo,
}

def get_tool_class(tool_name):
    """Get a tool class by name."""
    return AVAILABLE_TOOLS.get(tool_name)

def get_enabled_tools(config):
    """Get instances of all enabled tools based on configuration."""
    enabled_tools = []
    for tool_name in config.get_enabled_tools():
        tool_class = get_tool_class(tool_name)
        if tool_class:
            enabled_tools.append(tool_class(config))
    return enabled_tools
