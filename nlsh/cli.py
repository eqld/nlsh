"""
Command-line interface for nlsh.

This module provides the command-line interface for the nlsh utility.
"""

import argparse
import asyncio
import os
import sys
from typing import List, Optional

from nlsh.config import Config
from nlsh.backends import BackendManager
from nlsh.tools import get_enabled_tools
from nlsh.prompt import PromptBuilder


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
    
    # Prompt (positional argument)
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Prompt for command generation"
    )
    
    return parser.parse_args(args)


async def generate_command(config: Config, backend_index: Optional[int], prompt: str) -> str:
    """Generate a command using the specified backend.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        prompt: User prompt.
        
    Returns:
        str: Generated command.
    """
    # Get enabled tools
    tools = get_enabled_tools(config)
    
    # Build prompt
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_system_prompt(tools)
    user_prompt = prompt_builder.build_user_prompt(prompt)
    
    # Get backend
    backend_manager = BackendManager(config)
    backend = backend_manager.get_backend(backend_index)
    
    # Generate command
    return await backend.generate_command(user_prompt, system_prompt)


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
        prompt = args.prompt
    
    # Generate command
    try:
        command = asyncio.run(generate_command(config, args.backend, prompt))
        
        # Display the command
        if args.interactive:
            # In interactive mode, ask for confirmation
            if confirm_execution(command):
                print(f"Executing: {command}")
                # Note: We don't actually execute the command for safety
                # The user can copy and paste it if they want to run it
            else:
                print("Command execution cancelled")
        else:
            # In non-interactive mode, just print the command
            print(command)
            
        return 0
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
