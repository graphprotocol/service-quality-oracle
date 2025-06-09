"""
Service Quality Oracle's core module for fetching & processing data.
This module serves as the entry point for the oracle functionality, responsible for:
1. Fetching eligibility data from BigQuery
2. Processing indexer data to determine eligibility
3. Submitting eligible indexers to the blockchain contract
4. Sending Slack notifications about run status
"""

import logging
import os
import sys
import time
from datetime import date, timedelta

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

# Import data access utilities with absolute import
from src.models.issuance_data_access_helper import (
    batch_allow_indexers_issuance_eligibility_smart_contract,
    bigquery_fetch_and_save_indexer_issuance_eligibility_data_finally_return_eligible_indexers,
)
from src.utils.config_loader import load_config
from src.utils.config_manager import credential_manager
from src.utils.slack_notifier import create_slack_notifier

# Set up basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """
    Main entry point for the Service Quality Oracle.
    This function:
    1. Sets up Google credentials (if not already set up by scheduler)
    2. Fetches and processes indexer eligibility data
    3. Submits eligible indexers to the blockchain
    4. Sends Slack notifications about the run status
    """
    start_time = time.time()
    slack_notifier = None

    try:
        # Load configuration to get Slack webhook and other settings
        config = load_config()
        slack_notifier = create_slack_notifier(config.get("SLACK_WEBHOOK_URL"))
        if slack_notifier:
            logger.info("Slack notifications enabled")
        else:
            logger.info("Slack notifications disabled (no webhook URL configured)")

    except Exception as e:
        logger.error(f"Failed to load configuration: {str(e)}")
        sys.exit(1)

    try:
        # Attempt to load google bigquery data access credentials
        try:
            # fmt: off
            import google.auth
            _ = google.auth.default()
            # fmt: on

        # If credentials could not be loaded, set them up in memory via helper function using environment variables
        except Exception:
            credential_manager.setup_google_credentials()

        try:
            # Fetch + save indexer eligibility data and return eligible list as 'eligible_indexers' array
            eligible_indexers = (
                bigquery_fetch_and_save_indexer_issuance_eligibility_data_finally_return_eligible_indexers(
                    start_date=date.today() - timedelta(days=28),
                    end_date=date.today(),
                    current_date=date.today(),
                    max_age_before_deletion=config.get("MAX_AGE_BEFORE_DELETION"),
                )
            )

            logger.info(f"Found {len(eligible_indexers)} eligible indexers.")

            # Send eligible indexers to the blockchain contract
            try:
                transaction_links = batch_allow_indexers_issuance_eligibility_smart_contract(
                    eligible_indexers, replace=True, batch_size=config.get("BATCH_SIZE"), data_bytes=b""
                )

                # Calculate execution time and send success notification
                execution_time = time.time() - start_time
                logger.info(f"Oracle run completed successfully in {execution_time:.2f} seconds")

                if slack_notifier:
                    # Calculate batch information for notification
                    batch_count = len(transaction_links) if transaction_links else 0
                    total_processed = len(eligible_indexers)

                    slack_notifier.send_success_notification(
                        eligible_indexers=eligible_indexers,
                        total_processed=total_processed,
                        execution_time=execution_time,
                        transaction_links=transaction_links,
                        batch_count=batch_count,
                    )

            except Exception as e:
                execution_time = time.time() - start_time
                error_msg = f"Failed to allow indexers to claim issuance because: {str(e)}"
                logger.error(error_msg)

                if slack_notifier:
                    slack_notifier.send_failure_notification(
                        error_message=str(e), stage="Blockchain Submission", execution_time=execution_time
                    )

                sys.exit(1)

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Failed to process indexer issuance eligibility data because: {str(e)}"
            logger.error(error_msg)

            if slack_notifier:
                slack_notifier.send_failure_notification(
                    error_message=str(e), stage="Data Processing", execution_time=execution_time
                )

            sys.exit(1)

    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"Oracle initialization or authentication failed: {str(e)}"
        logger.error(error_msg)

        if slack_notifier:
            slack_notifier.send_failure_notification(
                error_message=str(e), stage="Initialization", execution_time=execution_time
            )

        sys.exit(1)


if __name__ == "__main__":
    main()
