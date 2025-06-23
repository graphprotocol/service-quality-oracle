"""
Unit tests for the private key validator, refactored for clarity and maintainability.
"""

import pytest

from src.utils.key_validator import KeyValidationError, validate_and_format_private_key

# =============================================================================
# POSITIVE TEST CASES (VALID INPUTS)
# =============================================================================

# Test cases for valid keys. Each tuple contains: (test_id, input_key, expected_output)
VALID_KEY_TEST_CASES = [
    ("no_prefix", "f" * 64, "0x" + "f" * 64),
    ("with_0x_prefix", "0x" + "a" * 64, "0x" + "a" * 64),
    ("with_0X_prefix", "0X" + "c" * 64, "0x" + "c" * 64),
    ("with_whitespace", "  " + "b" * 64 + "  ", "0x" + "b" * 64),
    ("mixed_case_key", "a1B2c3D4" * 8, "0x" + "a1b2c3d4" * 8),
    ("all_digits_key", "12345678" * 8, "0x" + "12345678" * 8),
]


@pytest.mark.parametrize(
    "test_id, input_key, expected",
    VALID_KEY_TEST_CASES,
    ids=[case[0] for case in VALID_KEY_TEST_CASES],
)
def test_validate_and_format_private_key_succeeds_on_valid_keys(test_id, input_key, expected):
    """
    Test that various valid private key formats are correctly validated and formatted.
    This single test covers multiple valid input scenarios.
    """
    # Act
    formatted_key = validate_and_format_private_key(input_key)
    # Assert
    assert formatted_key == expected


# =============================================================================
# NEGATIVE TEST CASES (INVALID FORMAT)
# =============================================================================

# Test cases for keys with invalid format (length or characters).
# Each tuple contains: (test_id, invalid_key)
INVALID_FORMAT_TEST_CASES = [
    ("too_short", "a" * 63),
    ("too_long", "a" * 65),
    ("non_hex_chars", "g" * 64),
    ("mixed_hex_and_non_hex", "f" * 63 + "z"),
]


@pytest.mark.parametrize(
    "test_id, invalid_key",
    INVALID_FORMAT_TEST_CASES,
    ids=[case[0] for case in INVALID_FORMAT_TEST_CASES],
)
def test_validate_and_format_private_key_fails_on_invalid_format(test_id, invalid_key):
    """
    Test that keys with an invalid format (incorrect length or non-hex characters)
    raise a KeyValidationError with a specific message.
    """
    # Act and Assert
    with pytest.raises(KeyValidationError, match="Private key must be 64 hex characters"):
        validate_and_format_private_key(invalid_key)


# =============================================================================
# NEGATIVE TEST CASES (INVALID INPUT TYPE)
# =============================================================================

# Test cases for invalid input types or empty values.
# Each tuple contains: (test_id, invalid_input)
INVALID_INPUT_TYPE_CASES = [
    ("empty_string", ""),
    ("none_value", None),
    ("non_string_integer", 12345),
    ("non_string_list", []),
]


@pytest.mark.parametrize(
    "test_id, invalid_input",
    INVALID_INPUT_TYPE_CASES,
    ids=[case[0] for case in INVALID_INPUT_TYPE_CASES],
)
def test_validate_and_format_private_key_fails_on_invalid_input_type(test_id, invalid_input):
    """
    Test that invalid input types (e.g., None, non-string) or an empty string
    raise a KeyValidationError with a specific message.
    """
    # Act and Assert
    with pytest.raises(KeyValidationError, match="Private key must be a non-empty string"):
        validate_and_format_private_key(invalid_input)
