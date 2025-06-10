"""
Centralized configuration and credential management for the Service Quality Oracle.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Handle Python version compatibility for TOML loading
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""
    pass


# --- Configuration Loading ---

class ConfigLoader:
    """Internal class to load configuration from TOML and environment variables."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the config loader"""
        self.config_path = config_path or self._get_default_config_path()
        self._env_var_pattern = re.compile(r"\$([A-Z_][A-Z0-9_]*)")


    def _get_default_config_path(self) -> str:
        """Get the default configuration template path."""
        # Check if we're in a Docker container
        docker_path = Path("/app/config.toml")
        if docker_path.exists():
            return str(docker_path)
        
        # For local development, look in project root
        current_path = Path(__file__).parent
        while current_path != current_path.parent:
            config_path = current_path / "config.toml"
            if config_path.exists():
                return str(config_path)
            current_path = current_path.parent
        
        raise ConfigurationError("Could not find config.toml in project root or Docker container")


    def _substitute_env_vars(self, config_toml: Any) -> Any:
        """
        Recursively substitute environment variables in the config.

        Supports $VARIABLE_NAME syntax for environment variable substitution.

        Args:
            config_toml: config file to process

        Returns:
            Processed config with environment variables substituted

        Raises:
            ConfigurationError: If required environment variable is missing
        """
        if isinstance(config_toml, str):
            # Find all environment variable references
            env_vars = self._env_var_pattern.findall(config_toml)


            for env_var in env_vars:
                env_value = os.getenv(env_var)
                if env_value is None:
                    raise ConfigurationError(f"Required environment variable {env_var} is not set")
            
                # Replace the environment variable reference with actual value
                config_toml = config_toml.replace(f"${env_var}", env_value)

            return config_toml
        
        elif isinstance(config_toml, dict):
            return {k: self._substitute_env_vars(v) for k, v in config_toml.items()}
        
        elif isinstance(config_toml, list):
            return [self._substitute_env_vars(item) for item in config_toml]
        
        return config_toml


    def _get_raw_config(self) -> dict:
        """
        Get raw configuration from TOML file.

        Returns:
            toml file as a dictionary
        """
        try:
            with open(self.config_path, "rb") as f:
                return tomllib.load(f)

        except FileNotFoundError as e:
            raise ConfigurationError(f"Configuration not found: {self.config_path}") from e

        except Exception as e:
            raise ConfigurationError(f"Failed to parse configuration: {e}") from e


    def get_flat_config(self) -> dict[str, Any]:
        """
        Get configuration in flat format.

        Returns:
            Flat dictionary with all configuration values
        """
        raw_config = self._get_raw_config()
        substituted_config = self._substitute_env_vars(raw_config)
        
        # fmt: off
        # Convert nested structure to flat format
        return {
            # BigQuery settings
            "BIGQUERY_LOCATION": substituted_config.get("bigquery", {}).get("BIGQUERY_LOCATION_ID", "US"),
            "BIGQUERY_PROJECT_ID": substituted_config.get("bigquery", {}).get("BIGQUERY_PROJECT_ID", "graph-mainnet"),
            "BIGQUERY_DATASET_ID": substituted_config.get("bigquery", {}).get("BIGQUERY_DATASET_ID", "internal_metrics"),
            
            # Blockchain settings
            "CONTRACT_ADDRESS": substituted_config.get("blockchain", {}).get("BLOCKCHAIN_CONTRACT_ADDRESS"),
            "CONTRACT_FUNCTION": substituted_config.get("blockchain", {}).get("BLOCKCHAIN_FUNCTION_NAME"),
            "CHAIN_ID": substituted_config.get("blockchain", {}).get("BLOCKCHAIN_CHAIN_ID"),
            "RPC_PROVIDERS": self._parse_rpc_urls(substituted_config.get("blockchain", {}).get("BLOCKCHAIN_RPC_URLS", [])),
            
            # Scheduling
            "SCHEDULED_RUN_TIME": substituted_config.get("scheduling", {}).get("SCHEDULED_RUN_TIME"),
            
            # Subgraph URLs
            "SUBGRAPH_URL": substituted_config.get("subgraph", {}).get("SUBGRAPH_URL_PRODUCTION"),
            
            # Processing settings
            "BATCH_SIZE": substituted_config.get("processing", {}).get("BATCH_SIZE", 125),
            "MAX_AGE_BEFORE_DELETION": substituted_config.get("processing", {}).get("MAX_AGE_BEFORE_DELETION", 120),
            
            # Secrets
            "GOOGLE_APPLICATION_CREDENTIALS": substituted_config.get("secrets", {}).get("GOOGLE_APPLICATION_CREDENTIALS"),
            "PRIVATE_KEY": substituted_config.get("secrets", {}).get("BLOCKCHAIN_PRIVATE_KEY"),
            "STUDIO_API_KEY": substituted_config.get("secrets", {}).get("STUDIO_API_KEY"),
            "SLACK_WEBHOOK_URL": substituted_config.get("secrets", {}).get("SLACK_WEBHOOK_URL"),
        }
        # fmt: on


    def _parse_rpc_urls(self, rpc_urls: list) -> list[str]:
        """Parse RPC URLs from list format."""
        if not rpc_urls or not isinstance(rpc_urls, list) or not all(isinstance(url, str) for url in rpc_urls):
            raise ConfigurationError("BLOCKCHAIN_RPC_URLS must be a list of valid string providers")

        valid_providers = [url.strip() for url in rpc_urls if url.strip()]
        if not valid_providers:

            raise ConfigurationError("No valid RPC providers found in BLOCKCHAIN_RPC_URLS")

        return valid_providers


    def _collect_missing_env_vars(self, obj: Any) -> list[str]:
        """
        Collect all missing environment variables from config object.

        Args:
            obj: config object to collect missing environment variables from

        Returns:
            list of missing environment variables (if any)
        """
        missing = []
        # Collect the missing enviroment vaiables using the appropriate speicifc method
        if isinstance(obj, str):
            env_vars = self._env_var_pattern.findall(obj)
            for var in env_vars:
                if os.getenv(var) is None:
                    missing.append(var)

        elif isinstance(obj, dict):
            for value in obj.values():
                missing.extend(self._collect_missing_env_vars(value))

        elif isinstance(obj, list):
            for item in obj:
                missing.extend(self._collect_missing_env_vars(item))

        # After all the missing variables have been collected, return the list
        return missing


    def get_missing_env_vars(self) -> list[str]:
        raw_config = self._get_raw_config()
        return self._collect_missing_env_vars(raw_config)


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("CHAIN_ID"):
        try:
            config["CHAIN_ID"] = int(config["CHAIN_ID"])
        except (ValueError, TypeError) as e:
            raise ConfigurationError(f"Invalid CHAIN_ID: {config['CHAIN_ID']} - must be an integer.") from e
    
    if config.get("SCHEDULED_RUN_TIME"):
        try:
            datetime.strptime(config["SCHEDULED_RUN_TIME"], "%H:%M")
        except (ValueError, TypeError) as e:
            raise ConfigurationError(f"Invalid SCHEDULED_RUN_TIME: {config['SCHEDULED_RUN_TIME']} - must be HH:MM.") from e
            
    required = ["PRIVATE_KEY", "CONTRACT_ADDRESS", "CONTRACT_FUNCTION", "CHAIN_ID", "SCHEDULED_RUN_TIME"]
    missing = [field for field in required if not config.get(field)]
    if missing:
        raise ConfigurationError(f"Missing required configuration fields: {', '.join(missing)}")
        
    return config


