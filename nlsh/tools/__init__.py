"""
System tools for enhancing LLM context.

This module provides various tools that gather system information
to enhance the context provided to the LLM.
"""

from nlsh.config import Config
from nlsh.tools.availability import ToolAvailability
from nlsh.tools.directory import DirLister
from nlsh.tools.environment import EnvInspector
from nlsh.tools.system import SystemInfo

# Register all available tools
AVAILABLE_TOOLS = {
    "SystemInfo": SystemInfo,
    "EnvInspector": EnvInspector,
    "ToolAvailability": ToolAvailability,
    "DirLister": DirLister,
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


def get_minimal_tools(config: Config):
    """Get instances of only the cheap up-front context tools.

    Used when native model tool calling (see `nlsh.local_tools` and
    `LLMBackend.generate_command_with_tools`) is active for a request: the
    up-front system prompt only needs `SystemInfo` and `ToolAvailability`,
    since the model can call the local tools (`list_directory`,
    `read_env_var`, etc.) to fetch the rest on demand instead of always
    paying for `EnvInspector` and `DirLister` context up-front.

    Args:
        config: Configuration object.

    Returns:
        list: List of `SystemInfo` and `ToolAvailability` tool instances.
    """
    return [SystemInfo(config), ToolAvailability(config)]
