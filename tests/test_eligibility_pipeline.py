"""
Unit tests for the EligibilityPipeline.
"""

# TODO: Test `process` method correctly separates eligible and ineligible indexers into two lists.
# TODO: Test `process` method handles an empty input DataFrame gracefully.
# TODO: Test `_generate_files` creates the three expected CSV files with the correct content.
# TODO: Test `clean_old_date_directories` correctly identifies and removes directories older than the max age.
# TODO: Test `clean_old_date_directories` does not remove directories that are not old enough.
# TODO: Test `clean_old_date_directories` handles the output directory not existing.
# TODO: Test `validate_dataframe_structure` passes with a valid DataFrame.
# TODO: Test `validate_dataframe_structure` raises `ValueError` for a DataFrame with missing columns.
# TODO: Test `get_directory_size_info` for both an existing and a non-existing directory.
