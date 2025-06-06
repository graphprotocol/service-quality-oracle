"""
Helper module containing utility functions related to data access and processing
for the Service Quality Oracle.
"""

import json
import logging
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
from web3 import Web3
from web3.contract import Contract

# Import data providers
from src.models.bigquery_data_access_provider import BigQueryProvider
from src.models.subgraph_data_access_provider import SubgraphProvider

# Import configuration and key validation
from src.utils.config_loader import ConfigLoader, ConfigurationError
from src.utils.key_validator import KeyValidationError, validate_and_format_private_key

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION AND SETUP FUNCTIONS
# =============================================================================
def _validate_required_fields(data: dict, required_fields: list[str], context: str) -> None:
    """
    Helper function to validate required fields are present in a dictionary.
    Args:
        data: Dictionary to validate
        required_fields: List of required fields
        context: Context for error message
    Raises:
        ValueError: If required fields are missing
    """
    # Check if any required fields are missing from the data dictionary
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        raise ValueError(f"{context}: missing {missing_fields}")


def _load_config_and_return_validated() -> dict[str, Any]:
    """
    Load all necessary configurations using config loader, validate, and return them.
    # TODO: check config file return dict format correct (also in other functions throughout the codebase)
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
        _validate_required_fields(config, required_fields, "Missing required blockchain configuration")
        # Validate RPC providers
        if not config.get("rpc_providers") or not isinstance(config["rpc_providers"], list):
            raise ValueError("BLOCKCHAIN_RPC_URLS must be a list of valid RPC URLs")
        return config
    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed: {e}") from e


def _get_path_to_project_root() -> Path:
    """
    Get the path to the project root directory.
    In Docker environments, use /app. Otherwise, find by marker files.
    """
    # Use the /app directory as the project root if it exists
    docker_path = Path("/app")
    if docker_path.exists():
        return docker_path
    # If the /app directory doesn't exist fall back to secondary detection logic
    current_path = Path(__file__).parent
    while current_path != current_path.parent:
        if (current_path / ".gitignore").exists() or (current_path / "pyproject.toml").exists():
            logger.info(f"Found project root at: {current_path}")
            return current_path
        # Attempt to traverse upwards (will not work if the directory has no parent)
        current_path = current_path.parent
    # If we got here, something is wrong
    raise FileNotFoundError("Could not find project root directory. Investigate.")


def _parse_and_validate_credentials_json(creds_env: str) -> dict:
    """
    Parse and validate Google credentials JSON from environment variable.
    Args:
        creds_env: JSON string containing credentials
    Returns:
        dict: Parsed and validated credentials data
    Raises:
        ValueError: If JSON is invalid or credentials are incomplete
    """
    # Try to parse the credentials JSON
    try:
        creds_data = json.loads(creds_env)
        cred_type = creds_data.get("type", "")
        # Validate the credentials data based on the type
        if cred_type == "authorized_user":
            required_fields = ["client_id", "client_secret", "refresh_token"]
            _validate_required_fields(creds_data, required_fields, "Incomplete authorized_user credentials")
        elif cred_type == "service_account":
            required_fields = ["private_key", "client_email", "project_id"]
            _validate_required_fields(creds_data, required_fields, "Incomplete service_account credentials")
        else:
            raise ValueError(
                f"Unsupported credential type: '{cred_type}'. Expected 'authorized_user' or 'service_account'"
            )
    # If the JSON is invalid, log an error and raise a ValueError
    except Exception as e:
        logger.error(f"Failed to parse and validate credentials JSON: {e}")
        raise ValueError(f"Invalid credentials JSON: {e}") from e
    # Return the parsed and validated credentials data
    return creds_data


def _setup_user_credentials_in_memory(creds_data: dict) -> None:
    """Set up user account credentials directly in memory."""
    import google.auth
    from google.oauth2.credentials import Credentials

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
    finally:
        # Clear sensitive data from local scope
        if "creds_data" in locals():
            creds_data.clear()


def _setup_service_account_credentials_in_memory(creds_data: dict) -> None:
    """Set up service account credentials directly in memory."""
    import google.auth
    from google.oauth2 import service_account

    try:
        # Create credentials object directly from dict
        credentials = service_account.Credentials.from_service_account_info(creds_data)
        # Set credentials globally for GCP libraries
        google.auth._default._CREDENTIALS = credentials  # type: ignore[attr-defined]
        logger.info("Successfully loaded service account credentials from environment variable")
    except Exception as e:
        logger.error(f"Failed to create service account credentials: {e}")
        raise ValueError(f"Invalid service account credentials: {e}") from e
    finally:
        # Clear sensitive data from local scope
        if "creds_data" in locals():
            creds_data.clear()


def _setup_google_credentials_in_memory_from_env_var():
    """
    Set up Google credentials directly in memory from environment variable.
    This function handles multiple credential formats securely:
    1. JSON string in GOOGLE_APPLICATION_CREDENTIALS (inline credentials)
    2. Automatic fallback to gcloud CLI authentication
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
    if creds_env.startswith("{"):
        creds_data = None
        try:
            # Parse and validate credentials
            creds_data = _parse_and_validate_credentials_json(creds_env)
            cred_type = creds_data.get("type")
            # Set up credentials based on type
            if cred_type == "authorized_user":
                _setup_user_credentials_in_memory(creds_data.copy())
            elif cred_type == "service_account":
                _setup_service_account_credentials_in_memory(creds_data.copy())
        # If the credentials are invalid, log an error and raise a ValueError
        except Exception as e:
            logger.error("Failed to set up credentials from environment variable")
            raise ValueError(f"Error processing inline credentials: {e}") from e
        # Clear the original credentials dict from memory if it exists
        finally:
            if creds_data is not None:
                creds_data.clear()
                del creds_data
    else:
        logger.warning(
            "GOOGLE_APPLICATION_CREDENTIALS is not set or not in the correct format. "
            "Falling back to gcloud CLI authentication if available"
        )
        return


