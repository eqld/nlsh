#!/usr/bin/env python3
"""
Neural Git Commit (nlgc) - AI-driven commit message generator.

This module provides the command-line interface for the nlgc utility,
which generates Git commit messages based on staged changes.
"""

import argparse
import asyncio
import datetime
import json
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
from nlsh.cli import handle_keyboard_interrupt, safe_write # Reuse existing handlers


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


# System prompt template for commit message generation
GIT_COMMIT_SYSTEM_PROMPT = """You are an AI assistant that generates concise git commit messages following conventional commit standards (e.g., 'feat: description'). Analyze the provided git diff and the full content of changed files (if provided) to create a suitable commit message summarizing the changes. Output only the commit message (subject and optional body). Do not include explanations or markdown formatting like ```.

{file_content_section}

Git Diff:
```diff
{git_diff}
```
"""

FILE_CONTENT_HEADER = "Full content of changed files:"


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


async def generate_commit_message(
    config: Config,
    backend_index: Optional[int],
    git_diff: str,
    changed_files_content: Optional[Dict[str, str]], # Dict of {filepath: content}
    declined_messages: List[str] = [],
    verbose: bool = False,
    print_stack_trace: bool = False,
    log_file: Optional[str] = None
) -> str:
    """Generate a commit message using the specified backend.

    Raises:
        ContextLengthExceededError: If the prompt is too long for the model.
        EmptyCommitMessageError: If the model returns an empty message.
        Exception: For other API or backend errors.
    """
    backend_manager = BackendManager(config)
    backend = backend_manager.get_backend(backend_index)

    # Prepare file content section for the prompt
    file_content_section = ""
    if changed_files_content:
        file_content_section += FILE_CONTENT_HEADER + "\n"
        for file_path, content in changed_files_content.items():
            file_content_section += f"--- {file_path} ---\n"
            file_content_section += content + "\n\n"
        file_content_section = file_content_section.strip() # Remove trailing newlines

    # Build the system prompt
    system_prompt = GIT_COMMIT_SYSTEM_PROMPT.format(
        git_diff=git_diff,
        file_content_section=file_content_section
    )
    
    # Add declined messages if any
    user_prompt = "Generate a commit message." # Simple user prompt
    if declined_messages:
        user_prompt += "\nDo not suggest the following messages:\n" + "\n".join(f"- {msg}" for msg in declined_messages)

    spinner = None
    if not verbose:
        spinner = Spinner("Generating commit message")
        spinner.start()

    error_msg = None

    try:
        # Generate commit message using a simplified call (no tools needed here)
        # Reusing generate_command logic structure but with specific prompt
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response_content = ""
        
        if verbose:
            full_response = ""
            sys.stderr.write("Reasoning: ")
            stream = backend.client.chat.completions.create(
                model=backend.model, messages=messages, temperature=0.2, max_tokens=150, n=1, stream=True
            )
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        # Reasoning models might have specific fields, adjust if needed
                        sys.stderr.write(delta.content)
                        sys.stderr.flush()
                        full_response += delta.content
            sys.stderr.write("\n")
            response_content = full_response.strip()
        else:
            response = backend.client.chat.completions.create(
                model=backend.model, messages=messages, temperature=0.2, max_tokens=150, n=1
            )
            if response.choices and len(response.choices) > 0:
                response_content = response.choices[0].message.content.strip()

        # Basic cleanup - remove potential markdown fences if LLM didn't obey
        if response_content.startswith("```") and response_content.endswith("```"):
            response_content = response_content[3:-3].strip()
        if response_content.startswith("`") and response_content.endswith("`"):
            response_content = response_content[1:-1].strip()

        # Log if needed
        if log_file:
            log_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "backend": {"name": backend.name, "model": backend.model, "url": backend.url},
                "system_prompt": system_prompt, # Log the full prompt
                "user_prompt": user_prompt,
                "response": response_content
            }
            try:
                log_dir = os.path.dirname(log_file)
                if log_dir and not os.path.exists(log_dir): os.makedirs(log_dir)
                with open(log_file, 'a') as f: f.write(json.dumps(log_entry, indent=2) + "\n")
            except Exception as e:
                print(f"Error writing to log file: {str(e)}", file=sys.stderr)

        if not response_content:
            raise EmptyCommitMessageError("LLM returned an empty commit message.")

        return response_content

    except openai.BadRequestError as e:
        # Check if the error is likely due to context length
        error_str = str(e).lower()
        if "context_length_exceeded" in error_str or "too large" in error_str or "context length" in error_str:
            error_msg = (
                "Error: The diff and file contents combined are too large for the selected model's context window.\n"
                "Try running again with the '--no-full-files' flag."
            )
            # Raise the custom exception
            raise ContextLengthExceededError(error_msg) from e
        else:
            # Re-raise other BadRequestErrors
            raise NlgcError(f"LLM API request failed: {str(e)}") from e
    except Exception as e:
        # Catch other potential exceptions during API call
        raise NlgcError(f"Error generating commit message: {str(e)}") from e
    finally:
        if spinner:
            spinner.stop()
        if error_msg:
            print(error_msg, file=sys.stderr)


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
        return "edit" # We'll handle editing later if needed
    
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


