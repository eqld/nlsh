"""
Spinner utility for showing progress.

This module provides a simple spinner for showing progress in the terminal.
"""

import sys
import time
import threading


class Spinner:
    """Simple spinner to show progress."""
    
    def __init__(self, message="Thinking", stream=sys.stderr):
        """Initialize the spinner.
        
        Args:
            message: Message to display before the spinner.
            stream: Stream to write to (default: stderr).
        """
        self.message = message
        self.stream = stream
        self.running = False
        self.spinner_thread = None
        self.spinner_chars = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
        self.current = 0
    
    def spin(self):
        """Spin the spinner."""
        while self.running:
            self.stream.write(f"\r{self.message}... {self.spinner_chars[self.current]} ")
            self.stream.flush()
            self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)
        # Clear the spinner line
        self.stream.write("\r" + " " * (len(self.message) + 15) + "\r")
        self.stream.flush()
    
    def start(self):
        """Start the spinner."""
        if not self.running:
            self.running = True
            self.spinner_thread = threading.Thread(target=self.spin)
            self.spinner_thread.daemon = True
            self.spinner_thread.start()
    
    def stop(self):
        """Stop the spinner."""
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()
