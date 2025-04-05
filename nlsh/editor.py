"""
Editor interaction utility for nlsh and nlgc.
"""

import os
import subprocess
import sys
import tempfile
from typing import Optional

def edit_text_in_editor(initial_text: str, suffix: str = ".txt") -> Optional[str]:
    """Opens the default editor to edit the given text.

    Args:
        initial_text: The text to be edited.
        suffix: The file suffix to use for the temporary file (e.g., ".sh", ".txt").

    Returns:
        The edited text as a string if the user saves changes, 
        or None if the edit is cancelled, the resulting text is empty,
        or an error occurs during editing.
    """
    editor = os.environ.get("EDITOR", "vim")  # Fallback to vim

    try:
        # Write text to a temporary file
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=suffix) as tf:
            tf.write(initial_text)
            temp_file_path = tf.name
        
        # Open the editor
        try:
            subprocess.run([editor, temp_file_path], check=True)
        except FileNotFoundError:
             print(f"Error: Editor '{editor}' not found. Please set the EDITOR environment variable.", file=sys.stderr)
             return None
        except subprocess.CalledProcessError as e:
            print(f"Error: Editor '{editor}' exited with error code {e.returncode}.", file=sys.stderr)
            return None

        # Read the edited text back
        with open(temp_file_path, 'r') as tf:
            edited_text = tf.read().strip()

        if not edited_text:
            print("Edit cancelled or resulting text is empty.", file=sys.stderr)
            return None
        
        return edited_text

    except Exception as e:
        print(f"An error occurred during the editing process: {e}", file=sys.stderr)
        return None
    finally:
        # Attempt cleanup if temp_file_path was created
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as cleanup_err:
                print(f"Error cleaning up temporary file: {cleanup_err}", file=sys.stderr)
