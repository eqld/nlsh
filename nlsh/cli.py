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
from typing import List, Optional, Dict, Any

from nlsh.config import Config
from nlsh.backends import BackendManager
from nlsh.tools import get_enabled_tools
from nlsh.prompt import PromptBuilder


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


async def generate_command(config: Config, backend_index: Optional[int], prompt: str, verbose: bool = False, log_file: Optional[str] = None, enable_tools: Optional[List[str]] = None, disable_tools: Optional[List[str]] = None) -> str:
    """Generate a command using the specified backend.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        prompt: User prompt.
        verbose: Whether to print reasoning tokens to stderr.
        
    Returns:
        str: Generated shell command.
    """
    # Get enabled tools with overrides
    tools = get_enabled_tools(config, enable=enable_tools, disable=disable_tools)
    
    # Build prompt
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_system_prompt(tools)
    user_prompt = prompt_builder.build_user_prompt(prompt)
    
    # Get backend
    backend_manager = BackendManager(config)
    backend = backend_manager.get_backend(backend_index)
    
    # Start spinner if not in verbose mode
    spinner = None
    if not verbose:
        spinner = Spinner("Thinking")
        spinner.start()
    
    try:
        # Generate command
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


def confirm_execution(command: str) -> bool:
    """Ask for confirmation before executing a command.
    
    Args:
        command: Command to execute.
        
    Returns:
        bool: True if confirmed, False otherwise.
    """
    print(f"Suggested: {command}")
    response = input("[Confirm] Run this command? (y/N) ").strip().lower()
    return response in ["y", "yes"]


def execute_command(command: str) -> int:
    """Execute a shell command.
    
    Args:
        command: Command to execute.
        
    Returns:
        int: Exit code of the command.
    """
    try:
        # Use the user's shell to execute the command
        shell = os.environ.get("SHELL", "/bin/sh")
        
        # Execute the command in the user's shell
        process = subprocess.Popen(
            command,
            shell=True,
            executable=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Stream output in real-time
        while True:
            stdout_line = process.stdout.readline()
            stderr_line = process.stderr.readline()
            
            if stdout_line:
                print(stdout_line, end="")
            if stderr_line:
                print(stderr_line, end="", file=sys.stderr)
                
            # Check if process has finished
            if process.poll() is not None and not stdout_line and not stderr_line:
                break
        
        # Get any remaining output
        stdout, stderr = process.communicate()
        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, end="", file=sys.stderr)
            
        return process.returncode
        
    except Exception as e:
        print(f"Error executing command: {str(e)}", file=sys.stderr)
        return 1


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
            if confirm_execution(command):
                print(f"Executing: {command}")
                # Actually execute the command
                return execute_command(command)
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