# =============================================================================
# DATA PROCESSING UTILITY FUNCTIONS
# =============================================================================
def _export_bigquery_data_as_csvs_and_return_lists_of_ineligible_and_eligible_indexers(
    input_data_from_bigquery: pd.DataFrame, output_date_dir: Path
) -> tuple[list, list]:
    """
    Export BigQuery data as CSVs and return lists of eligible/ineligible indexers.
    Args:
        input_data_from_bigquery: Indexer data returned from BigQuery
        output_date_dir: Path to date directory for output files
    Returns:
        Tuple[list, list]: Two lists of indexer addresses, eligible and ineligible
    """
    # Ensure the output directory exists, creating parent directories if necessary
    output_date_dir.mkdir(exist_ok=True, parents=True)
    # Save raw data
    raw_data_path = output_date_dir / "indexer_issuance_eligibility_data.csv"
    input_data_from_bigquery.to_csv(raw_data_path, index=False)
    logger.info(f"Saved raw bigquery results df to: {raw_data_path}")
    # Filter eligible and ineligible indexers
    eligible_df = input_data_from_bigquery[input_data_from_bigquery["eligible_for_indexing_rewards"] == 1]
    ineligible_df = input_data_from_bigquery[input_data_from_bigquery["eligible_for_indexing_rewards"] == 0]
    # Save filtered data
    eligible_path = output_date_dir / "eligible_indexers.csv"
    ineligible_path = output_date_dir / "ineligible_indexers.csv"
    eligible_df[["indexer"]].to_csv(eligible_path, index=False)
    ineligible_df[["indexer"]].to_csv(ineligible_path, index=False)
    # Return lists of eligible and ineligible indexers
    return eligible_df["indexer"].tolist(), ineligible_df["indexer"].tolist()


def _clean_old_date_directories(data_output_dir: Path, max_age_before_deletion: int):
    """
    Remove old date directories to prevent unlimited growth.
    Args:
        data_output_dir: Path to the output directory
        max_age_before_deletion: Maximum age in days before deleting data output
    """
    today = date.today()
    output_path = Path(data_output_dir)
    # Only process directories with date format YYYY-MM-DD
    for item in output_path.iterdir():
        if not item.is_dir():
            continue
        try:
            # Try to parse the directory name as a date
            dir_date = datetime.strptime(item.name, "%Y-%m-%d").date()
            age_days = (today - dir_date).days
            # Remove if older than max_age_before_deletion
            if age_days > max_age_before_deletion:
                logger.info(f"Removing old data directory: {item} ({age_days} days old)")
                shutil.rmtree(item)
        # Skip directories that don't match date format
        except ValueError:
            continue


