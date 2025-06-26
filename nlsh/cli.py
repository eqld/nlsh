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
import select
import signal
import subprocess
import sys
import traceback
from typing import Any, List, Optional, Union, TextIO

from nlsh.config import Config
from nlsh.backends import BackendManager, LLMBackend
from nlsh.config import Config
from nlsh.backends import BackendManager, LLMBackend
from nlsh.tools import get_tools
from nlsh.prompt import PromptBuilder
from nlsh.spinner import Spinner
from nlsh.editor import edit_text_in_editor


def _check_stdin_input() -> Optional[str]:
    """Check if there's input from STDIN and read it.
    
    Returns:
        str: STDIN content if available, None otherwise.
    """
    if not sys.stdin.isatty():
        try:
            return sys.stdin.read().strip()
        except Exception as e:
            print(f"Error reading from STDIN: {e}", file=sys.stderr)
            return None
    return None


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
    
    # Initialize configuration
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize a new configuration file"
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
    verbose: bool = False, 
    log_file: Optional[str] = None,
) -> str:
    """Generate a command using the specified backend.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        prompt: User prompt.
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
    system_prompt = prompt_builder.build_system_prompt(tools)
    
    # Get backend
    backend = backend_manager.get_backend(backend_index)
    
    # Start spinner if not in verbose mode
    spinner = None
    if not verbose:
        spinner = Spinner("Thinking")
        spinner.start()
    
    try:
        # Generate command
        response = await backend.generate_response(prompt, system_prompt, verbose=verbose, regeneration_count=0)
        log(log_file, backend, system_prompt, prompt, response)
        return response
    finally:
        if spinner: spinner.stop()


async def generate_command_regeneration(
    config: Config,
    backend_index: Optional[int],
    original_request: str,
    declined_commands: List[dict],
    verbose: bool = False,
    log_file: Optional[str] = None,
) -> str:
    """Generate a regenerated command using the specified backend.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        original_request: Original user request.
        declined_commands: List of declined commands with optional notes.
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
    system_prompt = prompt_builder.build_regeneration_system_prompt(tools)
    user_prompt = prompt_builder.build_regeneration_user_prompt(original_request, declined_commands)
    regeneration_count = len(declined_commands)
    
    # Get backend
    backend = backend_manager.get_backend(backend_index)
    
    # Start spinner if not in verbose mode
    spinner = None
    if not verbose:
        spinner = Spinner("Regenerating")
        spinner.start()
    
    try:
        # Generate command
        response = await backend.generate_response(user_prompt, system_prompt, verbose=verbose, regeneration_count=regeneration_count)
        log(log_file, backend, system_prompt, user_prompt, response)
        return response
    finally:
        if spinner: spinner.stop()


async def generate_command_fix(
    config: Config, 
    backend_index: Optional[int], 
    prompt: str,
    failed_command: str,
    failed_command_exit_code: int,
    failed_command_output: str,
    verbose: bool = False, 
    log_file: Optional[str] = None,
) -> str:
    """Generate a fix for failed command using the specified backend.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        prompt: User prompt.
        failed_command: Failed command.
        failed_command_exit_code: Exit code of the failed command.
        failed_command_output: Output of the failed command.
        verbose: Whether to print reasoning tokens to stderr.
        log_file: Optional path to log file.
        
    Returns:
        str: Fixed shell command.
        
    Raises:
        Exception: If command generation fails.
    """
    # Get backend manager
    backend_manager = BackendManager(config)
    
    # Get tools
    tools = get_tools(config=config)
    
    # Build prompt
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_fixing_system_prompt(tools)
    user_prompt = prompt_builder.build_fixing_user_prompt(
        prompt,
        failed_command, 
        failed_command_exit_code, 
        failed_command_output,
    )

    # Get backend
    backend = backend_manager.get_backend(backend_index)
    
    # Start spinner if not in verbose mode
    spinner = None
    if not verbose:
        spinner = Spinner("Fixing")
        spinner.start()
    
    try:
        # Generate command
        response = await backend.generate_response(user_prompt, system_prompt, verbose=verbose)
        log(log_file, backend, system_prompt, user_prompt, response)
        return response
    finally:
        if spinner: spinner.stop()


