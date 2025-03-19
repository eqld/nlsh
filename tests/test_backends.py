"""
Tests for the LLM backends module.
"""

import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from nlsh.config import Config
from nlsh.backends import LLMBackend, BackendManager


class TestLLMBackend:
    """Tests for the LLMBackend class."""
    
    def test_initialization(self):
        """Test that the backend is initialized correctly."""
        # Create a mock config
        backend_config = {
            "name": "test-backend",
            "url": "https://api.test.com/v1",
            "api_key": "test-api-key",
            "model": "test-model"
        }
        
        with patch('openai.OpenAI'):
            # Create an instance of LLMBackend
            backend = LLMBackend(backend_config)
            
            # Check that the backend properties are set correctly
            assert backend.name == "test-backend"
            assert backend.url == "https://api.test.com/v1"
            assert backend.api_key == "test-api-key"
            assert backend.model == "test-model"
    
    @pytest.mark.asyncio
    async def test_generate_command(self):
        """Test that generate_command returns the expected command."""
        # Create a mock config
        backend_config = {
            "name": "test-backend",
            "url": "https://api.test.com/v1",
            "api_key": "test-api-key",
            "model": "test-model"
        }
        
        # Create a mock response using MagicMock
        mock_message = MagicMock()
        mock_message.content = "ls -la"
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        # Create a mock OpenAI client
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        
        with patch('openai.OpenAI', return_value=mock_client):
            # Create an instance of LLMBackend
            backend = LLMBackend(backend_config)
            
            # Generate a command
            prompt = "List all files in the current directory"
            system_context = "You are a helpful assistant."
            command = await backend.generate_command(prompt, system_context)
            
            # Check that the command is correct
            assert command == "ls -la"
            
            # Check that the client was called with the correct arguments
            mock_client.chat.completions.create.assert_called_once()
            call_args = mock_client.chat.completions.create.call_args[1]
            assert call_args["model"] == "test-model"
            assert len(call_args["messages"]) == 2
            assert call_args["messages"][0]["role"] == "system"
            assert call_args["messages"][0]["content"] == system_context
            assert call_args["messages"][1]["role"] == "user"
            assert call_args["messages"][1]["content"] == prompt
    
    @pytest.mark.asyncio
    async def test_generate_command_error(self):
        """Test error handling in generate_command."""
        # Create a mock config
        backend_config = {
            "name": "test-backend",
            "url": "https://api.test.com/v1",
            "api_key": "test-api-key",
            "model": "test-model"
        }
        
        # Create a mock OpenAI client that raises an exception
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        
        with patch('openai.OpenAI', return_value=mock_client):
            # Create an instance of LLMBackend
            backend = LLMBackend(backend_config)
            
            # Generate a command
            prompt = "List all files in the current directory"
            system_context = "You are a helpful assistant."
            command = await backend.generate_command(prompt, system_context)
            
            # Check that the error is handled
            assert "Error generating command" in command
            assert "API error" in command


class TestBackendManager:
    """Tests for the BackendManager class."""
    
    def test_get_backend_default(self):
        """Test getting the default backend."""
        # Create a mock config
        config = MagicMock()
        config.get_backend.return_value = {
            "name": "default-backend",
            "url": "https://api.default.com/v1",
            "api_key": "default-api-key",
            "model": "default-model"
        }
        
        with patch('nlsh.backends.LLMBackend') as mock_backend_class:
            # Create an instance of BackendManager
            manager = BackendManager(config)
            
            # Get the default backend
            backend = manager.get_backend()
            
            # Check that the config was called correctly
            config.get_backend.assert_called_once_with(None)
            
            # Check that the backend was created correctly
            mock_backend_class.assert_called_once()
    
    def test_get_backend_specific(self):
        """Test getting a specific backend."""
        # Create a mock config
        config = MagicMock()
        config.get_backend.return_value = {
            "name": "specific-backend",
            "url": "https://api.specific.com/v1",
            "api_key": "specific-api-key",
            "model": "specific-model"
        }
        
        with patch('nlsh.backends.LLMBackend') as mock_backend_class:
            # Create an instance of BackendManager
            manager = BackendManager(config)
            
            # Get a specific backend
            backend = manager.get_backend(1)
            
            # Check that the config was called correctly
            config.get_backend.assert_called_once_with(1)
            
            # Check that the backend was created correctly
            mock_backend_class.assert_called_once()
    
    def test_get_backend_caching(self):
        """Test that backends are cached."""
        # Create a mock config
        config = MagicMock()
        config.get_backend.return_value = {
            "name": "cached-backend",
            "url": "https://api.cached.com/v1",
            "api_key": "cached-api-key",
            "model": "cached-model"
        }
        
        with patch('nlsh.backends.LLMBackend') as mock_backend_class:
            # Create an instance of BackendManager
            manager = BackendManager(config)
            
            # Get the same backend twice
            backend1 = manager.get_backend(1)
            backend2 = manager.get_backend(1)
            
            # Check that the backend was only created once
            assert mock_backend_class.call_count == 1
    
    def test_get_backend_error(self):
        """Test error handling when no backend configuration is available."""
        # Create a mock config
        config = MagicMock()
        config.get_backend.return_value = None
        
        # Create an instance of BackendManager
        manager = BackendManager(config)
        
        # Try to get a backend
        with pytest.raises(ValueError, match="No backend configuration available"):
            manager.get_backend()
