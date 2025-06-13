"""
Unit tests for the retry decorator.
"""

import time
from unittest.mock import MagicMock

import pytest

from src.utils.retry_decorator import retry_with_backoff

# A custom exception for testing


class CustomError(Exception):
    pass


def test_decorated_function_called_once_on_success():
    """
    Tests that the decorated function is called only once if it succeeds on the first attempt.
    """
    # 1. Setup
    mock_func = MagicMock()


    @retry_with_backoff(max_attempts=3)
    def decorated_func():
        mock_func()

    # 2. Action
    decorated_func()

    # 3. Assertions
    mock_func.assert_called_once()


def test_retries_on_exception_and_reraises():
    """
    Tests that the decorator retries on a specified exception, up to the max
    number of attempts, and then re-raises the exception.
    """
    # 1. Setup
    mock_func = MagicMock()
    max_attempts = 4


    @retry_with_backoff(max_attempts=max_attempts, exceptions=CustomError, min_wait=0)
    def decorated_func():
        mock_func()
        raise CustomError("Function failed")

    # 2. Action & Assertion
    with pytest.raises(CustomError, match="Function failed"):
        decorated_func()

    # 3. Assertion
    assert mock_func.call_count == max_attempts


def test_exception_is_suppressed_with_reraise_false():
    """
    Tests that the final exception is suppressed when reraise is set to False.
    """
    # 1. Setup
    mock_func = MagicMock()


    @retry_with_backoff(max_attempts=3, exceptions=CustomError, reraise=False, min_wait=0)
    def decorated_func():
        mock_func()
        raise CustomError("Function failed")

    # 2. Action
    result = decorated_func()

    # 3. Assertions
    assert result is None  # The decorator should return None when the exception is suppressed
    assert mock_func.call_count == 3


def test_succeeds_after_initial_failures():
    """
    Tests that the decorator stops retrying and returns the result as soon as
    the decorated function succeeds.
    """
    # 1. Setup
    mock_func = MagicMock()
    # Let the function fail twice, then succeed on the third attempt
    mock_func.side_effect = [CustomError("Attempt 1"), CustomError("Attempt 2"), "Success"]


    @retry_with_backoff(max_attempts=5, exceptions=CustomError, min_wait=0)
    def decorated_func():
        return mock_func()

    # 2. Action
    result = decorated_func()

    # 3. Assertions
    assert result == "Success"
    assert mock_func.call_count == 3


def test_backoff_timing(monkeypatch):
    """
    Tests that there is a measurable delay between retries, confirming that the
    exponential backoff is being engaged.
    """
    # 1. Setup
    # We will use a real sleep but with a very short duration to keep tests fast.
    min_wait_time = 0.01
    max_attempts = 3

    mock_func = MagicMock()
    mock_func.side_effect = CustomError("Failing to test timing")


    @retry_with_backoff(max_attempts=max_attempts, exceptions=CustomError, min_wait=min_wait_time)
    def decorated_func():
        mock_func()

    # 2. Action
    start_time = time.time()
    with pytest.raises(CustomError):
        decorated_func()
    end_time = time.time()

    # 3. Assertions
    duration = end_time - start_time
    # The total wait time should be at least the sum of the first n-1 waits.
    # For min_wait=0.01, multiplier=2: 0.01 + 0.02 = 0.03
    expected_minimum_duration = min_wait_time + (min_wait_time * 2)
    assert duration > expected_minimum_duration
    assert mock_func.call_count == max_attempts
