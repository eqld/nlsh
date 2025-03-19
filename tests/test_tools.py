"""
Tests for the system tools.
"""

import os
import platform
from unittest.mock import patch, MagicMock

import pytest

from nlsh.config import Config
from nlsh.tools.base import BaseTool
from nlsh.tools.system import SystemInfo
from nlsh.tools.directory import DirLister


class TestBaseTool:
    """Tests for the BaseTool base class."""
    
    def test_name_property(self):
        """Test that the name property returns the class name."""
        # Create a mock config
        config = MagicMock()
        
        # Create a concrete subclass of BaseTool for testing
        class TestTool(BaseTool):
            def get_context(self):
                return "Test context"
        
        # Create an instance of the test tool
        tool = TestTool(config)
        
        # Check that the name property returns the class name
        assert tool.name == "TestTool"


class TestSystemInfo:
    """Tests for the SystemInfo tool."""
    
    def test_get_context(self):
        """Test that get_context returns system information."""
        # Create a mock config
        config = MagicMock()
        
        # Create an instance of SystemInfo
        tool = SystemInfo(config)
        
        # Get the context
        context = tool.get_context()
        
        # Check that the context contains expected information
        assert isinstance(context, str)
        assert "OS:" in context
        assert platform.system() in context
        assert "Architecture:" in context


class TestDirLister:
    """Tests for the DirLister tool."""
    
    def test_get_context(self):
        """Test that get_context returns directory information."""
        # Create a mock config
        config = MagicMock()
        
        # Create an instance of DirLister
        tool = DirLister(config)
        
        # Create a temporary directory with some files for testing
        with patch('os.getcwd') as mock_getcwd, \
             patch('os.scandir') as mock_scandir:
            
            # Mock the current directory
            mock_getcwd.return_value = "/test/dir"
            
            # Create mock file entries
            mock_entries = []
            
            # Regular file
            file_entry = MagicMock()
            file_entry.name = "test.txt"
            file_entry.is_dir.return_value = False
            file_entry.is_file.return_value = True
            file_entry.stat.return_value.st_size = 1024
            file_entry.stat.return_value.st_mtime = 1600000000
            mock_entries.append(file_entry)
            
            # Directory
            dir_entry = MagicMock()
            dir_entry.name = "test_dir"
            dir_entry.is_dir.return_value = True
            dir_entry.is_file.return_value = False
            dir_entry.stat.return_value.st_size = 4096
            dir_entry.stat.return_value.st_mtime = 1600000000
            mock_entries.append(dir_entry)
            
            # Set up the mock scandir to return our mock entries
            mock_scandir.return_value = mock_entries
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert "Current directory: /test/dir" in context
            assert "test.txt" in context
            assert "test_dir" in context
            assert "Directory" in context