def load_config() -> dict[str, Any]:
    """Loads, validates, and returns the application configuration."""
    loader = ConfigLoader()
    flat_config = loader.get_flat_config()
    logger.info("Successfully loaded configuration")
    return _validate_config(flat_config)


def validate_all_required_env_vars() -> None:
    """Validates that all required environment variables are set."""
    loader = ConfigLoader()
    missing = loader.get_missing_env_vars()
    if missing:
        raise ConfigurationError(f"Missing required environment variables: {', '.join(sorted(set(missing)))}")
    logger.info("Successfully validated all required environment variables")


# --- Credential Management ---

class CredentialManager:
    """Handles credential management for Google Cloud services."""


    def _parse_and_validate_credentials_json(self, creds_env: str) -> dict:
        """
        Parse and validate Google credentials JSON from environment variable.

        Args:
            creds_env: JSON string containing credentials

        Returns:
            dict: Parsed and validated credentials data

        Raises:
            ValueError: If JSON is invalid or credentials are incomplete
        """
        # Try to parse the credentials
        try:
            # Parse the credentials
            creds_data = json.loads(creds_env)
            cred_type = creds_data.get("type", "")

            # Validate the credentials data based on the type
            if cred_type == "authorized_user":
                required = ["client_id", "client_secret", "refresh_token"]
                if not all(k in creds_data for k in required):
                    raise ValueError("Incomplete authorized_user credentials")

            elif cred_type == "service_account":
                required = ["private_key", "client_email", "project_id"]
                if not all(k in creds_data for k in required):
                    raise ValueError("Incomplete service_account credentials")

            else:
                raise ValueError(f"Unsupported credential type: '{cred_type}'")

            return creds_data

        except Exception as e:
            raise ValueError(f"Invalid credentials JSON: {e}") from e


    def _setup_user_credentials_from_dict(self, creds_data: dict) -> None:
        """Set up user account credentials directly from a dictionary."""
        import google.auth
        from google.oauth2.credentials import Credentials
    
        # Try to set up the credentials
        try:
            credentials = Credentials(
                token=None,
                refresh_token=creds_data.get("refresh_token"),
                client_id=creds_data.get("client_id"),
                client_secret=creds_data.get("client_secret"),
                token_uri="https://oauth2.googleapis.com/token",
            )

            # Set credentials globally for GCP libraries
            google.auth._default._CREDENTIALS = credentials # type: ignore[attr-defined]
            logger.info("Successfully loaded user account credentials from environment variable")

        # Clear credentials from memory
        finally:
            if "creds_data" in locals():
                creds_data.clear()


    def _setup_service_account_credentials_from_dict(self, creds_data: dict) -> None:
        """Set up service account credentials directly from a dictionary."""
        import google.auth
        from google.oauth2 import service_account

        # Try to set up the credentials
        try:
            # Create credentials object directly from dict
            credentials = service_account.Credentials.from_service_account_info(creds_data)

            # Set credentials globally for GCP libraries
            google.auth._default._CREDENTIALS = credentials
            logger.info("Successfully loaded service account credentials from environment variable")
        
        # If the credentials creation fails, raise an error
        except Exception as e:
            raise ValueError(f"Invalid service account credentials: {e}") from e

        # Clear the original credentials dict from memory if it exists
        finally:
            if "creds_data" in locals():
                creds_data.clear()


    def setup_google_credentials(self) -> None:
        """
        Set up Google credentials directly in memory from environment variable.
        This function handles multiple credential formats securely:
        1. JSON string in GOOGLE_APPLICATION_CREDENTIALS (inline credentials)
        2. File path in GOOGLE_APPLICATION_CREDENTIALS
        """
        # Get the account credentials from the environment variable
        creds_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

        # If the credentials are not set, log a warning and return
        if not creds_env:
            logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set. Falling back to gcloud CLI.")
            return

        # Case 1: JSON credentials provided inline
        if creds_env.strip().startswith("{"):
            creds_data = None
            try:
                # Parse and validate the credentials
                creds_data = self._parse_and_validate_credentials_json(creds_env)

                # Set up the credentials based on the type
                if creds_data.get("type") == "authorized_user":
                    self._setup_user_credentials_from_dict(creds_data.copy())
                else:
                    self._setup_service_account_credentials_from_dict(creds_data.copy())

            # If the credentials parsing fails, raise an error
            except Exception as e:
                raise ValueError(f"Error processing inline credentials: {e}") from e
        
            # Clear the credentials from memory
            finally:
                if creds_data:
                    creds_data.clear()
        
        # Case 2: File path provided
        elif not os.path.exists(creds_env):
            logger.warning(f"GOOGLE_APPLICATION_CREDENTIALS is not valid JSON or a file path.")
            logger.warning("Falling back to gcloud CLI authentication if available.")

# Global instance for easy access
credential_manager = CredentialManager() 