# =============================================================================
# BLOCKCHAIN UTILITY FUNCTIONS (LOW-LEVEL)
# =============================================================================
def _load_contract_abi() -> list[dict]:
    """Load the contract ABI from the contracts directory."""
    try:
        project_root = _get_path_to_project_root()
        abi_path = project_root / "contracts" / "contract.abi.json"
        with open(abi_path) as f:
            return json.load(f)
    # If the ABI file cannot be loaded, raise an error
    except Exception as e:
        logger.error(f"Failed to load contract ABI: {str(e)}")
        raise


def _get_working_web3_connection(
    rpc_providers: list[str], contract_address: str, contract_abi: list[dict]
) -> tuple[Web3, Contract, str]:
    """
    Try connecting to RPC providers until one works.
    Args:
        rpc_providers: List of RPC provider URLs to try connecting to
        contract_address: Contract address for creating contract instance
        contract_abi: Contract ABI for creating contract instance
    Returns:
        Tuple[Web3, Contract, str]: Working web3 instance, contract instance, and provider URL
    Raises:
        ConnectionError: If all RPC providers fail
    """
    for i, rpc_url in enumerate(rpc_providers):
        try:
            provider_type = "primary" if i == 0 else f"backup #{i}"
            logger.info(f"Attempting to connect to {provider_type} RPC provider: {rpc_url}")
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            # Test connection
            if w3.is_connected():
                logger.info(f"Successfully connected to {provider_type} RPC provider")
                # Create contract instance and return web3 instance, contract instance, and provider URL
                contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=contract_abi)
                return w3, contract, rpc_url
            else:
                logger.warning(f"Could not connect to {provider_type} RPC provider: {rpc_url}")
        except Exception as e:
            provider_type = "primary" if i == 0 else f"backup #{i}"
            logger.warning(f"Error connecting to {provider_type} RPC provider {rpc_url}: {str(e)}")
    # If we get here, all providers failed
    raise ConnectionError(f"Failed to connect to any of {len(rpc_providers)} RPC providers: {rpc_providers}")


def _setup_transaction_account(private_key: str, w3) -> tuple[str, object]:
    """
    Get the address of the account from the private key.
    Args:
        private_key: Private key for the account
        w3: Web3 instance
    Returns:
        str: Address of the account
    """
    try:
        account = w3.eth.account.from_key(private_key)
        logger.info(f"Using account: {account.address}")
        return account.address
    # If the account cannot be retrieved, log the error and raise an exception
    except Exception as e:
        logger.error(f"Failed to retrieve account from private key: {str(e)}")
        raise


def _estimate_transaction_gas(
    w3, contract_func, indexer_addresses: list[str], data_bytes: bytes, sender_address: str
) -> int:
    """
    Estimate gas for the transaction with 25% buffer.
    Args:
        w3: Web3 instance
        contract_func: Contract function to call
        indexer_addresses: List of indexer addresses
        data_bytes: Data bytes for the transaction
        sender_address: Transaction sender address
    Returns:
        int: Estimated gas with 25% buffer
    """
    # Try to estimate the gas for the transaction
    try:
        estimated_gas = contract_func(indexer_addresses, data_bytes).estimate_gas({"from": sender_address})
        gas_limit = int(estimated_gas * 1.25)  # 25% buffer
        logger.info(f"Estimated gas: {estimated_gas}, with buffer: {gas_limit}")
        return gas_limit
    # If the gas estimation fails, raise an error
    except Exception as e:
        logger.error(f"Gas estimation failed: {str(e)}")
        raise


