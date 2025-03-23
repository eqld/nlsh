"""
Command-line interface for nlsh.

This module provides the command-line interface for the nlsh utility.
"""

import argparse
import asyncio
import datetime
import json
import os
import subprocess
import sys
import time
import threading
import io
from typing import List, Optional, Dict, Any, Tuple, Union

from nlsh.config import Config
from nlsh.backends import BackendManager
from nlsh.tools import get_enabled_tools
from nlsh.prompt import PromptBuilder
from nlsh.chat import ChatSession, count_tokens
from nlsh.tool_selector import ToolSelector


class Spinner:
    """Simple spinner to show progress."""
    
    def __init__(self, message="Thinking", stream=sys.stderr):
        """Initialize the spinner.
        
        Args:
            message: Message to display before the spinner.
            stream: Stream to write to (default: stderr).
        """
        self.message = message
        self.stream = stream
        self.running = False
        self.spinner_thread = None
        self.spinner_chars = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
        self.current = 0
    
    def spin(self):
        """Spin the spinner."""
        while self.running:
            self.stream.write(f"\r{self.message}... {self.spinner_chars[self.current]} ")
            self.stream.flush()
            self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)
        # Clear the spinner line
        self.stream.write("\r" + " " * (len(self.message) + 15) + "\r")
        self.stream.flush()
    
    def start(self):
        """Start the spinner."""
        if not self.running:
            self.running = True
            self.spinner_thread = threading.Thread(target=self.spin)
            self.spinner_thread.daemon = True
            self.spinner_thread.start()
    
    def stop(self):
        """Stop the spinner."""
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()


