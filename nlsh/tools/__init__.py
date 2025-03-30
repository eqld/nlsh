"""
System tools for enhancing LLM context.

This module provides various tools that gather system information
to enhance the context provided to the LLM.
"""

from nlsh.tools.directory import DirLister
from nlsh.tools.environment import EnvInspector
from nlsh.tools.system import SystemInfo

from nlsh.config import Config

# Register all available tools
AVAILABLE_TOOLS = {
    "DirLister": DirLister,
    "EnvInspector": EnvInspector,
    "SystemInfo": SystemInfo,
}

def get_tool_class(tool_name):
    """Get a tool class by name."""
    return AVAILABLE_TOOLS.get(tool_name)

def get_tools(config: Config):
    """Get instances of all available tools.
    
    Args:
        config: Configuration object.

    Returns:
        list: List of tool instances.
    """
    return [tool(config) for tool in AVAILABLE_TOOLS.values()]