def _determine_transaction_nonce(w3, sender_address: str, replace: bool) -> int:
    """
    Determine the appropriate nonce for the transaction.
    Args:
        w3: Web3 instance
        sender_address: Transaction sender address
        replace: Whether to replace pending transactions
    Returns:
        int: Transaction nonce to use
    """
    # If we are not replacing a pending transaction, use the next available nonce
    if not replace:
        nonce = w3.eth.get_transaction_count(sender_address)
        logger.info(f"Using next available nonce: {nonce}")
        return nonce
    # If we are replacing a pending transaction, try to find and replace it
    logger.info("Attempting to find and replace a pending transaction")
    # Try to find pending transactions
    try:
        pending_txs = w3.eth.get_block("pending", full_transactions=True)
        sender_pending_txs = [
            tx for tx in pending_txs.transactions if hasattr(tx, "from") and tx["from"] == sender_address
        ]
        # If we found pending transactions, use the nonce of the first pending transaction
        if sender_pending_txs:
            sender_pending_txs.sort(key=lambda x: x["nonce"])
            nonce = sender_pending_txs[0]["nonce"]
            logger.info(f"Found pending transaction with nonce {nonce} for replacement")
            return nonce
    # If we could not find pending transactions log a warning
    except Exception as e:
        logger.warning(f"Could not check pending transactions: {str(e)}")
    # Check for nonce gaps
    try:
        current_nonce = w3.eth.get_transaction_count(sender_address, "pending")
        latest_nonce = w3.eth.get_transaction_count(sender_address, "latest")
        if current_nonce > latest_nonce:
            logger.info(f"Detected nonce gap: latest={latest_nonce}, pending={current_nonce}")
            return latest_nonce
    except Exception as e:
        logger.warning(f"Could not check nonce gap: {str(e)}")
    # Fallback to next available nonce
    nonce = w3.eth.get_transaction_count(sender_address)
    logger.info(f"Using next available nonce: {nonce}")
    return nonce


def _get_gas_prices(w3, replace: bool) -> tuple[int, int]:
    """Get base fee and max priority fee for transaction."""
    # Get current gas prices with detailed logging
    try:
        latest_block = w3.eth.get_block("latest")
        base_fee = latest_block["baseFeePerGas"]
        logger.info(f"Latest block base fee: {base_fee/1e9:.2f} gwei")
    # If the base fee cannot be retrieved, use a fallback value
    except Exception as e:
        logger.warning(f"Could not get base fee: {e}")
        base_fee = w3.to_wei(10, "gwei")
    try:
        max_priority_fee = w3.eth.max_priority_fee
        logger.info(f"Max priority fee: {max_priority_fee/1e9:.2f} gwei")
    except Exception as e:
        logger.warning(f"Could not get max priority fee: {e}")
        max_priority_fee = w3.to_wei(2, "gwei")  # fallback
    return base_fee, max_priority_fee


def _build_transaction_params(
    sender_address: str,
    nonce: int,
    chain_id: int,
    gas_limit: int,
    base_fee: int,
    max_priority_fee: int,
    replace: bool,
) -> dict:
    """Build transaction parameters with appropriate gas prices."""
    tx_params = {"from": sender_address, "nonce": nonce, "chainId": chain_id, "gas": gas_limit}
    # Set gas prices (higher for replacement transactions)
    if replace:
        max_fee_per_gas = base_fee * 4 + max_priority_fee * 2
        max_priority_fee_per_gas = max_priority_fee * 2
        tx_params["maxFeePerGas"] = max_fee_per_gas
        tx_params["maxPriorityFeePerGas"] = max_priority_fee_per_gas
        logger.info(f"High gas for replacement: {max_fee_per_gas/1e9:.2f} gwei")
    # If we are not replacing a pending transaction, use a lower gas price
    else:
        max_fee_per_gas = base_fee * 2 + max_priority_fee
        max_priority_fee_per_gas = max_priority_fee
        tx_params["maxFeePerGas"] = max_fee_per_gas
        tx_params["maxPriorityFeePerGas"] = max_priority_fee_per_gas
        logger.info(f"Standard gas: {max_fee_per_gas/1e9:.2f} gwei")
    logger.info(f"Transaction parameters: nonce={nonce}, gas={gas_limit}, chain_id={chain_id}")
    return tx_params


