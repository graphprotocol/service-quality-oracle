"""
Unit tests for the configuration loader and validator.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.utils.configuration import (
    ConfigLoader,
    ConfigurationError,
    CredentialManager,
    _validate_config,
    load_config,
    validate_all_required_env_vars,
)

# --- Constants for Mocks ---

MOCK_TOML_CONFIG = """
[secrets]
BLOCKCHAIN_PRIVATE_KEY = "$TEST_PRIVATE_KEY"
STUDIO_API_KEY = "$STUDIO_API_KEY"

[scheduling]
SCHEDULED_RUN_TIME = "10:00"

[bigquery]
BIGQUERY_PROJECT_ID = "test-project"

[blockchain]
BLOCKCHAIN_RPC_URLS = ["http://main.com", " http://backup.com ", ""]

[eligibility_criteria]
MIN_ONLINE_DAYS = "5" # Test string to int conversion
"""

MOCK_TOML_INVALID_INT = """
[eligibility_criteria]
MIN_ONLINE_DAYS = "not-an-integer"
"""

MOCK_TOML_EMPTY_INT = """
[eligibility_criteria]
MIN_ONLINE_DAYS = "" # Test empty string to None conversion
"""

MOCK_TOML_NULL_INT = """
[eligibility_criteria]
MIN_ONLINE_DAYS = # Test TOML null to None conversion
"""

MOCK_SERVICE_ACCOUNT_JSON = (
    '{"type": "service_account", "private_key": "pk", "client_email": "ce", "project_id": "pi"}'
)
MOCK_AUTH_USER_JSON = '{"type": "authorized_user", "client_id": "ci", "client_secret": "cs", "refresh_token": "rt"}'


# --- Fixtures ---


@pytest.fixture
def mock_service_account_json() -> str:
    """Provides a mock service account JSON string."""
    return '{"type": "service_account", "private_key": "pk", "client_email": "ce", "project_id": "pi"}'


@pytest.fixture
def mock_auth_user_json() -> str:
    """Provides a mock authorized user JSON string."""
    return '{"type": "authorized_user", "client_id": "ci", "client_secret": "cs", "refresh_token": "rt"}'


@pytest.fixture
def full_valid_config() -> dict:
    """Provides a complete and valid configuration dictionary for testing."""
    return {
        "BIGQUERY_LOCATION_ID": "us-central1",
        "BIGQUERY_PROJECT_ID": "test-project",
        "BIGQUERY_DATASET_ID": "test-dataset",
        "BIGQUERY_TABLE_ID": "test-table",
        "MIN_ONLINE_DAYS": 5,
        "MIN_SUBGRAPHS": 10,
        "MAX_LATENCY_MS": 5000,
        "MAX_BLOCKS_BEHIND": 100,
        "BLOCKCHAIN_CONTRACT_ADDRESS": "0x1234",
        "BLOCKCHAIN_FUNCTION_NAME": "allow",
        "BLOCKCHAIN_CHAIN_ID": 1,
        "BLOCKCHAIN_RPC_URLS": ["http://test.com"],
        "BLOCK_EXPLORER_URL": "http://etherscan.io",
        "TX_TIMEOUT_SECONDS": 180,
        "SCHEDULED_RUN_TIME": "10:30",
        "SUBGRAPH_URL_PRE_PRODUCTION": "http://pre-prod.com",
        "SUBGRAPH_URL_PRODUCTION": "http://prod.com",
        "BATCH_SIZE": 100,
        "MAX_AGE_BEFORE_DELETION": 90,
        "BIGQUERY_ANALYSIS_PERIOD_DAYS": 28,
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/creds.json",  # Added for completeness
        "PRIVATE_KEY": "0x123",
        "STUDIO_API_KEY": "key",
        "STUDIO_DEPLOY_KEY": "key",
        "SLACK_WEBHOOK_URL": "http://slack.com",
        "ETHERSCAN_API_KEY": "key",
        "ARBITRUM_API_KEY": "key",
    }


@pytest.fixture
def temp_config_file(tmp_path: Path) -> str:
    """Creates a temporary config file with standard mock data."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(MOCK_TOML_CONFIG)
    return str(config_path)