async def process_stdin_input(
    config: Config,
    backend_index: Optional[int],
    stdin_content: str,
    user_prompt: str,
    verbose: bool = False,
    log_file: Optional[str] = None,
) -> str:
    """Process STDIN input using the specified backend.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        stdin_content: Content read from STDIN.
        user_prompt: User's instruction for processing the content.
        verbose: Whether to print reasoning tokens to stderr.
        log_file: Optional path to log file.
        
    Returns:
        str: Processed result.
        
    Raises:
        Exception: If processing fails.
    """
    # Get backend manager
    backend_manager = BackendManager(config)
    
    # Build prompt (no system tools needed for STDIN processing)
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_stdin_processing_system_prompt()
    user_prompt_formatted = prompt_builder.build_stdin_processing_user_prompt(stdin_content, user_prompt)
    
    # Get backend
    backend = backend_manager.get_backend(backend_index)
    
    # Start spinner if not in verbose mode
    spinner = None
    if not verbose:
        spinner = Spinner("Processing")
        spinner.start()
    
    try:
        # Process input
        response = await backend.generate_response(
            user_prompt_formatted, 
            system_prompt, 
            verbose=verbose, 
            strip_markdown=False,  # Don't strip markdown for text processing
            max_tokens=2000  # Allow longer responses for text processing
        )
        log(log_file, backend, system_prompt, user_prompt_formatted, response)
        return response
    finally:
        if spinner: spinner.stop()


async def explain_command(
    config: Config,
    backend_index: Optional[int],
    command: str,
    verbose: int,
    log_file: Optional[str] = None
) -> str:
    """Generate an explanation for a shell command.
    
    Args:
        config: Configuration object.
        backend_index: Backend index to use.
        command: Shell command to explain.
        verbose: Verbosity mode.
        log_file: Optional path to log file.
        
    Returns:
        str: Generated explanation.
        
    Raises:
        Exception: If explanation generation fails.
    """
    # Get backend manager
    backend_manager = BackendManager(config)
    
    # Get tools
    tools = get_tools(config=config)
    
    # Build prompt
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_explanation_system_prompt(tools)
    
    # Get backend
    backend = backend_manager.get_backend(backend_index)
    
    # Start spinner if not in verbose mode
    spinner = None
    if verbose == 0:
        spinner = Spinner("Explaining")
        spinner.start()
    
    try:
        # Generate explanation
        explanation = await backend.generate_response(command, system_prompt, verbose=verbose, strip_markdown=False, max_tokens=1000)
        log(log_file, backend, system_prompt, command, explanation)
        return explanation
    finally:
        if spinner: spinner.stop()


def confirm_execution(command: str) -> Union[bool, str, tuple]:
    """Ask for confirmation before executing a command.
    
    Args:
        command: Command to execute.
        
    Returns:
        Union[bool, str, tuple]: True if confirmed, False if declined, "regenerate" if regeneration requested,
                               "explain" if explanation requested, "edit" if editing requested.
                               For regeneration, returns tuple ("regenerate", note) where note can be None.
    """
    print(f"Suggested: {command}")
    response = input("[Confirm] Run this command? (y/N/e/r/x) ").strip().lower()
    
    if response in ["r", "regenerate"]:
        note = input("Note for regeneration (optional): ").strip()
        return ("regenerate", note if note else None)
    elif response in ["e", "edit"]:
        return "edit"
    elif response in ["x", "explain"]:
        return "explain"
    
    return response in ["y", "yes"]


def confirm_fix(command: str, code: int) -> bool:
    """Ask for confirmation before fixing failed command.
    
    Args:
        command: Command to fix.
        
    Returns:
        bool: True if confirmed, False if declined.
    """
    print()
    print("----------------")
    print(f"Command execution failed with code {code}")
    print(f"Failed command: {command}")
    print("Try to fix? If you confirm, the command output and exit code will be sent to LLM.")
    response = input("[Confirm] Try to fix this command? (y/N) ").strip().lower()

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


