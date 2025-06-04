"""
Subgraph data access provider for the Service Quality Oracle.
Provides functionality to query data from the subgraph indexing the ServiceQualityOracle contract.
"""

import json
import logging
from typing import Any, Optional

import requests

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SubgraphProvider:
    """
    A provider class housing methods used for accessing data from the indexer eligibility subgraph on The Graph.

    This class automatically loads configuration from secure config loader when initialized.

    Methods:
        fetch_all_indexers: Fetch all indexers that have ever been eligible to claim issuance regardless
                            of their current eligibility status.

        get_indexer_eligibility_statuses: Get list of indexers that are eligible to claim issuance
                                          and the unix timestamp of when their eligibility expires
    """

    def __init__(self):
        """
        Initialize the subgraph provider.
        Automatically loads configuration from config loader.
        """
        # Import here to avoid circular imports
        from src.utils.config_loader import load_config

        # Load configuration
        config = load_config()

        # Get subgraph URL and API key from config
        self.subgraph_url = config.get("subgraph_url")
        self.api_key = config.get("studio_api_key")

        # Validate configuration
        if not self.subgraph_url:
            raise ValueError("SUBGRAPH_URL_PRODUCTION not set in configuration")
        logger.info(f"Initialized SubgraphProvider with endpoint: {self.subgraph_url}")

        if self.api_key:
            logger.info("API key loaded for subgraph queries")
        else:
            logger.warning("No API key found, subgraph queries may be limited")

    def fetch_all_indexers(self) -> list[dict[str, Any]]:
        """
        Fetch all indexers that have been input into the subgraph.
        This function handles pagination on its own.

        Returns:
            List of all indexers with their eligibility status
        """
        all_indexers = []
        page_size = 1000
        current_skip = 0

        while True:
            logger.info(f"Fetching indexers page: skip={current_skip}, limit={page_size}")
            page_results = self.get_indexer_eligibility_statuses(first=page_size, skip=current_skip)

            all_indexers.extend(page_results)

            # If we got fewer results than the page size, we've reached the end
            if len(page_results) < page_size:
                break

            current_skip += page_size

        logger.info(f"Fetched {len(all_indexers)} total indexers from subgraph")
        return all_indexers

    def get_indexer_eligibility_statuses(self, first: int = 1000, skip: int = 0) -> list[dict[str, Any]]:
        """
        Get eligibility statuses for all indexers.
        Uses pagination to handle large datasets.

        Args:
            first: Number of results to return per page
            skip: Number of results to skip (for pagination)

        Returns:
            List of indexers with their eligibility status
        """
        query = """
        query GetIndexers($first: Int!, $skip: Int!) {
          indexers(first: $first, skip: $skip) {
            id
            isDenied
            lastUpdated
            statusChangeCount
          }
        }
        """

        variables = {"first": first, "skip": skip}

        result = self.execute_query(query, variables)

        if "data" in result and "indexers" in result["data"]:
            return result["data"]["indexers"]
        else:
            logger.error(f"Unexpected response format: {result}")
            return []

    def execute_query(self, query: str, variables: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """
        Execute a GraphQL query against the subgraph.

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            Query result as dictionary
        """
        headers = {"Content-Type": "application/json"}

        data = {"query": query}

        if variables:
            data["variables"] = variables

        try:
            logger.info(f"Executing query against subgraph: {self.subgraph_url}")
            response = requests.post(self.subgraph_url, headers=headers, data=json.dumps(data))
            response.raise_for_status()  # Raise exception for non-200 status codes
            result = response.json()

            if "errors" in result:
                logger.error(f"GraphQL query errors: {result['errors']}")
                raise Exception(f"GraphQL query failed: {result['errors']}")

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Request to subgraph failed: {str(e)}")
            raise