@pytest.fixture
def mock_env(monkeypatch):
    """A fixture to mock standard environment variables."""
    monkeypatch.setenv("TEST_PRIVATE_KEY", "0x12345")
    monkeypatch.setenv("STUDIO_API_KEY", "studio-key")
    return monkeypatch


@pytest.fixture
def mock_google_auth():
    """Mocks the google.auth and dependent libraries to isolate credential logic."""
    with patch("src.utils.configuration.google.oauth2.service_account.Credentials") as mock_service_account, patch(
        "src.utils.configuration.google.oauth2.credentials.Credentials"
    ) as mock_creds, patch("src.utils.configuration.google.auth") as mock_auth:
        # Configure the mock to prevent AttributeError for '_default'
        mock_auth._default = MagicMock()

        yield {
            "service_account": mock_service_account,
            "creds": mock_creds,
            "auth": mock_auth,
        }


# --- Test Classes ---


class TestConfigLoader:
    """Tests for the ConfigLoader class."""

    def test_successful_loading_and_substitution(self, temp_config_file: str, mock_env):
        """
        GIVEN a valid config file and set environment variables
        WHEN the config is loaded
        THEN it should correctly parse TOML, substitute env vars, and handle types.
        """
        # Arrange
        loader = ConfigLoader(config_path=temp_config_file)

        # Act
        config = loader.get_flat_config()

        # Assert
        assert config["PRIVATE_KEY"] == "0x12345"
        assert config["STUDIO_API_KEY"] == "studio-key"
        assert config["SCHEDULED_RUN_TIME"] == "10:00"
        assert config["BIGQUERY_PROJECT_ID"] == "test-project"
        assert config["BLOCKCHAIN_RPC_URLS"] == ["http://main.com", "http://backup.com"]
        assert config["MIN_ONLINE_DAYS"] == 5  # Should be converted to int

    def test_optional_integer_fields_default_to_none(self, temp_config_file: str, mock_env):
        """
        GIVEN a config file where optional integer fields are missing
        WHEN the config is loaded
        THEN the missing fields should default to None.
        """
        # Arrange
        loader = ConfigLoader(config_path=temp_config_file)

        # Act
        config = loader.get_flat_config()

        # Assert
        # These fields are not in MOCK_TOML_CONFIG, so they should be None
        assert config["MAX_LATENCY_MS"] is None
        assert config["BATCH_SIZE"] is None

    def test_raises_error_if_config_missing(self):
        """
        GIVEN an invalid file path
        WHEN the config is loaded
        THEN it should raise a ConfigurationError.
        """
        with pytest.raises(ConfigurationError, match="Configuration not found"):
            ConfigLoader(config_path="/a/fake/path/config.toml").get_flat_config()

    def test_raises_error_if_toml_is_malformed(self, tmp_path: Path):
        """
        GIVEN a malformed TOML file
        WHEN the config is loaded
        THEN it should raise a ConfigurationError.
        """
        # Arrange
        config_path = tmp_path / "config.toml"
        config_path.write_text("this is not valid toml")

        # Act & Assert
        with pytest.raises(ConfigurationError, match="Failed to parse configuration"):
            ConfigLoader(config_path=str(config_path)).get_flat_config()

    def test_raises_error_if_env_var_missing(self, temp_config_file: str):
        """
        GIVEN a config referencing an unset environment variable
        WHEN the config is loaded
        THEN it should raise a ConfigurationError.
        """
        # Act & Assert
        # Note: `mock_env` fixture is NOT used here.
        with pytest.raises(ConfigurationError, match="Required environment variable TEST_PRIVATE_KEY is not set"):
            ConfigLoader(config_path=temp_config_file).get_flat_config()

    def test_raises_error_for_invalid_integer_value(self, tmp_path: Path):
        """
        GIVEN a config with a non-integer value for a numeric field
        WHEN the config is loaded
        THEN it should raise a ValueError.
        """
        # Arrange
        config_path = tmp_path / "config.toml"
        config_path.write_text(MOCK_TOML_INVALID_INT)
        loader = ConfigLoader(config_path=str(config_path))

        # Act & Assert
        with pytest.raises(ValueError):
            loader.get_flat_config()

    def test_get_default_config_path_docker(self):
        """
        GIVEN the app is running in a Docker-like environment
        WHEN the default config path is retrieved
        THEN it should return the /app/config.toml path.
        """
        # Arrange
        with patch("pathlib.Path.exists", return_value=True) as mock_exists:
            # Act
            found_path = ConfigLoader()._get_default_config_path()

            # Assert
            assert "/app/config.toml" in found_path
            mock_exists.assert_called_once_with(Path("/app/config.toml"))

    @pytest.mark.parametrize(
        "start_dir_str",
        ["src/utils", "src/utils/deep/nested"],
        ids=["from-nested-dir", "from-deeply-nested-dir"],
    )
    def test_get_default_config_path_local_dev(self, monkeypatch, tmp_path: Path, start_dir_str: str):
        """
        GIVEN a local dev environment with config in project root
        WHEN the default config path is retrieved from a nested directory
        THEN it should find config.toml by traversing up the directory tree.
        """
        # Arrange
        project_root = tmp_path / "project"
        start_dir = project_root / start_dir_str
        start_dir.mkdir(parents=True)
        (project_root / "config.toml").touch()
        monkeypatch.chdir(start_dir)

        with patch("src.utils.configuration.__file__", str(start_dir / "configuration.py")), patch(
            "pathlib.Path.exists"
        ) as mock_exists:
            mock_exists.side_effect = lambda p: p == project_root / "config.toml"
            # Act
            loader = ConfigLoader()
            found_path = loader.config_path

            # Assert
            assert found_path == str(project_root / "config.toml")

    def test_get_default_config_path_not_found(self):
        """
        GIVEN no config.toml exists in the expected locations
        WHEN the default path is retrieved
        THEN it should raise a ConfigurationError.
        """
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(ConfigurationError, match="Could not find config.toml"):
                ConfigLoader()

    def test_get_missing_env_vars(self, temp_config_file: str):
        """
        GIVEN a config with missing environment variables
        WHEN get_missing_env_vars is called
        THEN it should return a list of the missing variables.
        """
        # Arrange
        # `mock_env` is not used, so TEST_PRIVATE_KEY and STUDIO_API_KEY are unset
        loader = ConfigLoader(config_path=temp_config_file)

        # Act
        missing_vars = loader.get_missing_env_vars()

        # Assert
        assert sorted(missing_vars) == sorted(["TEST_PRIVATE_KEY", "STUDIO_API_KEY"])

    @pytest.mark.parametrize(
        "rpc_input, expected_output",
        [
            (["http://main.com", " http://backup.com ", ""], ["http://main.com", "http://backup.com"]),
            ([], []),
            (None, []),
            ("not-a-list", []),
            (["  "], []),
            (["http://test.com"], ["http://test.com"]),
        ],
    )
    def test_parse_rpc_urls(self, rpc_input, expected_output):
        """
        GIVEN various RPC URL list formats (including invalid types)
        WHEN _parse_rpc_urls is called
        THEN it should return a clean list of valid URLs or an empty list.
        """
        # Arrange
        loader = ConfigLoader(config_path="dummy_path")  # Path doesn't matter here

        # Act
        result = loader._parse_rpc_urls(rpc_input)

        # Assert
        assert result == expected_output

    def test_empty_string_for_integer_field_is_none(self, tmp_path: Path):
        """
        GIVEN a config with an empty string for a numeric field
        WHEN the config is loaded
        THEN it should be converted to None.
        """
        # Arrange
        config_path = tmp_path / "config.toml"
        config_path.write_text(MOCK_TOML_EMPTY_INT)
        loader = ConfigLoader(config_path=str(config_path))

        # Act
        config = loader.get_flat_config()

        # Assert
        assert config["MIN_ONLINE_DAYS"] is None

    def test_null_value_for_integer_field_is_none(self, tmp_path: Path):
        """
        GIVEN a config with a null value for a numeric field
        WHEN the config is loaded
        THEN it should be converted to None.
        """
        # Arrange
        config_path = tmp_path / "config.toml"
        config_path.write_text(MOCK_TOML_NULL_INT)
        loader = ConfigLoader(config_path=str(config_path))

        # Act
        config = loader.get_flat_config()

        # Assert
        assert config["MIN_ONLINE_DAYS"] is None


