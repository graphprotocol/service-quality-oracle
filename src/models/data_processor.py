"""
Data processing utility module for Service Quality Oracle.

This module handles data processing operations including:
- CSV export and file management
- Data cleaning and directory maintenance
- Indexer data filtering and organization
"""

import logging
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class DataProcessor:
    """Handles data processing and file management operations."""

    def __init__(self, project_root: Path):
        """
        Initialize the data processor.

        Args:
            project_root: Path to project root directory
        """
        # Set the project root and output directory
        self.project_root = project_root
        self.output_dir = project_root / "data" / "output"


    def export_bigquery_data_as_csvs_and_return_indexer_lists(
        self, input_data_from_bigquery: pd.DataFrame, output_date_dir: Path
    ) -> Tuple[List[str], List[str]]:
        """
        Export BigQuery data as CSVs and return lists of eligible/ineligible indexers.

        Args:
            input_data_from_bigquery: Indexer data returned from BigQuery
            output_date_dir: Path to date directory for output files

        Returns:
            Tuple[List[str], List[str]]: Two lists of indexer addresses, eligible and ineligible
        """
        # Ensure the output directory exists, creating parent directories if necessary
        output_date_dir.mkdir(exist_ok=True, parents=True)

        # Save raw data for internal use
        raw_data_path = output_date_dir / "indexer_issuance_eligibility_data.csv"
        input_data_from_bigquery.to_csv(raw_data_path, index=False)
        logger.info(f"Saved raw bigquery results df to: {raw_data_path}")

        # Filter eligible and ineligible indexers
        eligible_df = input_data_from_bigquery[input_data_from_bigquery["eligible_for_indexing_rewards"] == 1]
        ineligible_df = input_data_from_bigquery[input_data_from_bigquery["eligible_for_indexing_rewards"] == 0]

        # Save filtered data
        eligible_path = output_date_dir / "eligible_indexers.csv"
        ineligible_path = output_date_dir / "ineligible_indexers.csv"

        eligible_df[["indexer"]].to_csv(eligible_path, index=False)
        ineligible_df[["indexer"]].to_csv(ineligible_path, index=False)

        logger.info(f"Saved {len(eligible_df)} eligible indexers to: {eligible_path}")
        logger.info(f"Saved {len(ineligible_df)} ineligible indexers to: {ineligible_path}")

        # Return lists of eligible and ineligible indexers
        return eligible_df["indexer"].tolist(), ineligible_df["indexer"].tolist()


    def clean_old_date_directories(self, max_age_before_deletion: int) -> None:
        """
        Remove old date directories to prevent unlimited growth.
        
        Args:
            max_age_before_deletion: Maximum age in days before deleting data output
        """
        today = date.today()

        # Check if the output directory exists
        if not self.output_dir.exists():
            logger.warning(f"Output directory does not exist: {self.output_dir}")
            return

        directories_removed = 0

        # Only process directories with date format YYYY-MM-DD
        for item in self.output_dir.iterdir():
            if not item.is_dir():
                continue

            try:
                # Try to parse the directory name as a date
                dir_date = datetime.strptime(item.name, "%Y-%m-%d").date()
                age_days = (today - dir_date).days
                
                # Remove if older than max_age_before_deletion
                if age_days > max_age_before_deletion:
                    logger.info(f"Removing old data directory: {item} ({age_days} days old)")
                    shutil.rmtree(item)
                    directories_removed += 1

            except ValueError:
                # Skip directories that don't match date format
                logger.debug(f"Skipping non-date directory: {item.name}")
                continue

        if directories_removed > 0:
            logger.info(f"Removed {directories_removed} old data directories")
        else:
            logger.info("No old data directories found to remove")


    def get_date_output_directory(self, current_date: date) -> Path:
        """
        Get the output directory path for a specific date.
        
        Args:
            current_date: Date for which to get the output directory
            
        Returns:
            Path: Path to the date-specific output directory
        """
        return self.output_dir / current_date.strftime("%Y-%m-%d")


    def ensure_output_directory_exists(self) -> None:
        """Ensure the main output directory exists."""
        # Create the output directory if it doesn't exist
        self.output_dir.mkdir(exist_ok=True, parents=True)
        logger.debug(f"Ensured output directory exists: {self.output_dir}")
