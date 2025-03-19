"""
Tests for the main entry point module.
"""

import sys
from unittest.mock import patch

import pytest

import nlsh.main


def test_main_entry_point():
    """Test that the main entry point calls the CLI main function."""
    # Mock the CLI main function
    with patch('nlsh.cli.main', return_value=42) as mock_main:
        # Mock sys.exit to prevent the test from exiting
        with patch('sys.exit') as mock_exit:
            # Call the main entry point
            nlsh.main.main()
            
            # Check that the CLI main function was called
            mock_main.assert_called_once()
            
            # Check that sys.exit was called with the return value from main
            mock_exit.assert_called_once_with(42)


def test_main_module_execution():
    """Test that the main module calls main() when executed as __main__."""
    # Save the original __name__
    original_name = nlsh.main.__name__
    
    try:
        # Mock the main function
        with patch('nlsh.main.main') as mock_main:
            # Set __name__ to "__main__"
            nlsh.main.__name__ = "__main__"
            
            # Re-execute the module code
            exec(open(nlsh.main.__file__).read(), vars(nlsh.main))
            
            # Check that main was called
            mock_main.assert_called_once()
    finally:
        # Restore the original __name__
        nlsh.main.__name__ = original_name
