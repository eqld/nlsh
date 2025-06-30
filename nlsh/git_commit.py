#!/usr/bin/env python3
"""
Neural Git Commit (nlgc) - AI-driven commit message generator.

This module provides the command-line interface for the nlgc utility,
which generates Git commit messages based on staged changes.
"""

import argparse
import asyncio
import os
import signal
import subprocess
import sys
import traceback
from typing import List, Optional, Union, Dict

import openai  # For catching potential API errors like context length

from nlsh.config import Config, ConfigValidationError
from nlsh.backends import BackendManager
from nlsh.spinner import Spinner
from nlsh.cli import handle_keyboard_interrupt, log
from nlsh.editor import edit_text_in_editor
from nlsh.prompt import PromptBuilder


# Custom Exceptions
class NlgcError(Exception):
    """Base exception for nlgc errors."""
    pass

class GitCommandError(NlgcError):
    """Error executing a git command."""
    pass

class ContextLengthExceededError(NlgcError):
    """Error when prompt context exceeds the model's limit."""
    pass

class EmptyCommitMessageError(NlgcError):
    """Error when the LLM returns an empty commit message."""
    pass


FILE_CONTENT_HEADER = "Full content of changed files:"
GIT_COMMIT_MESSAGE_MAX_TOKENS = 150


def parse_args(args: List[str]) -> argparse.Namespace:
    """Parse command-line arguments for nlgc."""
    parser = argparse.ArgumentParser(
        description="Neural Git Commit (nlgc) - AI commit message generator"
    )
    
    # Backend selection arguments (similar to nlsh)
    for i in range(10):
        parser.add_argument(
            f"-{i}",
            dest="backend",
            action="store_const",
            const=i,
            help=f"Use backend {i}"
        )

    # Verbose mode (similar to nlsh)
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Verbose mode (-v for reasoning tokens, -vv for debug info)"
    )
    
    # Configuration file (similar to nlsh)
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
    
    # Log file (similar to nlsh)
    parser.add_argument(
        "--log-file",
        help="Path to file for logging LLM requests and responses"
    )

    # Flags to control inclusion of full file content
    full_files_group = parser.add_mutually_exclusive_group()
    full_files_group.add_argument(
        "--full-files",
        action="store_true",
        default=None, # Default is None to distinguish from explicitly setting False
        help="Force inclusion of full file contents in the prompt (overrides config)."
    )
    full_files_group.add_argument(
        "--no-full-files",
        action="store_false",
        dest="full_files", # Set dest to the same as --full-files
        help="Force exclusion of full file contents from the prompt (overrides config)."
    )

    # Optional arguments for git diff (e.g., --all for unstaged changes)
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Consider all tracked files, not just staged changes."
    )

    # Language for commit message generation
    parser.add_argument(
        "--language", "-l",
        help="Language for commit message generation (e.g., 'Spanish', 'French', 'German')"
    )

    return parser.parse_args(args)


