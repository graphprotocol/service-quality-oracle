"""
Unit tests for the Scheduler.
"""

import os
import sys
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, mock_open, patch

import pytest
from tenacity import wait_fixed

# Mocking at the global level is removed to prevent test pollution
# sys.modules["src.models.service_quality_oracle"] = MagicMock()
# The Scheduler will be imported within tests after mocks are set up
# from src.models.scheduler import Scheduler
from src.utils.configuration import ConfigurationError

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

    # Patch sys.modules just for the duration of this test setup
    with patch.dict(sys.modules, {"src.models.service_quality_oracle": MagicMock()}):
        from src.models.scheduler import Scheduler

        with patch.object(Scheduler, "check_missed_runs") as mock_check_missed:
            sch = Scheduler()
            sch.check_missed_runs = mock_check_missed
            return sch


@pytest.fixture
def scheduler_no_init(mock_dependencies):
    """Provides a Scheduler instance without running the default __init__."""
    with patch.dict(sys.modules, {"src.models.service_quality_oracle": MagicMock()}):
        from src.models.scheduler import Scheduler

        with patch.object(Scheduler, "__init__", return_value=None):
            sch = Scheduler()
            # Manually set attributes that would have been set in __init__
            sch.last_run_file = "/app/data/last_run.txt"
            sch.healthcheck_file = "/app/healthcheck"
            sch.slack_notifier = mock_dependencies["create_slack"].return_value
            yield sch


def test_initialize_success(scheduler: "Scheduler", mock_dependencies: dict):
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
    mock_dependencies["exit"].reset_mock()  # Reset mock from potential previous calls
    # Ensure the webhook is available in the mocked environment for the new logic
    mock_dependencies["os"].environ.get.return_value = MOCK_CONFIG["SLACK_WEBHOOK_URL"]

    # 2. Action & Assertions
    # We test that creating a Scheduler instance, which calls initialize(),
    # triggers a sys.exit.
    with patch.dict(sys.modules, {"src.models.service_quality_oracle": MagicMock()}):
        from src.models.scheduler import Scheduler

        # The __init__ of Scheduler calls initialize(), which should fail and call sys.exit
        Scheduler()

    # Assert that the failure notification was sent and the program tried to exit
    mock_dependencies["create_slack"].return_value.send_failure_notification.assert_called_once()
    mock_dependencies["exit"].assert_called_once_with(1)


def test_get_last_run_date_success(scheduler: "Scheduler", mock_dependencies: dict):
    """
    Tests that `get_last_run_date` correctly reads and parses a valid date from the file.
    """
    # 1. Setup
    mock_dependencies["os"].path.exists.return_value = True
    mock_dependencies["open"].return_value.read.return_value = (
        datetime.now().date() - timedelta(days=1)
    ).strftime("%Y-%m-%d")

    # 2. Action
    last_run = scheduler.get_last_run_date()

    # 3. Assertions
    assert last_run == datetime.now().date() - timedelta(days=1)


def test_get_last_run_date_not_exists(scheduler: "Scheduler", mock_dependencies: dict):
    """
    Tests that `get_last_run_date` returns None if the last run file does not exist.
    """
    # 1. Setup
    mock_dependencies["os"].path.exists.return_value = False

    # 2. Action
    last_run = scheduler.get_last_run_date()

    # 3. Assertions
    assert last_run is None


def test_get_last_run_date_is_capped(scheduler: "Scheduler", mock_dependencies: dict):
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


def test_save_last_run_date(scheduler: "Scheduler", mock_dependencies: dict):
    """
    Tests that `save_last_run_date` correctly opens the right file and writes
    the formatted date string to it.
    """
    # 1. Setup
    run_date = date(2023, 10, 27)
    expected_dir = os.path.dirname("/app/data/last_run.txt")
    mock_dependencies["os"].path.dirname.return_value = expected_dir
    mock_dependencies["open"].reset_mock()

    # 2. Action
    scheduler.save_last_run_date(run_date)

    # 3. Assertions
    # Check that the directory was created
    mock_dependencies["os"].makedirs.assert_called_once_with(expected_dir, exist_ok=True)

    # Check that the file was opened for writing
    mock_dependencies["open"].assert_called_once_with("/app/data/last_run.txt", "w")

    # Check that the correct content was written
    file_handle = mock_dependencies["open"].return_value.__enter__.return_value
    file_handle.write.assert_called_once_with("2023-10-27")


