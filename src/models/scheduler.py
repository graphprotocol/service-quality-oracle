import logging
import os
import sys
import time
from datetime import datetime, timedelta

import pytz
import schedule
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.models.issuance_data_access_helper import (
    _setup_google_credentials_in_memory_from_env_var,
)
from src.utils.config_loader import load_config
from src.utils.slack_notifier import create_slack_notifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("oracle-scheduler")
# Path to store last run info
LAST_RUN_FILE = "/app/data/last_run.txt"
HEALTHCHECK_FILE = "/app/healthcheck"

# Create a global slack notifier instance
slack_notifier = None


def get_last_run_date():
    """Get the date of the last successful run from a persistent file"""
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE) as f:
                last_run_str = f.read().strip()
                return datetime.strptime(last_run_str, "%Y-%m-%d").date()
        except Exception as e:
            logger.error(f"Error reading last run date: {e}")
    return None


def save_last_run_date(run_date):
    """Save the date of the last successful run to a file that we continuously overwrite each time"""
    try:
        os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
        with open(LAST_RUN_FILE, "w") as f:
            f.write(run_date.strftime("%Y-%m-%d"))
    except Exception as e:
        logger.error(f"Error saving last run date: {e}")


def update_healthcheck(message=None):
    """Update the healthcheck file with current timestamp and optional message"""
    try:
        with open(HEALTHCHECK_FILE, "w") as f:
            timestamp = datetime.now().isoformat()
            f.write(f"Last update: {timestamp}")
            if message:
                f.write(f"\n{message}")
    except Exception as e:
        logger.warning(f"Failed to update healthcheck file: {e}")


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=60, max=600),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(
        f"Retry attempt {retry_state.attempt_number} after error: {retry_state.outcome.exception()}"
    ),
)
def run_oracle(force_date=None):
    """
    Function to run the Service Quality Oracle

    Args:
        force_date: If provided, override the date for this run
    """
    global slack_notifier
    today = force_date or datetime.now().date()
    start_time = datetime.now()
    logger.info(f"Starting Service Quality Oracle run at {start_time} for date {today}")
    # Ensure we have valid google credentials before proceeding
    _setup_google_credentials_in_memory_from_env_var()

    # Attempt to run the oracle
    try:
        # Load latest configuration using config loader
        load_config()

        # Run the oracle
        import src.models.issuance_eligibility_oracle_core as oracle

        oracle.main()

        # Record successful run and overwrite the last run date
        save_last_run_date(today)
        end_time = datetime.now()
        duration_in_seconds = (end_time - start_time).total_seconds()
        success_message = f"Run completed successfully for {today}. Duration: {duration_in_seconds:.2f}s"
        logger.info(f"Service Quality Oracle {success_message}")

        # Touch healthcheck file to indicate successful runs
        update_healthcheck(success_message)

        # Send success notification from scheduler
        if slack_notifier:
            slack_notifier.send_success_notification(
                message=f"Run completed successfully for {today}. Duration: {duration_in_seconds:.2f}s",
                title="Scheduled Run Success",
            )

        # Return True to indicate success
        return True

    # If there is an error when trying to run the oracle, log the error and raise an exception
    except Exception as e:
        error_message = f"Run failed due to: {str(e)}"
        logger.error(error_message, exc_info=True)

        # Update healthcheck file to indicate failure
        update_healthcheck(f"ERROR: {error_message}")

        # Send failure notification to slack
        if slack_notifier:
            duration = (datetime.now() - start_time).total_seconds()
            slack_notifier.send_failure_notification(
                error_message=str(e),
                stage="Scheduled Run" if force_date is None else f"Missed Run ({force_date})",
                execution_time=duration,
            )

        # Raise an exception to indicate failure
        raise


