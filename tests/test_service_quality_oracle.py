"""
Unit tests for the main ServiceQualityOracle orchestrator.
"""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.models import service_quality_oracle

MOCK_CONFIG = {
    "SLACK_WEBHOOK_URL": "http://fake.slack.com",
    "BIGQUERY_PROJECT_ID": "test-proj",
    "BIGQUERY_DATASET_ID": "test-dset",
    "BIGQUERY_TABLE_ID": "test-tbl",
    "BIGQUERY_LOCATION_ID": "us-central1",
    "MIN_ONLINE_DAYS": 5,
    "MIN_SUBGRAPHS": 10,
    "MAX_LATENCY_MS": 5000,
    "MAX_BLOCKS_BEHIND": 100,
    "MAX_AGE_BEFORE_DELETION": 90,
    "BIGQUERY_ANALYSIS_PERIOD_DAYS": 28,
    "BLOCKCHAIN_RPC_URLS": ["http://fake-rpc.com"],
    "BLOCKCHAIN_CONTRACT_ADDRESS": "0x1234",
    "BLOCK_EXPLORER_URL": "http://etherscan.io",
    "TX_TIMEOUT_SECONDS": 180,
    "PRIVATE_KEY": "0xfakekey",
    "BLOCKCHAIN_CHAIN_ID": 1,
    "BLOCKCHAIN_FUNCTION_NAME": "allow",
    "BATCH_SIZE": 100,
}


@pytest.fixture
def mock_dependencies():
    """A comprehensive fixture to mock all external dependencies of the main oracle function."""
    with (
        patch("src.models.service_quality_oracle.credential_manager") as mock_creds,
        patch("src.models.service_quality_oracle.load_config", return_value=MOCK_CONFIG) as mock_load_config,
        patch("src.models.service_quality_oracle.create_slack_notifier") as mock_create_slack,
        patch("src.models.service_quality_oracle.BigQueryProvider") as mock_bq_provider,
        patch("src.models.service_quality_oracle.EligibilityPipeline") as mock_pipeline,
        patch("src.models.service_quality_oracle.BlockchainClient") as mock_blockchain_client,
        patch("src.models.service_quality_oracle.sys.exit") as mock_exit,
    ):
        # Configure the return values of mocked instances
        mock_bq_provider.return_value.fetch_indexer_issuance_eligibility_data.return_value = pd.DataFrame()
        mock_pipeline.return_value.process.return_value = (["0xEligible"], ["0xIneligible"])
        mock_blockchain_client.return_value.batch_allow_indexers_issuance_eligibility.return_value = [
            "http://tx-link"
        ]

        yield {
            "creds": mock_creds,
            "load_config": mock_load_config,
            "create_slack": mock_create_slack,
            "slack_notifier": mock_create_slack.return_value,
            "BigQueryProvider": mock_bq_provider,
            "bq_provider_instance": mock_bq_provider.return_value,
            "EligibilityPipeline": mock_pipeline,
            "pipeline_instance": mock_pipeline.return_value,
            "BlockchainClient": mock_blockchain_client,
            "blockchain_client_instance": mock_blockchain_client.return_value,
            "exit": mock_exit,
        }


def test_main_successful_run(mock_dependencies: dict):
    """
    Tests the successful end-to-end run of `main()` with all dependencies mocked,
    ensuring each component is called correctly and a success notification is sent.
    """
    # 1. Action
    service_quality_oracle.main()

    # 2. Assertions
    # Initialization
    mock_dependencies["creds"].setup_google_credentials.assert_called_once()
    mock_dependencies["load_config"].assert_called_once()
    mock_dependencies["create_slack"].assert_called_once_with(MOCK_CONFIG["SLACK_WEBHOOK_URL"])

    # BigQuery Fetching
    mock_dependencies["BigQueryProvider"].assert_called_once()
    mock_dependencies["bq_provider_instance"].fetch_indexer_issuance_eligibility_data.assert_called_once()

    # Eligibility Pipeline
    mock_dependencies["EligibilityPipeline"].assert_called_once()
    mock_dependencies["pipeline_instance"].process.assert_called_once()
    mock_dependencies["pipeline_instance"].clean_old_date_directories.assert_called_once_with(
        MOCK_CONFIG["MAX_AGE_BEFORE_DELETION"]
    )

    # Blockchain Submission
    mock_dependencies["BlockchainClient"].assert_called_once()
    mock_dependencies[
        "blockchain_client_instance"
    ].batch_allow_indexers_issuance_eligibility.assert_called_once_with(
        indexer_addresses=["0xEligible"],
        private_key=MOCK_CONFIG["PRIVATE_KEY"],
        chain_id=MOCK_CONFIG["BLOCKCHAIN_CHAIN_ID"],
        contract_function=MOCK_CONFIG["BLOCKCHAIN_FUNCTION_NAME"],
        batch_size=MOCK_CONFIG["BATCH_SIZE"],
        replace=True,
    )

    # Final Notifications and Exit
    mock_dependencies["slack_notifier"].send_success_notification.assert_called_once()
    mock_dependencies["exit"].assert_not_called()


