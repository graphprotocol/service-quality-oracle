"""
Application circuit breaker utility to prevent infinite restart loops.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    A simple circuit breaker to prevent an application from restarting indefinitely
    due to persistent, deterministic errors.

    It works by logging failure timestamps to a file. On startup, it checks how
    many failures have occurred within a given time window. If the count exceeds a
    threshold, it "opens" the circuit, signaling the application to halt.
    """

    def __init__(self, failure_threshold: int, window_minutes: int, log_file: Path):
        """
        Initialize the circuit breaker.

        Args:
            failure_threshold: The number of failures required to open the circuit.
            window_minutes: The time window in minutes to check for failures.
            log_file: The path to the file used for persisting failure timestamps.
        """
        self.failure_threshold = failure_threshold
        self.window_minutes = window_minutes
        self.log_file = log_file


    def _get_failure_timestamps(self) -> List[datetime]:
        """
        Reads and parses all timestamps from the log file.

        Returns:
            List[datetime]: A list of datetime objects representing the failure timestamps.
        """
        # If the log file does not exist, return an empty list
        if not self.log_file.exists():
            return []
        
        # If the log file exists, read and parse all timestamps
        try:
            with self.log_file.open("r") as f:
                timestamps = [datetime.fromisoformat(line.strip()) for line in f if line.strip()]
            return timestamps
        
        # If there is an error reading or parsing the log file, log the error and return an empty list
        except (IOError, ValueError) as e:
            logger.error(f"Error reading or parsing circuit breaker log file {self.log_file}: {e}")
            return []


    def check(self) -> bool:
        """
        Check the state of the circuit. This is used to determine if the application should proceed or halt.

        Returns:
            bool: True if the circuit is closed (safe to proceed), False if it is open (should halt).
        """
        # Get the failure timestamps from the log file
        timestamps = self._get_failure_timestamps()

        # If there are no failure timestamps, return True
        if not timestamps:
            return True

        # Calculate the window start time and get the recent failures
        window_start = datetime.now() - timedelta(minutes=self.window_minutes)
        recent_failures = [ts for ts in timestamps if ts > window_start]

        # If the number of recent failures is greater than or equal to the failure threshold, return False
        if len(recent_failures) >= self.failure_threshold:
            logger.critical(
                f"CIRCUIT BREAKER OPEN: Found {len(recent_failures)} failures in the last "
                f"{self.window_minutes} minutes (threshold is {self.failure_threshold}). Halting execution."
            )
            return False

        # If the number of recent failures is less than the failure threshold, return True
        logger.info("Circuit breaker is closed. Proceeding with execution.")
        return True


    def record_failure(self) -> None:
        """Records a failure by appending the current timestamp to the log file.

        Returns:
            None
        """
        # Try to log the failure
        try:
            # Create the parent directory if it doesn't exist
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

            # Append the current timestamp to the log file
            with self.log_file.open("a") as f:
                f.write(f"{datetime.now().isoformat()}\n")

            # Log the success
            logger.warning("Circuit breaker has recorded a failure.")
        
        # If there is an error appending the timestamp to the log file, log the error
        except IOError as e:
            logger.error(f"Failed to record failure to circuit breaker log {self.log_file}: {e}")


    def reset(self) -> None:
        """Resets the circuit by deleting the log file on a successful run.

        Returns:
            None
        """
        # If the log file exists, delete it
        if self.log_file.exists():
            try:
                self.log_file.unlink()
                logger.info("Circuit breaker has been reset after a successful run.")

            # If there is an error deleting the log file, log the error
            except IOError as e:
                logger.error(f"Failed to reset circuit breaker log {self.log_file}: {e}")
