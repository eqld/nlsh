"""
LLM backend handling for nlsh.

This module provides functionality for interacting with different LLM backends.
"""

import os
import json
from typing import Dict, List, Optional, Any

import openai


class LLMBackend:
    """Base class for LLM backends."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the backend.
        
        Args:
            config: Backend configuration.
        """
        self.config = config
        self.name = config.get("name", "unknown")
        self.url = config.get("url", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")
        
        # Configure OpenAI client
        self.client = openai.OpenAI(
            base_url=self.url,
            api_key=self.api_key
        )
    
    async def generate_command(self, prompt: str, system_context: str) -> str:
        """Generate a shell command based on the prompt and context.
        
        Args:
            prompt: User prompt.
            system_context: System context information.
            
        Returns:
            str: Generated shell command.
        """
        try:
            # Create messages for the chat completion
            messages = [
                {"role": "system", "content": system_context},
                {"role": "user", "content": prompt}
            ]
            
            # Call the API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,  # Lower temperature for more deterministic outputs
                max_tokens=500,   # Limit response length
                n=1,              # Generate a single response
            )
            
            # Extract the generated command
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content.strip()
            else:
                return "Error: No response generated"
                
        except Exception as e:
            return f"Error generating command: {str(e)}"


class BackendManager:
    """Manager for LLM backends."""
    
    def __init__(self, config):
        """Initialize the backend manager.
        
        Args:
            config: Configuration object.
        """
        self.config = config
        self.backends = {}
    
    def get_backend(self, index: Optional[int] = None) -> LLMBackend:
        """Get a backend instance.
        
        Args:
            index: Optional backend index. If not provided, uses default_backend.
            
        Returns:
            LLMBackend: Backend instance.
        """
        # Get backend configuration
        backend_config = self.config.get_backend(index)
        if not backend_config:
            raise ValueError("No backend configuration available")
            
        # Check if we already have an instance for this backend
        backend_key = f"{backend_config['name']}_{index}"
        if backend_key not in self.backends:
            # Create a new backend instance
            self.backends[backend_key] = LLMBackend(backend_config)
            
        return self.backends[backend_key]
