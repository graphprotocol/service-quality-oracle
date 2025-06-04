#!/usr/bin/env python3

import logging
import os
import sys

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

# Import data access utilities with absolute import

from src.models.subgraph_data_access_provider import SubgraphProvider

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    # Create subgraph provider - it will automatically load configuration
    subgraph_provider = SubgraphProvider()

    # Fetch all indexers from subgraph
    all_indexers = subgraph_provider.fetch_all_indexers()
    logger.info(f"Fetched {len(all_indexers)} indexers from subgraph")

    # TODO: rework this for the new .sol contract
    # Get eligibility statuses for all indexers
    eligibility_statuses = subgraph_provider.get_indexer_eligibility_statuses()
    logger.info(f"Fetched {len(eligibility_statuses)} eligibility statuses from subgraph")


if __name__ == "__main__":
    main()
