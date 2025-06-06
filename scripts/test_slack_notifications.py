#!/usr/bin/env python3
"""
Test script for Slack notifications.
This script tests the Slack notification functionality without running the full oracle.
"""

import logging
import os
import sys
import time
from typing import Optional

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("slack-notifier-test")

from src.utils.config_loader import load_config
from src.utils.slack_notifier import SlackNotifier, create_slack_notifier


def load_slack_configuration() -> Optional[str]:
    """
    Load Slack webhook URL from configuration.
    
    Returns:
        Slack webhook URL if found, None otherwise
    """
    # Load webhook_url from environment variable
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if slack_webhook_url and slack_webhook_url.strip():
        logger.info("Slack webhook URL loaded from environment variable")
        return slack_webhook_url.strip()


def create_and_validate_slack_notifier(webhook_url: str) -> Optional[SlackNotifier]:
    """
    Create and validate Slack notifier instance.
    
    Args:
        webhook_url: The Slack webhook URL
        
    Returns:
        SlackNotifier instance if successful, None otherwise
    """
    # Create notifier instance using factory function
    notifier = create_slack_notifier(webhook_url)
    
    if not notifier:
        logger.error("Failed to create Slack notifier instance")
        return None
        
    logger.info("Slack notifier created successfully")
    return notifier


def test_info_notification(notifier: SlackNotifier) -> bool:
    """
    Test sending an informational notification to Slack.
    
    Args:
        notifier: Configured SlackNotifier instance
        
    Returns:
        True if test passes, False otherwise
    """
    # Send test info notification with sample message
    logger.info("Testing info notification...")
    
    success = notifier.send_info_notification(
        message="Test send info notification",
        title="Test Notification"
    )
    
    if success:
        logger.info("Info notification TEST PASSED")
        return True
    else:
        logger.error("Info notification TEST FAILED")
        return False


def test_success_notification(notifier: SlackNotifier) -> bool:
    """
    Test sending a success notification to Slack.
    
    Args:
        notifier: Configured SlackNotifier instance
        
    Returns:
        True if test passes, False otherwise
    """
    # Send test success notification with sample indexer data
    logger.info("Testing success notification...")
    
    test_indexers = [
        "0x1234567890abcdef1234567890abcdef12345678",
        "0xabcdef1234567890abcdef1234567890abcdef12",
        "0x9876543210fedcba9876543210fedcba98765432"
    ]
    
    success = notifier.send_success_notification(
        eligible_indexers=test_indexers,
        total_processed=len(test_indexers),
        execution_time=1.0
    )
    
    if success:
        logger.info("Success notification TEST PASSED")
        return True
    else:
        logger.error("Success notification TEST FAILED")
        return False


def test_failure_notification(notifier: SlackNotifier) -> bool:
    """
    Test sending a failure notification to Slack.
    
    Args:
        notifier: Configured SlackNotifier instance
        
    Returns:
        True if test passes, False otherwise
    """
    # Send test failure notification with sample error
    logger.info("Testing failure notification...")
    
    success = notifier.send_failure_notification(
        error_message="Test error message to verify failure notifications work correctly.",
        stage="Test Stage",
        execution_time=1
    )
    
    if success:
        logger.info("Failure notification TEST PASSED")
        return True
    else:
        logger.error("Failure notification TEST FAILED")
        return False


def execute_all_slack_tests() -> bool:
    """
    Execute all Slack notification tests in sequence.

    Tests:
        - Info notification
        - Success notification
        - Failure notification
    
    Returns:
        True if all tests pass, False otherwise
    """
    # Load Slack configuration from environment and config file
    webhook_url = load_slack_configuration()
    if not webhook_url:
        logger.error("Failed to load webhook_url")
        return False
    
    # Create and validate Slack notifier instance
    notifier = create_and_validate_slack_notifier(webhook_url)
    if not notifier:
        logger.error("Failed to create Slack notifier instance")
        return False
    
    # Execute info notification test
    if not test_info_notification(notifier):
        logger.error("Failed to send info notification")
        return False
    
    # Execute success notification test
    if not test_success_notification(notifier):
        logger.error("Failed to send success notification")
        return False
    
    # Execute failure notification test
    if not test_failure_notification(notifier):
        logger.error("Failed to send failure notification")
        return False
    
    # All tests completed successfully
    logger.info("All Slack notification tests passed!")
    return True


def check_environment_variable_configuration():
    """
    Check if SLACK_WEBHOOK_URL environment variable is configured.
    Log warning if not set and cancel the script.
    """
    # Check if environment variable is set and warn if missing
    if not os.environ.get("SLACK_WEBHOOK_URL"):
        logger.warning("SLACK_WEBHOOK_URL environment variable not set")
        logger.warning("Set it with: export SLACK_WEBHOOK_URL='your_webhook_url'")
        return False

    # If the environment variable is set, log the success and return True
    logger.info("SLACK_WEBHOOK_URL environment variable set")
    return True


def main():
    """
    Main function to orchestrate Slack notification testing.
    """
    # Display test header information
    logger.info("Service Quality Oracle - Slack Notification Test")
    
    # Check environment variable configuration
    if not check_environment_variable_configuration():
        sys.exit(1)
    
    # Execute all tests and handle results
    if execute_all_slack_tests():
        logger.info("All tests completed successfully!")
        logger.info("Check your Slack channel to verify notifications were received.")
        sys.exit(0)

    else:
        logger.error("Some tests failed!")
        logger.error("Check error messages and Slack webhook configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main() 