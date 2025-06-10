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
from src.models.blockchain_client import BlockchainClient
from src.models.data_processor import DataProcessor
from src.utils.config_loader import load_config
from src.utils.slack_notifier import create_slack_notifier

# Set up basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main(run_date_override: date = None):
    """
    Main entry point for the Service Quality Oracle.
    This function:
    1. Sets up Google credentials (if not already set up by scheduler)
    2. Fetches and processes indexer eligibility data
    3. Submits eligible indexers to the blockchain
    4. Sends Slack notifications about the run status

    Args:
        run_date_override: If provided, use this date for the run instead of today.
    """
    start_time = time.time()
    slack_notifier = None
    stage = "Initialization"

    try:
        # Load configuration to get Slack webhook and other settings
        config = load_config()
        slack_notifier = create_slack_notifier(config.get("SLACK_WEBHOOK_URL"))
        if slack_notifier:
            logger.info("Slack notifications enabled")
        else:
            logger.info("Slack notifications disabled (no webhook URL configured)")

        # Define the date for the current run
        current_run_date = run_date_override or date.today()

        # Fetch + save indexer eligibility data and return eligible list
        stage = "Data Processing"
        data_processor = DataProcessor(config)
        eligible_indexers = data_processor.process_and_get_eligible_indexers(
            start_date=current_run_date - timedelta(days=28),
            end_date=current_run_date,
            current_date=current_run_date,
        )
        logger.info(f"Found {len(eligible_indexers)} eligible indexers.")
        
        data_processor.clean_old_date_directories(config["MAX_AGE_BEFORE_DELETION"])


        # --- Blockchain Submission Stage ---
        stage = "Blockchain Submission"
        logger.info("Instantiating BlockchainClient...")
        blockchain_client = BlockchainClient()
        transaction_links = blockchain_client.batch_allow_indexers_issuance_eligibility(
            indexer_addresses=eligible_indexers,
            private_key=config["PRIVATE_KEY"],
            chain_id=config["CHAIN_ID"],
            contract_function=config["CONTRACT_FUNCTION"],
            batch_size=config["BATCH_SIZE"],
            replace=True,
        )

        # Calculate execution time and send success notification
        execution_time = time.time() - start_time
        logger.info(f"Oracle run completed successfully in {execution_time:.2f} seconds")

        if slack_notifier:
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
        error_msg = f"Oracle failed at stage '{stage}': {str(e)}"
        logger.error(error_msg, exc_info=True)

        if slack_notifier:
            try:
                slack_notifier.send_failure_notification(
                    error_message=str(e), stage=stage, execution_time=execution_time
                )
            except Exception as slack_e:
                logger.error(f"Failed to send Slack failure notification: {slack_e}", exc_info=True)

        sys.exit(1)


if __name__ == "__main__":
    main()
