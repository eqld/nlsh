"""
Base class for all system tools.

This module provides the abstract base class that all system tools must implement.
"""

from abc import ABC, abstractmethod


class BaseTool(ABC):
    """Abstract base class for all system tools.
    
    All tools must inherit from this class and implement the get_context method.
    """
    
    def __init__(self, config):
        """Initialize the tool with configuration.
        
        Args:
            config: The configuration object.
        """
        self.config = config
    
    @abstractmethod
    def get_context(self):
        """Get context information from this tool.
        
        This method must be implemented by all tool classes.
        
        Returns:
            str: Formatted context information for the LLM.
        """
        pass
    
    @property
    def name(self):
        """Get the name of the tool.
        
        Returns:
            str: The name of the tool class.
        """
        return self.__class__.__name__
