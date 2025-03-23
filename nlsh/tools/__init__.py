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
from nlsh.tools.git import GitRepoInfo

# Register all available tools
AVAILABLE_TOOLS = {
    "DirLister": DirLister,
    "EnvInspector": EnvInspector,
    "SystemInfo": SystemInfo,
    "ShellHistoryInspector": ShellHistoryInspector,
    "ProcessSniffer": ProcessSniffer,
    "NetworkInfo": NetworkInfo,
    "GitRepoInfo": GitRepoInfo,
}

def get_tool_class(tool_name):
    """Get a tool class by name."""
    return AVAILABLE_TOOLS.get(tool_name)

def get_enabled_tools(config, enable=None, disable=None):
    """Get instances of all enabled tools based on configuration.
    
    Args:
        config: Configuration object.
        enable: Optional list of tool names to enable for this request.
        disable: Optional list of tool names to disable for this request.
        
    Returns:
        list: List of enabled tool instances.
    """
    enabled_tools = []
    for tool_name in config.get_enabled_tools(enable=enable, disable=disable):
        tool_class = get_tool_class(tool_name)
        if tool_class:
            enabled_tools.append(tool_class(config))
    return enabled_tools
