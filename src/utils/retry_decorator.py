"""
Standardized retry decorator with consistent backoff strategy across the application.
"""

import logging
from functools import wraps
from socket import timeout as SocketTimeout
from typing import Any, Callable, Type, Union

from requests.exceptions import ConnectionError, HTTPError, Timeout
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# A standard set of exceptions that are safe to retry for network-related operations.
DEFAULT_RETRY_EXCEPTIONS = (
    ConnectionError,
    HTTPError,
    Timeout,
    SocketTimeout,
)


# fmt: off
def retry_with_backoff(
    max_attempts: int = 5,
    min_wait: int = 1,
    max_wait: int = 120,
    multiplier: int = 2,
    exceptions: Union[Type[Exception], tuple[Type[Exception], ...]] = DEFAULT_RETRY_EXCEPTIONS,
    reraise: bool = True,
) -> Callable:
    """
    Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default: 5)
        min_wait: Minimum wait time between retries in seconds (default: 1)
        max_wait: Maximum wait time between retries in seconds (default: 120)
        multiplier: Exponential backoff multiplier (default: 2)
        exceptions: Exception types to retry on (default: includes common network errors)
        reraise: Whether to reraise the exception after all attempts fail (default: True)

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        """Retry decorator with exponential backoff."""
        @retry(
            retry=retry_if_exception_type(exceptions),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=reraise,
        )
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        return wrapper


    return decorator
# fmt: on
