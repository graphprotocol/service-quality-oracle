"""
Service Quality Oracle's core module for fetching & processing data.

This module serves as the entry point for the oracle functionality, responsible for:
1. Fetching eligibility data from BigQuery
2. Processing indexer data to determine eligibility
3. Submitting eligible indexers to the blockchain contract

For blockchain interactions and data processing utilities, see issuance_data_access_helper.py.
"""

import logging
import os
import sys
from datetime import date, timedelta

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

# Import data access utilities with absolute import
from src.models.issuance_data_access_helper import (
    _setup_google_credentials_in_memory_from_env_var,
    batch_allow_indexers_issuance_eligibility_smart_contract,
    bigquery_fetch_and_save_indexer_issuance_eligibility_data_finally_return_eligible_indexers,
)

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
    """
    # Attempt to load google bigquery data access credentials
    try:
        import google.auth

        _ = google.auth.default()

    # If credentials could not be loaded, set them up in memory via helper function using environment variables
    except Exception:
        _setup_google_credentials_in_memory_from_env_var()

    # TODO: Move max_age_before_deletion to config.toml
    try:
        # Fetch + save indexer eligibility data and return eligible list as 'eligible_indexers' array
        eligible_indexers = (
            bigquery_fetch_and_save_indexer_issuance_eligibility_data_finally_return_eligible_indexers(
                start_date=date.today() - timedelta(days=28),
                end_date=date.today(),
                current_date=date.today(),
                max_age_before_deletion=90,
            )
        )

        # Send eligible indexers to the blockchain contract
        # TODO move batch_size to config.toml
        try:
            batch_allow_indexers_issuance_eligibility_smart_contract(
                eligible_indexers, replace=True, batch_size=250, data_bytes=b""
            )

        except Exception as e:
            logger.error(f"Failed to allow indexers to claim issuance because: {str(e)}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Failed to process indexer issuance eligibility data because: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
