"""
Configuration Loader for Service Quality Oracle

This module implements TOML + environment variables:
- Config is defined in TOML
- Sensitive values are loaded from environment variables

Benefits:
- Clear separation between structure and sensitive data
- Production-ready for Docker
- Environment variable substitution with $VARIABLE_NAME syntax
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

# TODO: implement this in the requirements.txt file?
# Handle Python version compatibility for TOML loading
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Python < 3.11
    except ImportError:
        raise ImportError(
            "TOML support requires 'tomli' package for Python < 3.11. " "Install with: pip install tomli"
        ) from None

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration loading fails."""
    pass


class ConfigLoader:
    """Configuration loader with environment variable substitution"""

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

    # TODO: check this...
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

        else:
            return config_toml

    def load_config(self) -> dict[str, Any]:
        """
        Load configuration from config.toml and substitute environment variables.

        Returns:
            Dictionary containing the complete configuration with secrets loaded
            from environment variables

        Raises:
            ConfigurationError: If config file is missing or env vars are missing
        """
        try:
            # Load the TOML configuration
            with open(self.config_path, "rb") as f:
                config = tomllib.load(f)

            logger.info(f"Loaded configuration from: {self.config_path}")

        except FileNotFoundError:
            raise ConfigurationError(f"Configuration not found: {self.config_path}") from None
        except Exception as e:
            raise ConfigurationError(f"Failed to parse configuration: {e}") from e

        try:
            # Substitute environment variables throughout the configuration
            config = self._substitute_env_vars(config)

            logger.info("Successfully loaded configuration with environment variables")
            return config

        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(f"Failed to substitute environment variables: {e}") from e

    def validate_required_env_vars(self) -> None:
        """
        Validate that all required environment variables are set without loading full config.

        This can be used for early validation in startup scripts.

        Raises:
            ConfigurationError: If any required environment variables are missing
        """
        try:
            with open(self.config_path, "rb") as f:
                config = tomllib.load(f)
        except Exception as e:
            raise ConfigurationError(f"Cannot validate env vars - config error: {e}") from e

        missing_vars = []

        def check_env_vars(obj):
            if isinstance(obj, str):
                env_vars = self._env_var_pattern.findall(obj)
                for var in env_vars:
                    if os.getenv(var) is None:
                        missing_vars.append(var)
            elif isinstance(obj, dict):
                for value in obj.values():
                    check_env_vars(value)
            elif isinstance(obj, list):
                for item in obj:
                    check_env_vars(item)

        check_env_vars(config)

        if missing_vars:
            raise ConfigurationError(
                f"Missing required environment variables: {', '.join(sorted(set(missing_vars)))}"
            )

    def get_flat_config(self) -> dict[str, Any]:
        """
        Get configuration in flat format.

        Returns:
            Flat dictionary with all configuration values
        """
        config = self.load_config()

        # Convert nested structure to flat format
        flat_config = {
            # BigQuery settings
            "bigquery_location": config.get("bigquery", {}).get("BIGQUERY_LOCATION_ID", "US"),
            "bigquery_project_id": config.get("bigquery", {}).get("BIGQUERY_PROJECT_ID", "graph-mainnet"),
            "bigquery_dataset_id": config.get("bigquery", {}).get("BIGQUERY_DATASET_ID", "internal_metrics"),
            # Blockchain settings
            "contract_address": config.get("blockchain", {}).get("BLOCKCHAIN_CONTRACT_ADDRESS"),
            "contract_function": config.get("blockchain", {}).get("BLOCKCHAIN_FUNCTION_NAME"),
            "chain_id": config.get("blockchain", {}).get("BLOCKCHAIN_CHAIN_ID"),
            "rpc_providers": self._parse_rpc_urls(config.get("blockchain", {}).get("BLOCKCHAIN_RPC_URLS", [])),
            # Scheduling
            "scheduled_run_time": config.get("scheduling", {}).get("SCHEDULED_RUN_TIME"),
            # Subgraph URLs
            "subgraph_url": config.get("subgraph", {}).get("SUBGRAPH_URL_PRODUCTION"),
            # Secrets
            "google_application_credentials": config.get("secrets", {}).get("GOOGLE_APPLICATION_CREDENTIALS"),
            "private_key": config.get("secrets", {}).get("BLOCKCHAIN_PRIVATE_KEY"),
            "studio_api_key": config.get("secrets", {}).get("STUDIO_API_KEY"),
        }

        return flat_config

    def _parse_rpc_urls(self, rpc_urls: list) -> list[str]:
        """Parse RPC URLs from list format."""
        if not rpc_urls:
            raise ConfigurationError("BLOCKCHAIN_RPC_URLS is required")

        if not isinstance(rpc_urls, list) or not all(isinstance(url, str) for url in rpc_urls):
            raise ConfigurationError("RPC URLs must be a list of strings")

        valid_providers = [url.strip() for url in rpc_urls if url.strip()]
        if not valid_providers:
            raise ConfigurationError("No valid RPC providers found")

        return valid_providers


# Convenience function for easy integration with existing code
def load_config() -> dict[str, Any]:
    """
    Convenience function to load configuration.

    Returns configuration in flat format compatible with existing codebase.

    Returns:
        Dictionary containing configuration with secrets from environment variables

    Raises:
        ConfigurationError: If configuration loading fails
    """
    loader = ConfigLoader()
    return loader.get_flat_config()


# For startup validation
def validate_all_required_env_vars() -> None:
    """
    Validate that all required environment variables are set.

    Raises:
        ConfigurationError: If any required environment variables are missing
    """
    loader = ConfigLoader()
    loader.validate_required_env_vars()
