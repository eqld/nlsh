"""
Chat session management for nlsh.

This module provides functionality for managing chat sessions in follow-up mode.
"""

import re
from typing import List, Dict, Any, Optional, Tuple

# Approximate token count for context window management
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
    
    def __init__(self, max_tokens: int = 4096):
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


class CostTracker:
    """Tracks API call costs."""
    
    # Cost per 1000 tokens for different models (input/output)
    MODEL_COSTS = {
        # OpenAI models
        "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        
        # Anthropic models
        "claude-instant-1": {"input": 0.0008, "output": 0.0024},
        "claude-2": {"input": 0.008, "output": 0.024},
        
        # Default fallback for unknown models
        "default": {"input": 0.001, "output": 0.002}
    }
    
    def __init__(self):
        """Initialize the cost tracker."""
        self.total_cost = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
    
    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for an API call.
        
        Args:
            model: Model name.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            
        Returns:
            float: Cost in USD.
        """
        # Skip for local models
        if "localhost" in model or "127.0.0.1" in model:
            return 0.0
        
        # Get cost rates for the model
        model_name = model.split(':')[-1] if ':' in model else model
        cost_rates = self.MODEL_COSTS.get(model_name, self.MODEL_COSTS["default"])
        
        # Calculate cost
        input_cost = (input_tokens / 1000) * cost_rates["input"]
        output_cost = (output_tokens / 1000) * cost_rates["output"]
        cost = input_cost + output_cost
        
        # Update totals
        self.total_cost += cost
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        
        return cost
    
    def display_cost(self, model: str, input_tokens: int, output_tokens: int):
        """Display cost for an API call.
        
        Args:
            model: Model name.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
        """
        # Skip for local models
        if "localhost" in model or "127.0.0.1" in model:
            return
        
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        print(f"Cost: ${cost:.6f} (Total: ${self.total_cost:.6f})")


class ChatSession:
    """Manages chat history for follow-up mode."""
    
    def __init__(self, system_prompt: str, max_tokens: int = 4096):
        """Initialize the chat session.
        
        Args:
            system_prompt: System prompt to use for the session.
            max_tokens: Maximum number of tokens in the context window.
        """
        self.history = [{"role": "system", "content": system_prompt}]
        self.context_manager = ContextWindowManager(max_tokens)
        self.cost_tracker = CostTracker()
        
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
    
    def track_cost(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """Track cost for an API call.
        
        Args:
            model: Model name.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
        """
        self.cost_tracker.display_cost(model, input_tokens, output_tokens)
    
    def display_context_usage(self) -> None:
        """Display context window usage."""
        self.context_manager.display_usage()
