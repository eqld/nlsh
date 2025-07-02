"""
LLM backend handling for nlsh.

This module provides functionality for interacting with different LLM backends.
"""

import sys
import re
import traceback
from typing import Dict, List, Optional, Any, Union

import openai
from nlsh.image_utils import prepare_image_for_api, is_image_type


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

    async def _generate_streaming_response(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float, 
        max_tokens: int,
        strip_markdown: bool
    ) -> str:
        """Generate a response using streaming mode.
        
        Args:
            messages: List of message dictionaries.
            temperature: Temperature for generation.
            max_tokens: Maximum tokens to generate.
            strip_markdown: Whether to strip markdown code blocks.
            
        Returns:
            str: Generated response.
        """
        full_response = ""
        sys.stderr.write("Reasoning: ")
        
        # Call the API with streaming
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            n=1,
            stream=True
        )
        
        # Process the stream
        for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                
                # Handle reasoning content
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    sys.stderr.write(delta.reasoning_content)
                    sys.stderr.flush()
                
                # Handle regular content
                if hasattr(delta, 'content') and delta.content:
                    if not self.is_reasoning_model:
                        sys.stderr.write(delta.content)
                        sys.stderr.flush()
                    full_response += delta.content
        
        sys.stderr.write("\n")
        
        # Process the response
        response_text = full_response.strip()
        if strip_markdown:
            response_text = strip_markdown_code_blocks(response_text)
        
        return response_text
    
    async def _generate_non_streaming_response(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float, 
        max_tokens: int,
        strip_markdown: bool
    ) -> str:
        """Generate a response without streaming.
        
        Args:
            messages: List of message dictionaries.
            temperature: Temperature for generation.
            max_tokens: Maximum tokens to generate.
            strip_markdown: Whether to strip markdown code blocks.
            
        Returns:
            str: Generated response.
        """
        # Call the API without streaming
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            n=1
        )
        
        # Extract and process the content
        if response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content.strip()
            
            if strip_markdown:
                return strip_markdown_code_blocks(content)

            return content
        
        return "Error: No response generated"
    
    async def generate_response(
        self,
        prompt: str,
        system_context: str,
        verbose: bool = False,
        strip_markdown: bool = True,
        max_tokens: int = 500,
        regeneration_count: int = 0,
        image_data: Optional[bytes] = None,
        image_mime_type: Optional[str] = None
    ) -> str:
        """Generate a response from the LLM based on the prompt and context.
        
        Args:
            prompt: User prompt.
            system_context: System context information.
            verbose: Whether to print reasoning tokens to stderr.
            strip_markdown: Whether to strip markdown code blocks from the response.
            max_tokens: Maximum tokens to generate.
            regeneration_count: Number of times the response has been regenerated.
            image_data: Optional image data for vision models.
            image_mime_type: MIME type of the image data.
            
        Returns:
            str: Generated response.
        """
        try:
            # Create messages for the chat completion
            messages = [
                {"role": "system", "content": system_context}
            ]
            
            # Handle image input for vision models
            if image_data and image_mime_type:
                if not self.supports_vision():
                    raise ValueError(f"Backend {self.name} does not support vision/image processing")
                
                # Prepare image for API
                base64_image, mime_type = prepare_image_for_api(image_data, image_mime_type)
                
                # Create user message with image
                user_message = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            else:
                # Text-only message
                user_message = {"role": "user", "content": prompt}
            
            messages.append(user_message)
            
            # Calculate temperature based on regeneration count
            temperature = self._calculate_temperature(regeneration_count)
            
            # Generate response with or without streaming
            if verbose:
                return await self._generate_streaming_response(
                    messages, temperature, max_tokens, strip_markdown
                )
            else:
                return await self._generate_non_streaming_response(
                    messages, temperature, max_tokens, strip_markdown
                )
                
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

    def _calculate_temperature(self, regeneration_count: int) -> float:
        # Calculate temperature based on regeneration count (0.2 base, +0.1 per regeneration, max 1.0)
        return min(0.2 + (regeneration_count * 0.1), 1.0)
    
    def supports_vision(self) -> bool:
        """Check if this backend supports vision/image processing.
        
        Returns:
            bool: True if backend supports vision.
        """
        return self.config.get("supports_vision", False)

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
    
    def get_vision_capable_backend(self, preferred_index: Optional[int] = None) -> LLMBackend:
        """Get a vision-capable backend, preferring the specified index.
        
        Args:
            preferred_index: Preferred backend index to try first.
            
        Returns:
            LLMBackend: Vision-capable backend instance.
            
        Raises:
            ValueError: If no vision-capable backend is found.
        """
        # Try preferred backend first if specified
        if preferred_index is not None:
            backend_config = self.config.get_backend(preferred_index)
            if backend_config and backend_config.get("supports_vision", False):
                return self.get_backend(preferred_index)
        
        # Find first vision-capable backend
        for i, backend_config in enumerate(self.config.config["backends"]):
            if backend_config.get("supports_vision", False):
                return self.get_backend(i)
        
        # No vision-capable backend found
        raise ValueError(
            "No vision-capable backend found. Please configure a backend with 'supports_vision: true'.\n\n"
            "Example configuration:\n"
            "backends:\n"
            "  - name: \"openai-gpt4-vision\"\n"
            "    model: \"gpt-4-vision-preview\"\n"
            "    supports_vision: true\n\n"
            "stdin:\n"
            "  default_backend_vision: 0"
        )
