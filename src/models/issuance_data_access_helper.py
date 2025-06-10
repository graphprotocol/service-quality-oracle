"""
Helper module containing high-level functions for the Service Quality Oracle.

This module focuses on:
- Main data processing
- BigQuery data fetching and processing
- Integration between different components
"""

import logging
from datetime import date
from typing import List

from tenacity import retry, stop_after_attempt, wait_exponential

from src.models.bigquery_data_access_provider import BigQueryProvider
from src.models.data_processor import DataProcessor
from src.utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=30, max=120), reraise=True)
def bigquery_fetch_and_save_indexer_issuance_eligibility_data_finally_return_eligible_indexers(
    start_date: date,
    end_date: date,
    current_date: date,
    max_age_before_deletion: int,
) -> List[str]:
    """
    Main function to fetch and process data from BigQuery.

    Args:
        start_date: Start date for BigQuery data
        end_date: End date for BigQuery data
        current_date: Current date for output directory
        max_age_before_deletion: Maximum age in days before deleting old data

    Returns:
        List[str]: List of indexers that should be allowed issuance based on BigQuery data
    """
    # Load configuration
    config_manager = ConfigManager()
    config = config_manager.load_and_validate_config()
    project_root = config_manager.get_project_root()

    # Initialize bigquery provider
    bq_provider = BigQueryProvider(
        project=str(config["bigquery_project_id"]), location=str(config["bigquery_location"])
    )

    # Initialize data processor
    data_processor = DataProcessor(project_root)

    try:
        # Fetch eligibility dataframe
        logger.info(f"Fetching eligibility data between {start_date} and {end_date}")
        indexer_issuance_eligibility_data = bq_provider.fetch_indexer_issuance_eligibility_data(
            start_date, end_date
        )
        logger.info(f"Retrieved issuance eligibility data for {len(indexer_issuance_eligibility_data)} indexers")

        # Get output directory for current date
        date_dir = data_processor.get_date_output_directory(current_date)

        # Export data and get indexer lists
        logger.info(f"Attempting to export indexer issuance eligibility lists to: {date_dir}")
        eligible_indexers, ineligible_indexers = (
            data_processor.export_bigquery_data_as_csvs_and_return_indexer_lists(
                indexer_issuance_eligibility_data, date_dir
            )
        )
        logger.info("Exported indexer issuance eligibility lists.")

        # Clean old eligibility lists
        logger.info("Cleaning old eligibility lists.")
        data_processor.clean_old_date_directories(max_age_before_deletion)

        # Log final summary
        logger.info(f"Processing complete. Output available at: {date_dir}")
        logger.info(
            f"No. of eligible indexers to insert into smart contract on "
            f"{date.today()} is: {len(eligible_indexers)}"
        )

        # Return list of indexers that should be allowed issuance
        return eligible_indexers

    except Exception as e:
        logger.error(f"Failed to fetch and process BigQuery data: {str(e)}")
        raise
