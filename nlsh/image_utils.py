"""
Image processing utilities for nlsh.

This module provides functionality for detecting and processing image input.
"""

import base64
import io
from typing import Tuple, Optional


def detect_input_type(data: bytes) -> str:
    """Detect the type of input data.
    
    Args:
        data: Raw input data.
        
    Returns:
        str: MIME type of the detected format or 'text/plain' for text.
    """
    if not data:
        return 'text/plain'
    
    # Check for common image magic bytes
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    elif data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    elif data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
        return 'image/gif'
    elif data.startswith(b'RIFF') and b'WEBP' in data[:12]:
        return 'image/webp'
    elif data.startswith(b'BM'):
        return 'image/bmp'
    
    # Check if it's already base64-encoded image data
    try:
        data_str = data.decode('utf-8', errors='ignore').strip()
        if data_str.startswith('data:image/'):
            # Extract MIME type from data URL
            if ';base64,' in data_str:
                mime_type = data_str.split(';base64,')[0].replace('data:', '')
                return mime_type
        elif _is_base64_image(data_str):
            # Try to detect format from base64 data
            try:
                decoded = base64.b64decode(data_str)
                return detect_input_type(decoded)
            except Exception:
                pass
    except UnicodeDecodeError:
        pass
    
    # Default to text
    return 'text/plain'


def _is_base64_image(data_str: str) -> bool:
    """Check if a string looks like base64-encoded image data.
    
    Args:
        data_str: String to check.
        
    Returns:
        bool: True if it looks like base64 image data.
    """
    # Basic heuristics for base64 image data
    if len(data_str) < 100:  # Too short to be an image
        return False
    
    # Check if it's valid base64
    try:
        # Remove whitespace and check if it's valid base64
        clean_data = ''.join(data_str.split())
        if len(clean_data) % 4 != 0:
            # Pad with = if needed
            clean_data += '=' * (4 - len(clean_data) % 4)
        
        decoded = base64.b64decode(clean_data, validate=True)
        
        # Check if decoded data has image magic bytes
        return detect_input_type(decoded) != 'text/plain'
    except Exception:
        return False


def prepare_image_for_api(data: bytes, mime_type: str) -> Tuple[str, str]:
    """Prepare image data for OpenAI API.
    
    Args:
        data: Raw image data.
        mime_type: MIME type of the image.
        
    Returns:
        tuple: (base64_data, mime_type) ready for API.
        
    Raises:
        ValueError: If image format is not supported.
    """
    supported_formats = {
        'image/png': 'png',
        'image/jpeg': 'jpeg', 
        'image/gif': 'gif',
        'image/webp': 'webp'
    }
    
    if mime_type not in supported_formats:
        raise ValueError(f"Unsupported image format: {mime_type}")
    
    # Check if data is already base64 encoded
    try:
        data_str = data.decode('utf-8', errors='ignore').strip()
        if data_str.startswith('data:image/'):
            # Extract base64 part from data URL
            if ';base64,' in data_str:
                base64_part = data_str.split(';base64,')[1]
                return base64_part, mime_type
        elif _is_base64_image(data_str):
            # Clean up base64 string
            clean_data = ''.join(data_str.split())
            if len(clean_data) % 4 != 0:
                clean_data += '=' * (4 - len(clean_data) % 4)
            return clean_data, mime_type
    except UnicodeDecodeError:
        pass
    
    # Encode raw binary data to base64
    base64_data = base64.b64encode(data).decode('utf-8')
    return base64_data, mime_type


def validate_image_size(data: bytes, max_size_mb: float = 20.0) -> None:
    """Validate image size.
    
    Args:
        data: Image data.
        max_size_mb: Maximum allowed size in MB.
        
    Raises:
        ValueError: If image is too large.
    """
    size_mb = len(data) / (1024 * 1024)
    if size_mb > max_size_mb:
        raise ValueError(f"Image too large: {size_mb:.1f}MB (max: {max_size_mb}MB)")


def get_backend_image_size_limit(backend_config: dict) -> float:
    """Get the image size limit for a backend.
    
    Args:
        backend_config: Backend configuration dictionary.
        
    Returns:
        float: Maximum image size in MB.
    """
    return backend_config.get("max_image_size_mb", 20.0)


def is_image_type(mime_type: str) -> bool:
    """Check if MIME type represents an image.
    
    Args:
        mime_type: MIME type to check.
        
    Returns:
        bool: True if it's an image type.
    """
    return mime_type.startswith('image/')
