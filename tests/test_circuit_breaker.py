"""
Unit tests for the CircuitBreaker utility.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.utils.circuit_breaker import CircuitBreaker


@pytest.fixture
def mock_path():
    """Fixture to mock the Path object for file system interactions."""
    with patch("src.utils.circuit_breaker.Path"):
        mock_instance = MagicMock()
        mock_instance.exists.return_value = False
        mock_instance.open = mock_open()
        yield mock_instance


@pytest.fixture
def breaker(mock_path: MagicMock) -> CircuitBreaker:
    """Provides a CircuitBreaker instance with a mocked log file path."""
    return CircuitBreaker(failure_threshold=3, window_minutes=60, log_file=mock_path)


def test_check_returns_true_when_log_file_does_not_exist(breaker: CircuitBreaker, mock_path: MagicMock):
    """
    GIVEN no circuit breaker log file exists
    WHEN check() is called
    THEN it should return True, allowing execution.
    """
    mock_path.exists.return_value = False
    assert breaker.check() is True


def test_check_returns_true_when_failures_are_below_threshold(breaker: CircuitBreaker, mock_path: MagicMock):
    """
    GIVEN a log file with fewer failures than the threshold
    WHEN check() is called
    THEN it should return True.
    """
    now = datetime.now()
    timestamps = [(now - timedelta(minutes=i)).isoformat() for i in range(2)]  # 2 failures
    mock_path.exists.return_value = True
    mock_path.open.return_value.__enter__.return_value.readlines.return_value = [f"{ts}\n" for ts in timestamps]

    assert breaker.check() is True


def test_check_returns_false_when_failures_meet_threshold(breaker: CircuitBreaker, mock_path: MagicMock):
    """
    GIVEN a log file with failures meeting the threshold
    WHEN check() is called
    THEN it should return False, halting execution.
    """
    now = datetime.now()
    timestamps = [(now - timedelta(minutes=i)).isoformat() for i in range(3)]  # 3 failures
    mock_path.exists.return_value = True
    mock_path.open.return_value.__enter__.return_value = mock_open(read_data="\n".join(timestamps)).return_value

    assert breaker.check() is False


def test_check_ignores_old_failures(breaker: CircuitBreaker, mock_path: MagicMock):
    """
    GIVEN a log file with old and recent failures
    WHEN check() is called
    THEN it should only count recent failures and return True.
    """
    now = datetime.now()
    timestamps = [
        (now - timedelta(minutes=10)).isoformat(),  # Recent
        (now - timedelta(minutes=20)).isoformat(),  # Recent
        (now - timedelta(minutes=70)).isoformat(),  # Old
        (now - timedelta(minutes=80)).isoformat(),  # Old
    ]
    mock_path.exists.return_value = True
    mock_path.open.return_value.__enter__.return_value = mock_open(read_data="\n".join(timestamps)).return_value

    assert breaker.check() is True


def test_record_failure_appends_timestamp_to_log(breaker: CircuitBreaker, mock_path: MagicMock):
    """
    GIVEN a circuit breaker
    WHEN record_failure() is called
    THEN it should create the parent directory and append a timestamp to the log file.
    """
    breaker.record_failure()

    mock_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_path.open.assert_called_once_with("a")
    # Check that something was written, without being too specific about the exact timestamp
    handle = mock_path.open()
    handle.write.assert_called_once()
    assert len(handle.write.call_args[0][0]) > 10


def test_reset_deletes_log_file(breaker: CircuitBreaker, mock_path: MagicMock):
    """
    GIVEN a circuit breaker log file exists
    WHEN reset() is called
    THEN it should delete the log file.
    """
    mock_path.exists.return_value = True
    breaker.reset()
    mock_path.unlink.assert_called_once()


def test_reset_does_nothing_if_log_file_does_not_exist(breaker: CircuitBreaker, mock_path: MagicMock):
    """
    GIVEN no circuit breaker log file exists
    WHEN reset() is called
    THEN it should not attempt to delete anything.
    """
    mock_path.exists.return_value = False
    breaker.reset()
    mock_path.unlink.assert_not_called()
