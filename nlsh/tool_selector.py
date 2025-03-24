"""
Tool selection for nlsh.

This module provides functionality for selecting the most appropriate tools
for a given prompt using a preflight system prompt.
"""

import sys
import re
import json
import traceback
from typing import List, Dict, Any, Optional, Set

from nlsh.config import Config
from nlsh.backends import BackendManager
from nlsh.tools import get_tool_class, get_enabled_tools
from nlsh.tools.base import BaseTool
from nlsh.spinner import Spinner


class ToolSelector:
    """Selects appropriate tools for a given prompt."""
    
    # Preflight system prompt template
    PREFLIGHT_SYSTEM_PROMPT = """You are an AI assistant that selects context supplementing tools for another AI assistant called "nlsh" that generates shell commands based on user prompts and system context. Your task is to analyze the user's prompt for that "nlsh" AI assistant and determine the most appropriate tools to supplement the user prompt context for generating an accurate and useful shell command. It can be possible that no tools are actually needed.

The available tools are:
{tools_text}

For each tool, respond with either "yes" or "no" to indicate whether it should be used for the given prompt.
Format your response as a JSON object with tool names as keys and boolean values.
For example: {{"DirLister": true, "EnvInspector": true, "SystemInfo": false, ...}}

Only select tools that are truly necessary for the specific prompt. Do not select tools that would not provide relevant information.
"""
    
    # Default tools to use if tool selection fails
    DEFAULT_TOOLS = ["SystemInfo"]
    
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
        
        try:
            # Format the preflight prompt
            formatted_prompt = self.PREFLIGHT_SYSTEM_PROMPT.format(tools_text=tools_text)
            return formatted_prompt
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            
            # Return a simple fallback prompt
            return """You are an AI assistant that selects context supplementing tools for another AI assistant called "nlsh" that generates shell commands based on user prompts and system context. Your task is to analyze the user's prompt for that "nlsh" AI assistant and determine the most appropriate tools to supplement the user prompt context for generating an accurate and useful shell command. It can be possible that no tools are actually needed.
Respond with a JSON object with tool names as keys and boolean values.
For example: {"DirLister": true, "EnvInspector": true, "SystemInfo": false}"""
    
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
        
        try:
            # Build preflight prompt
            preflight_prompt = self._build_preflight_prompt(available_tools)
            
            # Get backend
            try:
                backend = self.backend_manager.get_backend(backend_index)
            except Exception as e:
                print(f"Error getting backend: {str(e)}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                return self._get_default_tools(available_tools.keys())
            
            # Start spinner if not in verbose mode
            spinner = None
            if not verbose:
                spinner = Spinner("Selecting tools")
                spinner.start()
            
            try:
                # In verbose mode, we don't print the preflight system prompt itself and user prompt,
                # but we stream the reasoning tokens from the preflight response
                if verbose:
                    print("\nPreflight reasoning:", file=sys.stderr)
                
                # Generate tool selection
                try:
                    response = await backend.generate_command(
                        prompt, 
                        preflight_prompt, 
                        verbose=verbose
                    )
                except Exception as e:
                    print(f"Error generating tool selection: {str(e)}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    return self._get_default_tools(available_tools.keys())
                
                # Log preflight prompt and response if log file is specified
                if log_file:
                    self._log_preflight(log_file, backend, prompt, preflight_prompt, response)
                
                # Parse the response to get selected tools
                try:
                    selected_tools = self._parse_tool_selection(response, available_tools.keys())
                    
                    # Display selected tools
                    if selected_tools:
                        print(f"Selected tools: {', '.join(selected_tools)}", file=sys.stderr)
                    else:
                        print("No tools selected, using defaults", file=sys.stderr)
                        selected_tools = self._get_default_tools(available_tools.keys())
                    
                    return selected_tools
                except Exception as e:
                    print(f"Error parsing tool selection: {str(e)}", file=sys.stderr)
                    print(f"Response was: {repr(response)}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    return self._get_default_tools(available_tools.keys())
                
            finally:
                # Stop spinner
                if spinner:
                    spinner.stop()
        except Exception as e:
            print(f"Error in select_tools: {str(e)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return self._get_default_tools(available_tools.keys() if available_tools else [])
    
    def _log_preflight(self, log_file: str, backend: Any, prompt: str, preflight_prompt: str, response: str) -> None:
        """Log preflight prompt and response.
        
        Args:
            log_file: Path to log file.
            backend: Backend instance.
            prompt: User prompt.
            preflight_prompt: Preflight system prompt.
            response: Response from the LLM.
        """
        try:
            import os
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
            
            # Create directory if it doesn't exist
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            # Append to log file
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry, indent=2) + "\n")
        except Exception as e:
            print(f"Error writing to log file: {str(e)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
    
    def _get_default_tools(self, available_tools: Set[str]) -> List[str]:
        """Get default tools to use if tool selection fails.
        
        Args:
            available_tools: Set of available tool names.
            
        Returns:
            list: List of default tool names.
        """
        # Return intersection of default tools and available tools
        default_tools = [tool for tool in self.DEFAULT_TOOLS if tool in available_tools]
        
        # If none of the default tools are available, return the first available tool
        if not default_tools and available_tools:
            return [next(iter(available_tools))]
            
        return default_tools
    
    def _parse_tool_selection(self, response: str, available_tools: Set[str]) -> List[str]:
        """Parse the tool selection response.
        
        Args:
            response: Response from the LLM.
            available_tools: Set of available tool names.
            
        Returns:
            list: List of selected tool names.
        """
        # Handle empty response
        if not response or not response.strip():
            return self._get_default_tools(available_tools)
        
        # Clean up the response to handle potential formatting issues
        response = response.strip()
        
        # Check if the response is just a tool name in quotes
        if response.startswith('"') and response.endswith('"'):
            tool_name = response.strip('"')
            if tool_name in available_tools:
                return [tool_name]
            else:
                return self._get_default_tools(available_tools)
        
        # Try to extract JSON from the response
        json_match = re.search(r'{.*}', response, re.DOTALL)
        if not json_match:
            return self._get_default_tools(available_tools)
        
        try:
            # Parse the JSON
            json_str = json_match.group(0)
            
            # Fix common JSON formatting issues
            json_str = json_str.replace("'", '"')
            
            # Fix missing commas in JSON
            json_str = re.sub(r'"\s*\n\s*"', '",\n"', json_str)
            json_str = re.sub(r'(true|false)\s*\n\s*"', r'\1,\n"', json_str)
            
            # Parse the JSON
            selection = json.loads(json_str)
            
            # Get selected tools
            selected_tools = []
            for tool, selected in selection.items():
                # Handle both boolean and string values
                if (isinstance(selected, bool) and selected) or \
                   (isinstance(selected, str) and selected.lower() in ['yes', 'true', '1']):
                    if tool in available_tools:
                        selected_tools.append(tool)
            
            # If no tools were selected, use default tools
            if not selected_tools:
                return self._get_default_tools(available_tools)
            
            return selected_tools
            
        except json.JSONDecodeError:
            # If JSON parsing fails, try a simpler approach
            # Look for patterns like "ToolName": true or "ToolName": "yes"
            selected_tools = []
            for tool in available_tools:
                # Check for various patterns that indicate a tool is selected
                patterns = [
                    f'"{tool}"\\s*:\\s*true',
                    f'"{tool}"\\s*:\\s*"yes"',
                    f'"{tool}"\\s*:\\s*"true"',
                    f'"{tool}"\\s*:\\s*1',
                    f'"{tool}"\\s*:\\s*"1"'
                ]
                for pattern in patterns:
                    if re.search(pattern, json_str, re.IGNORECASE):
                        selected_tools.append(tool)
                        break
            
            # If no tools were selected, use default tools
            if not selected_tools:
                return self._get_default_tools(available_tools)
            
            return selected_tools
        except Exception:
            return self._get_default_tools(available_tools)
