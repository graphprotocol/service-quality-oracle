#!/usr/bin/env python3
"""
Test script for Slack notifications.
This script tests the Slack notification functionality without running the full oracle.
"""

import logging
import os
import sys

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("slack-test")

from src.utils.slack_notifier import SlackNotifier, create_slack_notifier


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
    success = notifier.send_info_notification("Test info notification", "Test Notification")
    logger.info(f"Info notification: {'PASSED' if success else 'FAILED'}")
    return success


def test_success_notification(notifier: SlackNotifier) -> bool:
    """
    Test sending a success notification to Slack.

    Args:
        notifier: Configured SlackNotifier instance

    Returns:
        True if test passes, False otherwise
    """
    # Send test success notification with sample indexer data and transaction links
    logger.info("Testing success notification...")

    test_indexers = [
        "0x1234567890abcdef1234567890abcdef12345678",
        "0xabcdef1234567890abcdef1234567890abcdef12",
        "0x9876543210fedcba9876543210fedcba98765432",
    ]

    test_transaction_links = [
        "https://sepolia.arbiscan.io/tx/0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef12",
        "https://sepolia.arbiscan.io/tx/0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
    ]

    success = notifier.send_success_notification(
        eligible_indexers=test_indexers,
        total_processed=len(test_indexers),
        execution_time=1,
        transaction_links=test_transaction_links,
        batch_count=2,
    )

    logger.info(f"Success notification: {'PASSED' if success else 'FAILED'}")
    return success


def test_failure_notification(notifier: SlackNotifier) -> bool:
    """
    Test sending a failure notification to Slack.

    Args:
        notifier: Configured SlackNotifier instance

    Returns:
        True if test passes, False otherwise
    """
    # Send test failure notification with sample error and partial transaction info
    logger.info("Testing failure notification...")

    partial_transactions = [
        "https://sepolia.arbiscan.io/tx/0x1111111111111111111111111111111111111111111111111111111111111111",
    ]

    success = notifier.send_failure_notification(
        error_message="Test error message for verification",
        stage="Test Blockchain Submission",
        execution_time=1,
        partial_transaction_links=partial_transactions,
        indexers_processed=150,
    )

    logger.info(f"Failure notification: {'PASSED' if success else 'FAILED'}")
    return success


def run_all_tests() -> bool:
    """
    Run all tests and return True if all tests pass, False otherwise.

    Returns:
        True if all tests pass, False otherwise
    """
    # Get the Slack webhook URL from the environment variable
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.error("SLACK_WEBHOOK_URL environment variable not set")
        return False

    # Create a Slack notifier instance using the webhook URL
    notifier = create_slack_notifier(webhook_url)
    if not notifier:
        logger.error("Failed to create Slack notifier")
        return False

    # Define the list of tests to run
    tests = [
        test_info_notification,
        test_success_notification,
        test_failure_notification,
    ]

    # Run each test and return False if any test fails
    for test in tests:
        if not test(notifier):
            return False

    # If all tests pass, return True
    return True


def main():
    """
    Main function to orchestrate Slack notification testing.
    """
    # Display test header information
    logger.info("Service Quality Oracle - Slack Notification Test")

    if run_all_tests():
        logger.info("All tests completed successfully!")
        logger.info("Check Slack channel to verify notifications were received.")
        sys.exit(0)

    else:
        logger.error("Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
