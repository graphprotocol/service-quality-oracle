"""
Unit tests for the Scheduler.
"""

# TODO: Test `initialize` successfully loads config and schedules the main job.
# TODO: Test `initialize` fails gracefully if required environment variables are missing.
# TODO: Test `get_last_run_date` correctly reads a valid date from the last run file.
# TODO: Test `get_last_run_date` returns None if the last run file does not exist.
# TODO: Test `get_last_run_date` caps the date at 7 days ago if the last run is too old.
# TODO: Test `save_last_run_date` correctly writes the date to the last run file.
# TODO: Test `check_missed_runs` correctly identifies and executes a run for a missed day.
# TODO: Test `check_missed_runs` does nothing if the last run was recent.
# TODO: Test `run_oracle` successfully calls `oracle.main` and saves the run date.
# TODO: Test the `@retry` decorator on `run_oracle` by mocking a failing `oracle.main`.
# TODO: Test `update_healthcheck` correctly writes to the healthcheck file.