def _build_and_sign_transaction(
    w3, contract_func, indexer_addresses: list[str], data_bytes: bytes, tx_params: dict, private_key: str
):
    """Build and sign the transaction."""
    # Attempt to build the transaction
    try:
        transaction = contract_func(indexer_addresses, data_bytes).build_transaction(tx_params)
        logger.info("Transaction built successfully")
    # If the transaction cannot be built, log the error and raise an exception
    except Exception as e:
        logger.error(f"Failed to build transaction: {e}")
        logger.error(f"Contract function: {contract_func}")
        logger.error(f"Indexer addresses count: {len(indexer_addresses)}")
        logger.error(f"Data bytes length: {len(data_bytes)}")
        logger.error(f"Transaction params: {tx_params}")
        raise
    # Attempt to sign the transaction
    try:
        signed_tx = w3.eth.account.sign_transaction(transaction, private_key)
        logger.info("Transaction signed successfully")
        return signed_tx
    # If the transaction cannot be signed, log the error and raise an exception
    except Exception as e:
        logger.error(f"Failed to sign transaction: {e}")
        raise


def _handle_transaction_error(error_msg: str) -> None:
    """Handle and log specific transaction error types."""
    if "insufficient funds" in error_msg.lower():
        logger.error("Insufficient funds to pay for gas")
    elif "nonce too low" in error_msg.lower():
        logger.error("Nonce is too low - transaction may have already been sent")
    elif "nonce too high" in error_msg.lower():
        logger.error("Nonce is too high - there may be pending transactions")
    elif "gas" in error_msg.lower():
        logger.error("Gas-related issue - transaction may consume too much gas")
    elif "400" in error_msg:
        logger.error("HTTP 400 Bad Request - RPC provider rejected the request")


def _send_signed_transaction(w3, signed_tx) -> str:
    """Send the signed transaction and handle errors."""
    # Attempt to send the transaction to the network
    try:
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        logger.info(f"Transaction sent! Hash: {tx_hash.hex()}")
        return tx_hash.hex()
    # If the transaction could not be sent, log the error and raise an exception
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Transaction rejected by network: {error_msg}")
        _handle_transaction_error(error_msg)
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending transaction: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise


def _build_and_send_transaction(
    w3,
    contract_func,
    indexer_addresses: list[str],
    data_bytes: bytes,
    sender_address: str,
    private_key: str,
    chain_id: int,
    gas_limit: int,
    nonce: int,
    replace: bool,
) -> str:
    """
    Build, sign, and send the transaction.
    Args:
        w3: Web3 instance
        contract_func: Contract function to call
        indexer_addresses: List of indexer addresses
        data_bytes: Data bytes for transaction
        sender_address: Transaction sender address
        private_key: Private key for signing
        chain_id: Chain ID
        gas_limit: Gas limit for transaction
        nonce: Transaction nonce
        replace: Whether this is a replacement transaction
    Returns:
        str: Transaction hash
    """
    try:
        # Get gas prices
        base_fee, max_priority_fee = _get_gas_prices(w3, replace)
        # Build transaction parameters
        tx_params = _build_transaction_params(
            sender_address, nonce, chain_id, gas_limit, base_fee, max_priority_fee, replace
        )
        # Build and sign transaction
        signed_tx = _build_and_sign_transaction(
            w3, contract_func, indexer_addresses, data_bytes, tx_params, private_key
        )
        # Send transaction
        return _send_signed_transaction(w3, signed_tx)
    except Exception as e:
        logger.error(f"Error in _build_and_send_transaction: {e}")
        raise


