#!/usr/bin/env python3
"""
Neural Language Tokenizer (nlt) - Token counting utility.

This module provides the command-line interface for the nlt utility,
which counts tokens in text and image inputs using tiktoken.
"""

import argparse
import os
import sys
import traceback
from typing import List, Optional, Tuple
from PIL import Image
import io

try:
    import tiktoken
except ImportError:
    print("Error: tiktoken library is required. Install with: pip install tiktoken", file=sys.stderr)
    sys.exit(1)

from nlsh.image_utils import detect_input_type, is_image_type, validate_image_size


def parse_args(args: List[str]) -> argparse.Namespace:
    """Parse command-line arguments for nlt."""
    parser = argparse.ArgumentParser(
        description="Neural Language Tokenizer (nlt) - Count tokens in text and image inputs"
    )
    
    # File inputs
    parser.add_argument(
        "-f", "--file",
        action="append",
        dest="files",
        help="Input file(s) to count tokens from (can be specified multiple times)"
    )
    
    # Encoding selection
    parser.add_argument(
        "--encoding",
        default="cl100k_base",
        help="Tokenizer encoding to use (default: cl100k_base)"
    )
    
    # Verbose mode
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show breakdown by input source"
    )
    
    return parser.parse_args(args)


def _check_stdin_input() -> Optional[bytes]:
    """Check if there's input from STDIN and read it.
    
    Returns:
        bytes: STDIN content if available, None otherwise.
    """
    if not sys.stdin.isatty():
        try:
            # Read binary data from stdin
            stdin_data = sys.stdin.buffer.read()
            return stdin_data if stdin_data else None
        except Exception as e:
            print(f"Error reading from STDIN: {e}", file=sys.stderr)
            return None
    return None


def count_text_tokens(text: str, encoding_name: str) -> int:
    """Count tokens in text using tiktoken.
    
    Args:
        text: Text content to tokenize.
        encoding_name: Name of the tiktoken encoding to use.
        
    Returns:
        int: Number of tokens.
        
    Raises:
        ValueError: If encoding is not supported.
    """
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        raise ValueError(f"Error with encoding '{encoding_name}': {str(e)}")


def count_image_tokens(image_data: bytes) -> int:
    """Count tokens for an image using standard vision model formula.
    
    Args:
        image_data: Raw image data.
        
    Returns:
        int: Estimated number of tokens.
        
    Raises:
        ValueError: If image cannot be processed.
    """
    try:
        # Open image to get dimensions
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        
        # Standard vision model token calculation
        # Base tokens + image patches (14x14 patches)
        base_tokens = 85
        patch_size = 14
        
        # Calculate number of patches
        width_patches = (width + patch_size - 1) // patch_size  # Ceiling division
        height_patches = (height + patch_size - 1) // patch_size
        
        # Each patch contributes tokens
        patch_tokens = width_patches * height_patches
        
        total_tokens = base_tokens + patch_tokens
        return total_tokens
        
    except Exception as e:
        raise ValueError(f"Error processing image: {str(e)}")


def process_file(file_path: str, encoding_name: str) -> Tuple[int, str]:
    """Process a single file and count its tokens.
    
    Args:
        file_path: Path to the file.
        encoding_name: Tokenizer encoding name.
        
    Returns:
        tuple: (token_count, file_type) where file_type is 'text' or 'image'.
        
    Raises:
        Exception: If file cannot be processed.
    """
    try:
        # Read file as binary to detect type
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        if not file_data:
            return 0, 'text'  # Empty file
        
        # Detect file type
        mime_type = detect_input_type(file_data)
        
        if is_image_type(mime_type):
            # Process as image
            token_count = count_image_tokens(file_data)
            return token_count, 'image'
        else:
            # Process as text
            try:
                text_content = file_data.decode('utf-8', errors='replace')
                token_count = count_text_tokens(text_content, encoding_name)
                return token_count, 'text'
            except Exception as e:
                raise ValueError(f"Error processing text file: {str(e)}")
                
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except Exception as e:
        raise Exception(f"Error processing file '{file_path}': {str(e)}")


def process_stdin(stdin_data: bytes, encoding_name: str) -> Tuple[int, str]:
    """Process STDIN data and count its tokens.
    
    Args:
        stdin_data: Raw data from STDIN.
        encoding_name: Tokenizer encoding name.
        
    Returns:
        tuple: (token_count, data_type) where data_type is 'text' or 'image'.
        
    Raises:
        Exception: If data cannot be processed.
    """
    if not stdin_data:
        return 0, 'text'
    
    # Detect input type
    mime_type = detect_input_type(stdin_data)
    
    if is_image_type(mime_type):
        # Process as image
        token_count = count_image_tokens(stdin_data)
        return token_count, 'image'
    else:
        # Process as text
        try:
            text_content = stdin_data.decode('utf-8', errors='replace')
            token_count = count_text_tokens(text_content, encoding_name)
            return token_count, 'text'
        except Exception as e:
            raise ValueError(f"Error processing STDIN text: {str(e)}")


def main() -> int:
    """Main entry point for nlt.
    
    Returns:
        int: Exit code.
    """
    try:
        # Parse arguments
        args = parse_args(sys.argv[1:])
        
        # Check for input sources
        stdin_data = _check_stdin_input()
        files = args.files or []
        
        if not stdin_data and not files:
            print("Error: No input provided. Use STDIN or specify files with -f", file=sys.stderr)
            return 1
        
        # Validate encoding
        try:
            tiktoken.get_encoding(args.encoding)
        except Exception as e:
            print(f"Error: Invalid encoding '{args.encoding}': {str(e)}", file=sys.stderr)
            return 1
        
        total_tokens = 0
        results = []
        
        # Process STDIN if available
        if stdin_data:
            try:
                tokens, data_type = process_stdin(stdin_data, args.encoding)
                total_tokens += tokens
                if args.verbose:
                    results.append(("STDIN", tokens, data_type))
            except Exception as e:
                print(f"Error processing STDIN: {str(e)}", file=sys.stderr)
                return 1
        
        # Process files
        for file_path in files:
            try:
                tokens, file_type = process_file(file_path, args.encoding)
                total_tokens += tokens
                if args.verbose:
                    results.append((file_path, tokens, file_type))
            except Exception as e:
                print(f"Error processing file '{file_path}': {str(e)}", file=sys.stderr)
                # Continue processing other files
                continue
        
        # Output results
        if args.verbose and results:
            for source, tokens, data_type in results:
                print(f"{source}: {tokens}")
            print(f"Total: {total_tokens}")
        else:
            print(total_tokens)
        
        return 0
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
