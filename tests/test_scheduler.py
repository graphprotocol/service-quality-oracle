"""
Unit tests for the Scheduler.
"""

import sys
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Mock the main oracle entry point before it's even imported by the scheduler
sys.modules["src.models.service_quality_oracle"] = MagicMock()

from src.models.scheduler import ConfigurationError, Scheduler

MOCK_CONFIG = {
    "SLACK_WEBHOOK_URL": "http://fake.slack.com",
    "SCHEDULED_RUN_TIME": "10:00",
}


@pytest.fixture
def mock_dependencies():
    """A comprehensive fixture to mock all external dependencies of the scheduler."""
    with (
        patch("src.models.scheduler.validate_all_required_env_vars") as mock_validate,
        patch("src.models.scheduler.load_config", return_value=MOCK_CONFIG) as mock_load_config,
        patch("src.models.scheduler.create_slack_notifier") as mock_create_slack,
        patch("src.models.scheduler.credential_manager") as mock_creds,
        patch("src.models.scheduler.schedule") as mock_schedule,
        patch("src.models.scheduler.oracle") as mock_oracle,
        patch("src.models.scheduler.os") as mock_os,
        patch("builtins.open", new_callable=mock_open) as mock_open_file,
        patch("src.models.scheduler.sys.exit") as mock_exit,
    ):
        yield {
            "validate": mock_validate,
            "load_config": mock_load_config,
            "create_slack": mock_create_slack,
            "creds": mock_creds,
            "schedule": mock_schedule,
            "oracle": mock_oracle,
            "os": mock_os,
            "open": mock_open_file,
            "exit": mock_exit,
        }


@pytest.fixture
def scheduler(mock_dependencies):
    """Provides a Scheduler instance with all dependencies mocked."""
    # Prevent initialize from running check_missed_runs or run_on_startup
    mock_dependencies["os"].environ.get.return_value = "false"
    with patch.object(Scheduler, "check_missed_runs") as mock_check_missed:
        sch = Scheduler()
        sch.check_missed_runs = mock_check_missed
        return sch


def test_initialize_success(scheduler: Scheduler, mock_dependencies: dict):
    """
    Tests that the scheduler initializes correctly on a happy path, scheduling the job
    and performing initial checks.
    """
    # Assertions for the state set during initialization in the fixture
    mock_dependencies["validate"].assert_called_once()
    mock_dependencies["creds"].setup_google_credentials.assert_called_once()
    mock_dependencies["load_config"].assert_called_once()
    mock_dependencies["create_slack"].assert_called_once_with(MOCK_CONFIG["SLACK_WEBHOOK_URL"])

    # Check that the job was scheduled correctly
    mock_dependencies["schedule"].every.return_value.day.at.assert_called_once_with(
        MOCK_CONFIG["SCHEDULED_RUN_TIME"]
    )
    mock_dependencies["schedule"].every.return_value.day.at.return_value.do.assert_called_once_with(
        scheduler.run_oracle, run_date_override=None
    )

    # Check that initial healthcheck and missed run checks were performed
    scheduler.check_missed_runs.assert_called_once()
    assert mock_dependencies["open"].call_count > 0


def test_initialize_failure(mock_dependencies: dict):
    """
    Tests that the scheduler calls sys.exit if initialization fails due to a
    configuration error.
    """
    # 1. Setup
    # Have the validation function raise an error
    mock_dependencies["validate"].side_effect = ConfigurationError("Missing env var")

    # 2. Action
    # We re-initialize the scheduler here to test the __init__ -> initialize() flow
    Scheduler()

    # 3. Assertions
    # Get the mock slack_notifier instance created by the patched `create_slack_notifier`
    mock_slack_notifier = mock_dependencies["create_slack"].return_value
    mock_slack_notifier.send_failure_notification.assert_called_once()

    # Assert that the program tried to exit
    mock_dependencies["exit"].assert_called_once_with(1)


def test_get_last_run_date_success(scheduler: Scheduler, mock_dependencies: dict):
    """
    Tests that `get_last_run_date` correctly reads and parses a valid date from the file.
    """
    # 1. Setup
    mock_dependencies["os"].path.exists.return_value = True
    mock_dependencies["open"].return_value.read.return_value = "2023-10-26"

    # 2. Action
    last_run = scheduler.get_last_run_date()

    # 3. Assertions
    assert last_run == date(2023, 10, 26)


def test_get_last_run_date_not_exists(scheduler: Scheduler, mock_dependencies: dict):
    """
    Tests that `get_last_run_date` returns None if the last run file does not exist.
    """
    # 1. Setup
    mock_dependencies["os"].path.exists.return_value = False

    # 2. Action
    last_run = scheduler.get_last_run_date()

    # 3. Assertions
    assert last_run is None