async def _async_main(config: Config, args: argparse.Namespace) -> int: # Accept config and args
    """Asynchronous main logic for nlgc."""
    # Args and config are now passed directly

    try:
        # Config is already loaded and validated by the caller (main)

        # Determine whether to include full files
        nlgc_config = config.get_nlgc_config()
        include_full_files = nlgc_config.get("include_full_files", True) # Default to True if missing
        if args.full_files is not None: # CLI flag overrides config
            include_full_files = args.full_files

        # Get git diff, root, and file contents
        try:
            git_root = _get_git_root() # Get repo root first
            git_diff = get_git_diff(staged=not args.all) # Use --all flag correctly

            changed_files_content = None
            if include_full_files:
                changed_files = get_changed_files(staged=not args.all)
                if changed_files:
                    print(f"Reading content of {len(changed_files)} changed file(s)...")
                    changed_files_content = {}
                    for file_path in changed_files:
                        # Pass git_root to read_file_content
                        content = read_file_content(file_path, git_root)
                        if content is not None:
                            # Limit file size to avoid excessively large prompts (e.g., 100KB)
                            MAX_FILE_SIZE = 100 * 1024
                            if len(content) > MAX_FILE_SIZE:
                                print(f"Warning: File '{file_path}' is large ({len(content)} bytes), truncating for prompt.", file=sys.stderr)
                                content = content[:MAX_FILE_SIZE] + "\n... [TRUNCATED]"
                            changed_files_content[file_path] = content
        except GitCommandError as e: # Catch specific Git error
            print(f"Error: {str(e)}", file=sys.stderr)
            return 1
        except RuntimeError as e: # Catch other runtime errors during file reading/diff
            print(f"Error preparing Git data: {str(e)}", file=sys.stderr)
            return 1

        declined_messages = []
        while True:
            try:
                # Generate commit message - wrapped in try/except for specific errors
                commit_message = await generate_commit_message(
                    config,
                    args.backend,
                    git_diff,
                    changed_files_content,
                    declined_messages=declined_messages,
                    verbose=args.verbose > 0,
                    print_stack_trace=args.verbose > 1,
                    log_file=args.log_file,
                )

                # Confirmation logic remains the same, but error checks above are removed
                confirmation = confirm_commit(commit_message)

                if confirmation == "regenerate":
                    print("Regenerating commit message...")
                    declined_messages.append(commit_message)
                    continue
                elif confirmation == "edit":
                    # Basic editor support (could be enhanced)
                    editor = os.environ.get("EDITOR", "vim") # Fallback to vim
                    try:
                        # Write message to temp file
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".txt") as tf:
                            tf.write(commit_message)
                            temp_file_path = tf.name
                        
                        # Open editor
                        subprocess.run([editor, temp_file_path], check=True)
                        
                        # Read edited message
                        with open(temp_file_path, 'r') as tf:
                            edited_message = tf.read().strip()
                        
                        os.remove(temp_file_path) # Clean up temp file

                        if not edited_message:
                            print("Edit cancelled or message empty.", file=sys.stderr)
                            return 1
                        
                        print("\nUsing edited message:")
                        print("-" * 20)
                        print(edited_message)
                        print("-" * 20)
                        if input("Commit with this message? (y/N) ").strip().lower() == 'y':
                            return run_git_commit(edited_message)
                        else:
                            print("Commit cancelled.")
                            return 0

                    except Exception as edit_err:
                        print(f"Error during editing: {edit_err}", file=sys.stderr)
                        print("Falling back to original message confirmation.")
                        if input("Commit with the original suggested message? (y/N) ").strip().lower() == 'y':
                            return run_git_commit(commit_message)
                        else:
                            print("Commit cancelled.")
                            return 0
                elif confirmation:
                    return run_git_commit(commit_message)
                else:
                    print("Commit cancelled.")
                    return 0

            # Catch specific errors from generate_commit_message
            except ContextLengthExceededError as e:
                print(str(e), file=sys.stderr) # Error message already includes suggestion
                # Optionally add more context here if needed
                return 1 # Exit with error code
            except EmptyCommitMessageError as e:
                print(f"Error: {str(e)}", file=sys.stderr)
                print("Exiting due to empty message.", file=sys.stderr)
                return 1
            except NlgcError as e: # Catch other nlgc-related errors (includes API errors)
                print(f"Error: {str(e)}", file=sys.stderr)
                if args.verbose > 1: traceback.print_exc(file=sys.stderr)
                return 1
            except ValueError as e: # Catch config/backend validation errors if they slip through
                print(f"Configuration or Backend Error: {str(e)}", file=sys.stderr)
                if args.verbose > 1: traceback.print_exc(file=sys.stderr)
                return 1
            except Exception as e: # Catch unexpected errors during the loop
                print(f"An unexpected error occurred during commit generation: {str(e)}", file=sys.stderr)
                if args.verbose > 1: traceback.print_exc(file=sys.stderr)
                return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Fatal error: {str(e)}", file=sys.stderr)
        if getattr(args, 'verbose', 0) > 1: # Check if args exists before accessing
            traceback.print_exc(file=sys.stderr)
        return 1


