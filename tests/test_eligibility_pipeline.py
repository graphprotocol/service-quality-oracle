"""
Unit tests for the EligibilityPipeline.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.models.eligibility_pipeline import EligibilityPipeline


@pytest.fixture
def sample_data() -> pd.DataFrame:
    """Provides a sample DataFrame for testing."""
    return pd.DataFrame({"indexer": ["0x1", "0x2", "0x3", "0x4"], "eligible_for_indexing_rewards": [1, 0, 1, 0]})


@pytest.fixture
def pipeline(tmp_path: Path) -> EligibilityPipeline:
    """Provides an EligibilityPipeline instance using a temporary directory."""
    # The EligibilityPipeline's output dir is project_root / "data" / "output"
    # So we set the mock project_root to tmp_path
    return EligibilityPipeline(project_root=tmp_path)


def test_process_separates_indexers_correctly(pipeline: EligibilityPipeline, sample_data: pd.DataFrame):
    """
    Tests that the `process` method correctly separates eligible and ineligible indexers
    into two distinct lists.
    """
    # 1. Setup
    # Mock the internal method to prevent file I/O in this unit test
    pipeline._generate_files = lambda a, b, c, d: None

    # 2. Action
    eligible, ineligible = pipeline.process(sample_data, current_date=date.today())

    # 3. Assertions
    assert sorted(eligible) == ["0x1", "0x3"]
    assert sorted(ineligible) == ["0x2", "0x4"]


def test_process_handles_empty_dataframe(pipeline: EligibilityPipeline):
    """
    Tests that the `process` method handles an empty DataFrame without errors,
    returning two empty lists.
    """
    # 1. Setup
    empty_df = pd.DataFrame({"indexer": [], "eligible_for_indexing_rewards": []})
    pipeline._generate_files = lambda a, b, c, d: None

    # 2. Action
    eligible, ineligible = pipeline.process(empty_df, current_date=date.today())

    # 3. Assertions
    assert eligible == []
    assert ineligible == []


def test_generate_files_creates_correct_csvs(pipeline: EligibilityPipeline, sample_data: pd.DataFrame):
    """
    Tests that `_generate_files` creates the three expected CSV files with the
    correct data in the specified output directory.
    """
    # 1. Setup
    current_date_val = date.today()
    output_dir = pipeline.get_date_output_directory(current_date_val)

    eligible_df = sample_data[sample_data["eligible_for_indexing_rewards"] == 1]
    ineligible_df = sample_data[sample_data["eligible_for_indexing_rewards"] == 0]

    # 2. Action
    pipeline._generate_files(sample_data, eligible_df, ineligible_df, output_dir)

    # 3. Assertions
    raw_path = output_dir / "indexer_issuance_eligibility_data.csv"
    eligible_path = output_dir / "eligible_indexers.csv"
    ineligible_path = output_dir / "ineligible_indexers.csv"

    assert raw_path.exists()
    assert eligible_path.exists()
    assert ineligible_path.exists()

    # Verify content of eligible_indexers.csv
    eligible_content = pd.read_csv(eligible_path)
    assert eligible_content["indexer"].tolist() == ["0x1", "0x3"]


def test_clean_old_date_directories_removes_old(pipeline: EligibilityPipeline):
    """
    Tests that `clean_old_date_directories` correctly identifies and removes a directory
    that is older than the specified max age.
    """
    # 1. Setup
    max_age = 30
    old_date = date.today() - timedelta(days=max_age + 1)
    new_date = date.today() - timedelta(days=max_age - 1)

    old_dir = pipeline.get_date_output_directory(old_date)
    new_dir = pipeline.get_date_output_directory(new_date)
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)

    # 2. Action
    pipeline.clean_old_date_directories(max_age_before_deletion=max_age)

    # 3. Assertions
    assert not old_dir.exists()
    assert new_dir.exists()


def test_clean_old_directories_does_not_exist(pipeline: EligibilityPipeline):
    """
    Tests that `clean_old_date_directories` runs without errors if the main
    output directory does not exist.
    """
    # 1. Setup
    # Ensure the directory does not exist (the fixture provides a clean slate)

    # 2. Action & Assertion
    # The test passes if no exception is raised
    pipeline.clean_old_date_directories(max_age_before_deletion=30)


def test_validate_dataframe_structure_success(pipeline: EligibilityPipeline):
    """
    Tests that `validate_dataframe_structure` returns True for a DataFrame
    with the required columns.
    """
    # 1. Setup
    df = pd.DataFrame({"col1": [1], "col2": [2]})

    # 2. Action & Assertion
    assert pipeline.validate_dataframe_structure(df, required_columns=["col1", "col2"])


def test_validate_dataframe_structure_failure(pipeline: EligibilityPipeline):
    """
    Tests that `validate_dataframe_structure` raises a ValueError for a DataFrame
    with missing columns.
    """
    # 1. Setup
    df = pd.DataFrame({"col1": [1]})

    # 2. Action & Assertion
    with pytest.raises(ValueError, match="DataFrame missing required columns: .*'col2'"):
        pipeline.validate_dataframe_structure(df, required_columns=["col1", "col2"])


def test_get_directory_size_info_exists(pipeline: EligibilityPipeline):
    """
    Tests `get_directory_size_info` for an existing directory with content.
    """
    # 1. Setup
    output_dir = pipeline.output_dir
    output_dir.mkdir(parents=True)
    (output_dir / "file1.txt").write_text("hello")  # 5 bytes
    (output_dir / "subdir").mkdir()
    (output_dir / "subdir" / "file2.txt").write_text("world")  # 5 bytes

    # 2. Action
    info = pipeline.get_directory_size_info()

    # 3. Assertions
    assert info["exists"] is True
    assert info["total_size_bytes"] == 10
    assert info["directory_count"] == 1
    assert info["file_count"] == 2


def test_get_directory_size_info_not_exists(pipeline: EligibilityPipeline):
    """
    Tests `get_directory_size_info` for a non-existent directory.
    """
    # 1. Setup
    # The directory does not exist by default from the fixture

    # 2. Action
    info = pipeline.get_directory_size_info()

    # 3. Assertions
    assert info["exists"] is False
    assert info["total_size_bytes"] == 0
    assert info["directory_count"] == 0
    assert info["file_count"] == 0
