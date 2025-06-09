"""
Centralized configuration manager with validation and credential handling.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.config_loader import ConfigLoader, ConfigurationError
from src.utils.retry_decorator import retry_with_backoff

logger = logging.getLogger(__name__)


class ConfigManager:
    """Centralized configuration manager with validation and credential handling."""
    
    def __init__(self):
        self._config = None
        

    def _validate_required_fields(self, data: dict, required_fields: list[str], context: str) -> None:
        """
        Helper function to validate required fields are present in a dictionary.

        Args:
            data: Dictionary to validate
            required_fields: List of required fields
            context: Context for error message

        Raises:
            ValueError: If required fields are missing
        """
        # Validate that all required fields are present in the data
        missing_fields = [field for field in required_fields if field not in data]

        # If any required fields are missing, raise an error
        if missing_fields:
            raise ValueError(f"{context}: missing {missing_fields}")


    def load_and_validate_config(self) -> dict[str, Any]:
        """
        Load all necessary configurations using config loader, validate, and return them.
        This function is called once at startup to load the configuration.

        Returns:
            Dict[str, Any]: Config dictionary with validated and converted values.
                            {
                                "bigquery_project_id": str,
                                "bigquery_location": str,
                                "rpc_providers": list[str],
                                "contract_address": str,
                                "contract_function": str,
                                "chain_id": int,
                                "scheduled_run_time": str,
                                "batch_size": int,
                                "max_age_before_deletion": int,
                            }
        Raises:
            ConfigurationError: If configuration loading fails
            ValueError: If configuration validation fails
        """
        # If the configuration has already been loaded, return it
        if self._config is not None:
            return self._config
        
        try:
            # Load configuration using config loader
            loader = ConfigLoader()
            config = loader.get_flat_config()
            logger.info("Successfully loaded configuration")
            
            # Validate and convert chain_id to integer
            if config.get("chain_id"):
                try:
                    config["chain_id"] = int(config["chain_id"])
                except ValueError as e:
                    raise ValueError(f"Invalid BLOCKCHAIN_CHAIN_ID: {config['chain_id']} - must be an integer.") from e
                    
            # Validate scheduled run time format (HH:MM)
            if config.get("scheduled_run_time"):
                try:
                    datetime.strptime(config["scheduled_run_time"], "%H:%M")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid SCHEDULED_RUN_TIME format: {config['scheduled_run_time']} - "
                        "must be in HH:MM format"
                    ) from e
                    
            # Validate blockchain configuration contains all required fields
            required_fields = [
                "private_key",
                "contract_address",
                "contract_function",
                "chain_id",
                "scheduled_run_time",
            ]
            self._validate_required_fields(config, required_fields, "Missing required blockchain configuration")
            
            # Validate RPC providers
            if not config.get("rpc_providers") or not isinstance(config["rpc_providers"], list):
                raise ValueError("BLOCKCHAIN_RPC_URLS must be a list of valid RPC URLs")
            
            # Set the configuration in the class & return it
            self._config = config
            return config

        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(f"Configuration validation failed: {e}") from e


    @staticmethod
    def get_project_root() -> Path:
        """
        Get the path to the project root directory.
        In Docker environments, use /app. Otherwise, find by marker files.
        """
        # Use the /app directory as the project root if it exists
        docker_path = Path("/app")
        if docker_path.exists():
            return docker_path
            
        # If the /app directory doesn't exist fall back to marker files
        current_path = Path(__file__).parent
        while current_path != current_path.parent:
            if (current_path / ".gitignore").exists() or (current_path / "pyproject.toml").exists():
                logger.info(f"Found project root at: {current_path}")
                return current_path
            # Attempt to traverse upwards (will not work if the directory has no parent)
            current_path = current_path.parent
            
        # If we got here, something is wrong
        raise FileNotFoundError("Could not find project root directory. Investigate.")


class CredentialManager:
    """Handles credential management for Google Cloud services."""
    
    def __init__(self):
        pass


    def _validate_required_fields(self, data: dict, required_fields: list[str], context: str) -> None:
        """
        Helper function to validate required fields are present in a dictionary.

        Args:
            data: Dictionary to validate
            required_fields: List of required fields
            context: Context for error message

        Raises:
            ValueError: If required fields are missing
        """
        # Validate that all required fields are present in the data
        missing_fields = [field for field in required_fields if field not in data]

        # If any required fields are missing, raise an error
        if missing_fields:
            raise ValueError(f"{context}: missing {missing_fields}")


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
                required_fields = ["client_id", "client_secret", "refresh_token"]
                self._validate_required_fields(
                    creds_data, required_fields, "Incomplete authorized_user credentials"
                )
            
            elif cred_type == "service_account":
                required_fields = ["private_key", "client_email", "project_id"]
                self._validate_required_fields(
                    creds_data, required_fields, "Incomplete service_account credentials"
                )
            
            else:
                raise ValueError(
                    f"Unsupported credential type: '{cred_type}'. Expected 'authorized_user' or 'service_account'"
                )

        # If the credentials parsing fails, raise an error
        except Exception as e:
            logger.error(f"Failed to parse and validate credentials JSON: {e}")
            raise ValueError(f"Invalid credentials JSON: {e}") from e
        
        # Return the parsed credentials
        return creds_data


    def _setup_user_credentials_in_memory(self, creds_data: dict) -> None:
        """Set up user account credentials directly in memory."""
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
            google.auth._default._CREDENTIALS = credentials  # type: ignore[attr-defined]
            logger.info("Successfully loaded user account credentials from environment variable")
        
        # Clear credentials from memory
        finally:
            if "creds_data" in locals():
                creds_data.clear()


    def _setup_service_account_credentials_in_memory(self, creds_data: dict) -> None:
        """Set up service account credentials directly in memory."""
        import google.auth
        from google.oauth2 import service_account

        # Try to set up the credentials
        try:
            # Create credentials object directly from dict
            credentials = service_account.Credentials.from_service_account_info(
                creds_data
            )

            # Set credentials globally for GCP libraries
            google.auth._default._CREDENTIALS = credentials  # type: ignore[attr-defined]
            logger.info("Successfully loaded service account credentials from environment variable")
        
        # If the credentials creation fails, raise an error
        except Exception as e:
            logger.error(f"Failed to create service account credentials: {e}")
            raise ValueError(f"Invalid service account credentials: {e}") from e
        
        # Clear the original credentials dict from memory if it exists
        finally:
            if "creds_data" in locals():
                creds_data.clear()


    @retry_with_backoff(max_attempts=3, exceptions=(ValueError,))
    def setup_google_credentials(self) -> None:
        """
        Set up Google credentials directly in memory from environment variable.
        This function handles multiple credential formats securely:
        1. JSON string in GOOGLE_APPLICATION_CREDENTIALS (inline credentials)
        2. File path in GOOGLE_APPLICATION_CREDENTIALS
        3. Automatic fallback to gcloud CLI authentication
        """
        # Get the account credentials from the environment variable
        creds_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        
        # If the credentials are not set, log a warning and return
        if not creds_env:
            logger.warning(
                "GOOGLE_APPLICATION_CREDENTIALS not set. Falling back to gcloud CLI user credentials if available"
            )
            return
            
        # Case 1: JSON credentials provided inline
        if creds_env.strip().startswith("{"):
            creds_data = None
            try:
                # Parse and validate credentials
                creds_data = self._parse_and_validate_credentials_json(creds_env)
                cred_type = creds_data.get("type")
                
                # Set up credentials based on type
                if cred_type == "authorized_user":
                    self._setup_user_credentials_in_memory(creds_data.copy())
                elif cred_type == "service_account":
                    self._setup_service_account_credentials_in_memory(creds_data.copy())
                    
            except Exception as e:
                logger.error("Failed to set up credentials from environment variable")
                raise ValueError(f"Error processing inline credentials: {e}") from e
            finally:
                if creds_data is not None:
                    creds_data.clear()
        
        # Case 2: File path provided
        elif os.path.exists(creds_env):
            logger.info(f"Using credentials file: {creds_env}")
            
        # Case 3: Invalid format
        else:
            logger.warning(
                f"GOOGLE_APPLICATION_CREDENTIALS appears to be neither valid JSON nor existing file path: {creds_env[:50]}..."
            )
            logger.warning("Falling back to gcloud CLI authentication if available")


    def validate_google_credentials(self) -> bool:
        """
        Validate that Google credentials are properly configured and working.
        
        Returns:
            bool: True if credentials are valid and working
        """
        try:
            import google.auth
            
            # Try to get default credentials
            credentials, project = google.auth.default()
            
            if credentials:
                logger.info(f"Google credentials validated successfully for project: {project}")
                return True
            else:
                logger.error("No valid Google credentials found")
                return False
                
        except Exception as e:
            logger.error(f"Google credentials validation failed: {e}")
            return False


# Global instances for easy access
config_manager = ConfigManager()
credential_manager = CredentialManager() 