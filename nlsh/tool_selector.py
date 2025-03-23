"""
Tool selection for nlsh.

This module provides functionality for selecting the most appropriate tools
for a given prompt using a preflight system prompt.
"""

import sys
from typing import List, Dict, Any, Optional, Set

from nlsh.config import Config
from nlsh.backends import BackendManager
from nlsh.tools import get_tool_class, get_enabled_tools
from nlsh.tools.base import BaseTool
from nlsh.cli import Spinner


class ToolSelector:
    """Selects appropriate tools for a given prompt."""
    
    # Preflight system prompt template
    PREFLIGHT_SYSTEM_PROMPT = """You are an AI assistant that helps select the most appropriate tools that supplement the user's prompt to another AI assistant called "nlsh" for generating shell commands based on user prompts.
Your task is to analyze the user's prompt for that "nlsh" AI assistant and determine which tools would be most helpful for generating an accurate and useful shell command.

The available tools are:
{available_tools}

For each tool, respond with either "yes" or "no" to indicate whether it should be used for the given prompt.
Format your response as a JSON object with tool names as keys and boolean values.
For example: {"DirLister": true, "EnvInspector": true, "SystemInfo": false, ...}

Only select tools that are truly necessary for the specific prompt. Do not select tools that would not provide relevant information.
"""
    
    def __init__(self, config: Config, backend_manager: BackendManager):
        """Initialize the tool selector.
        
        Args:
            config: Configuration object.
            backend_manager: Backend manager instance.
        """
        self.config = config
        self.backend_manager = backend_manager
    
    def _build_preflight_prompt(self, available_tools: Dict[str, BaseTool]) -> str:
        """Build the preflight system prompt.
        
        Args:
            available_tools: Dictionary of available tools.
            
        Returns:
            str: Formatted preflight system prompt.
        """
        # Build tool descriptions
        tool_descriptions = []
        for name, tool in available_tools.items():
            # Get the tool's docstring as description
            description = tool.__doc__ or "No description available."
            tool_descriptions.append(f"- {name}: {description}")
        
        # Join all tool descriptions
        tools_text = "\n".join(tool_descriptions)
        
        # Format the preflight prompt
        return self.PREFLIGHT_SYSTEM_PROMPT.format(
            available_tools=tools_text
        )
    
    async def select_tools(
        self, 
        prompt: str, 
        backend_index: Optional[int] = None,
        verbose: bool = False,
        log_file: Optional[str] = None
    ) -> List[str]:
        """Select appropriate tools for the given prompt.
        
        Args:
            prompt: User prompt.
            backend_index: Optional backend index to use.
            verbose: Whether to print reasoning tokens to stderr.
            log_file: Optional path to log file.
            
        Returns:
            list: List of selected tool names.
        """
        # Get all available tools
        enabled_tools = self.config.get_enabled_tools()
        
        # Create a dictionary of available tool instances
        available_tools = {}
        for name in enabled_tools:
            tool_class = get_tool_class(name)
            if tool_class:
                available_tools[name] = tool_class(self.config)
        
        # If no tools are enabled, return an empty list
        if not available_tools:
            return []
        
        # Build preflight prompt
        preflight_prompt = self._build_preflight_prompt(available_tools)
        
        # Get backend
        backend = self.backend_manager.get_backend(backend_index)
        
        # Start spinner if not in verbose mode
        spinner = None
        if not verbose:
            spinner = Spinner("Selecting tools")
            spinner.start()
        
        try:
            # Display preflight prompt if verbose
            if verbose:
                print("Preflight system prompt:", file=sys.stderr)
                print(preflight_prompt, file=sys.stderr)
                print("\nUser prompt:", file=sys.stderr)
                print(prompt, file=sys.stderr)
                print("\nSelecting tools...", file=sys.stderr)
            
            # Generate tool selection
            response = await backend.generate_command(
                prompt, 
                preflight_prompt, 
                verbose=verbose
            )
            
            # Log preflight prompt and response if log file is specified
            if log_file:
                import json
                import datetime
                
                log_entry = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "type": "preflight",
                    "backend": {
                        "name": backend.name,
                        "model": backend.model,
                        "url": backend.url
                    },
                    "prompt": prompt,
                    "system_context": preflight_prompt,
                    "response": response
                }
                
                try:
                    import os
                    # Create directory if it doesn't exist
                    log_dir = os.path.dirname(log_file)
                    if log_dir and not os.path.exists(log_dir):
                        os.makedirs(log_dir)
                    
                    # Append to log file
                    with open(log_file, 'a') as f:
                        f.write(json.dumps(log_entry, indent=2) + "\n")
                except Exception as e:
                    print(f"Error writing to log file: {str(e)}", file=sys.stderr)
            
            # Parse the response to get selected tools
            selected_tools = self._parse_tool_selection(response, available_tools.keys())
            
            # Display selected tools
            if selected_tools:
                print(f"Selected tools: {', '.join(selected_tools)}", file=sys.stderr)
            else:
                print("No tools selected", file=sys.stderr)
            
            return selected_tools
            
        finally:
            # Stop spinner
            if spinner:
                spinner.stop()
    
    def _parse_tool_selection(self, response: str, available_tools: Set[str]) -> List[str]:
        """Parse the tool selection response.
        
        Args:
            response: Response from the LLM.
            available_tools: Set of available tool names.
            
        Returns:
            list: List of selected tool names.
        """
        import json
        import re
        
        # Try to extract JSON from the response
        json_match = re.search(r'{.*}', response, re.DOTALL)
        if not json_match:
            # No JSON found, return all available tools
            return list(available_tools)
        
        try:
            # Parse the JSON
            selection = json.loads(json_match.group(0))
            
            # Get selected tools
            selected_tools = []
            for tool, selected in selection.items():
                if selected and tool in available_tools:
                    selected_tools.append(tool)
            
            return selected_tools
            
        except json.JSONDecodeError:
            # JSON parsing failed, return all available tools
            return list(available_tools)
