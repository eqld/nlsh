"""
Tests for the prompt engineering module.
"""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from nlsh.prompt import PromptBuilder
from nlsh.tools.base import BaseTool


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    def __init__(self, config, name="MockTool", context="Mock context"):
        super().__init__(config)
        self._name = name
        self._context = context
    
    def get_context(self):
        return self._context
    
    @property
    def name(self):
        return self._name


class TestPromptBuilder:
    """Tests for the PromptBuilder class."""
    
    def test_initialization(self):
        """Test that the prompt builder is initialized correctly."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "bash"
        
        # Create an instance of PromptBuilder
        builder = PromptBuilder(config)
        
        # Check that the builder properties are set correctly
        assert builder.shell == "bash"
    
    def test_build_system_prompt(self):
        """Test building a system prompt with context from tools."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "bash"
        
        # Create an instance of PromptBuilder
        builder = PromptBuilder(config)
        
        # Create some mock tools
        tools = [
            MockTool(config, "Tool1", "Context from tool 1"),
            MockTool(config, "Tool2", "Context from tool 2"),
            MockTool(config, "Tool3", "Context from tool 3")
        ]
        
        # Build the system prompt
        prompt = builder.build_system_prompt(tools)
        
        # Check that the prompt contains the expected information
        assert "bash" in prompt
        assert "--- Tool1 ---" in prompt
        assert "Context from tool 1" in prompt
        assert "--- Tool2 ---" in prompt
        assert "Context from tool 2" in prompt
        assert "--- Tool3 ---" in prompt
        assert "Context from tool 3" in prompt
    
    def test_build_system_prompt_with_error(self):
        """Test building a system prompt when a tool raises an error."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "bash"
        
        # Create an instance of PromptBuilder
        builder = PromptBuilder(config)
        
        # Create some mock tools, one of which raises an error
        error_tool = MagicMock()
        error_tool.name = "ErrorTool"
        error_tool.get_context.side_effect = Exception("Tool error")
        
        tools = [
            MockTool(config, "Tool1", "Context from tool 1"),
            error_tool,
            MockTool(config, "Tool3", "Context from tool 3")
        ]
        
        # Build the system prompt
        prompt = builder.build_system_prompt(tools)
        
        # Check that the prompt contains the expected information
        assert "bash" in prompt
        assert "--- Tool1 ---" in prompt
        assert "Context from tool 1" in prompt
        assert "Error getting context from ErrorTool" in prompt
        assert "Tool error" in prompt
        assert "--- Tool3 ---" in prompt
        assert "Context from tool 3" in prompt
    
    def test_build_user_prompt(self):
        """Test building a user prompt."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "bash"
        
        # Create an instance of PromptBuilder
        builder = PromptBuilder(config)
        
        # Build the user prompt
        user_input = "List all files in the current directory"
        prompt = builder.build_user_prompt(user_input)
        
        # Check that the prompt is the same as the user input
        assert prompt == user_input
    
    def test_load_prompt_from_file(self):
        """Test loading a prompt from a file."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "bash"
        
        # Create an instance of PromptBuilder
        builder = PromptBuilder(config)
        
        # Create a temporary file with a prompt
        prompt_content = "This is a test prompt from a file."
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp:
            temp.write(prompt_content)
        
        try:
            # Load the prompt from the file
            prompt = builder.load_prompt_from_file(temp.name)
            
            # Check that the prompt is loaded correctly
            assert prompt == prompt_content
        finally:
            # Clean up the temporary file
            os.unlink(temp.name)
    
    def test_load_prompt_from_file_error(self):
        """Test error handling when loading a prompt from a non-existent file."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "bash"
        
        # Create an instance of PromptBuilder
        builder = PromptBuilder(config)
        
        # Try to load a prompt from a non-existent file
        prompt = builder.load_prompt_from_file("non_existent_file.txt")
        
        # Check that the error is handled
        assert "Error loading prompt file" in prompt
