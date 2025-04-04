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
import locale
import os
import signal
import subprocess
import sys
import traceback
from typing import Any, List, Optional, Union, TextIO, Dict

import openai  # For catching potential API errors like context length

from nlsh.config import Config, ConfigValidationError
from nlsh.backends import BackendManager
from nlsh.spinner import Spinner
from nlsh.cli import handle_keyboard_interrupt, safe_write # Reuse existing handlers


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
        raise RuntimeError("Git command not found. Make sure Git is installed and in your PATH.")
    except subprocess.CalledProcessError as e:
        error_message = f"Git command failed: {e.stderr}"
        if "not a git repository" in e.stderr.lower():
            error_message = "Not a git repository (or any of the parent directories)."
        raise RuntimeError(error_message)
    except Exception as e:
        raise RuntimeError(f"Failed to get git diff: {str(e)}")


def get_changed_files(staged: bool = True) -> List[str]:
    """Get the list of changed files.
    
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
    except Exception as e:
        raise RuntimeError(f"Failed to get changed file list: {str(e)}")


def read_file_content(file_path: str) -> Optional[str]:
    """Read the content of a file, handling potential errors."""
    try:
        # Ensure the path is relative to the git top-level directory if needed
        # For simplicity, assuming paths from git diff --name-only are correct relative to CWD
        # If running from a subdirectory, might need `git rev-parse --show-toplevel`
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Warning: Changed file not found: {file_path}", file=sys.stderr)
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
    log_file: Optional[str] = None
) -> str:
    """Generate a commit message using the specified backend."""
    
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

        return response_content if response_content else "Error: No commit message generated"

    except openai.BadRequestError as e:
        # Check if the error is likely due to context length
        if "context_length_exceeded" in str(e) or "too large" in str(e):
             error_msg = (
                "Error: The diff and file contents combined are too large for the selected model's context window.\n"
                "Try running again with the '--no-full-files' flag."
            )
             print(error_msg, file=sys.stderr)
             # Return a specific error string or raise a custom exception
             return "Error: Context length exceeded" 
        else:
            print(f"Error generating commit message: {str(e)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise
    except Exception as e:
        print(f"Error generating commit message: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise
    finally:
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
        return "edit" # We'll handle editing later if needed
    
    return response in ["y", "yes"]


def run_git_commit(message: str) -> int:
    """Run the git commit command."""
    try:
        # Using -m avoids needing an editor for simple cases
        result = subprocess.run(['git', 'commit', '-m', message], check=True, encoding='utf-8')
        print("Commit successful.")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Git commit failed:\n{e.stderr}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error running git commit: {str(e)}", file=sys.stderr)
        return 1


async def main() -> int: # Make main async
    """Main entry point for nlgc."""
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)
    
    try:
        args = parse_args(sys.argv[1:])
        
        try:
            config = Config(args.config)
        except ConfigValidationError as e:
            print(f"Configuration error: {str(e)}", file=sys.stderr)
            if args.verbose > 1: traceback.print_exc(file=sys.stderr)
            return 1
        except Exception as e: # Catch other potential config loading errors
             print(f"Error loading configuration: {str(e)}", file=sys.stderr)
             if args.verbose > 1: traceback.print_exc(file=sys.stderr)
             return 1

        # Determine whether to include full files
        nlgc_config = config.get_nlgc_config()
        include_full_files = nlgc_config.get("include_full_files", True) # Default to True if missing
        if args.full_files is not None: # CLI flag overrides config
            include_full_files = args.full_files

        # Get git diff and file contents
        try:
            git_diff = get_git_diff(staged=True) # Currently only supports staged
            
            changed_files_content = None
            if include_full_files:
                changed_files = get_changed_files(staged=not args.all)
                if changed_files:
                    print(f"Reading content of {len(changed_files)} changed file(s)...")
                    changed_files_content = {}
                    for file_path in changed_files:
                        content = read_file_content(file_path)
                        if content is not None:
                             # Limit file size to avoid excessively large prompts (e.g., 100KB)
                             MAX_FILE_SIZE = 100 * 1024 
                             if len(content) > MAX_FILE_SIZE:
                                 print(f"Warning: File '{file_path}' is large ({len(content)} bytes), truncating for prompt.", file=sys.stderr)
                                 content = content[:MAX_FILE_SIZE] + "\n... [TRUNCATED]"
                             changed_files_content[file_path] = content
        except RuntimeError as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            return 1

        declined_messages = []
        while True:
            try:
                commit_message = await generate_commit_message(
                    config,
                    args.backend,
                    git_diff,
                    changed_files_content,
                    declined_messages=declined_messages,
                    verbose=args.verbose > 0,
                    log_file=args.log_file,
                )

                if commit_message == "Error: Context length exceeded":
                     # Specific error handled in generate_commit_message, exit gracefully
                     return 1
                if commit_message.startswith("Error:"):
                    print(commit_message, file=sys.stderr)
                    return 1

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

            except ValueError as e: # Catch config/backend errors
                print(f"Error: {str(e)}", file=sys.stderr)
                if args.verbose > 1: traceback.print_exc(file=sys.stderr)
                return 1
            except Exception as e:
                print(f"An unexpected error occurred: {str(e)}", file=sys.stderr)
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


if __name__ == "__main__":
    # Run the async main function
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully if it happens before signal handler is set in main
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        # Catch any other unexpected errors during startup/asyncio run
        print(f"Fatal error during execution: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