class TestConfigValidation:
    """Tests for config validation logic."""

    def test_validate_config_success(self, full_valid_config: dict):
        """
        GIVEN a complete, valid config dictionary
        WHEN _validate_config is called
        THEN it should complete without raising an exception.
        """
        # Act & Assert
        _validate_config(full_valid_config)  # Should not raise

    def test_validate_config_handles_zero_values(self, full_valid_config: dict):
        """
        GIVEN a config where a required numeric field is 0
        WHEN _validate_config is called
        THEN it should not raise an error, treating 0 as a valid value.
        """
        # Arrange
        config = full_valid_config.copy()
        config["MIN_ONLINE_DAYS"] = 0  # Set a required field to 0

        # Act & Assert
        try:
            _validate_config(config)
        except ConfigurationError as e:
            pytest.fail(f"Validation incorrectly failed for a field with value 0: {e}")

    def test_validate_config_missing_required_field(self):
        """
        GIVEN a config dictionary missing required fields
        WHEN _validate_config is called
        THEN it should raise a ConfigurationError listing the missing fields.
        """
        # Arrange
        config = {"BIGQUERY_PROJECT_ID": "test-project"}  # Missing many fields

        # Act & Assert
        with pytest.raises(ConfigurationError, match="Missing required configuration fields"):
            _validate_config(config)

    def test_validate_config_invalid_time_format(self, full_valid_config: dict):
        """
        GIVEN a config with an invalid SCHEDULED_RUN_TIME format
        WHEN _validate_config is called
        THEN it should raise a ConfigurationError.
        """
        # Arrange
        config = full_valid_config.copy()
        config["SCHEDULED_RUN_TIME"] = "invalid-time"

        # Act & Assert
        with pytest.raises(ConfigurationError, match="Invalid SCHEDULED_RUN_TIME"):
            _validate_config(config)

    def test_validate_config_invalid_time_type(self, full_valid_config: dict):
        """
        GIVEN a config with a non-string value for SCHEDULED_RUN_TIME
        WHEN _validate_config is called
        THEN it should raise a ConfigurationError.
        """
        # Arrange
        config = full_valid_config.copy()
        config["SCHEDULED_RUN_TIME"] = 1030  # Invalid type

        # Act & Assert
        with pytest.raises(ConfigurationError, match="Invalid SCHEDULED_RUN_TIME"):
            _validate_config(config)

    def test_validate_all_required_env_vars_success(self, mock_env):
        """
        GIVEN all required environment variables are set
        WHEN validate_all_required_env_vars is called
        THEN it should complete without raising an exception.
        """
        # Arrange
        with patch("src.utils.configuration.ConfigLoader") as mock_loader:
            mock_loader.return_value.get_missing_env_vars.return_value = []

            # Act & Assert
            validate_all_required_env_vars()  # Should not raise
            mock_loader.return_value.get_missing_env_vars.assert_called_once()

    def test_validate_all_required_env_vars_failure(self):
        """
        GIVEN that required environment variables are missing
        WHEN validate_all_required_env_vars is called
        THEN it should raise a ConfigurationError.
        """
        # Arrange
        with patch("src.utils.configuration.ConfigLoader") as mock_loader:
            mock_loader.return_value.get_missing_env_vars.return_value = ["MISSING_VAR"]

            # Act & Assert
            with pytest.raises(ConfigurationError, match="Missing required environment variables: MISSING_VAR"):
                validate_all_required_env_vars()