def main() -> None:
    """Synchronous wrapper function for the nlgc entry point."""
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)
    exit_code = 1 # Default exit code
    try:
        # Parse args and load config here so errors happen before asyncio.run
        args = parse_args(sys.argv[1:])
        config = Config(args.config)
        
        # Pass config and args directly to the async function
        exit_code = asyncio.run(_async_main(config, args))

    except (ConfigValidationError, GitCommandError, NlgcError, ValueError) as e:
        # Catch known errors that might occur during config loading or async execution
        print(f"Error: {str(e)}", file=sys.stderr)
        # Check if verbose debugging is requested via args, even if config failed
        verbose_level = 0
        for _, arg in enumerate(sys.argv):
            if arg == '-v': verbose_level += 1
            if arg == '--verbose': verbose_level += 1
            if arg.startswith('-v') and not arg.startswith('--'):
                verbose_level += len(arg) -1 # handles -vv, -vvv etc.

        if verbose_level > 1:
            traceback.print_exc(file=sys.stderr)
        exit_code = 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        exit_code = 130
    except Exception as e:
        print(f"Fatal error: {str(e)}", file=sys.stderr)
        # Check verbose level again for unexpected errors
        verbose_level = 0
        for i, arg in enumerate(sys.argv):
            if arg == '-v': verbose_level += 1
            if arg == '--verbose': verbose_level += 1
            if arg.startswith('-v') and not arg.startswith('--'):
                verbose_level += len(arg) -1
        if verbose_level > 1:
            traceback.print_exc(file=sys.stderr)
        exit_code = 1
    finally:
        sys.exit(exit_code)


if __name__ == "__main__":
    # Call the synchronous wrapper when script is run directly
    main()