def execute_command(command: str) -> tuple[int, str]:
    """Execute a shell command safely."""
    output = ""
    process = None

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
            bufsize=0,  # Unbuffered
            encoding=system_encoding,
            errors='replace'  # Replace invalid characters
        )
        
        # Use select for non-blocking I/O
        stdout_fd = process.stdout.fileno()
        stderr_fd = process.stderr.fileno()
        
        readable_fds = [stdout_fd, stderr_fd]
        stdout_data, stderr_data = "", ""
        
        while readable_fds:
            # Use select to wait for data to be available
            ready_to_read, _, _ = select.select(readable_fds, [], [], 0.1)
            
            # Process has exited and no more data to read
            if not ready_to_read and process.poll() is not None:
                break
                
            for fd in ready_to_read:
                if fd == stdout_fd:
                    data = process.stdout.read(1024)
                    if not data:  # EOF
                        readable_fds.remove(stdout_fd)
                    else:
                        safe_write(sys.stdout, data)
                        stdout_data += data
                        output += data
                        
                elif fd == stderr_fd:
                    data = process.stderr.read(1024)
                    if not data:  # EOF
                        readable_fds.remove(stderr_fd)
                    else:
                        safe_write(sys.stderr, data)
                        stderr_data += data
                        output += data
        
        # Wait for process to complete and get exit code
        return process.wait(), output
        
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


def log(log_file: str, backend: LLMBackend, system_prompt: str, prompt: str, response: str):
    if not log_file:
        return
    
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


def _handle_edit_command(command: str) -> tuple[str, bool]:
    """Handle editing a command.
    
    Args:
        command: Command to edit.
        
    Returns:
        tuple: (edited_command, should_continue)
    """
    edited_command = edit_text_in_editor(command, suffix=".sh")

    if edited_command is None:
        # Edit was cancelled, errored, or resulted in empty command.
        print("Edit cancelled or failed. Returning to original command confirmation.", file=sys.stderr)
        return command, True
    
    if edited_command == command:
        print("Command unchanged.", file=sys.stderr)
        return command, True

    # Confirm execution of the edited command
    print(f"\nEdited command: {edited_command}")
    return edited_command, True


def _handle_explain_command(config: Config, args: argparse.Namespace, command: str) -> bool:
    """Handle explaining a command.
    
    Args:
        config: Configuration object.
        args: Command-line arguments.
        command: Command to explain.
        
    Returns:
        bool: Whether to continue with confirmation.
    """
    try:
        explanation = asyncio.run(explain_command(
            config,
            args.backend,
            command,
            verbose=args.verbose,
            log_file=args.log_file,
        ))
        print("\nExplanation:")
        print("-" * 40)
        print(explanation)
        print("-" * 40)
        return True
    except Exception as e:
        print(f"Error generating explanation: {str(e)}", file=sys.stderr)
        if args.verbose > 1:  # Show stack trace in double verbose mode
            traceback.print_exc(file=sys.stderr)
        return True


def _process_command_confirmation(config: Config, args: argparse.Namespace, command: str, declined_commands: List[dict]) -> tuple[int, bool, dict]:
    """Process command confirmation and execution.
    
    Args:
        config: Configuration object.
        args: Command-line arguments.
        command: Command to confirm and execute.
        declined_commands: List of declined commands with optional notes.
        
    Returns:
        tuple: (exit_code, should_continue, fix_info)
    """
    fix_info = {
        "fix_command": False,
        "failed_command": None,
        "failed_command_exit_code": None,
        "failed_command_output": None,
        "regenerate": False,
    }
    
    while True:
        # Ask for confirmation
        confirmation = confirm_execution(command)
        
        if isinstance(confirmation, tuple) and confirmation[0] == "regenerate":
            # Regenerate the command with optional note
            _, note = confirmation
            declined_commands.append({"command": command, "note": note})
            fix_info["regenerate"] = True
            return -1, False, fix_info  # Continue outer loop
        elif confirmation == "edit":
            command, should_continue = _handle_edit_command(command)
            if should_continue:
                continue
        elif confirmation == "explain":
            should_continue = _handle_explain_command(config, args, command)
            if should_continue:
                continue
        elif confirmation:
            print(f"Executing: {command}")
            # Actually execute the command
            code, output = execute_command(command)
            if code == 0:
                # Command execution finished successfully
                return 0, True, fix_info
            
            # Command execution failed, ask for fixing
            fix_command = confirm_fix(command, code)
            if fix_command:
                fix_info["fix_command"] = True
                fix_info["failed_command"] = command
                fix_info["failed_command_output"] = output
                fix_info["failed_command_exit_code"] = code
                return -1, False, fix_info  # Continue outer loop

            # Fixing declined, return error code
            return code, True, fix_info
        else:
            print("Command execution cancelled")
            return 0, True, fix_info


