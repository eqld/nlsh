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

    # Explanation system prompt template
    EXPLANATION_SYSTEM_PROMPT = """You are an AI assistant that explains shell commands or one-liner scripts in detail.
User will provide you a shell command or one-liner script for `{shell}` and your task is to provide a clear, detailed explanation of it.
Explain what it does, how it works, and the purpose of each part or flag.
Break down complex commands or scripts into understandable components.
If there are potential risks or side effects, mention them, and suggest alternative approaches or improvements.

Use the following system context to inform your explanation:

{system_context}"""

    # Git commit system prompt template
    GIT_COMMIT_SYSTEM_PROMPT = """You are an AI assistant that generates concise git commit messages following conventional commit standards (e.g., 'feat: description').
user will provide you a git diff and optionally the full content of changed files, and you have to create a suitable commit message summarizing the changes.
Output only the commit message (subject and optional body). Do not include explanations or markdown formatting like ```.

{declined_messages}
"""
    
    def __init__(self, config):
        """Initialize the prompt builder.
        
        Args:
            config: Configuration object.
        """
        self.config = config
        self.shell = config.get_shell()
    

    def _gather_tools_context(self, tools: List[BaseTool]) -> str:
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
        return system_context

    def build_explanation_system_prompt(self, tools: List[BaseTool]):
        """Build the explanation system prompt with context from tools.
        
        Args:
            tools: List of tool instances.
            
        Returns:
            str: Formatted system prompt.
        """
        system_context = self._gather_tools_context(tools)

        return self.EXPLANATION_SYSTEM_PROMPT.format(
            shell=self.shell,
            system_context=system_context
        )

    def build_system_prompt(self, tools: List[BaseTool], declined_commands: List[str] = []) -> str:
        """Build the system prompt with context from tools.
        
        Args:
            tools: List of tool instances.
            declined_commands: List of declined commands.
            
        Returns:
            str: Formatted system prompt.
        """
        system_context = self._gather_tools_context(tools)
        
        declined_commands_str = ""
        if declined_commands:
            declined_commands_str = "Do not generate these commands:\n" + "\n".join(declined_commands)

        # Format the base prompt with shell and system context
        return self.BASE_SYSTEM_PROMPT.format(
            shell=self.shell,
            system_context=system_context,
            declined_commands=declined_commands_str
        )
    
    def build_git_commit_system_prompt(self, declined_messages: List[str] = []) -> str:
        """Build the system prompt for git commit message generation.
        
        Args:
            declined_messages: List of declined commit messages.
            
        Returns:
            str: Formatted system prompt for git commit message generation.
        """
        declined_messages_str = ""
        if declined_messages:
            declined_messages_str = "The following commit messages were previously declined by the user, so propose something different:\n\n" + "\n\n----------------\n\n".join(declined_messages)
            
        return self.GIT_COMMIT_SYSTEM_PROMPT.format(
            declined_messages=declined_messages_str
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