def parse_args(args: List[str]) -> argparse.Namespace:
    """Parse command-line arguments.
    
    Args:
        args: Command-line arguments.
        
    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Neural Shell (nlsh) - AI-driven command-line assistant"
    )
    
    # Backend selection arguments
    for i in range(10):  # Support up to 10 backends
        parser.add_argument(
            f"-{i}",
            dest="backend",
            action="store_const",
            const=i,
            help=f"Use backend {i}"
        )
    
    # Interactive mode
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive mode (confirm before executing)"
    )
    
    # Follow-up mode
    parser.add_argument(
        "-f", "--follow-up",
        action="store_true",
        help="Follow-up mode (remember context between commands)"
    )
    
    # Verbose mode
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose mode (print reasoning tokens to stderr)"
    )
    
    # Configuration file
    parser.add_argument(
        "--config",
        help="Path to configuration file"
    )
    
    # Prompt file
    parser.add_argument(
        "--prompt-file",
        help="Path to prompt file"
    )
    
    # Version
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information"
    )
    
    # Log file
    parser.add_argument(
        "--log-file",
        help="Path to file for logging LLM requests and responses"
    )
    
    # Tool management
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List all available tools and their status (enabled/disabled)"
    )
    
    parser.add_argument(
        "--enable-tool",
        action="append",
        help="Enable a specific tool for the current request (can be used multiple times)"
    )
    
    parser.add_argument(
        "--disable-tool",
        action="append",
        help="Disable a specific tool for the current request (can be used multiple times)"
    )
    
    # Prompt (positional argument)
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt for command generation"
    )
    
    return parser.parse_args(args)


async def generate_command(
    config: Config, 
    backend_index: Optional[int], 
    prompt: str, 
    verbose: bool = False, 
    log_file: Optional[str] = None, 
    enable_tools: Optional[List[str]] = None, 
    disable_tools: Optional[List[str]] = None,
    chat_session: Optional[ChatSession] = None,
    use_tool_selector: bool = True
) -> str:
    """Generate a command using the specified backend.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        prompt: User prompt.
        verbose: Whether to print reasoning tokens to stderr.
        log_file: Optional path to log file.
        enable_tools: Optional list of tools to enable.
        disable_tools: Optional list of tools to disable.
        chat_session: Optional chat session for follow-up mode.
        use_tool_selector: Whether to use the tool selector to select tools.
        
    Returns:
        str: Generated shell command.
    """
    # Get backend manager
    backend_manager = BackendManager(config)
    
    # Select tools
    if use_tool_selector:
        # Use tool selector to select appropriate tools
        tool_selector = ToolSelector(config, backend_manager)
        selected_tool_names = await tool_selector.select_tools(
            prompt, 
            backend_index=backend_index,
            verbose=verbose,
            log_file=log_file
        )
        
        # Get selected tool instances
        tools = get_enabled_tools(config, enable=selected_tool_names, disable=disable_tools)
    else:
        # Get all enabled tools with overrides
        tools = get_enabled_tools(config, enable=enable_tools, disable=disable_tools)
    
    # Build prompt
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_system_prompt(tools)
    user_prompt = prompt_builder.build_user_prompt(prompt)
    
    # Get backend
    backend = backend_manager.get_backend(backend_index)
    
    # Start spinner if not in verbose mode
    spinner = None
    if not verbose:
        spinner = Spinner("Thinking")
        spinner.start()
    
    try:
        # Generate command
        if chat_session:
            # Add user prompt to chat history
            chat_session.add_user_message(user_prompt)
            
            # Display context window usage
            chat_session.display_context_usage()
            
            # Generate command using chat history
            response = await backend.generate_command(
                user_prompt, 
                system_prompt, 
                verbose=verbose,
                chat_history=chat_session.get_messages()
            )
            
            # Add assistant response to chat history
            chat_session.add_assistant_message(response)
            
            # Track cost (approximate)
            input_tokens = sum(count_tokens(msg["content"]) for msg in chat_session.get_messages())
            output_tokens = count_tokens(response)
            chat_session.track_cost(backend.model, input_tokens, output_tokens)
        else:
            # Generate command without chat history
            response = await backend.generate_command(user_prompt, system_prompt, verbose=verbose)
        
        # Log request and response if log file is specified
        if log_file:
            log_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "backend": {
                    "name": backend.name,
                    "model": backend.model,
                    "url": backend.url
                },
                "prompt": prompt,
                "system_context": system_prompt,
                "response": response
            }
            
            try:
                # Create directory if it doesn't exist
                log_dir = os.path.dirname(log_file)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                
                # Append to log file
                with open(log_file, 'a') as f:
                    f.write(json.dumps(log_entry, indent=2) + "\n")
            except Exception as e:
                print(f"Error writing to log file: {str(e)}", file=sys.stderr)
        
        return response
    finally:
        # Stop spinner
        if spinner:
            spinner.stop()


def confirm_execution(command: str, chat_session: Optional[ChatSession] = None) -> Union[bool, str]:
    """Ask for confirmation before executing a command.
    
    Args:
        command: Command to execute.
        chat_session: Optional chat session for follow-up mode.
        
    Returns:
        Union[bool, str]: True if confirmed, False if declined, "regenerate" if regeneration requested.
    """
    print(f"Suggested: {command}")
    response = input("[Confirm] Run this command? (y/N/r) ").strip().lower()
    
    if response in ["r", "regenerate"]:
        # Add declined command to chat history if in follow-up mode
        if chat_session:
            chat_session.add_declined_command(command)
        return "regenerate"
    
    return response in ["y", "yes"]


def execute_command(command: str, chat_session: Optional[ChatSession] = None) -> Tuple[int, str]:
    """Execute a shell command.
    
    Args:
        command: Command to execute.
        chat_session: Optional chat session for follow-up mode.
        
    Returns:
        Tuple[int, str]: Exit code and command output.
    """
    try:
        # Use the user's shell to execute the command
        shell = os.environ.get("SHELL", "/bin/sh")
        
        # Capture output for chat history
        output_buffer = io.StringIO()
        
        # Execute the command in the user's shell
        process = subprocess.Popen(
            command,
            shell=True,
            executable=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Stream output in real-time and capture it
        while True:
            stdout_line = process.stdout.readline()
            stderr_line = process.stderr.readline()
            
            if stdout_line:
                print(stdout_line, end="")
                output_buffer.write(stdout_line)
            if stderr_line:
                print(stderr_line, end="", file=sys.stderr)
                output_buffer.write(stderr_line)
                
            # Check if process has finished
            if process.poll() is not None and not stdout_line and not stderr_line:
                break
        
        # Get any remaining output
        stdout, stderr = process.communicate()
        if stdout:
            print(stdout, end="")
            output_buffer.write(stdout)
        if stderr:
            print(stderr, end="", file=sys.stderr)
            output_buffer.write(stderr)
        
        # Get the captured output
        output = output_buffer.getvalue()
        
        # Add command execution to chat history if in follow-up mode
        if chat_session:
            chat_session.add_command_execution(command, output)
            
        return process.returncode, output
        
    except Exception as e:
        error_msg = f"Error executing command: {str(e)}"
        print(error_msg, file=sys.stderr)
        return 1, error_msg


async def run_follow_up_mode(
    config: Config,
    backend_index: Optional[int],
    initial_prompt: str,
    verbose: bool = False,
    log_file: Optional[str] = None,
    enable_tools: Optional[List[str]] = None,
    disable_tools: Optional[List[str]] = None
) -> int:
    """Run in follow-up mode.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        initial_prompt: Initial user prompt.
        verbose: Whether to print reasoning tokens to stderr.
        log_file: Optional path to log file.
        enable_tools: Optional list of tools to enable.
        disable_tools: Optional list of tools to disable.
        
    Returns:
        int: Exit code.
    """
    # Get backend manager
    backend_manager = BackendManager(config)
    
    # Select tools for initial prompt
    tool_selector = ToolSelector(config, backend_manager)
    selected_tool_names = await tool_selector.select_tools(
        initial_prompt, 
        backend_index=backend_index,
        verbose=verbose,
        log_file=log_file
    )
    
    # Get selected tool instances
    tools = get_enabled_tools(config, enable=selected_tool_names, disable=disable_tools)
    
    # Build initial system prompt
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_system_prompt(tools)
    
    # Create chat session
    chat_session = ChatSession(system_prompt)
    
    # Process initial prompt
    prompt = initial_prompt
    
    try:
        while True:
            # Generate command
            command = await generate_command(
                config,
                backend_index,
                prompt,
                verbose=verbose,
                log_file=log_file,
                enable_tools=enable_tools,
                disable_tools=disable_tools,
                chat_session=chat_session,
                use_tool_selector=True
            )
            
            # Ask for confirmation
            confirmation = confirm_execution(command, chat_session)
            
            if confirmation == "regenerate":
                # Regenerate the command
                print("Regenerating command...")
                continue
            elif confirmation:
                # Execute the command
                print(f"Executing: {command}")
                exit_code, _ = execute_command(command, chat_session)
                
                # If command failed, we still continue with the session
                if exit_code != 0:
                    print(f"Command exited with code {exit_code}")
            else:
                print("Command execution cancelled")
            
            # Ask for next prompt
            try:
                prompt = input("\nEnter next prompt (Ctrl+C to exit): ").strip()
                if not prompt:
                    continue
            except KeyboardInterrupt:
                print("\nExiting follow-up mode")
                break
                
    except KeyboardInterrupt:
        print("\nExiting follow-up mode")
        
    return 0


def main() -> int:
    """Main entry point.
    
    Returns:
        int: Exit code.
    """
    # Parse arguments
    args = parse_args(sys.argv[1:])
    
    # Show version and exit
    if args.version:
        from nlsh import __version__
        print(f"nlsh version {__version__}")
        return 0
    
    # Load configuration
    config = Config(args.config)
    
    # List tools if requested
    if args.list_tools:
        all_tools = config.get_all_tools()
        print("Available tools:")
        for name, enabled in all_tools.items():
            status = "enabled" if enabled else "disabled"
            print(f"- {name}: {status}")
        return 0
    
    # Check if we have a prompt
    if not args.prompt and not args.prompt_file:
        print("Error: No prompt provided")
        return 1
    
    # Get prompt from file or command line
    prompt = ""
    if args.prompt_file:
        prompt_builder = PromptBuilder(config)
        prompt = prompt_builder.load_prompt_from_file(args.prompt_file)
    else:
        # Join all prompt arguments into a single string
        prompt = " ".join(args.prompt) if args.prompt else ""
    
    # Check if follow-up mode is enabled
    if args.follow_up:
        # Follow-up mode requires interactive mode
        if not args.interactive:
            print("Follow-up mode requires interactive mode (-i)")
            return 1
            
        # Run in follow-up mode
        return asyncio.run(run_follow_up_mode(
            config,
            args.backend,
            prompt,
            verbose=args.verbose,
            log_file=args.log_file,
            enable_tools=args.enable_tool,
            disable_tools=args.disable_tool
        ))
    
    # Generate command
    try:
        command = asyncio.run(generate_command(
            config, 
            args.backend, 
            prompt, 
            verbose=args.verbose,
            log_file=args.log_file,
            enable_tools=args.enable_tool,
            disable_tools=args.disable_tool
        ))
        
        # Display the command
        if args.interactive:
            # In interactive mode, ask for confirmation
            confirmation = confirm_execution(command)
            
            if confirmation == "regenerate":
                # Regenerate the command
                print("Command regeneration is only available in follow-up mode (-f)")
                return 1
            elif confirmation:
                print(f"Executing: {command}")
                # Actually execute the command
                exit_code, _ = execute_command(command)
                return exit_code
            else:
                print("Command execution cancelled")
                return 0
        else:
            # In non-interactive mode, just print the command
            print(command)
            return 0
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