# =============================================================================
# BLOCKCHAIN TRANSACTION FUNCTIONS (MID-LEVEL)
# =============================================================================
def _execute_transaction_with_rpc_failover(
    operation_name: str, rpc_providers: list[str], contract_address: str, operation_func, operation_params: dict
):
    """
    Execute a transaction operation with automatic RPC failover.
    This function tries each RPC provider in sequence until one succeeds.
    If an RPC fails during any part of the transaction process, it moves to the next one.
    Args:
        operation_name: Human-readable name for the transaction operation, used for logging purposes
        rpc_providers: List of RPC provider URLs to try connecting to
        contract_address: Contract address
        operation_func: Function that takes (w3, contract, operation_params) and does 'operation_name' operation
                        default 'operation_func' is _execute_complete_transaction()
        operation_params: Parameters for the operation, e.g.
            {
                "private_key": private_key,
                "contract_function": contract_function,
                "indexer_addresses": indexer_addresses,
                "data_bytes": data_bytes,
                "sender_address": sender_address,
                "account": account,
                "chain_id": chain_id,
                "replace": replace
            }
    Returns:
        Result of the operation_func
    Raises:
        Exception: If all RPC providers fail
    """
    # Initialize last_exception to None
    last_exception = None
    for rpc_url in rpc_providers:
        try:
            # Log the attempt
            logger.info(f"Attempting to do '{operation_name}' using RPC provider: {rpc_url}")
            # Get fresh connection for this rpc provider attempt
            w3, contract, _ = _get_working_web3_connection([rpc_url], contract_address, _load_contract_abi())
            # Execute the operation with this rpc provider and return the result
            return operation_func(w3, contract, operation_params)
        # If the operation fails, log the error and continue to the next rpc provider
        except Exception as e:
            logger.warning(f"{operation_name} failed with RPC provider {rpc_url}: {str(e)}")
            # Store the exception for later use
            last_exception = e
    # If we get here, all providers failed
    logger.error(f"{operation_name} failed on all {len(rpc_providers)} RPC providers")
    raise last_exception or Exception(f"All RPC providers failed for {operation_name}")


def _execute_complete_transaction(w3, contract, params):
    """
    Execute the complete transaction process using a single RPC connection.
    Args:
        w3: Web3 instance
        contract: Contract instance
        params: Dictionary containing all transaction parameters
    Returns:
        str: Transaction hash
    """
    # Extract parameters
    private_key = params["private_key"]
    contract_function = params["contract_function"]
    indexer_addresses = params["indexer_addresses"]
    data_bytes = params["data_bytes"]
    sender_address = params["sender_address"]
    chain_id = params["chain_id"]
    replace = params["replace"]
    # Validate contract function exists
    if not hasattr(contract.functions, contract_function):
        raise ValueError(f"Contract {contract.address} does not have function: {contract_function}")
    contract_func = getattr(contract.functions, contract_function)
    # Log transaction details
    logger.info(f"Contract address: {contract.address}")
    logger.info(f"Contract function: {contract_function}")
    logger.info(f"Number of indexers: {len(indexer_addresses)}")
    logger.info(f"Data bytes length: {len(data_bytes)}")
    logger.info(f"Chain ID: {chain_id}")
    logger.info(f"Sender address: {sender_address}")
    logger.info(f"Using RPC: {w3.provider.endpoint_uri}")
    # Check account balance
    balance_wei = w3.eth.get_balance(sender_address)
    balance_eth = w3.from_wei(balance_wei, "ether")
    logger.info(f"Account balance: {balance_eth} ETH")
    # All transaction steps with the same RPC connection
    gas_limit = _estimate_transaction_gas(w3, contract_func, indexer_addresses, data_bytes, sender_address)
    nonce = _determine_transaction_nonce(w3, sender_address, replace)
    tx_hash = _build_and_send_transaction(
        w3,
        contract_func,
        indexer_addresses,
        data_bytes,
        sender_address,
        private_key,
        chain_id,
        gas_limit,
        nonce,
        replace,
    )
    # Wait for receipt with the same connection
    try:
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        if tx_receipt["status"] == 1:
            logger.info(
                f"Transaction confirmed in block {tx_receipt['blockNumber']}, gas used: {tx_receipt['gasUsed']}"
            )
        else:
            logger.error(f"Transaction failed on-chain: {tx_hash}")
    except Exception as e:
        logger.warning(f"Could not get transaction receipt: {str(e)} (transaction may still be pending)")
    return tx_hash


