"""
Chat session management for nlsh.

This module provides functionality for managing chat sessions in follow-up mode.
"""

import re
import sys
from typing import List, Dict, Any, Optional, Tuple

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


class ChatSession:
    """Manages chat history for follow-up mode."""
    
    def __init__(self, system_prompt: str, client=None, model_name: Optional[str] = None):
        """Initialize the chat session.
        
        Args:
            system_prompt: System prompt to use for the session.
            client: OpenAI-compatible client for retrieving model information.
            model_name: Optional model name to get context window size.
        """
        self.history = [{"role": "system", "content": system_prompt}]
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to the chat history.
        
        Args:
            content: Message content.
        """
        message = {"role": "user", "content": content}
        self.history.append(message)
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the chat history.
        
        Args:
            content: Message content.
        """
        message = {"role": "assistant", "content": content}
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
        self.history.append(message)
    
    def add_declined_command(self, command: str) -> None:
        """Add a declined command to the chat history.
        
        Args:
            command: Declined command.
        """
        # Format the declined command as a user message
        content = f"I declined to execute the command: {command}\nPlease suggest a different command."
        message = {"role": "user", "content": content}
        self.history.append(message)
    
    def get_messages(self) -> List[Dict[str, str]]:
        """Get all messages in the chat history.
        
        Returns:
            list: List of message dictionaries.
        """
        return self.history
