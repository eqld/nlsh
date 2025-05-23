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

    # Fixing system prompt template
    FIXING_SYSTEM_PROMPT = """You are an AI assistant that fixes failed shell commands.
Your task is to analyze a failed command and generate a fixed version that will work correctly.
Only generate commands for the `{shell}` shell.
Do not include explanations or descriptions.
Ensure the commands are safe and do not cause data loss or security issues.
Use the following system context to inform your command generation:

{system_context}

Generate only the fixed command, nothing else. If the original command is completely wrong or cannot be fixed, 
generate a new command that accomplishes the original intent."""

    # Explanation system prompt template
    EXPLANATION_SYSTEM_PROMPT = """You are an AI assistant that explains shell commands for `{shell}` in plain text. 
When the user provides a command, follow these steps:
1. PURPOSE: Briefly summarize its goal.
2. WORKFLOW: Explain how it works step-by-step, including pipes, redirections, and logic.
3. BREAKDOWN: List each flag, argument, and operator with its role. For example:
   - `-v`:
   - `|`:
4. RISKS: Highlight dangers (e.g., data loss, permissions). If none, state "No significant risks."
5. IMPROVEMENTS: Suggest safer/more efficient alternatives if relevant.

Use the system context below to tailor the explanation:
{system_context}


Formatting rules:
- DO NOT USE Markdown
- Use uppercase headings like "PURPOSE:", "RISKS:".
- Separate sections with two newlines.
- Avoid technical jargon if possible."""

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
            
    def build_fixing_system_prompt(self, tools: List[BaseTool]) -> str:
        """Build the system prompt for fixing failed commands with context from tools.
        
        Args:
            tools: List of tool instances.
            
        Returns:
            str: Formatted system prompt for command fixing.
        """
        system_context = self._gather_tools_context(tools)
        
        # Format the fixing prompt with shell and system context
        return self.FIXING_SYSTEM_PROMPT.format(
            shell=self.shell,
            system_context=system_context
        )
    
    def build_fixing_user_prompt(
        self,
        prompt: str,
        failed_command: str,
        failed_command_exit_code: int,
        failed_command_output: str
    ) -> str:
        """Build the user prompt for fixing failed commands.
        
        Args:
            prompt: Original user prompt for command generation.
            failed_command: The command that failed.
            failed_command_exit_code: Exit code of the failed command.
            failed_command_output: Output of the failed command.
            
        Returns:
            str: Formatted user prompt for command fixing.
        """
        user_prompt = f"""I need to fix a failed command.

Original request (purpose of the command): {prompt}

The failed command: {failed_command}

Exit code: {failed_command_exit_code}

Command output:
{failed_command_output}

Please provide a fixed version of this command or a completely different command that accomplishes the original request."""
        
        return user_prompt
        
    def build_git_commit_user_prompt(self, git_diff: str, changed_files_content: dict = None) -> str:
        """Build the user prompt for commit message generation.
        
        Args:
            git_diff: Git diff output.
            changed_files_content: Dict of file contents.
            
        Returns:
            str: Formatted user prompt for commit message generation.
        """
        user_prompt = "Generate a commit message for the following changes:\n\n"
        user_prompt += "Git Diff:\n```diff\n" + git_diff + "\n```\n\n"
        
        # Add file content if available
        if changed_files_content:
            user_prompt += "Full content of changed files:\n"
            for file_path, content in changed_files_content.items():
                user_prompt += f"--- {file_path} ---\n"
                user_prompt += content + "\n\n"
                
        return user_prompt
