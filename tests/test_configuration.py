"""
Unit tests for the configuration loader and validator.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.configuration import (
    ConfigLoader,
    ConfigurationError,
    CredentialManager,
    _validate_config,
    validate_all_required_env_vars,
)

# A mock TOML config string that uses an environment variable
MOCK_TOML_CONFIG = """
[secrets]
BLOCKCHAIN_PRIVATE_KEY = "$TEST_PRIVATE_KEY"

[scheduling]
SCHEDULED_RUN_TIME = "10:00"

[bigquery]
BIGQUERY_PROJECT_ID = "test-project"
"""


@pytest.fixture
def temp_config_file(tmp_path: Path) -> str:
    """Creates a temporary config file and returns its path."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(MOCK_TOML_CONFIG)
    return str(config_path)


@pytest.fixture
def mock_env(monkeypatch):
    """A fixture to mock environment variables."""
    monkeypatch.setenv("TEST_PRIVATE_KEY", "0x12345")
    return monkeypatch


# 1. ConfigLoader Tests


def test_successful_config_loading(temp_config_file: str, mock_env):
    """
    Tests the happy path for ConfigLoader, including parsing a TOML file and
    substituting an environment variable.
    """
    # 1. Action
    loader = ConfigLoader(config_path=temp_config_file)
    config = loader.get_flat_config()

    # 2. Assertions
    assert config["PRIVATE_KEY"] == "0x12345"
    assert config["SCHEDULED_RUN_TIME"] == "10:00"
    assert config["BIGQUERY_PROJECT_ID"] == "test-project"


def test_loader_raises_error_if_config_missing():
    """Tests that a ConfigurationError is raised if the config file does not exist."""
    with pytest.raises(ConfigurationError, match="Configuration not found"):
        ConfigLoader(config_path="/a/fake/path/config.toml").get_flat_config()


def test_loader_raises_error_if_toml_is_malformed(tmp_path: Path):
    """Tests that a ConfigurationError is raised for a malformed TOML file."""
    config_path = tmp_path / "config.toml"
    config_path.write_text("this is not valid toml")

    with pytest.raises(ConfigurationError, match="Failed to parse configuration"):
        ConfigLoader(config_path=str(config_path)).get_flat_config()


def test_loader_raises_error_if_env_var_missing(temp_config_file: str):
    """
    Tests that a ConfigurationError is raised if a required environment variable is not set.
    Note: This test does not use the `mock_env` fixture.
    """
    with pytest.raises(ConfigurationError, match="Required environment variable TEST_PRIVATE_KEY is not set"):
        ConfigLoader(config_path=temp_config_file).get_flat_config()


# 2. Validation Tests


def test_validate_config_missing_required_field():
    """
    Tests that _validate_config raises a ConfigurationError if a required field is missing.
    """
    # Create a dummy config that is missing a required field
    config = {"BIGQUERY_PROJECT_ID": "test-project"}  # Missing many fields

    with pytest.raises(ConfigurationError, match="Missing required configuration fields"):
        _validate_config(config)


def test_validate_config_invalid_time_format():
    """
    Tests that _validate_config raises a ConfigurationError for an invalid time format.
    """
    # Create a full dummy config, but with one invalid field
    config = {f: "dummy" for f in _validate_config.__closure__[0].cell_contents}
    config["SCHEDULED_RUN_TIME"] = "invalid-time"

    with pytest.raises(ConfigurationError, match="Invalid SCHEDULED_RUN_TIME"):
        _validate_config(config)


def test_get_missing_env_vars(temp_config_file: str):
    """
    Tests that get_missing_env_vars correctly identifies unset environment variables
    that are referenced in the config file.
    """
    # 1. Action
    # This test does not use the `mock_env` fixture, so TEST_PRIVATE_KEY is not set
    loader = ConfigLoader(config_path=temp_config_file)
    missing_vars = loader.get_missing_env_vars()

    # 2. Assertions
    assert missing_vars == ["TEST_PRIVATE_KEY"]


# 3. CredentialManager Tests


@pytest.fixture
def mock_google_auth():
    """Mocks the google.auth and dependent libraries."""
    with (
        patch("src.utils.configuration.google.auth") as mock_auth,
        patch("src.utils.configuration.google.oauth2.credentials") as mock_creds,
        patch("src.utils.configuration.google.oauth2.service_account") as mock_service_account,
    ):
        yield {
            "auth": mock_auth,
            "creds": mock_creds,
            "service_account": mock_service_account,
        }


def test_credential_manager_service_account_json(mock_env, mock_google_auth):
    """Tests that the credential manager can handle inline service account JSON."""
    # 1. Setup
    creds_json = '{"type": "service_account", "private_key": "pk", "client_email": "ce", "project_id": "pi"}'
    mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", creds_json)

    # 2. Action
    CredentialManager().setup_google_credentials()

    # 3. Assertions
    mock_google_auth["service_account"].Credentials.from_service_account_info.assert_called_once()


def test_credential_manager_authorized_user_json(mock_env, mock_google_auth):
    """Tests that the credential manager can handle inline authorized user JSON."""
    # 1. Setup
    creds_json = '{"type": "authorized_user", "client_id": "ci", "client_secret": "cs", "refresh_token": "rt"}'
    mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", creds_json)

    # 2. Action
    CredentialManager().setup_google_credentials()

    # 3. Assertions
    mock_google_auth["creds"].Credentials.assert_called_once()


def test_credential_manager_invalid_path(mock_env):
    """Tests that the credential manager warns and continues if the path is invalid."""
    # 1. Setup
    mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/a/fake/path.json")

    # 2. Action
    # Test succeeds if no exception is raised
    CredentialManager().setup_google_credentials()


def test_credential_manager_invalid_json(mock_env):
    """Tests that a ValueError is raised for malformed JSON."""
    # 1. Setup
    mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "{not valid json}")

    # 2. Action & Assertion
    with pytest.raises(ValueError, match="Error processing inline credentials"):
        CredentialManager().setup_google_credentials()


# 4. Standalone Validator Tests


def test_validate_all_required_env_vars_success(mock_env):
    """
    Tests that `validate_all_required_env_vars` passes when all variables are set.
    """
    # 1. Setup
    # The mock_env fixture sets the required TEST_PRIVATE_KEY
    with patch("src.utils.configuration.ConfigLoader") as mock_loader:
        # Simulate that no missing env vars were found
        mock_loader.return_value.get_missing_env_vars.return_value = []

        # 2. Action & Assertion
        # Test passes if no exception is raised
        validate_all_required_env_vars()
        mock_loader.return_value.get_missing_env_vars.assert_called_once()


def test_validate_all_required_env_vars_failure():
    """
    Tests that `validate_all_required_env_vars` fails when variables are missing.
    """
    # 1. Setup
    with patch("src.utils.configuration.ConfigLoader") as mock_loader:
        # Simulate that a missing env var was found
        mock_loader.return_value.get_missing_env_vars.return_value = ["MISSING_VAR"]

        # 2. Action & Assertion
        with pytest.raises(ConfigurationError, match="Missing required environment variables: MISSING_VAR"):
            validate_all_required_env_vars()