def _get_prompt(args: argparse.Namespace, config: Config) -> str:
    """Get prompt from file or command line.
    
    Args:
        args: Command-line arguments.
        config: Configuration object.
        
    Returns:
        str: Prompt.
    """
    if args.prompt_file:
        prompt_builder = PromptBuilder(config)
        return prompt_builder.load_prompt_from_file(args.prompt_file)
    else:
        # Join all prompt arguments into a single string
        return " ".join(args.prompt) if args.prompt else ""


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
        
        # Handle --init flag
        if args.init:
            Config.create_default_config()
            return 0
        
        # Show version and exit
        if args.version:
            from nlsh import __version__
            print(f"nlsh version {__version__}")
            return 0
        
        # Load configuration
        config = Config(args.config)
        
        # Notify if no config file was found
        if not config.config_file_found:
            print("Note: No configuration file found at default locations.", file=sys.stderr)
            print("Using default configuration. Run 'nlsh --init' to create a config file.", file=sys.stderr)
            print()

        # Check for STDIN input first
        stdin_content = _check_stdin_input()
        
        if stdin_content:
            # STDIN processing mode
            if not args.prompt and not args.prompt_file:
                print("Error: No prompt provided for STDIN processing")
                return 1
            
            # Get prompt from file or command line
            prompt = _get_prompt(args, config)
            
            try:
                # Process STDIN input
                result = asyncio.run(process_stdin_input(
                    config,
                    args.backend,
                    stdin_content,
                    prompt,
                    verbose=args.verbose > 0,
                    log_file=args.log_file,
                ))
                
                # Output result to STDOUT
                print(result)
                return 0
                
            except Exception as e:
                print(f"Error processing STDIN input: {str(e)}", file=sys.stderr)
                if args.verbose > 1:
                    traceback.print_exc(file=sys.stderr)
                return 1
        
        # Normal command generation mode
        # Check if we have a prompt
        if not args.prompt and not args.prompt_file:
            print("Error: No prompt provided")
            return 1

        # Get prompt from file or command line
        prompt = _get_prompt(args, config)

        # Command generation and execution loop
        fix_info = {
            "fix_command": False,
            "failed_command": None,
            "failed_command_exit_code": None,
            "failed_command_output": None,
            "regenerate": False,
        }
        declined_commands = []
        
        while True:
            try:
                # Generate, fix, or regenerate command
                if fix_info["fix_command"]:
                    command = asyncio.run(generate_command_fix(
                        config,
                        args.backend,
                        prompt,
                        fix_info["failed_command"],
                        fix_info["failed_command_exit_code"],
                        fix_info["failed_command_output"],
                        verbose=args.verbose > 0,
                        log_file=args.log_file,
                    ))
                elif fix_info["regenerate"] or declined_commands:
                    # Use regeneration logic if we have declined commands or explicit regeneration request
                    command = asyncio.run(generate_command_regeneration(
                        config,
                        args.backend,
                        prompt,
                        declined_commands,
                        verbose=args.verbose > 0,
                        log_file=args.log_file,
                    ))
                else:
                    # Initial command generation
                    command = asyncio.run(generate_command(
                        config,
                        args.backend,
                        prompt,
                        verbose=args.verbose > 0,
                        log_file=args.log_file,
                    ))
                
                # Process command confirmation and execution
                exit_code, should_exit, fix_info = _process_command_confirmation(
                    config, args, command, declined_commands
                )
                
                if should_exit:
                    return exit_code
                
                # Reset regenerate flag after processing
                if fix_info.get("regenerate"):
                    fix_info["regenerate"] = False
                # Otherwise continue the loop
            except Exception as e:
                print(f"Error during command generation or execution: {str(e)}", file=sys.stderr)
                if args.verbose > 1:
                    traceback.print_exc(file=sys.stderr)
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