def test_get_last_run_date_is_capped(scheduler: Scheduler, mock_dependencies: dict):
    """
    Tests that `get_last_run_date` caps the returned date at 7 days ago if the
    recorded date is too old.
    """
    # 1. Setup
    very_old_date = "2020-01-01"
    seven_days_ago = datetime.now().date() - timedelta(days=7)
    mock_dependencies["os"].path.exists.return_value = True
    mock_dependencies["open"].return_value.read.return_value = very_old_date

    # 2. Action
    last_run = scheduler.get_last_run_date()

    # 3. Assertions
    assert last_run == seven_days_ago


def test_save_last_run_date(scheduler: Scheduler, mock_dependencies: dict):
    """
    Tests that `save_last_run_date` correctly opens the right file and writes
    the formatted date string to it.
    """
    # 1. Setup
    run_date = date(2023, 10, 27)

    # 2. Action
    scheduler.save_last_run_date(run_date)

    # 3. Assertions
    # Check that the directory was created
    mock_dependencies["os"].makedirs.assert_called_once_with("/app/data", exist_ok=True)

    # Check that the file was opened for writing
    mock_dependencies["open"].assert_called_once_with("/app/data/last_run.txt", "w")

    # Check that the correct content was written
    file_handle = mock_dependencies["open"].return_value.__enter__.return_value
    file_handle.write.assert_called_once_with("2023-10-27")


def test_check_missed_runs_executes_for_missed_day(scheduler: Scheduler):
    """
    Tests that `check_missed_runs` triggers `run_oracle` for yesterday if the
    last recorded run was two days ago.
    """
    # 1. Setup
    two_days_ago = datetime.now().date() - timedelta(days=2)
    yesterday = datetime.now().date() - timedelta(days=1)
    scheduler.get_last_run_date = MagicMock(return_value=two_days_ago)
    scheduler.run_oracle = MagicMock()

    # 2. Action
    scheduler.check_missed_runs()

    # 3. Assertions
    scheduler.get_last_run_date.assert_called_once()
    scheduler.run_oracle.assert_called_once_with(run_date_override=yesterday)


def test_check_missed_runs_does_nothing_if_recent(scheduler: Scheduler):
    """
    Tests that `check_missed_runs` does not trigger a run if the last run was yesterday.
    """
    # 1. Setup
    yesterday = datetime.now().date() - timedelta(days=1)
    scheduler.get_last_run_date = MagicMock(return_value=yesterday)
    scheduler.run_oracle = MagicMock()

    # 2. Action
    scheduler.check_missed_runs()

    # 3. Assertions
    scheduler.get_last_run_date.assert_called_once()
    scheduler.run_oracle.assert_not_called()


def test_run_oracle_success(scheduler: Scheduler, mock_dependencies: dict):
    """
    Tests that `run_oracle` calls the main oracle function and saves state upon success.
    """
    # 1. Setup
    scheduler.save_last_run_date = MagicMock()
    scheduler.update_healthcheck = MagicMock()

    # 2. Action
    scheduler.run_oracle()

    # 3. Assertions
    mock_dependencies["oracle"].main.assert_called_once()
    scheduler.save_last_run_date.assert_called_once()
    scheduler.update_healthcheck.assert_called_once()


def test_run_oracle_retry_logic(scheduler: Scheduler, mock_dependencies: dict):
    """
    Tests that the @retry decorator on `run_oracle` functions as expected.
    """
    # 1. Setup
    # The decorator is configured with stop_after_attempt(5)
    expected_attempts = 5
    mock_dependencies["oracle"].main.side_effect = Exception("Oracle failed!")

    # 2. Action & Assertion
    with pytest.raises(Exception, match="Oracle failed!"):
        scheduler.run_oracle()

    assert mock_dependencies["oracle"].main.call_count == expected_attempts


def test_update_healthcheck(scheduler: Scheduler, mock_dependencies: dict):
    """
    Tests that `update_healthcheck` writes a timestamp to the healthcheck file.
    """
    # 1. Action
    scheduler.update_healthcheck("testing")

    # 2. Assertions
    mock_dependencies["open"].assert_called_once_with("/app/healthcheck", "w")
    file_handle = mock_dependencies["open"].return_value.__enter__.return_value

    # Check that write was called, its content will have a timestamp so we just check the start
    write_call_args = file_handle.write.call_args[0][0]
    assert write_call_args.startswith("Last update:")
    assert "testing" in write_call_args
