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
    GIT_COMMIT_SYSTEM_PROMPT = """You are an AI assistant that generates concise git commit messages following conventional commit standards (e.g., 'feat: description', 'fix: description', 'docs: description').
user will provide you a git diff and optionally the full content of changed files, and you have to create a suitable commit message summarizing the changes.
Output only the commit message (subject and optional body). Do not include explanations or markdown formatting like ```.

{language_instruction}
"""

    # Git commit regeneration system prompt template
    GIT_COMMIT_REGENERATION_SYSTEM_PROMPT = """You are an AI assistant that regenerates git commit messages based on user feedback.
The user has rejected previous commit message suggestions and may have provided specific guidance.
Your task is to generate a different commit message that better summarizes the changes.
Follow conventional commit standards (e.g., 'feat: description', 'fix: description', 'docs: description').
Output only the commit message (subject and optional body). Do not include explanations or markdown formatting like ```.

{language_instruction}
"""

    # STDIN processing system prompt template
    STDIN_PROCESSING_SYSTEM_PROMPT = """You are an AI assistant that processes text input according to user instructions.
You will receive text content from STDIN and a user instruction about what to do with that content.
Your task is to process the input content according to the user's request and output the result directly.

Do not generate shell commands. Do not include explanations unless specifically requested.
Focus on the task and provide a clean, direct output that can be used in pipelines.

Process the input content according to the user's instructions and output the result."""

    # Regeneration system prompt template
    REGENERATION_SYSTEM_PROMPT = """You are an AI assistant that regenerates shell commands based on user feedback.
The user has rejected previous command suggestions and may have provided specific guidance.
Your task is to generate a different shell command that accomplishes the user's original request.
Only generate commands for the `{shell}` shell.
Do not include explanations or descriptions.
Ensure the commands are safe and do not cause data loss or security issues.

Use the following system context to inform your command generation:
{system_context}

Generate only the command, nothing else."""
    
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

    def build_system_prompt(self, tools: List[BaseTool]) -> str:
        """Build the system prompt with context from tools.
        
        Args:
            tools: List of tool instances.
            
        Returns:
            str: Formatted system prompt.
        """
        system_context = self._gather_tools_context(tools)
        
        # Format the base prompt with shell and system context
        return self.BASE_SYSTEM_PROMPT.format(
            shell=self.shell,
            system_context=system_context,
        )
    
    def build_git_commit_system_prompt(self, language: str = None) -> str:
        """Build the system prompt for git commit message generation.
        
        Args:
            language: Language for commit message generation.
            
        Returns:
            str: Formatted system prompt for git commit message generation.
        """
        language_instruction = ""
        if language:
            language_instruction = f"Generate the commit message in {language}."
            
        return self.GIT_COMMIT_SYSTEM_PROMPT.format(
            language_instruction=language_instruction
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

    def build_stdin_processing_system_prompt(self) -> str:
        """Build the system prompt for STDIN processing (no system context needed).
        
        Returns:
            str: Formatted system prompt for STDIN processing.
        """
        return self.STDIN_PROCESSING_SYSTEM_PROMPT

    def build_stdin_processing_user_prompt(self, stdin_content: str, user_prompt: str) -> str:
        """Build the user prompt for STDIN processing.
        
        Args:
            stdin_content: Content read from STDIN.
            user_prompt: User's instruction for processing the content.
            
        Returns:
            str: Formatted user prompt for STDIN processing.
        """
        return f"""Task: {user_prompt}

Input content:
{stdin_content}"""

    def build_regeneration_system_prompt(self, tools: List[BaseTool]) -> str:
        """Build the system prompt for command regeneration with context from tools.
        
        Args:
            tools: List of tool instances.
            
        Returns:
            str: Formatted system prompt for command regeneration.
        """
        system_context = self._gather_tools_context(tools)
        
        # Format the regeneration prompt with shell and system context
        return self.REGENERATION_SYSTEM_PROMPT.format(
            shell=self.shell,
            system_context=system_context
        )

    def build_regeneration_user_prompt(self, original_request: str, declined_commands: List[dict]) -> str:
        """Build user prompt for command regeneration with notes.
        
        Args:
            original_request: The original user request for command generation.
            declined_commands: List of declined commands with optional notes.
                              Each item should be a dict with 'command' and optional 'note' keys.
            
        Returns:
            str: Formatted user prompt for command regeneration.
        """
        prompt = f"Original request: {original_request}\n\n"
        
        if declined_commands:
            prompt += "Previously rejected commands:\n"
            for i, declined in enumerate(declined_commands, 1):
                prompt += f"{i}. `{declined['command']}`"
                if declined.get('note'):
                    prompt += f" (Reason: {declined['note']})"
                prompt += "\n"
            
            prompt += "\nPlease generate a different command that accomplishes the original request."
            if any(d.get('note') for d in declined_commands):
                prompt += " Take the provided feedback into account."
        else:
            prompt += "Please generate a command that accomplishes this request."
        
        return prompt

    def build_git_commit_regeneration_system_prompt(self, language: str = None) -> str:
        """Build the system prompt for git commit message regeneration.
        
        Args:
            language: Language for commit message generation.
            
        Returns:
            str: Formatted system prompt for git commit message regeneration.
        """
        language_instruction = ""
        if language:
            language_instruction = f"Generate the commit message in {language}."
            
        return self.GIT_COMMIT_REGENERATION_SYSTEM_PROMPT.format(
            language_instruction=language_instruction
        )

    def build_git_commit_regeneration_user_prompt(
        self, 
        git_diff: str, 
        changed_files_content: dict = None, 
        declined_messages: List[str] = []
    ) -> str:
        """Build the user prompt for git commit message regeneration.
        
        Args:
            git_diff: Git diff output.
            changed_files_content: Dict of file contents.
            declined_messages: List of previously declined commit messages.
            
        Returns:
            str: Formatted user prompt for git commit message regeneration.
        """
        user_prompt = "Generate a different commit message for the following changes:\n\n"
        user_prompt += "Git Diff:\n```diff\n" + git_diff + "\n```\n\n"
        
        # Add file content if available
        if changed_files_content:
            user_prompt += "Full content of changed files:\n"
            for file_path, content in changed_files_content.items():
                user_prompt += f"--- {file_path} ---\n"
                user_prompt += content + "\n\n"
        
        # Add declined messages
        if declined_messages:
            user_prompt += "Previously declined commit messages:\n\n"
            for i, message in enumerate(declined_messages, 1):
                user_prompt += f"* Declined commit message {i}:\n{message}\n\n"
            user_prompt += "\n\nPlease generate a different commit message that better summarizes the changes.\n"
                
        return user_prompt
