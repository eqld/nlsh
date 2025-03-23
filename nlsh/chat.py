"""
Chat session management for nlsh.

This module provides functionality for managing chat sessions in follow-up mode.
"""

import re
import sys
from typing import List, Dict, Any, Optional, Tuple

# Default context window size for modern models (16k tokens)
DEFAULT_CONTEXT_SIZE = 16384

def get_model_context_size(client, model_name: str) -> int:
    """Get the context window size for a model.
    
    This function attempts to get the context window size from the API
    if possible, otherwise falls back to a default size.
    
    Args:
        client: OpenAI-compatible client.
        model_name: Name of the model.
        
    Returns:
        int: Context window size in tokens.
    """
    try:
        # Extract the base model name (without any additional parameters)
        base_model = model_name.split(':')[-1] if ':' in model_name else model_name
        
        # Try to get model information from the API
        model_info = client.models.retrieve(base_model)
        
        # Extract context window size if available
        if hasattr(model_info, 'context_window') and model_info.context_window:
            return model_info.context_window
    except Exception as e:
        # If there's any error, fall back to default size
        print(f"Could not retrieve context window size for model {model_name}: {str(e)}", file=sys.stderr)
    
    # Fall back to default size
    return DEFAULT_CONTEXT_SIZE

def count_tokens(text: str) -> int:
    """Count tokens in text (approximate).
    
    This is a simple approximation. For more accurate counting,
    we would need to use the tokenizer specific to the model.
    
    Args:
        text: Text to count tokens for.
        
    Returns:
        int: Approximate token count.
    """
    # Simple approximation: 4 characters per token on average
    return len(text) // 4


class ContextWindowManager:
    """Manages context window usage."""
    
    def __init__(self, max_tokens: int = DEFAULT_CONTEXT_SIZE):
        """Initialize the context window manager.
        
        Args:
            max_tokens: Maximum number of tokens in the context window.
        """
        self.max_tokens = max_tokens
        self.current_tokens = 0
    
    def add_message(self, message: Dict[str, str]) -> int:
        """Add a message and count its tokens.
        
        Args:
            message: Message to add.
            
        Returns:
            int: Token count of the message.
        """
        token_count = count_tokens(message["content"])
        self.current_tokens += token_count
        return token_count
    
    def trim_history_if_needed(self, history: List[Dict[str, str]], new_message_tokens: int) -> List[Dict[str, str]]:
        """Trim history if adding a new message would exceed the context window.
        
        Args:
            history: Current chat history.
            new_message_tokens: Token count of the new message.
            
        Returns:
            list: Trimmed chat history.
        """
        # Check if we need to trim
        if self.current_tokens + new_message_tokens <= self.max_tokens:
            return history
        
        # Calculate how many tokens we need to remove
        tokens_to_remove = (self.current_tokens + new_message_tokens) - self.max_tokens
        
        # Remove oldest messages until we have enough space
        tokens_removed = 0
        messages_to_remove = 0
        
        for i, message in enumerate(history):
            # Skip the system message (first message)
            if i == 0 and message["role"] == "system":
                continue
                
            message_tokens = count_tokens(message["content"])
            tokens_removed += message_tokens
            messages_to_remove += 1
            
            if tokens_removed >= tokens_to_remove:
                break
        
        # Update current token count
        self.current_tokens -= tokens_removed
        
        # Return trimmed history
        return history[messages_to_remove:]
    
    def get_usage_percentage(self) -> float:
        """Get context window usage percentage.
        
        Returns:
            float: Usage percentage (0-100).
        """
        return (self.current_tokens / self.max_tokens) * 100
    
    def display_usage(self):
        """Display context window usage as a progress bar."""
        percentage = self.get_usage_percentage()
        bar_length = 30
        filled_length = int(bar_length * percentage / 100)
        
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        print(f"\rContext window: [{bar}] {percentage:.1f}%", end="")


# CostTracker class has been removed as the prompt cost calculation was not precise enough


class ChatSession:
    """Manages chat history for follow-up mode."""
    
    def __init__(self, system_prompt: str, max_tokens: int = DEFAULT_CONTEXT_SIZE, client=None, model_name: Optional[str] = None):
        """Initialize the chat session.
        
        Args:
            system_prompt: System prompt to use for the session.
            max_tokens: Maximum number of tokens in the context window.
            client: OpenAI-compatible client for retrieving model information.
            model_name: Optional model name to get context window size.
        """
        self.history = [{"role": "system", "content": system_prompt}]
        
        # If client and model_name are provided, try to get context window size
        context_size = max_tokens
        if client and model_name:
            context_size = get_model_context_size(client, model_name)
        
        self.context_manager = ContextWindowManager(context_size)
        
        # Add system message to token count
        self.context_manager.add_message(self.history[0])
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to the chat history.
        
        Args:
            content: Message content.
        """
        message = {"role": "user", "content": content}
        token_count = self.context_manager.add_message(message)
        
        # Trim history if needed
        self.history = self.context_manager.trim_history_if_needed(self.history, token_count)
        
        # Add message to history
        self.history.append(message)
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the chat history.
        
        Args:
            content: Message content.
        """
        message = {"role": "assistant", "content": content}
        self.context_manager.add_message(message)
        self.history.append(message)
    
    def add_command_execution(self, command: str, output: str) -> None:
        """Add command execution result to the chat history.
        
        Args:
            command: Executed command.
            output: Command output.
        """
        # Format the execution result as a user message
        content = f"I executed the command: {command}\n\nOutput:\n{output}"
        message = {"role": "user", "content": content}
        token_count = self.context_manager.add_message(message)
        
        # Trim history if needed
        self.history = self.context_manager.trim_history_if_needed(self.history, token_count)
        
        # Add message to history
        self.history.append(message)
    
    def add_declined_command(self, command: str) -> None:
        """Add a declined command to the chat history.
        
        Args:
            command: Declined command.
        """
        # Format the declined command as a user message
        content = f"I declined to execute the command: {command}\nPlease suggest a different command."
        message = {"role": "user", "content": content}
        token_count = self.context_manager.add_message(message)
        
        # Trim history if needed
        self.history = self.context_manager.trim_history_if_needed(self.history, token_count)
        
        # Add message to history
        self.history.append(message)
    
    def get_messages(self) -> List[Dict[str, str]]:
        """Get all messages in the chat history.
        
        Returns:
            list: List of message dictionaries.
        """
        return self.history
    
    def display_context_usage(self) -> None:
        """Display context window usage."""
        self.context_manager.display_usage()