@pytest.mark.parametrize(
    "failure_stage, expected_stage_name",
    [
        ("bq_provider_instance", "Data Fetching from BigQuery"),
        ("pipeline_instance", "Data Processing and Artifact Generation"),
        ("blockchain_client_instance", "Blockchain Submission"),
    ],
)
def test_main_failure_at_stage(mock_dependencies: dict, failure_stage: str, expected_stage_name: str):
    """
    Tests that `main` sends a failure notification and exits if any stage of the
    pipeline fails.
    """
    # 1. Setup
    # Simulate an error in one of the main methods
    if failure_stage == "bq_provider_instance":
        mock_dependencies[failure_stage].fetch_indexer_issuance_eligibility_data.side_effect = Exception(
            "BigQuery Error"
        )
    elif failure_stage == "pipeline_instance":
        mock_dependencies[failure_stage].process.side_effect = Exception("Pipeline Error")
    elif failure_stage == "blockchain_client_instance":
        mock_dependencies[failure_stage].batch_allow_indexers_issuance_eligibility.side_effect = Exception(
            "Blockchain Error"
        )

    # 2. Action
    service_quality_oracle.main()

    # 3. Assertions
    mock_dependencies["slack_notifier"].send_failure_notification.assert_called_once()
    # Check that the stage name in the notification is correct
    call_args, call_kwargs = mock_dependencies["slack_notifier"].send_failure_notification.call_args
    assert call_kwargs["stage"] == expected_stage_name

    mock_dependencies["exit"].assert_called_once_with(1)


def test_main_with_date_override(mock_dependencies: dict):
    """
    Tests that `main()` correctly uses the `run_date_override` parameter to calculate
    the date range for the BigQuery query.
    """
    # 1. Setup
    override_date = date(2023, 10, 27)
    expected_start_date = override_date - pd.Timedelta(days=MOCK_CONFIG["BIGQUERY_ANALYSIS_PERIOD_DAYS"])

    # 2. Action
    service_quality_oracle.main(run_date_override=override_date)

    # 3. Assertions
    # Check that the BQ provider was called with the correct, overridden date range
    call_args, call_kwargs = mock_dependencies[
        "bq_provider_instance"
    ].fetch_indexer_issuance_eligibility_data.call_args
    assert call_kwargs["start_date"] == expected_start_date
    assert call_kwargs["end_date"] == override_date


def test_main_with_no_eligible_indexers(mock_dependencies: dict):
    """
    Tests that the pipeline completes gracefully and sends a success notification
    even when no eligible indexers are found.
    """
    # 1. Setup
    # Simulate the pipeline returning no eligible indexers
    mock_dependencies["pipeline_instance"].process.return_value = ([], ["0x1", "0x2"])

    # 2. Action
    service_quality_oracle.main()

    # 3. Assertions
    # Check that the blockchain client was still called, but with an empty list
    mock_dependencies[
        "blockchain_client_instance"
    ].batch_allow_indexers_issuance_eligibility.assert_called_once_with(
        indexer_addresses=[],
        private_key=MOCK_CONFIG["PRIVATE_KEY"],
        chain_id=MOCK_CONFIG["BLOCKCHAIN_CHAIN_ID"],
        contract_function=MOCK_CONFIG["BLOCKCHAIN_FUNCTION_NAME"],
        batch_size=MOCK_CONFIG["BATCH_SIZE"],
        replace=True,
    )

    # Ensure a success notification is still sent
    mock_dependencies["slack_notifier"].send_success_notification.assert_called_once()
    mock_dependencies["exit"].assert_not_called()