def check_missed_runs():
    """Check if we missed any runs and execute them if needed"""
    global slack_notifier
    today = datetime.now().date()
    last_run = get_last_run_date()
    if last_run is None:
        logger.info("No record of previous runs. Will run at next scheduled time.")
        return False
    if last_run < today - timedelta(days=1):
        # We missed at least one day
        missed_days = (today - last_run).days - 1
        logger.warning(f"Detected {missed_days} missed runs. Last run was on {last_run}.")

        # Send notification about missed runs
        if slack_notifier:
            message = (
                f"Detected {missed_days} missed oracle runs. "
                f"Last successful run was on {last_run}. "
                "Attempting to execute missed run for yesterday."
            )
            slack_notifier.send_info_notification(
                message=message,
                title="Missed Runs Detected",
            )

        # Run for the missed day (just run for yesterday, not all missed days)
        yesterday = today - timedelta(days=1)
        logger.info(f"Executing missed run for {yesterday}")
        try:
            run_oracle(force_date=yesterday)
            return True
        except Exception as e:
            logger.error(f"Failed to execute missed run for {yesterday}: {e}")
            return False
    return False


def initialize():
    """Initialize the scheduler and validate configuration"""
    global slack_notifier
    logger.info("Initializing scheduler...")
    try:
        # Early validation of required environment variables
        from src.utils.config_loader import validate_all_required_env_vars

        logger.info("Validating required environment variables...")
        validate_all_required_env_vars()

        # Validate credentials early to fail fast if there are issues
        _setup_google_credentials_in_memory_from_env_var()

        # Load and validate configuration
        config = load_config()

        # Initialize Slack notifications
        slack_notifier = create_slack_notifier(config.get("slack_webhook_url"))
        if slack_notifier:
            logger.info("Slack notifications enabled for scheduler")

            # Send startup notification
            startup_message = (
                f"Service Quality Oracle scheduler started successfully.\n"
                f"**Scheduled time:** {config['scheduled_run_time']} UTC\n"
                f"**Environment:** {os.environ.get('ENVIRONMENT', 'unknown')}"
            )
            slack_notifier.send_info_notification(
                message=startup_message,
                title="Scheduler Started",
            )
        else:
            logger.info("Slack notifications disabled for scheduler")

        # Set timezone for consistent scheduling
        timezone = pytz.timezone("UTC")
        logger.info(f"Using timezone: {timezone}")
        # Schedule the job
        run_time = config["scheduled_run_time"]
        logger.info(f"Scheduling daily run at {run_time} UTC")
        schedule.every().day.at(run_time).do(run_oracle)
        # Create initial healthcheck file
        update_healthcheck("Scheduler initialized")
        # Run on startup if requested
        if os.environ.get("RUN_ON_STARTUP", "false").lower() == "true":
            logger.info("RUN_ON_STARTUP=true, executing oracle immediately")
            run_oracle()
        else:
            # Check for missed runs
            logger.info("Checking for missed runs...")
            if check_missed_runs():
                logger.info("Executed missed run successfully")
            else:
                logger.info("No missed runs to execute")
        return config
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {e}", exc_info=True)

        # Try to send failure notification even if initialization failed
        if slack_notifier:
            slack_notifier.send_failure_notification(
                error_message=str(e), stage="Scheduler Initialization", execution_time=0
            )

        sys.exit(1)


if __name__ == "__main__":
    # Initialize the scheduler
    config = initialize()
    logger.info("Scheduler started and waiting for scheduled runs")

    # Main loop
    try:
        while True:
            schedule.run_pending()
            # Update healthcheck file periodically (every 30 seconds)
            if datetime.now().second % 30 == 0:
                update_healthcheck("Scheduler heartbeat")

            # Sleep
            time.sleep(15)

    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")

        if slack_notifier:
            slack_notifier.send_info_notification(
                message="Scheduler stopped by user interrupt", title="Scheduler Stopped"
            )

    except Exception as e:
        logger.error(f"Scheduler crashed: {e}", exc_info=True)

        # Send failure notification to slack
        if slack_notifier:
            slack_notifier.send_failure_notification(
                error_message=str(e), stage="Scheduler Runtime", execution_time=0
            )

        # Exit the scheduler
        sys.exit(1)