class TestCredentialManager:
    """Tests for the CredentialManager class."""

    @pytest.mark.parametrize(
        "creds_json, expected_error_msg",
        [
            ('{"type": "service_account", "client_email": "ce", "project_id": "pi"}', "Incomplete service_account"),
            ('{"type": "authorized_user", "client_id": "ci", "client_secret": "cs"}', "Incomplete authorized_user"),
            ('{"type": "unsupported"}', "Unsupported credential type"),
            ("{not valid json}", "Invalid credentials JSON"),
        ],
    )
    def test_parse_and_validate_credentials_json_raises_for_invalid(self, creds_json, expected_error_msg):
        """
        GIVEN various forms of invalid or incomplete credential JSON
        WHEN _parse_and_validate_credentials_json is called
        THEN it should raise a ValueError with a specific message.
        """
        # Arrange
        manager = CredentialManager()

        # Act & Assert
        with pytest.raises(ValueError, match=expected_error_msg):
            manager._parse_and_validate_credentials_json(creds_json)

    @pytest.mark.parametrize(
        "creds_json, expected_error_msg",
        [
            ('{"type": "service_account", "client_email": "ce", "project_id": "pi"}', "Incomplete service_account"),
            ('{"type": "authorized_user", "client_id": "ci", "client_secret": "cs"}', "Incomplete authorized_user"),
            ('{"type": "unsupported"}', "Unsupported credential type"),
            ("{not valid json}", "Error processing inline credentials"),
        ],
    )
    def test_setup_google_credentials_raises_for_invalid_json(self, mock_env, creds_json, expected_error_msg):
        """
        GIVEN various forms of invalid or incomplete credential JSON
        WHEN setup_google_credentials is called
        THEN it should raise a ValueError with a specific message.
        """
        # Arrange
        mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", creds_json)
        manager = CredentialManager()

        # Act & Assert
        with pytest.raises(ValueError, match=expected_error_msg):
            manager.setup_google_credentials()

    def test_setup_google_credentials_handles_service_account_json(
        self, mock_env, mock_google_auth, mock_service_account_json
    ):
        """
        GIVEN valid inline service account JSON in the environment variable
        WHEN setup_google_credentials is called
        THEN it should correctly parse and set up the credentials.
        """
        # Arrange
        mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", mock_service_account_json)
        manager = CredentialManager()

        # Act
        manager.setup_google_credentials()

        # Assert
        creds_dict = json.loads(mock_service_account_json)
        mock_google_auth["service_account"].from_service_account_info.assert_called_once_with(creds_dict)
        assert mock_google_auth["auth"]._default._CREDENTIALS is not None

    def test_setup_service_account_raises_value_error_on_sdk_failure(
        self, mock_env, mock_google_auth, mock_service_account_json
    ):
        """
        GIVEN the Google SDK fails to create credentials from service account info
        WHEN setup_google_credentials is called
        THEN it should raise a ValueError detailing the nested exceptions.
        """
        # Arrange
        mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", mock_service_account_json)
        # Simulate the Google SDK raising an exception when creating credentials from dict
        mock_google_auth["service_account"].from_service_account_info.side_effect = Exception("SDK Error")
        manager = CredentialManager()

        # Act & Assert
        # The error is wrapped twice, so we check for the final message.
        expected_msg = "Error processing inline credentials: Invalid service account credentials: SDK Error"
        with pytest.raises(ValueError, match=expected_msg):
            manager.setup_google_credentials()

    def test_setup_google_credentials_handles_authorized_user_json(
        self, mock_env, mock_google_auth, mock_auth_user_json
    ):
        """
        GIVEN valid inline authorized user JSON in the environment variable
        WHEN setup_google_credentials is called
        THEN it should correctly parse and set up the credentials.
        """
        # Arrange
        mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", mock_auth_user_json)
        manager = CredentialManager()

        # Act
        manager.setup_google_credentials()

        # Assert
        mock_google_auth["creds"].assert_called_once_with(
            token=None,
            refresh_token="rt",
            client_id="ci",
            client_secret="cs",
            token_uri="https://oauth2.googleapis.com/token",
        )
        assert mock_google_auth["auth"]._default._CREDENTIALS is not None

    def test_setup_authorized_user_raises_on_sdk_failure(self, mock_env, mock_google_auth, mock_auth_user_json):
        """
        GIVEN the Google SDK fails to create credentials from authorized user info
        WHEN setup_google_credentials is called
        THEN it should raise an exception detailing the nested error.
        """
        # Arrange
        mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", mock_auth_user_json)
        mock_google_auth["creds"].side_effect = Exception("SDK Error")
        manager = CredentialManager()

        # Act & Assert
        with pytest.raises(Exception, match="Error processing inline credentials: SDK Error"):
            manager.setup_google_credentials()

    @patch("src.utils.configuration.json.loads")
    def test_setup_google_credentials_clears_dictionary_on_success(
        self, mock_json_loads, mock_env, mock_google_auth, mock_service_account_json
    ):
        """
        GIVEN valid credentials that are processed successfully
        WHEN setup_google_credentials is called
        THEN it should clear the credentials dictionary for security.
        """
        # Arrange
        mock_creds_dict = MagicMock()
        mock_creds_dict.get.return_value = "service_account"  # Mock the "type"
        mock_json_loads.return_value = mock_creds_dict
        mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", mock_service_account_json)
        manager = CredentialManager()

        # Act
        manager.setup_google_credentials()

        # Assert
        mock_creds_dict.clear.assert_called_once()

    @patch("src.utils.configuration.CredentialManager._parse_and_validate_credentials_json")
    def test_setup_google_credentials_clears_dictionary_on_failure(
        self, mock_parse_and_validate, mock_env, mock_service_account_json
    ):
        """
        GIVEN credentials that cause a failure during setup
        WHEN setup_google_credentials is called
        THEN it should still clear the credentials dictionary for security.
        """
        # Arrange
        mock_creds_dict = MagicMock()
        mock_parse_and_validate.return_value = mock_creds_dict
        mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", mock_service_account_json)
        manager = CredentialManager()

        # Simulate a failure after parsing by making setup fail
        with patch.object(manager, "_setup_service_account_credentials_from_dict", side_effect=Exception("Setup failed")):
            # Act
            with pytest.raises(Exception, match="Setup failed"):
                manager.setup_google_credentials()

        # Assert
        mock_creds_dict.clear.assert_called_once()

    def test_setup_google_credentials_handles_invalid_file_path(self, mock_env, caplog):
        """
        GIVEN a file path in GOOGLE_APPLICATION_CREDENTIALS that does not exist
        WHEN setup_google_credentials is called
        THEN it should log a warning about an invalid path.
        """
        # Arrange
        mock_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/a/fake/path.json")
        manager = CredentialManager()

        with patch("src.utils.configuration.os.path.exists", return_value=False):
            # Act
            manager.setup_google_credentials()

            # Assert
            assert "is not valid JSON or a file path" in caplog.text

    def test_setup_google_credentials_not_set(self, mock_env, caplog):
        """
        GIVEN the GOOGLE_APPLICATION_CREDENTIALS env var is not set
        WHEN setup_google_credentials is called
        THEN it should log a warning and return.
        """
        # Arrange
        mock_env.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        manager = CredentialManager()

        # Act
        manager.setup_google_credentials()

        # Assert
        assert "GOOGLE_APPLICATION_CREDENTIALS not set" in caplog.text


class TestLoadConfig:
    """High-level tests for the main `load_config` function."""

    @patch("src.utils.configuration._validate_config")
    @patch("src.utils.configuration.ConfigLoader")
    def test_load_config_happy_path(self, mock_loader_cls, mock_validate, mock_env):
        """
        GIVEN a valid configuration environment
        WHEN load_config is called
        THEN it should load, flatten, and validate the config.
        """
        # Arrange
        mock_flat_config = {"key": "value"}
        mock_loader_instance = mock_loader_cls.return_value
        mock_loader_instance.get_flat_config.return_value = mock_flat_config

        # Act
        config = load_config()

        # Assert
        mock_loader_cls.assert_called_once()
        mock_loader_instance.get_flat_config.assert_called_once()
        mock_validate.assert_called_once_with(mock_flat_config)
        assert config == mock_validate.return_value