def test_check_missed_runs_executes_for_missed_day(scheduler_no_init: "Scheduler"):
    """
    Tests that `check_missed_runs` triggers `run_oracle` for yesterday if the
    last recorded run was two days ago.
    """
    # 1. Setup
    scheduler = scheduler_no_init
    two_days_ago = datetime.now().date() - timedelta(days=2)
    yesterday = datetime.now().date() - timedelta(days=1)

    with patch.object(scheduler, "get_last_run_date", return_value=two_days_ago) as mock_get_last_run:
        scheduler.run_oracle = MagicMock()

        # 2. Action
        scheduler.check_missed_runs()

        # 3. Assertions
        mock_get_last_run.assert_called_once()
        scheduler.run_oracle.assert_called_once_with(run_date_override=yesterday)


def test_check_missed_runs_does_nothing_if_recent(scheduler_no_init: "Scheduler"):
    """
    Tests that `check_missed_runs` does not trigger a run if the last run was yesterday.
    """
    # 1. Setup
    scheduler = scheduler_no_init
    yesterday = datetime.now().date() - timedelta(days=1)
    with patch.object(scheduler, "get_last_run_date", return_value=yesterday) as mock_get_last_run:
        scheduler.run_oracle = MagicMock()

        # 2. Action
        scheduler.check_missed_runs()

        # 3. Assertions
        mock_get_last_run.assert_called_once()
        scheduler.run_oracle.assert_not_called()


def test_check_missed_runs_sends_slack_notification(scheduler_no_init: "Scheduler"):
    """
    Tests that a Slack notification is sent when missed runs are detected.
    """
    # 1. Setup
    scheduler = scheduler_no_init
    two_days_ago = datetime.now().date() - timedelta(days=2)
    scheduler.get_last_run_date = MagicMock(return_value=two_days_ago)
    scheduler.run_oracle = MagicMock()  # Mock the main run function
    scheduler.slack_notifier.send_info_notification.reset_mock()

    # 2. Action
    scheduler.check_missed_runs()

    # 3. Assertions
    scheduler.slack_notifier.send_info_notification.assert_called_once()
    call_kwargs = scheduler.slack_notifier.send_info_notification.call_args.kwargs
    assert "Missed Runs Detected" in call_kwargs["title"]
    assert "Detected 1 missed oracle runs" in call_kwargs["message"]


def test_get_last_run_date_handles_corrupted_file(scheduler: "Scheduler", mock_dependencies: dict):
    """
    Tests that get_last_run_date returns None if the file contains an invalid date string.
    """
    # 1. Setup
    mock_dependencies["os"].path.exists.return_value = True
    # Simulate a file with corrupted content
    mock_dependencies["open"].return_value.read.return_value = "not-a-date"

    # 2. Action
    last_run = scheduler.get_last_run_date()

    # 3. Assertions
    assert last_run is None


def test_run_oracle_success(scheduler: "Scheduler", mock_dependencies: dict):
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


def test_run_oracle_retry_logic(scheduler: "Scheduler", mock_dependencies: dict):
    """
    Tests that the @retry decorator on `run_oracle` functions as expected.
    """
    # 1. Setup
    # The decorator is configured with stop_after_attempt(5)
    expected_attempts = 5
    mock_dependencies["oracle"].main.side_effect = Exception("Oracle failed!")

    # Speed up the test by removing the wait from the retry decorator
    scheduler.run_oracle.retry.wait = wait_fixed(0)

    # 2. Action & Assertion
    with pytest.raises(Exception):
        scheduler.run_oracle()

    assert mock_dependencies["oracle"].main.call_count == expected_attempts


def test_update_healthcheck(scheduler: "Scheduler", mock_dependencies: dict):
    """
    Tests that `update_healthcheck` writes a timestamp to the healthcheck file.
    """
    # 1. Setup
    mock_dependencies["open"].reset_mock()

    # 2. Action
    scheduler.update_healthcheck("testing")

    # 3. Assertions
    mock_dependencies["open"].assert_called_once_with("/app/healthcheck", "w")
    file_handle = mock_dependencies["open"].return_value.__enter__.return_value

    # Check that write was called, its content will have a timestamp so we just check the start
    # We check call_args_list to isolate the call made in this test
    write_call = file_handle.write.call_args_list[0]
    write_string = write_call.args[0]
    assert write_string.startswith("Last update:")
