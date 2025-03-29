"""
Prompt engineering for nlsh.

This module provides functionality for constructing prompts for LLMs.
"""

from typing import List

from nlsh.tools.base import BaseTool


class PromptBuilder:
    """Builder for LLM prompts."""
    
    # Base system prompt template
    BASE_SYSTEM_PROMPT = """You are an AI assistant that generates shell commands based on user requests.
Your task is to generate a single shell command or a short oneliner script that accomplishes the user's request.
Only generate commands for the `{shell}` shell.
Do not include explanations or descriptions.
Ensure the commands are safe and do not cause data loss or security issues.
Use the following system context to inform your command generation:

{system_context}

{declined_commands}

Generate only the command, nothing else."""
    
    def __init__(self, config):
        """Initialize the prompt builder.
        
        Args:
            config: Configuration object.
        """
        self.config = config
        self.shell = config.get_shell()
    
    def build_system_prompt(self, tools: List[BaseTool], declined_commands: List[str] = []) -> str:
        """Build the system prompt with context from tools.
        
        Args:
            tools: List of tool instances.
            declined_commands: List of declined commands.
            
        Returns:
            str: Formatted system prompt.
        """
        # Gather context from all tools
        context_parts = []
        for tool in tools:
            try:
                context = tool.get_context()
                if context:
                    context_parts.append(f"--- {tool.name} ---")
                    context_parts.append(context)
            except Exception as e:
                context_parts.append(f"Error getting context from {tool.name}: {str(e)}")
        
        # Join all context parts
        system_context = "\n\n".join(context_parts)
        
        declined_commands_str = ""
        if declined_commands:
            declined_commands_str = "Do not generate these commands:\n" + "\n".join(declined_commands)

        # Format the base prompt with shell and system context
        return self.BASE_SYSTEM_PROMPT.format(
            shell=self.shell,
            system_context=system_context,
            declined_commands=declined_commands_str
        )
    
    def build_user_prompt(self, user_input: str) -> str:
        """Build the user prompt.
        
        Args:
            user_input: User input string.
            
        Returns:
            str: Formatted user prompt.
        """
        # For now, just return the user input as is
        # In the future, we could add more processing here
        return user_input
    
    def load_prompt_from_file(self, file_path: str) -> str:
        """Load a prompt from a file.
        
        Args:
            file_path: Path to the prompt file.
            
        Returns:
            str: Prompt content.
        """
        try:
            with open(file_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            return f"Error loading prompt file: {str(e)}"
