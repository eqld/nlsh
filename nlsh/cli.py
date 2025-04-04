"""
Command-line interface for nlsh.

This module provides the command-line interface for the nlsh utility.
"""

import argparse
import asyncio
import datetime
import json
import locale
import os
import signal
import subprocess
import sys
import traceback
from typing import Any, List, Optional, Union, TextIO

from nlsh.config import Config
from nlsh.backends import BackendManager
from nlsh.tools import get_tools
from nlsh.prompt import PromptBuilder
from nlsh.spinner import Spinner


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

    # Verbose mode
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Verbose mode (-v for reasoning tokens, -vv for debug info)"
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
    declined_commands: List[str] = [],
    verbose: bool = False, 
    log_file: Optional[str] = None
) -> str:
    """Generate a command using the specified backend.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        prompt: User prompt.
        declined_commands: List of declined commands.
        verbose: Whether to print reasoning tokens to stderr.
        log_file: Optional path to log file.
        
    Returns:
        str: Generated shell command.
        
    Raises:
        Exception: If command generation fails.
    """
    # Get backend manager
    backend_manager = BackendManager(config)
    
    # Get tools
    tools = get_tools(config=config)
    
    # Build prompt
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_system_prompt(tools, declined_commands)
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
    except Exception as e:
        print(f"Error generating command: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise  # Re-raise the exception instead of returning error message
    finally:
        # Stop spinner
        if spinner:
            spinner.stop()


def confirm_execution(command: str) -> Union[bool, str]:
    """Ask for confirmation before executing a command.
    
    Args:
        command: Command to execute.
        
    Returns:
        Union[bool, str]: True if confirmed, False if declined, "regenerate" if regeneration requested.
    """
    print(f"Suggested: {command}")
    response = input("[Confirm] Run this command? (y/N/r) ").strip().lower()
    
    if response in ["r", "regenerate"]:
        return "regenerate"
    
    return response in ["y", "yes"]


def handle_keyboard_interrupt(signum: int, frame: Any) -> None:
    """Handle keyboard interrupt (Ctrl+C)."""
    print("\nOperation cancelled by user", file=sys.stderr)
    sys.exit(130)  # 128 + SIGINT


def safe_write(stream: TextIO, text: str) -> None:
    """Safely write text to a stream, handling encoding errors.
    
    Args:
        stream: Output stream (stdout/stderr).
        text: Text to write.
    """
    try:
        stream.write(text)
        stream.flush()
    except UnicodeEncodeError:
        # Fall back to ascii with replacement characters
        stream.write(text.encode(stream.encoding or 'ascii', 'replace').decode())
        stream.flush()


def execute_command(command: str) -> int:
    """Execute a shell command safely."""
    try:
        shell = os.environ.get("SHELL", "/bin/sh")
        
        # Set up signal handler for Ctrl+C
        signal.signal(signal.SIGINT, handle_keyboard_interrupt)
        
        # Get system encoding
        system_encoding = locale.getpreferredencoding()
        
        # Security Note: Using shell=True can be risky if the command is crafted maliciously.
        # User confirmation (confirm_execution) is the primary safeguard.
        process = subprocess.Popen(
            command,
            shell=True,
            executable=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,  # Line buffered
            encoding=system_encoding,
            errors='replace'  # Replace invalid characters
        )
        
        # Note: Reading line-by-line may not render interactive command output (e.g., progress bars) correctly.
        while True:
            stdout_line = process.stdout.readline() if process.stdout else ''
            stderr_line = process.stderr.readline() if process.stderr else ''
            
            if not stdout_line and not stderr_line and process.poll() is not None:
                break
                
            if stdout_line:
                safe_write(sys.stdout, stdout_line)
            if stderr_line:
                safe_write(sys.stderr, stderr_line)
        
        return process.wait()
        
    except KeyboardInterrupt:
        if process:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
        print("\nCommand interrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error executing command: {str(e)}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point.
    
    Returns:
        int: Exit code.
    """
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)
    
    try:
        # Parse arguments
        args = parse_args(sys.argv[1:])
        
        # Show version and exit
        if args.version:
            from nlsh import __version__
            print(f"nlsh version {__version__}")
            return 0
        
        # Load configuration
        try:
            config = Config(args.config)
        except Exception as e:
            print(f"Configuration error: {str(e)}", file=sys.stderr)
            if args.verbose > 1:  # Show stack trace in double verbose mode
                traceback.print_exc(file=sys.stderr)
            return 1

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
            declined_commands = []
            # Interactive mode with command regeneration
            while True:
                try:
                    # Generate command
                    command = asyncio.run(generate_command(
                        config, 
                        args.backend, 
                        prompt, 
                        declined_commands=declined_commands,
                        verbose=args.verbose > 0,  # Single verbose for reasoning
                        log_file=args.log_file,
                    ))
                    
                    # Ask for confirmation only if command generation succeeded
                    if not command.startswith("Error:"):
                        # Ask for confirmation
                        confirmation = confirm_execution(command)
                        
                        if confirmation == "regenerate":
                            # Regenerate the command
                            print("Regenerating command...")
                            declined_commands.append(command)
                            continue
                        elif confirmation:
                            print(f"Executing: {command}")
                            # Actually execute the command
                            return execute_command(command)
                        else:
                            print("Command execution cancelled")
                            return 0
                    
                    # If we got an error, return error code
                    return 1
                except ValueError as e:
                    print(f"Error: {str(e)}", file=sys.stderr)
                    if args.verbose > 1:  # Show stack trace in double verbose mode
                        traceback.print_exc(file=sys.stderr)
                    if "API key" in str(e) or "Authentication failed" in str(e):
                        print("\nTroubleshooting tips:", file=sys.stderr)
                        print("1. Check that your API key is correctly set in the environment variable", file=sys.stderr)
                        print("2. Verify the API key is valid with your provider", file=sys.stderr)
                        print("3. Check the backend URL is correct in your configuration", file=sys.stderr)
                    return 1
                except Exception as e:
                    print(f"Error: {str(e)}", file=sys.stderr)
                    if args.verbose > 1:  # Show stack trace in double verbose mode
                        traceback.print_exc(file=sys.stderr)
                    return 1
        except Exception as e:
            print(f"Error generating command: {str(e)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        if args.verbose > 1:  # Show stack trace in double verbose mode
            traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
