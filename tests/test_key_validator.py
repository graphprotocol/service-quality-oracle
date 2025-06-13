"""
Unit tests for the private key validator.
"""

import pytest

from src.utils.key_validator import KeyValidationError, validate_and_format_private_key

# =============================================================================
# POSITIVE TEST CASES
# =============================================================================


def test_valid_key_no_prefix():
    """Test a valid 64-character hex key without a prefix."""
    key = "f" * 64
    assert validate_and_format_private_key(key) == f"0x{key}"


def test_valid_key_with_0x_prefix():
    """Test a valid key that already has the '0x' prefix."""
    key = "a" * 64
    assert validate_and_format_private_key(f"0x{key}") == f"0x{key}"


def test_valid_key_with_leading_whitespace():
    """Test a key with leading/trailing whitespace, which should be stripped."""
    key = "b" * 64
    assert validate_and_format_private_key(f"  {key}  ") == f"0x{key}"


def test_mixed_case_key_is_lowercased():
    """Test a key with mixed-case hex characters, expecting lowercase output."""
    key_mixed = "a1B2c3D4" * 8
    key_lower = key_mixed.lower()
    assert validate_and_format_private_key(key_mixed) == f"0x{key_lower}"


# =============================================================================
# NEGATIVE TEST CASES (INVALID INPUT)
# =============================================================================


def test_invalid_key_too_short():
    """Test a key that is too short, expecting a KeyValidationError."""
    with pytest.raises(KeyValidationError, match="Private key must be 64 hex characters"):
        validate_and_format_private_key("a" * 63)


def test_invalid_key_too_long():
    """Test a key that is too long, expecting a KeyValidationError."""
    with pytest.raises(KeyValidationError, match="Private key must be 64 hex characters"):
        validate_and_format_private_key("a" * 65)


def test_invalid_key_non_hex():
    """Test a key containing non-hexadecimal characters."""
    with pytest.raises(KeyValidationError, match="Private key must be 64 hex characters"):
        validate_and_format_private_key("g" * 64)


def test_empty_string_key():
    """Test an empty string, which should be invalid."""
    with pytest.raises(KeyValidationError, match="Private key must be a non-empty string"):
        validate_and_format_private_key("")


def test_none_key():
    """Test a None input, which should be invalid."""
    with pytest.raises(KeyValidationError, match="Private key must be a non-empty string"):
        validate_and_format_private_key(None)


def test_non_string_key():
    """Test a non-string input type (e.g., integer), which should be invalid."""
    with pytest.raises(KeyValidationError, match="Private key must be a non-empty string"):
        validate_and_format_private_key(12345)