def _send_transaction_to_allow_indexers_in_list_to_claim_issuance(
    list_of_indexers_that_can_claim_issuance: list[str],
    private_key: str,
    chain_id: int,
    rpc_providers: list[str],
    contract_address: str,
    contract_function: str,
    replace: bool = False,
    data_bytes: bytes = b"",
) -> str:
    """
    Send a transaction to the indexer eligibility oracle contract to allow a subset of indexers
    to claim issuance rewards.
    This function builds, signs, and sends a transaction to the blockchain using RPC failover.
    This function is called by the batch_allow_indexers_issuance_eligibility_smart_contract function, which handles
    batching of transactions if the list before input into this function.
    Args:
        list_of_indexers_that_can_claim_issuance: List of indexer addresses to allow issuance
        private_key: Private key for transaction signing
        chain_id: Chain ID of the target blockchain
        rpc_providers: List of RPC provider URLs (primary + backups)
        contract_address: Contract address
        contract_function: Contract function name to call
        replace: Flag to replace pending transactions
        data_bytes: Optional bytes data to pass to contract function
    Returns:
        str: Transaction hash
    """
    # Set up account
    from web3 import Web3

    temp_w3 = Web3()
    sender_address = _setup_transaction_account(private_key, temp_w3)
    # Convert addresses to checksum format
    checksum_addresses = [Web3.to_checksum_address(addr) for addr in list_of_indexers_that_can_claim_issuance]
    # Prepare all parameters for the transaction
    transaction_params = {
        "private_key": private_key,
        "contract_function": contract_function,
        "indexer_addresses": checksum_addresses,
        "data_bytes": data_bytes,
        "sender_address": sender_address,
        "chain_id": chain_id,
        "replace": replace,
    }
    # Execute the transaction to allow indexers to claim issuance with RPC failover
    try:
        return _execute_transaction_with_rpc_failover(
            "Allow indexers to claim issuance",
            rpc_providers,
            contract_address,
            _execute_complete_transaction,
            transaction_params,
        )
    except Exception as e:
        logger.error(f"Transaction failed on all RPC providers: {str(e)}")
        raise


# =============================================================================
# HIGH-LEVEL BATCH TRANSACTION FUNCTION
# =============================================================================
def batch_allow_indexers_issuance_eligibility_smart_contract(
    list_of_indexers_to_allow: list[str], replace: bool = False, batch_size: int = 250, data_bytes: bytes = b""
) -> list[str]:
    """
    Allow the issuance eligibility status of a list of indexers in the smart contract.
    This function handles batching of transactions if the list is too large for a single
    transaction, and uses key validation for private keys.
    Args:
        list_of_indexers_to_allow: List of indexer addresses to allow
        replace: Optional flag to replace pending transactions
        batch_size: Optional batch size for processing large lists
        data_bytes: Optional bytes data to pass to contract_address:contract_function
    Returns:
        List[str]: List of transaction hashes from successful batches
    Raises:
        ConfigurationError: If configuration loading fails
        ValueError: If configuration is invalid
        ConnectionError: If unable to connect to any RPC providers
        Exception: If transaction processing fails
    """
    # Get config
    config = _load_config_and_return_validated()
    # Validate function parameters look correct
    if not list_of_indexers_to_allow:
        logger.warning("No indexers provided to allow. Returning empty list.")
        return []
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    # Calculate number of batches to process
    total_indexers_to_allow = len(list_of_indexers_to_allow)
    num_batches = (total_indexers_to_allow + batch_size - 1) // batch_size
    logger.info(f"Processing {total_indexers_to_allow} indexers in {num_batches} batch(es) of {batch_size}")
    try:
        tx_links = []
        # Validate and format private key
        private_key = validate_and_format_private_key(str(config["private_key"]))
        # Process each batch
        for i in range(num_batches):
            start_idx = i * batch_size
            end_idx = min(start_idx + batch_size, total_indexers_to_allow)
            batch_indexers = list_of_indexers_to_allow[start_idx:end_idx]
            logger.info(f"Processing batch {i+1}/{num_batches} with {len(batch_indexers)} indexers")
            try:
                tx_hash = _send_transaction_to_allow_indexers_in_list_to_claim_issuance(
                    batch_indexers,
                    private_key,
                    int(config["chain_id"]),
                    list(config["rpc_providers"]),
                    str(config["contract_address"]),
                    str(config["contract_function"]),
                    replace,
                    data_bytes,
                )
                tx_links.append(f"https://sepolia.arbiscan.io/tx/{tx_hash}")
                logger.info(f"Batch {i+1} transaction successful: {tx_hash}")
            except Exception as e:
                logger.error(f"Error processing batch {i+1} due to: {e}")
        # Print all the transaction links
        for i, tx_link in enumerate(tx_links, 1):
            logger.info(f"Transaction link {i} of {len(tx_links)}: {tx_link}")
        return tx_links
    except KeyValidationError as e:
        logger.error(f"Private key validation failed: {e}")
        raise ValueError(f"Invalid private key: {e}") from e


