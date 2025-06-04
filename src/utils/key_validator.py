"""
Private Key Validator for Service Quality Oracle

This module provides validation and formatting of private keys.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class KeyValidationError(Exception):
    """Raised when key validation fails."""
    pass


@dataclass
class KeyValidationResult:
    """Result of private key validation."""
    is_valid: bool
    formatted_key: Optional[str]
    error_message: Optional[str]


def validate_private_key(private_key: str) -> KeyValidationResult:
    """
    Validate and format a private key.

    Args:
        private_key: Raw private key string

    Returns:
        KeyValidationResult object with validation status, formatted key, and error message

    Raises:
        KeyValidationError: If key validation fails
    """
    if not private_key or not isinstance(private_key, str):
        return KeyValidationResult(
            is_valid=False,
            formatted_key=None,
            error_message="Private key must be a non-empty string",
        )

    # Remove whitespace and common prefixes
    clean_key = private_key.strip()

    # Handle hex prefixes
    if clean_key.startswith(("0x", "0X")):
        hex_key = clean_key[2:]
    else:
        hex_key = clean_key

    # Validate hex format (64 characters)
    if not re.match(r"^[0-9a-fA-F]{64}$", hex_key):
        return KeyValidationResult(
            is_valid=False,
            formatted_key=None,
            error_message="Private key must be 64 hex characters",
        )

    # Return formatted key with 0x prefix
    formatted_key = f"0x{hex_key.lower()}"
    return KeyValidationResult(
        is_valid=True,
        formatted_key=formatted_key,
        error_message=None,
    )


def validate_and_format_private_key(private_key: str) -> str:
    """
    Validate and format a private key, raising an exception if invalid.

    Args:
        private_key: Raw private key string

    Returns:
        Formatted private key string

    Raises:
        KeyValidationError: If key validation fails
    """
    result = validate_private_key(private_key)
    if not result.is_valid:
        raise KeyValidationError(f"Invalid private key: {result.error_message}")
    return result.formatted_key
