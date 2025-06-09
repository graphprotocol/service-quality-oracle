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
