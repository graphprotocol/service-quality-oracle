"""
Unit tests for the BigQueryProvider.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.models.bigquery_provider import BigQueryProvider

# Mock configuration values
MOCK_PROJECT = "test-project"
MOCK_LOCATION = "test-location"
MOCK_TABLE_NAME = "test.dataset.table"
MOCK_MIN_ONLINE_DAYS = 5
MOCK_MIN_SUBGRAPHS = 10
MOCK_MAX_LATENCY_MS = 5000
MOCK_MAX_BLOCKS_BEHIND = 50000


@pytest.fixture
def mock_bpd():
    """Fixture to mock the bigframes.pandas module."""
    with patch("src.models.bigquery_provider.bpd") as mock_bpd_module:
        # We need to mock the nested attribute access `bpd.options.bigquery`
        # and then allow attributes to be set on it.
        mock_options = MagicMock()
        mock_bigquery = MagicMock()
        mock_options.bigquery = mock_bigquery
        mock_bpd_module.options = mock_options
        yield mock_bpd_module


@pytest.fixture
def provider(mock_bpd: MagicMock) -> BigQueryProvider:
    """Fixture to create a BigQueryProvider instance with mocked dependencies."""
    return BigQueryProvider(
        project=MOCK_PROJECT,
        location=MOCK_LOCATION,
        table_name=MOCK_TABLE_NAME,
        min_online_days=MOCK_MIN_ONLINE_DAYS,
        min_subgraphs=MOCK_MIN_SUBGRAPHS,
        max_latency_ms=MOCK_MAX_LATENCY_MS,
        max_blocks_behind=MOCK_MAX_BLOCKS_BEHIND,
    )


# 1. Test Initialization


def test_initialization(provider: BigQueryProvider, mock_bpd: MagicMock):
    """
    Tests that BigQueryProvider initializes correctly, setting BigQuery options and instance variables.
    """
    # Assertions
    # Check that BigQuery options were configured
    assert mock_bpd.options.bigquery.project == MOCK_PROJECT
    assert mock_bpd.options.bigquery.location == MOCK_LOCATION

    # Check that instance variables are set correctly
    assert provider.table_name == MOCK_TABLE_NAME
    assert provider.min_online_days == MOCK_MIN_ONLINE_DAYS
    assert provider.min_subgraphs == MOCK_MIN_SUBGRAPHS
    assert provider.max_latency_ms == MOCK_MAX_LATENCY_MS
    assert provider.max_blocks_behind == MOCK_MAX_BLOCKS_BEHIND


# 2. Test Query Construction


def test_get_indexer_eligibility_query_constructs_correctly(provider: BigQueryProvider):
    """
    Tests that _get_indexer_eligibility_query constructs a query string that
    contains all the dynamic configuration parameters.
    """
    # 1. Action
    start_date_val = date(2025, 1, 1)
    end_date_val = date(2025, 1, 28)
    query = provider._get_indexer_eligibility_query(start_date=start_date_val, end_date=end_date_val)

    # 2. Assertions
    assert isinstance(query, str)
    assert MOCK_TABLE_NAME in query
    assert str(MOCK_MAX_LATENCY_MS) in query
    assert str(MOCK_MAX_BLOCKS_BEHIND) in query
    assert str(MOCK_MIN_SUBGRAPHS) in query
    assert str(MOCK_MIN_ONLINE_DAYS) in query
    assert start_date_val.strftime("%Y-%m-%d") in query
    assert end_date_val.strftime("%Y-%m-%d") in query


# 3. Test Data Reading


def test_read_gbq_dataframe_success(provider: BigQueryProvider, mock_bpd: MagicMock):
    """
    Tests the success case for _read_gbq_dataframe, ensuring it returns a DataFrame.
    """
    # 1. Setup
    mock_df = pd.DataFrame({"col1": [1, 2]})

    # The call chain is bpd.read_gbq(query).to_pandas()
    mock_bpd.read_gbq.return_value.to_pandas.return_value = mock_df

    # 2. Action
    result_df = provider._read_gbq_dataframe("SELECT * FROM table")

    # 3. Assertions
    mock_bpd.read_gbq.assert_called_once_with("SELECT * FROM table")
    mock_bpd.read_gbq.return_value.to_pandas.assert_called_once()
    pd.testing.assert_frame_equal(result_df, mock_df)


def test_read_gbq_dataframe_retry_and_fail(provider: BigQueryProvider, mock_bpd: MagicMock):
    """
    Tests that _read_gbq_dataframe retries on connection errors and eventually fails.
    """
    # 1. Setup
    # The decorator is configured with max_attempts=10
    expected_attempts = 10
    error_to_raise = ConnectionError("Test connection error")
    mock_bpd.read_gbq.side_effect = error_to_raise

    # 2. Action and Assertion
    with pytest.raises(ConnectionError, match="Test connection error"):
        provider._read_gbq_dataframe("SELECT * FROM table")

    assert mock_bpd.read_gbq.call_count == expected_attempts


# 4. Test Orchestration


def test_fetch_indexer_issuance_eligibility_data_orchestration(provider: BigQueryProvider):
    """
    Tests that the main `fetch_indexer_issuance_eligibility_data` method correctly
    orchestrates calls to its internal helper methods.
    """
    # 1. Setup
    start_date_val = date(2025, 1, 1)
    end_date_val = date(2025, 1, 28)
    mock_query = "SELECT * FROM mock_table;"
    mock_df = pd.DataFrame({"eligible": [1]})

    # Mock the internal methods
    provider._get_indexer_eligibility_query = MagicMock(return_value=mock_query)
    provider._read_gbq_dataframe = MagicMock(return_value=mock_df)

    # 2. Action
    result_df = provider.fetch_indexer_issuance_eligibility_data(
        start_date=start_date_val,
        end_date=end_date_val,
    )

    # 3. Assertions
    # Verify that the query builder was called correctly
    provider._get_indexer_eligibility_query.assert_called_once_with(
        start_date=start_date_val,
        end_date=end_date_val,
    )

    # Verify that the data reader was called with the query from the previous step
    provider._read_gbq_dataframe.assert_called_once_with(mock_query)

    # Verify that the final result is the DataFrame from the reader
    pd.testing.assert_frame_equal(result_df, mock_df)
