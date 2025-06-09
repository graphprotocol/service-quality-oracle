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
