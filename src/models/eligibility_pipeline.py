"""
Eligibility pipeline module for the Service Quality Oracle.

This module contains the logic for processing raw BigQuery data into a list of eligible indexers. It handles:
- Parsing and filtering of indexer performance data.
- Generation of CSV files for record-keeping.
- Cleanup of old data.
"""

import logging
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class EligibilityPipeline:
    """Handles the data processing pipeline and file management operations."""

    def __init__(self, project_root: Path):
        """
        Initialize the eligibility pipeline.

        Args:
            project_root: Path to project root directory
        """
        # Set the project root and output directory
        self.project_root = project_root
        self.output_dir = project_root / "data" / "output"


    def process(self, input_data_from_bigquery: pd.DataFrame, current_date: date) -> Tuple[List[str], List[str]]:
        """
        Process raw BigQuery data to generate data and return eligible indexer lists.

        Args:
            input_data_from_bigquery: DataFrame from BigQuery.
            current_date: The date of the current run, used for creating the output directory.

        Returns:
            Tuple[List[str], List[str]]: Two lists of indexer addresses, eligible and ineligible
        """
        # 1. Validate the structure of the input data
        required_cols = ["indexer", "eligible_for_indexing_rewards"]
        self.validate_dataframe_structure(input_data_from_bigquery, required_cols)

        # Make a copy to avoid modifying the original DataFrame and prevent SettingWithCopyWarning
        processed_df = input_data_from_bigquery.copy()

        # Coerce eligibility column to numeric, treating errors (e.g., non-numeric values) as NaN, then fill with 0
        processed_df["eligible_for_indexing_rewards"] = pd.to_numeric(
            processed_df["eligible_for_indexing_rewards"], errors="coerce"
        ).fillna(0)

        # 2. Filter data into eligible and ineligible groups
        eligible_df = processed_df[processed_df["eligible_for_indexing_rewards"] == 1].copy()

        ineligible_df = processed_df[processed_df["eligible_for_indexing_rewards"] != 1].copy()

        # 3. Generate and save files, ensuring the original data is used for the raw artifact
        output_date_dir = self.get_date_output_directory(current_date)
        self._generate_files(input_data_from_bigquery, eligible_df, ineligible_df, output_date_dir)

        # 4. Return the lists of indexers
        return eligible_df["indexer"].tolist(), ineligible_df["indexer"].tolist()


    def _generate_files(
        self, raw_data: pd.DataFrame, eligible_df: pd.DataFrame, ineligible_df: pd.DataFrame, output_date_dir: Path
    ) -> None:
        """
        Save the raw and filtered dataframes to CSV files in a date-specific directory.
        - indexer_issuance_eligibility_data.csv (raw data)
        - eligible_indexers.csv (only eligible indexer addresses)
        - ineligible_indexers.csv (only ineligible indexer addresses)

        Args:
            raw_data: The input DataFrame containing all indexer data.
            eligible_df: DataFrame containing only eligible indexers.
            ineligible_df: DataFrame containing only ineligible indexers.
            output_date_dir: The directory where files will be saved.
        """
        # Ensure the output directory exists, creating parent directories if necessary
        output_date_dir.mkdir(exist_ok=True, parents=True)

        # Save raw data for internal use
        raw_data_path = output_date_dir / "indexer_issuance_eligibility_data.csv"
        raw_data.to_csv(raw_data_path, index=False)
        logger.info(f"Saved raw BigQuery results to: {raw_data_path}")

        # Save filtered data
        eligible_path = output_date_dir / "eligible_indexers.csv"
        ineligible_path = output_date_dir / "ineligible_indexers.csv"

        eligible_df[["indexer"]].to_csv(eligible_path, index=False)
        ineligible_df[["indexer"]].to_csv(ineligible_path, index=False)

        logger.info(f"Saved {len(eligible_df)} eligible indexers to: {eligible_path}")
        logger.info(f"Saved {len(ineligible_df)} ineligible indexers to: {ineligible_path}")


    def clean_old_date_directories(self, max_age_before_deletion: int) -> None:
        """
        Remove old date directories to prevent unlimited growth.

        Args:
            max_age_before_deletion: Maximum age in days before deleting data output
        """
        if max_age_before_deletion < 0:
            logger.info("Negative max_age_before_deletion provided; no directories will be removed.")
            return

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


    def validate_dataframe_structure(self, df: pd.DataFrame, required_columns: List[str]) -> bool:
        """
        Validate that a DataFrame has the required columns.

        Args:
            df: DataFrame to validate
            required_columns: List of required column names

        Returns:
            bool: True if all required columns are present

        Raises:
            ValueError: If required columns are missing
        """
        # Check if any required columns are missing
        missing_columns = [col for col in required_columns if col not in df.columns]

        # If any required columns are missing, raise an error
        if missing_columns:
            raise ValueError(
                f"DataFrame missing required columns: {missing_columns}. Found columns: {list(df.columns)}"
            )

        # If all required columns are present, return True
        return True


    def get_directory_size_info(self) -> dict:
        """
        Get information about the output directory size and file counts.

        Returns:
            dict: Information about directory size and contents
        """
        # If the directory doesn't exist, return a dictionary with 0 values
        if not self.output_dir.exists():
            return {"exists": False, "total_size_bytes": 0, "directory_count": 0, "file_count": 0}

        total_size = 0
        file_count = 0
        directory_count = 0

        # Get the total size of the directory and the number of files and directories
        for item in self.output_dir.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1
            elif item.is_dir():
                directory_count += 1

        # Return the information about the directory size and contents
        return {
            "exists": True,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "directory_count": directory_count,
            "file_count": file_count,
            "path": str(self.output_dir),
        }
