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

