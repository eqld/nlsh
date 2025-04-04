"""
LLM backend handling for nlsh.

This module provides functionality for interacting with different LLM backends.
"""

import sys
import re
import traceback
from typing import Dict, Optional, Any

import openai


def strip_markdown_code_blocks(text: str) -> str:
    """Strip Markdown code blocks from text.
    
    This function removes Markdown code block formatting from the text.
    It handles three types of code blocks:
    1. Multiline code blocks with language info: ```language\ncode\n```
    2. Multiline code blocks without language info: ```\ncode\n```
    3. Single line code blocks: `code`
    
    Args:
        text: Text that may contain Markdown code blocks.
        
    Returns:
        str: Text with code blocks stripped of their Markdown formatting.
    """
    # Handle multiline code blocks with or without language info
    # Pattern: ```[language]\ncode\n```
    pattern = r"```(?:[a-zA-Z0-9_+-]+)?\n?(.*?)\n?```"
    result = re.sub(pattern, r"\1", text, flags=re.DOTALL)
    
    # Handle the case where the entire response is enclosed in single backticks
    # Pattern: `code`
    stripped_result = result.strip()
    if stripped_result.startswith("`") and stripped_result.endswith("`"):
        result = stripped_result[1:-1]
    
    return result.strip()


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
        self.is_reasoning_model = config.get("is_reasoning_model", False)
        self.timeout = float(config.get("timeout", 120.0))
        
        # Auto-detect reasoning models by name if not explicitly set
        if not self.is_reasoning_model and "reason" in self.name.lower():
            self.is_reasoning_model = True
        
        # Handle API key for different types of backends
        api_key = self.api_key
        
        # Enhanced local backend detection
        is_local = (
            "localhost" in self.url or
            "127.0.0.1" in self.url or
            "::1" in self.url or
            self.url.startswith("unix://")
        )
        
        # For local models, increase timeout
        if is_local:
            self.timeout = float(config.get("timeout", 300.0))  # 5 minutes for local models
        
        # Check if this is a dummy key for local models
        is_dummy_key = api_key and (api_key.startswith("dummy") or api_key == "ollama")
        
        # Validate API key for non-local endpoints
        if not is_local and not is_dummy_key:
            if not self.api_key or len(self.api_key.strip()) < 8:
                raise ValueError(f"Invalid API key configuration for backend {self.name}")
        
        # Configure OpenAI client
        try:
            if is_local:
                # For local endpoints, don't send any auth headers
                self.client = openai.OpenAI(
                    base_url=self.url,
                    api_key="dummy-key",
                    timeout=self.timeout,
                    default_headers={
                        "Content-Type": "application/json"
                    }
                )
                
                # Ensure both sync and async clients have no auth headers
                for client_attr in ['_client', '_async_client']:
                    if hasattr(self.client, client_attr):
                        client = getattr(self.client, client_attr)
                        if hasattr(client, 'headers'):
                            client.headers.clear()
                            client.headers["Content-Type"] = "application/json"
            else:
                self.client = openai.OpenAI(
                    base_url=self.url,
                    api_key=self.api_key,
                    timeout=self.timeout
                )
                # Test the connection with a minimal request
                if not is_dummy_key:
                    self.client.models.list()
        except openai.AuthenticationError as e:
            raise ValueError(f"Authentication failed for backend {self.name}: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to initialize backend {self.name}: {str(e)}")

    async def generate_command(self, prompt: str, system_context: str, verbose: bool = False) -> str:
        """Generate a shell command based on the prompt and context.
        
        Args:
            prompt: User prompt.
            system_context: System context information.
            verbose: Whether to print reasoning tokens to stderr.
            
        Returns:
            str: Generated shell command.
        """
        try:
            # Create messages for the chat completion
            messages = [
                {"role": "system", "content": system_context},
                {"role": "user", "content": prompt}
            ]
            
            if verbose:
                # Use streaming mode to show reasoning tokens
                full_response = ""
                sys.stderr.write("Reasoning: ")
                
                # Call the API with streaming
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.2,  # Lower temperature for more deterministic outputs
                    max_tokens=500,   # Limit response length
                    n=1,              # Generate a single response
                    stream=True       # Enable streaming
                )
                
                # Process the stream
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        
                        # Check for reasoning content (for reasoning models)
                        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                            sys.stderr.write(delta.reasoning_content)
                            sys.stderr.flush()
                            # Don't add reasoning content to the final response
                        
                        # Check for regular content
                        if hasattr(delta, 'content') and delta.content:
                            # For non-reasoning models or final output
                            if not self.is_reasoning_model:
                                sys.stderr.write(delta.content)
                                sys.stderr.flush()
                            full_response += delta.content
                
                sys.stderr.write("\n")
                
                # Strip markdown code blocks
                stripped_response = strip_markdown_code_blocks(full_response.strip())
                
                return stripped_response
            else:
                # Call the API without streaming
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.2,  # Lower temperature for more deterministic outputs
                    max_tokens=500,   # Limit response length
                    n=1               # Generate a single response
                )
                
                # Extract the generated command and strip any Markdown code blocks
                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content.strip()
                    
                    # Strip markdown code blocks
                    stripped_content = strip_markdown_code_blocks(content)
                    
                    return stripped_content
                else:
                    return "Error: No response generated"
                
        except openai.AuthenticationError as e:
            error_msg = str(e)
            if "api key" in error_msg.lower():
                raise ValueError(
                    f"Authentication failed for backend {self.name}. Please check your API key configuration."
                )
            raise ValueError(f"Authentication failed for backend {self.name}: {error_msg}")
        except Exception as e:
            print(f"Error generating command: {str(e)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise

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