# =============================================================================
# MAIN BIGQUERY DATA PROCESSING FUNCTION
# =============================================================================
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=30, max=120), reraise=True)
def bigquery_fetch_and_save_indexer_issuance_eligibility_data_finally_return_eligible_indexers(
    start_date: date,
    end_date: date,
    current_date: date,
    max_age_before_deletion: int,
) -> list[str]:
    """
    Main function to fetch and process data from BigQuery.
    Returns:
        List[str]: List of indexers that should be allowed issuance based on BigQuery data
    """
    # Load config using secure configuration loader
    config = _load_config_and_return_validated()
    # Initialize the BigQuery provider class so we can use its methods to fetch data from BigQuery
    bq_provider = BigQueryProvider(project=str(config["bigquery_project_id"]), location=str(config["bigquery_location"]))
    try:
        # Fetch eligibility dataframe
        logger.info(f"Fetching eligibility data between {start_date} and {end_date}")
        indexer_issuance_eligibility_data = bq_provider.fetch_indexer_issuance_eligibility_data(
            start_date, end_date
        )
        logger.info(f"Retrieved issuance eligibility data for {len(indexer_issuance_eligibility_data)} indexers")
        # Store the output directory paths as variables so we can pass them to other functions
        output_dir = _get_path_to_project_root() / "data" / "output"
        date_dir = output_dir / current_date.strftime("%Y-%m-%d")
        # Export separate lists for eligible and ineligible indexers
        logger.info(f"Attempting to export indexer issuance eligibility lists to: {date_dir}")
        eligible_indexers, ineligible_indexers = (
            _export_bigquery_data_as_csvs_and_return_lists_of_ineligible_and_eligible_indexers(
                indexer_issuance_eligibility_data, date_dir
            )
        )
        logger.info("Exported indexer issuance eligibility lists.")
        # Clean old eligibility lists
        logger.info("Cleaning old eligibility lists.")
        _clean_old_date_directories(output_dir, max_age_before_deletion)
        # Log final summary
        logger.info(f"Processing complete. Output available at: {date_dir}")
        # Log the number of eligible indexers
        logger.info(
            f"No. of elig. indxrs. to insert into smart contract on {date.today()} is: {len(eligible_indexers)}"
        )
        # Return list of indexers that should be allowed issuance
        return eligible_indexers
    except Exception as e:
        logger.error(f"Error processing data: {str(e)}", exc_info=True)
        raise


# =============================================================================
# FUTURE FUNCTIONS (NOT USED YET)
# =============================================================================
def _fetch_issuance_enabled_indexers_from_subgraph() -> list[str]:
    """
    TODO: fix this once we have the subgraph
    Queries the indexer eligibility subgraph to get the list of indexers that are
    currently allowed issuance.
    Returns:
        List[str]: A list of indexer addresses that are currently allowed issuance
    """
    # Load config and check that the necessary variables are set
    config = _load_config_and_return_validated()
    subgraph_url = config.get("subgraph_url")
    studio_api_key = config.get("studio_api_key")
    if not subgraph_url:
        raise ValueError("SUBGRAPH_URL_PRODUCTION not set in configuration")
    if not studio_api_key:
        raise ValueError("STUDIO_API_KEY not set in configuration")
    logger.info("Configuration for subgraph query loaded successfully.")
    try:
        # Initialize the subgraph provider class so we can use its methods to fetch data from our subgraph
        subgraph_provider = SubgraphProvider()
        # Fetch all indexers from the subgraph
        indexers_data = subgraph_provider.fetch_all_indexers()
        logger.info(f"Retrieved data for {len(indexers_data)} indexers from subgraph")
        # Extract currently denied indexers (those where isDenied is True)
        allowed_indexers = []
        for indexer in indexers_data:
            if indexer.get("isDenied", False):
                allowed_indexers.append(indexer["id"].lower())
        logger.info(f"Found {len(allowed_indexers)} indexers that are currently allowed issuance")
        return allowed_indexers
    except Exception as e:
        logger.error(f"Error fetching allowed indexers from subgraph: {str(e)}", exc_info=True)
        raise