def _get_git_root() -> str:
    """Find the root directory of the git repository."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True, encoding='utf-8'
        )
        return result.stdout.strip()
    except FileNotFoundError:
        raise GitCommandError("Git command not found. Make sure Git is installed and in your PATH.")
    except subprocess.CalledProcessError as e:
        # This error often means not in a git repository
        raise GitCommandError("Failed to find git repository root. Are you in a git repository?") from e
    except Exception as e:
        raise GitCommandError(f"Failed to get git root directory: {str(e)}") from e


def get_git_diff(staged: bool = True) -> str:
    """Get the git diff.
    
    Args:
        staged: If True, get diff for staged changes. Otherwise, get diff for all changes.
        
    Returns:
        str: The git diff output.
        
    Raises:
        RuntimeError: If git command fails or not in a git repository.
    """
    command = ['git', 'diff']
    if staged:
        command.append('--staged')
        
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        if not result.stdout.strip():
            raise RuntimeError("No changes detected." + (" Add files to staging area or use appropriate flags." if staged else ""))
        return result.stdout
    except FileNotFoundError:
        raise GitCommandError("Git command not found. Make sure Git is installed and in your PATH.")
    except subprocess.CalledProcessError as e:
        error_message = f"Git diff command failed: {e.stderr}"
        if "not a git repository" in e.stderr.lower():
            error_message = "Not a git repository (or any of the parent directories)."
        raise GitCommandError(error_message)
    except Exception as e:
        raise GitCommandError(f"Failed to get git diff: {str(e)}")


def get_changed_files(staged: bool = True) -> List[str]:
    """Get the list of changed files relative to the git root.

    Args:
        staged: If True, get staged files. Otherwise, get all changed files.
        
    Returns:
        List[str]: List of file paths relative to the git root.
        
    Raises:
        RuntimeError: If git command fails.
    """
    command = ['git', 'diff', '--name-only']
    if staged:
        command.append('--staged')
        
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        return [line for line in result.stdout.strip().split('\n') if line]
    except subprocess.CalledProcessError as e:
        raise GitCommandError(f"Git diff --name-only command failed: {e.stderr}")
    except Exception as e:
        raise GitCommandError(f"Failed to get changed file list: {str(e)}")


def read_file_content(file_path: str, git_root: str) -> Optional[str]:
    """Read the content of a file relative to the git root.

    Args:
        file_path: Path relative to git root.
        git_root: Absolute path to the git repository root.

    Returns:
        File content as string, or None if reading fails.
    """
    absolute_path = os.path.join(git_root, file_path)
    try:
        with open(absolute_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except FileNotFoundError:
        # This might happen if the file was deleted but still shows in diff temporarily
        print(f"Warning: Changed file not found at expected path: {absolute_path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Could not read file {file_path}: {str(e)}", file=sys.stderr)
        return None


def generate_commit_message(
    config: Config,
    backend_index: Optional[int],
    git_diff: str,
    changed_files_content: Optional[Dict[str, str]], # Dict of {filepath: content}
    verbose: bool = False,
    log_file: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """Generate a commit message using the specified backend.

    Raises:
        ContextLengthExceededError: If the prompt is too long for the model.
        EmptyCommitMessageError: If the model returns an empty message.
        NlgcError: For other API or backend errors.
    """
    # Initialize backend and build prompts
    backend_manager = BackendManager(config)
    backend = backend_manager.get_backend(backend_index)
    
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_git_commit_system_prompt(language)
    user_prompt = prompt_builder.build_git_commit_user_prompt(git_diff, changed_files_content)

    # Start spinner if not in verbose mode
    spinner = None
    if not verbose:
        spinner = Spinner("Generating commit message")
        spinner.start()

    try:
        # Generate response
        response_content = asyncio.run(backend.generate_response(
            user_prompt, 
            system_prompt, 
            verbose=verbose, 
            strip_markdown=True,
            max_tokens=GIT_COMMIT_MESSAGE_MAX_TOKENS
        ))

        log(log_file, backend, system_prompt, user_prompt, response_content)

        if not response_content:
            raise EmptyCommitMessageError("LLM returned an empty commit message.")

        return response_content

    except openai.BadRequestError as e:
        # Handle context length errors specifically
        error_str = str(e).lower()
        if "context_length_exceeded" in error_str or "too large" in error_str or "context length" in error_str:
            error_msg = (
                "Error: The diff and file contents combined are too large for the selected model's context window.\n"
                "Try running again with the '--no-full-files' flag."
            )
            print(error_msg, file=sys.stderr)
            raise ContextLengthExceededError(error_msg) from e
        
        # Re-raise other BadRequestErrors
        raise NlgcError(f"LLM API request failed: {str(e)}") from e
    except Exception as e:
        # Re-raise other exceptions
        if not isinstance(e, (ContextLengthExceededError, EmptyCommitMessageError)):
            raise NlgcError(f"Error generating commit message: {str(e)}") from e
        raise
    finally:
        # Always stop the spinner
        if spinner:
            spinner.stop()


def generate_commit_message_regeneration(
    config: Config,
    backend_index: Optional[int],
    git_diff: str,
    changed_files_content: Optional[Dict[str, str]],
    declined_messages: List[str],
    verbose: bool = False,
    log_file: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """Generate a regenerated commit message using the specified backend.

    Raises:
        ContextLengthExceededError: If the prompt is too long for the model.
        EmptyCommitMessageError: If the model returns an empty message.
        NlgcError: For other API or backend errors.
    """
    # Initialize backend and build prompts
    backend_manager = BackendManager(config)
    backend = backend_manager.get_backend(backend_index)
    regeneration_count = len(declined_messages)
    
    prompt_builder = PromptBuilder(config)
    system_prompt = prompt_builder.build_git_commit_regeneration_system_prompt(language)
    user_prompt = prompt_builder.build_git_commit_regeneration_user_prompt(
        git_diff, changed_files_content, declined_messages
    )

    # Start spinner if not in verbose mode
    spinner = None
    if not verbose:
        spinner = Spinner("Regenerating commit message")
        spinner.start()

    try:
        # Generate response
        response_content = asyncio.run(backend.generate_response(
            user_prompt, 
            system_prompt, 
            verbose=verbose, 
            strip_markdown=True,
            max_tokens=GIT_COMMIT_MESSAGE_MAX_TOKENS, 
            regeneration_count=regeneration_count
        ))

        log(log_file, backend, system_prompt, user_prompt, response_content)

        if not response_content:
            raise EmptyCommitMessageError("LLM returned an empty commit message.")

        return response_content

    except openai.BadRequestError as e:
        # Handle context length errors specifically
        error_str = str(e).lower()
        if "context_length_exceeded" in error_str or "too large" in error_str or "context length" in error_str:
            error_msg = (
                "Error: The diff and file contents combined are too large for the selected model's context window.\n"
                "Try running again with the '--no-full-files' flag."
            )
            print(error_msg, file=sys.stderr)
            raise ContextLengthExceededError(error_msg) from e
        
        # Re-raise other BadRequestErrors
        raise NlgcError(f"LLM API request failed: {str(e)}") from e
    except Exception as e:
        # Re-raise other exceptions
        if not isinstance(e, (ContextLengthExceededError, EmptyCommitMessageError)):
            raise NlgcError(f"Error generating commit message: {str(e)}") from e
        raise
    finally:
        # Always stop the spinner
        if spinner:
            spinner.stop()


def confirm_commit(message: str) -> Union[bool, str]:
    """Ask for confirmation before committing."""
    print("\nSuggested commit message:")
    print("-" * 20)
    print(message)
    print("-" * 20)
    response = input("[Confirm] Use this message? (y/N/e/r) ").strip().lower()
    
    if response in ["r", "regenerate"]:
        return "regenerate"
    if response in ["e", "edit"]:
        return "edit"
    
    return response in ["y", "yes"]


def run_git_commit(message: str) -> int:
    """Run the git commit command."""
    try:
        # Using -m avoids needing an editor for simple cases
        result = subprocess.run(['git', 'commit', '-m', message], check=True, encoding='utf-8')
        result.check_returncode()
        print("Commit successful.")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Git commit failed:\n{e.stderr}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error running git commit: {str(e)}", file=sys.stderr)
        return 1


def _prepare_git_data(args, include_full_files):
    """Prepare git data for commit message generation.
    
    Args:
        args: Command-line arguments.
        include_full_files: Whether to include full file contents.
        
    Returns:
        tuple: (git_diff, changed_files_content)
        
    Raises:
        GitCommandError: If a git command fails.
        RuntimeError: If there are no changes to commit.
    """
    git_root = _get_git_root()
    git_diff = get_git_diff(staged=not args.all)
    
    changed_files_content = None
    if include_full_files:
        changed_files = get_changed_files(staged=not args.all)
        if changed_files:
            print(f"Reading content of {len(changed_files)} changed file(s)...")
            changed_files_content = {}
            for file_path in changed_files:
                content = read_file_content(file_path, git_root)
                if content is not None:
                    MAX_FILE_SIZE = 100 * 1024
                    if len(content) > MAX_FILE_SIZE:
                        print(f"Warning: File '{file_path}' is large ({len(content)} bytes), truncating for prompt.", file=sys.stderr)
                        content = content[:MAX_FILE_SIZE] + "\n... [TRUNCATED]"
                    changed_files_content[file_path] = content
    
    return git_diff, changed_files_content


def _generate_and_confirm_message(config, args, git_diff, changed_files_content, declined_messages=None, language=None):
    """Generate and confirm a commit message.
    
    Args:
        config: Configuration object.
        args: Command-line arguments.
        git_diff: Git diff output.
        changed_files_content: Dict of file contents.
        declined_messages: List of previously declined messages.
        language: Language for commit message generation.
        
    Returns:
        tuple: (success, exit_code)
        
    Raises:
        Various exceptions from generate_commit_message.
    """
    if declined_messages is None:
        declined_messages = []
    
    # Use regeneration function if we have declined messages, otherwise use initial generation
    if declined_messages:
        commit_message = generate_commit_message_regeneration(
            config,
            args.backend,
            git_diff,
            changed_files_content,
            declined_messages,
            verbose=args.verbose > 0,
            log_file=args.log_file,
            language=language,
        )
    else:
        commit_message = generate_commit_message(
            config,
            args.backend,
            git_diff,
            changed_files_content,
            verbose=args.verbose > 0,
            log_file=args.log_file,
            language=language,
        )

    confirmation = confirm_commit(commit_message)

    if confirmation == "regenerate":
        declined_messages.append(commit_message)
        return False, 0  # Continue loop
    elif confirmation == "edit":
        edited_message = edit_text_in_editor(commit_message, suffix=".txt")

        if edited_message is None:
            print("Edit cancelled or failed. Aborting commit.", file=sys.stderr)
            return True, 1  # Exit with error

        print("\nUsing edited message:")
        print("-" * 20)
        print(edited_message)
        print("-" * 20)
        if input("Commit with this message? (y/N) ").strip().lower() == 'y':
            return True, run_git_commit(edited_message)
        else:
            print("Commit cancelled.")
            return True, 0
    elif confirmation:
        return True, run_git_commit(commit_message)
    else:
        print("Commit cancelled.")
        return True, 0


def _main(config: Config, args: argparse.Namespace) -> int:
    """Main logic for nlgc."""
    # Determine whether to include full files
    nlgc_config = config.get_nlgc_config()
    include_full_files = nlgc_config.get("include_full_files", True)
    if args.full_files is not None:
        include_full_files = args.full_files

    # Determine language (priority: CLI arg > env var > config > default)
    language = None
    if args.language:
        language = args.language.strip()
    elif nlgc_config.get("language"):
        language = nlgc_config.get("language")
    
    # Get git data
    try:
        git_diff, changed_files_content = _prepare_git_data(args, include_full_files)
    except (GitCommandError, RuntimeError) as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

    # Generate and confirm commit message
    declined_messages = []
    while True:
        try:
            done, exit_code = _generate_and_confirm_message(
                config, args, git_diff, changed_files_content, declined_messages, language
            )
            if done:
                return exit_code
        except (ContextLengthExceededError, EmptyCommitMessageError, NlgcError, ValueError) as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            if args.verbose > 1 and not isinstance(e, ContextLengthExceededError):
                traceback.print_exc(file=sys.stderr)
            return 1
        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}", file=sys.stderr)
            if args.verbose > 1:
                traceback.print_exc(file=sys.stderr)
            return 1



def main() -> None:
    """Synchronous wrapper function for the nlgc entry point."""
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)
    exit_code = 1 # Default exit code
    try:
        # Parse args
        args = parse_args(sys.argv[1:])
        
        # Handle --init flag
        if args.init:
            Config.create_default_config()
            sys.exit(0)
        
        # Load config
        config = Config(args.config)
        
        # Notify if no config file was found
        if not config.config_file_found:
            print("Note: No configuration file found at default locations.", file=sys.stderr)
            print("Using default configuration. Run 'nlgc --init' to create a config file.", file=sys.stderr)
            print()

        exit_code = _main(config, args)

    except (ConfigValidationError, GitCommandError, NlgcError, ValueError) as e:
        # Catch known errors that might occur during config loading or async execution
        print(f"Error: {str(e)}", file=sys.stderr)
        if _get_verbose_level() > 1: traceback.print_exc(file=sys.stderr)
        exit_code = 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        exit_code = 130
    except Exception as e:
        print(f"Fatal error: {str(e)}", file=sys.stderr)
        if _get_verbose_level() > 1: traceback.print_exc(file=sys.stderr)
        exit_code = 1
    finally:
        sys.exit(exit_code)


def _get_verbose_level() -> int:
    verbose_level = 0
    for _, arg in enumerate(sys.argv):
        if arg == '-v': verbose_level += 1
        if arg == '--verbose': verbose_level += 1
        if arg.startswith('-v') and not arg.startswith('--'):
            verbose_level += len(arg) -1
    
    return verbose_level


if __name__ == "__main__":
    main()
