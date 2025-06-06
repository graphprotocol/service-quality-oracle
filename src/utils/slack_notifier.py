"""
Slack notification utility module
Provides functionality to send notifications to Slack channels.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Module-level logger
logger = logging.getLogger(__name__)


class SlackNotifier:
    """A utility class for sending notifications to Slack via webhooks."""

    # Initialize the Slack notifier
    def __init__(self, webhook_url: str) -> None:
        """
        Initialize the Slack notifier.

        Args:
            webhook_url: The Slack webhook URL to send notifications to.
        """
        self.webhook_url = webhook_url
        self.timeout = 10  # seconds

    @retry(
        retry=retry_if_exception_type(
            (
                requests.exceptions.RequestException,
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            )
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _send_message_with_retry(self, payload: Dict) -> requests.Response:
        """
        Send a message to Slack via webhook, with retry logic for network issues.

        Args:
            payload: The message payload to send

        Returns:
            requests.Response object

        Raises:
            requests.exceptions.RequestException: If all retries fail
        """
        # Log the attempt with payload summary
        message_type = payload.get("text", "Unknown message type")
        logger.info(f"Sending Slack notification: {message_type[:50]}...")

        # Send the HTTP request to Slack webhook
        response = requests.post(
            self.webhook_url, json=payload, timeout=self.timeout, headers={"Content-Type": "application/json"}
        )

        # Log response details for debugging
        logger.debug(f"Slack API response: Status {response.status_code}, Body: {response.text[:200]}")

        # Raise exception for non-200 status codes to trigger retry
        if response.status_code != 200:
            logger.warning(f"Slack notification attempt failed with status {response.status_code}")
            response.raise_for_status()

        return response

    def _send_message(self, payload: Dict) -> bool:
        """
        Send a message to Slack via webhook with retry logic and detailed logging.

        Args:
            payload: The message payload to send

        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            # Attempt to send message with retry logic
            response = self._send_message_with_retry(payload)

            # Verify successful delivery
            if response.status_code == 200:
                logger.info("Slack notification delivered successfully")
                return True

            # If the message is not sent successfully, return False
            else:
                logger.error(f"Unexpected response after retry: {response.status_code}")
                return False

        # Handle all retry failures
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Slack notification after 3 attempts: {str(e)}")
            return False

        # Handle any other unexpected errors
        except Exception as e:
            logger.error(f"Unexpected error sending Slack notification: {str(e)}")
            return False

    def send_success_notification(
        self, eligible_indexers: List[str], total_processed: int, execution_time: Optional[float] = None
    ) -> bool:
        """
        Send a notification to Slack when the oracle run is successful.

        Args:
            eligible_indexers: List of eligible indexer addresses
            total_processed: Total number of indexers processed
            execution_time: Execution time in seconds (optional)

        Returns:
            bool: True if notification was sent successfully
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Create success message text
        text = "The Service Quality Oracle has successfully completed its run."

        # Create success message fields
        fields = [
            {"title": "Status", "value": "Successfully completed", "short": True},
            {"title": "Timestamp", "value": timestamp, "short": True},
            {"title": "Eligible Indexers", "value": str(len(eligible_indexers)), "short": True},
            {"title": "Total Processed", "value": str(total_processed), "short": True},
        ]

        # Add execution time to the message fields
        if execution_time:
            fields.append({"title": "Execution Time", "value": f"{execution_time:.2f} seconds", "short": True})

        # Create message payload
        payload = {
            "text": text,
            "attachments": [
                {"fields": fields, "footer": "Service Quality Oracle", "ts": int(datetime.now().timestamp())}
            ],
        }

        # Send message payload to Slack
        return self._send_message(payload)

    def send_failure_notification(
        self, error_message: str, stage: str, execution_time: Optional[float] = None
    ) -> bool:
        """
        Send a notification to Slack when the oracle run fails.

        Args:
            error_message: The error message that occurred
            stage: The stage where the failure occurred
            execution_time: Execution time before failure in seconds (optional)

        Returns:
            bool: True if notification was sent successfully
        """
        # Get the current timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Create failure message
        text = "The Service Quality Oracle has failed its run."

        # Create failure message fields
        fields = [
            {"title": "Status", "value": "Failed", "short": True},
            {"title": "Timestamp", "value": timestamp, "short": True},
            {"title": "Failed Stage", "value": stage, "short": True},
        ]

        # Add execution time to the message fields if one was provided
        if execution_time:
            fields.append(
                {"title": "Runtime Before Failure", "value": f"{execution_time:.2f} seconds", "short": True}
            )

        # Add error details to the message fields so we can debug the issue
        fields.append({"title": "Error Details", "value": f"```{error_message}```", "short": False})

        # Create message payload
        payload = {
            "text": text,
            "attachments": [
                {"fields": fields, "footer": "Service Quality Oracle", "ts": int(datetime.now().timestamp())}
            ],
        }

        return self._send_message(payload)

    def send_info_notification(self, message: str, title: str = "Info") -> bool:
        """
        Send an informational notification to Slack.

        Args:
            message: The message to send
            title: Title for the notification

        Returns:
            bool: True if notification was sent successfully
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Create message payload
        payload = {
            "text": f"Service Quality Oracle - {title}",
            "attachments": [
                {
                    "fields": [
                        {"title": "Message", "value": message, "short": False},
                        {"title": "Timestamp", "value": timestamp, "short": True},
                    ],
                    "footer": "Service Quality Oracle",
                    "ts": int(datetime.now().timestamp()),
                }
            ],
        }

        return self._send_message(payload)


def create_slack_notifier(webhook_url: Optional[str]) -> Optional[SlackNotifier]:
    """
    Factory function to create a SlackNotifier instance.

    Args:
        webhook_url: The Slack webhook URL (can be None)

    Returns:
        SlackNotifier instance if webhook_url is provided, None otherwise
    """
    # If the webhook URL is provided, create a SlackNotifier instance
    if webhook_url and webhook_url.strip():
        try:
            return SlackNotifier(webhook_url.strip())

        # If there is an error when trying to create the SlackNotifier instance, return None
        except Exception as e:
            logger.error(f"Failed to create Slack notifier: {str(e)}")
            return None

    # If the webhook URL is not provided, return None
    else:
        logger.info("No Slack webhook URL provided - Slack notifications disabled")
        return None
