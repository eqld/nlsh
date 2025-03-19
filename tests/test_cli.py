"""
Tests for the command-line interface module.
"""

import os
import sys
import asyncio
from unittest.mock import patch, MagicMock, call

import pytest

from nlsh.cli import parse_args, generate_command, confirm_execution, execute_command, main


class TestCLI:
    """Tests for the CLI module."""
    
    def test_parse_args_prompt(self):
        """Test parsing command-line arguments with a prompt."""
        # Parse arguments
        args = parse_args(["Find all text files"])
        
        # Check that the arguments are parsed correctly
        assert args.prompt == "Find all text files"
        assert not args.interactive
        assert args.backend is None
        assert args.config is None
        assert args.prompt_file is None
        assert not args.version
    
    def test_parse_args_backend(self):
        """Test parsing command-line arguments with a backend selection."""
        # Parse arguments
        args = parse_args(["-2", "Find all text files"])
        
        # Check that the arguments are parsed correctly
        assert args.prompt == "Find all text files"
        assert args.backend == 2
    
    def test_parse_args_interactive(self):
        """Test parsing command-line arguments with interactive mode."""
        # Parse arguments
        args = parse_args(["-i", "Find all text files"])
        
        # Check that the arguments are parsed correctly
        assert args.prompt == "Find all text files"
        assert args.interactive
    
    def test_parse_args_config(self):
        """Test parsing command-line arguments with a config file."""
        # Parse arguments
        args = parse_args(["--config", "custom_config.yml", "Find all text files"])
        
        # Check that the arguments are parsed correctly
        assert args.prompt == "Find all text files"
        assert args.config == "custom_config.yml"
    
    def test_parse_args_prompt_file(self):
        """Test parsing command-line arguments with a prompt file."""
        # Parse arguments
        args = parse_args(["--prompt-file", "prompt.txt"])
        
        # Check that the arguments are parsed correctly
        assert args.prompt is None
        assert args.prompt_file == "prompt.txt"
    
    def test_parse_args_version(self):
        """Test parsing command-line arguments with version flag."""
        # Parse arguments
        args = parse_args(["--version"])
        
        # Check that the arguments are parsed correctly
        assert args.version
    
    @pytest.mark.asyncio
    async def test_generate_command(self):
        """Test generating a command."""
        # Create mock objects
        config = MagicMock()
        backend = MagicMock()
        backend.generate_command.return_value = "ls -la"
        backend_manager = MagicMock()
        backend_manager.get_backend.return_value = backend
        tools = [MagicMock(), MagicMock()]
        prompt_builder = MagicMock()
        prompt_builder.build_system_prompt.return_value = "System prompt"
        prompt_builder.build_user_prompt.return_value = "User prompt"
        
        # Patch the necessary functions
        with patch('nlsh.tools.get_enabled_tools', return_value=tools), \
             patch('nlsh.prompt.PromptBuilder', return_value=prompt_builder), \
             patch('nlsh.backends.BackendManager', return_value=backend_manager):
            
            # Generate a command
            command = await generate_command(config, 1, "Find all text files")
            
            # Check that the command is generated correctly
            assert command == "ls -la"
            
            # Check that the functions were called correctly
            backend_manager.get_backend.assert_called_once_with(1)
            prompt_builder.build_system_prompt.assert_called_once_with(tools)
            prompt_builder.build_user_prompt.assert_called_once_with("Find all text files")
            backend.generate_command.assert_called_once_with("User prompt", "System prompt")
    
    def test_confirm_execution_yes(self):
        """Test confirming command execution with 'yes'."""
        # Mock the input function
        with patch('builtins.input', return_value="y"), \
             patch('builtins.print'):
            
            # Confirm execution
            result = confirm_execution("ls -la")
            
            # Check that the result is True
            assert result is True
    
    def test_confirm_execution_no(self):
        """Test confirming command execution with 'no'."""
        # Mock the input function
        with patch('builtins.input', return_value="n"), \
             patch('builtins.print'):
            
            # Confirm execution
            result = confirm_execution("ls -la")
            
            # Check that the result is False
            assert result is False
    
    def test_execute_command(self):
        """Test executing a command."""
        # Create a mock process
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["output1\n", "output2\n", ""]
        mock_process.stderr.readline.side_effect = ["error1\n", ""]
        mock_process.poll.side_effect = [None, None, 0]
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("", "")
        
        # Mock the subprocess.Popen function
        with patch('subprocess.Popen', return_value=mock_process), \
             patch('builtins.print'), \
             patch.dict(os.environ, {"SHELL": "/bin/bash"}):
            
            # Execute the command
            result = execute_command("ls -la")
            
            # Check that the result is the process return code
            assert result == 0
            
            # Check that the process was created correctly
            subprocess.Popen.assert_called_once()
            call_args = subprocess.Popen.call_args[0]
            assert call_args[0] == "ls -la"
            assert call_args[1] is True  # shell=True
            assert call_args[2] == "/bin/bash"  # executable
    
    def test_execute_command_error(self):
        """Test error handling when executing a command."""
        # Mock the subprocess.Popen function to raise an exception
        with patch('subprocess.Popen', side_effect=Exception("Command error")), \
             patch('builtins.print'):
            
            # Execute the command
            result = execute_command("ls -la")
            
            # Check that the result is an error code
            assert result == 1
    
    def test_main_version(self):
        """Test the main function with version flag."""
        # Mock the necessary functions
        with patch('nlsh.cli.parse_args') as mock_parse_args, \
             patch('builtins.print'), \
             patch('nlsh.__version__', "0.1.0"):
            
            # Set up the mock arguments
            mock_args = MagicMock()
            mock_args.version = True
            mock_parse_args.return_value = mock_args
            
            # Run the main function
            result = main()
            
            # Check that the result is 0 (success)
            assert result == 0
            
            # Check that the version was printed
            print.assert_called_once_with("nlsh version 0.1.0")
    
    def test_main_no_prompt(self):
        """Test the main function with no prompt."""
        # Mock the necessary functions
        with patch('nlsh.cli.parse_args') as mock_parse_args, \
             patch('builtins.print'):
            
            # Set up the mock arguments
            mock_args = MagicMock()
            mock_args.version = False
            mock_args.prompt = None
            mock_args.prompt_file = None
            mock_parse_args.return_value = mock_args
            
            # Run the main function
            result = main()
            
            # Check that the result is 1 (error)
            assert result == 1
            
            # Check that the error was printed
            print.assert_called_once_with("Error: No prompt provided")
    
    def test_main_generate_command(self):
        """Test the main function with a prompt."""
        # Mock the necessary functions
        with patch('nlsh.cli.parse_args') as mock_parse_args, \
             patch('nlsh.cli.Config') as mock_config_class, \
             patch('asyncio.run') as mock_asyncio_run, \
             patch('builtins.print'):
            
            # Set up the mock arguments
            mock_args = MagicMock()
            mock_args.version = False
            mock_args.prompt = "Find all text files"
            mock_args.prompt_file = None
            mock_args.interactive = False
            mock_args.backend = None
            mock_parse_args.return_value = mock_args
            
            # Set up the mock config
            mock_config = MagicMock()
            mock_config_class.return_value = mock_config
            
            # Set up the mock command
            mock_asyncio_run.return_value = "ls -la"
            
            # Run the main function
            result = main()
            
            # Check that the result is 0 (success)
            assert result == 0
            
            # Check that the command was generated and printed
            mock_asyncio_run.assert_called_once()
            print.assert_called_once_with("ls -la")
    
    def test_main_interactive_yes(self):
        """Test the main function in interactive mode with confirmation."""
        # Mock the necessary functions
        with patch('nlsh.cli.parse_args') as mock_parse_args, \
             patch('nlsh.cli.Config') as mock_config_class, \
             patch('asyncio.run') as mock_asyncio_run, \
             patch('nlsh.cli.confirm_execution', return_value=True), \
             patch('nlsh.cli.execute_command', return_value=0), \
             patch('builtins.print'):
            
            # Set up the mock arguments
            mock_args = MagicMock()
            mock_args.version = False
            mock_args.prompt = "Find all text files"
            mock_args.prompt_file = None
            mock_args.interactive = True
            mock_args.backend = None
            mock_parse_args.return_value = mock_args
            
            # Set up the mock config
            mock_config = MagicMock()
            mock_config_class.return_value = mock_config
            
            # Set up the mock command
            mock_asyncio_run.return_value = "ls -la"
            
            # Run the main function
            result = main()
            
            # Check that the result is 0 (success)
            assert result == 0
            
            # Check that the command was executed
            mock_asyncio_run.assert_called_once()
            confirm_execution.assert_called_once_with("ls -la")
            execute_command.assert_called_once_with("ls -la")
    
    def test_main_interactive_no(self):
        """Test the main function in interactive mode without confirmation."""
        # Mock the necessary functions
        with patch('nlsh.cli.parse_args') as mock_parse_args, \
             patch('nlsh.cli.Config') as mock_config_class, \
             patch('asyncio.run') as mock_asyncio_run, \
             patch('nlsh.cli.confirm_execution', return_value=False), \
             patch('builtins.print'):
            
            # Set up the mock arguments
            mock_args = MagicMock()
            mock_args.version = False
            mock_args.prompt = "Find all text files"
            mock_args.prompt_file = None
            mock_args.interactive = True
            mock_args.backend = None
            mock_parse_args.return_value = mock_args
            
            # Set up the mock config
            mock_config = MagicMock()
            mock_config_class.return_value = mock_config
            
            # Set up the mock command
            mock_asyncio_run.return_value = "ls -la"
            
            # Run the main function
            result = main()
            
            # Check that the result is 0 (success)
            assert result == 0
            
            # Check that the command was not executed
            mock_asyncio_run.assert_called_once()
            confirm_execution.assert_called_once_with("ls -la")
            assert not hasattr(execute_command, 'assert_called_once')
            print.assert_called_with("Command execution cancelled")
    
    def test_main_error(self):
        """Test error handling in the main function."""
        # Mock the necessary functions
        with patch('nlsh.cli.parse_args') as mock_parse_args, \
             patch('nlsh.cli.Config') as mock_config_class, \
             patch('asyncio.run', side_effect=Exception("Generation error")), \
             patch('builtins.print'):
            
            # Set up the mock arguments
            mock_args = MagicMock()
            mock_args.version = False
            mock_args.prompt = "Find all text files"
            mock_args.prompt_file = None
            mock_args.interactive = False
            mock_args.backend = None
            mock_parse_args.return_value = mock_args
            
            # Set up the mock config
            mock_config = MagicMock()
            mock_config_class.return_value = mock_config
            
            # Run the main function
            result = main()
            
            # Check that the result is 1 (error)
            assert result == 1
            
            # Check that the error was printed
            print.assert_called_once_with("Error: Generation error")
