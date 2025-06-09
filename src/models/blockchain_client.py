"""
Blockchain client for Service Quality Oracle.

This module handles all blockchain interactions including:
- Contract ABI loading
- RPC provider connections with failover
- Transaction building, signing, and sending
- Gas estimation and nonce management
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from web3 import Web3
from web3.contract import Contract

from src.utils.key_validator import KeyValidationError, validate_and_format_private_key
from src.utils.retry_decorator import retry_with_backoff

logger = logging.getLogger(__name__)


class BlockchainClient:
    """Handles all blockchain interactions"""
    
    def __init__(self, rpc_providers: List[str], contract_address: str, project_root: Path):
        """
        Initialize the blockchain client.

        Args:
            rpc_providers: List of RPC provider URLs
            contract_address: Smart contract address
            project_root: Path to project root directory
        """
        self.rpc_providers = rpc_providers
        self.contract_address = contract_address
        self.project_root = project_root
        self.contract_abi = self._load_contract_abi()


    def _load_contract_abi(self) -> List[Dict]:
        """Load the contract ABI from the contracts directory."""
        # Try to load the ABI file
        try:
            abi_path = self.project_root / "contracts" / "contract.abi.json"
            with open(abi_path) as f:
                return json.load(f)
        
        # If the ABI file cannot be loaded, raise an error
        except Exception as e:
            logger.error(f"Failed to load contract ABI: {str(e)}")
            raise


    @retry_with_backoff(max_attempts=3, exceptions=(ConnectionError,))
    def _get_working_web3_connection(
        self, rpc_providers: List[str], contract_address: str, contract_abi: List[Dict]
    ) -> Tuple[Web3, Contract, str]:
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
        # Try to connect to each RPC provider in sequence
        for i, rpc_url in enumerate(rpc_providers):
            try:
                provider_type = "primary" if i == 0 else f"backup #{i}"
                logger.info(f"Attempting to connect to {provider_type} RPC provider: {rpc_url}")
                w3 = Web3(Web3.HTTPProvider(rpc_url))
                
                # Test connection
                if w3.is_connected():
                    logger.info(f"Successfully connected to {provider_type} RPC provider")
                    # Create contract instance and return web3 instance, contract instance, and provider URL
                    contract = w3.eth.contract(
                        address=Web3.to_checksum_address(contract_address), abi=contract_abi
                    )

                    # 
                    return w3, contract, rpc_url

                # If we could not connect log the error
                else:
                    logger.warning(f"Could not connect to {provider_type} RPC provider: {rpc_url}")
                
            # If we get an error, log the error
            except Exception as e:
                provider_type = "primary" if i == 0 else f"backup #{i}"
                logger.warning(f"Error connecting to {provider_type} RPC provider {rpc_url}: {str(e)}")
        
        # If we get here, all providers failed
        raise ConnectionError(f"Failed to connect to any of {len(rpc_providers)} RPC providers: {rpc_providers}")
    

    def _setup_transaction_account(self, private_key: str, w3: Web3) -> str:
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
        self, w3: Web3, contract_func: Any, indexer_addresses: List[str], 
        data_bytes: bytes, sender_address: str
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

        # If the gas estimation fails, log the error and raise an exception
        except Exception as e:
            logger.error(f"Gas estimation failed: {str(e)}")
            raise


    def _determine_transaction_nonce(self, w3: Web3, sender_address: str, replace: bool) -> int:
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
                tx for tx in pending_txs.transactions 
                if hasattr(tx, "from") and tx["from"] == sender_address
            ]
            
            # If we found pending transactions, use the nonce of the first pending transaction
            if sender_pending_txs:
                sender_pending_txs.sort(key=lambda x: x["nonce"])
                nonce = sender_pending_txs[0]["nonce"]
                logger.info(f"Found pending transaction with nonce {nonce} for replacement")
                return nonce
        
        # If we could not find pending transactions log the issue
        except Exception as e:
            logger.warning(f"Could not check pending transactions: {str(e)}")
        
        # Check for nonce gaps
        try:
            current_nonce = w3.eth.get_transaction_count(sender_address, "pending")
            latest_nonce = w3.eth.get_transaction_count(sender_address, "latest")
            if current_nonce > latest_nonce:
                logger.info(f"Detected nonce gap: latest={latest_nonce}, pending={current_nonce}")
                return latest_nonce
        
        # If we could not check nonce gaps log the issue
        except Exception as e:
            logger.warning(f"Could not check nonce gap: {str(e)}")
        
        # Fallback to next available nonce
        nonce = w3.eth.get_transaction_count(sender_address)
        logger.info(f"Using next available nonce: {nonce}")
        return nonce


    def _get_gas_prices(self, w3: Web3, replace: bool) -> Tuple[int, int]:
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
        
        # Try to get the max priority fee
        try:
            max_priority_fee = w3.eth.max_priority_fee
            logger.info(f"Max priority fee: {max_priority_fee/1e9:.2f} gwei")
        
        # If the max priority fee cannot be retrieved, use a fallback value
        except Exception as e:
            logger.warning(f"Could not get max priority fee: {e}")
            max_priority_fee = w3.to_wei(2, "gwei")  # fallback
        
        # Return the base fee and max priority fee
        return base_fee, max_priority_fee


    def _build_transaction_params(
        self,
        sender_address: str,
        nonce: int,
        chain_id: int,
        gas_limit: int,
        base_fee: int,
        max_priority_fee: int,
        replace: bool,
    ) -> Dict:
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
        self, w3: Web3, contract_func: Any, indexer_addresses: List[str], 
        data_bytes: bytes, tx_params: Dict, private_key: str
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


    def _handle_transaction_error(self, error_msg: str) -> None:
        """Handle and log specific transaction error types."""
        # If the error message contains "insufficient funds", log the error
        if "insufficient funds" in error_msg.lower():
            logger.error("Insufficient funds to pay for gas")
        
        # If the error message contains "nonce too low", log the error
        elif "nonce too low" in error_msg.lower():
            logger.error("Nonce is too low - transaction may have already been sent")
        
        # If the error message contains "nonce too high", log the error
        elif "nonce too high" in error_msg.lower():
            logger.error("Nonce is too high - there may be pending transactions")
        
        # If the error message contains "gas", log the error
        elif "gas" in error_msg.lower():
            logger.error("Gas-related issue - transaction may consume too much gas")
        
        # If the error message contains "400", log the error
        elif "400" in error_msg:
            logger.error("HTTP 400 Bad Request - RPC provider rejected the request")


    def _send_signed_transaction(self, w3: Web3, signed_tx: Any) -> str:
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
            self._handle_transaction_error(error_msg)
            raise
            
        # If we get an unexpected error, log the error and raise an exception
        except Exception as e:
            logger.error(f"Unexpected error sending transaction: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            raise


    def _build_and_send_transaction(
        self,
        w3: Web3,
        contract_func: Any,
        indexer_addresses: List[str],
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
            base_fee, max_priority_fee = self._get_gas_prices(w3, replace)
            
            # Build transaction parameters
            tx_params = self._build_transaction_params(
                sender_address, nonce, chain_id, gas_limit, base_fee, max_priority_fee, replace
            )
            
            # Build and sign transaction
            signed_tx = self._build_and_sign_transaction(
                w3, contract_func, indexer_addresses, data_bytes, tx_params, private_key
            )
            
            # Send transaction
            return self._send_signed_transaction(w3, signed_tx)
        
        # If we get an error, log the error and raise an exception
        except Exception as e:
            logger.error(f"Error in _build_and_send_transaction: {e}")
            raise


    def _execute_complete_transaction(self, w3: Web3, contract: Contract, params: Dict) -> str:
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
        gas_limit = self._estimate_transaction_gas(w3, contract_func, indexer_addresses, data_bytes, sender_address)
        nonce = self._determine_transaction_nonce(w3, sender_address, replace)
        tx_hash = self._build_and_send_transaction(
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


    def _execute_transaction_with_rpc_failover(
        self, operation_name: str, operation_func: Callable, operation_params: Dict
    ) -> Any:
        """
        Execute a transaction operation with automatic RPC failover.
        This function tries each RPC provider in sequence until one succeeds.
        
        Args:
            operation_name: Human-readable name for the transaction operation
            operation_func: Function that takes (w3, contract, operation_params) and executes the operation
            operation_params: Parameters for the operation
            
        Returns:
            Result of the operation_func
            
        Raises:
            Exception: If all RPC providers fail
        """
        # Initialize last_exception to None
        last_exception = None

        # Try each RPC provider in sequence
        for rpc_url in self.rpc_providers:
            try:
                # Log the attempt
                logger.info(f"Attempting to do '{operation_name}' using RPC provider: {rpc_url}")

                # Get fresh connection for this rpc provider attempt
                w3, contract, _ = self._get_working_web3_connection([rpc_url], self.contract_address, self.contract_abi)

                # Execute the operation with this rpc provider and return the result
                return operation_func(w3, contract, operation_params)

            # If the operation fails, log the error and continue to the next rpc provider
            except Exception as e:
                logger.warning(f"{operation_name} failed with RPC provider {rpc_url}: {str(e)}")
                last_exception = e
        
        # If we get here, all providers failed
        logger.error(f"{operation_name} failed on all {len(self.rpc_providers)} RPC providers")
        raise last_exception or Exception(f"All RPC providers failed for {operation_name}")


    def send_transaction_to_allow_indexers(
        self,
        indexer_addresses: List[str],
        private_key: str,
        chain_id: int,
        contract_function: str,
        replace: bool = False,
        data_bytes: bytes = b"",
    ) -> str:
        """
        Send a transaction to allow a subset of indexers to claim issuance rewards.
        
        Args:
            indexer_addresses: List of indexer addresses to allow issuance
            private_key: Private key for transaction signing
            chain_id: Chain ID of the target blockchain
            contract_function: Contract function name to call
            replace: Flag to replace pending transactions
            data_bytes: Optional bytes data to pass to contract function
            
        Returns:
            str: Transaction hash
        """
        # Set up account
        temp_w3 = Web3()
        sender_address = self._setup_transaction_account(private_key, temp_w3)
        
        # Convert addresses to checksum format
        checksum_addresses = [Web3.to_checksum_address(addr) for addr in indexer_addresses]
        
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
        
        # Execute the transaction with RPC failover
        try:
            return self._execute_transaction_with_rpc_failover(
                "Allow indexers to claim issuance",
                self._execute_complete_transaction,
                transaction_params,
            )
        except Exception as e:
            logger.error(f"Transaction failed on all RPC providers: {str(e)}")
            raise


    def batch_allow_indexers_issuance_eligibility(
        self,
        indexer_addresses: List[str],
        private_key: str,
        chain_id: int,
        contract_function: str,
        replace: bool = False,
        batch_size: int = 250,
        data_bytes: bytes = b"",
    ) -> List[str]:
        """
        Allow the issuance eligibility status of a list of indexers in batches.
        
        Args:
            indexer_addresses: List of indexer addresses to allow
            private_key: Private key for transaction signing
            chain_id: Chain ID of the target blockchain
            contract_function: Contract function name to call
            replace: Optional flag to replace pending transactions
            batch_size: Optional batch size for processing large lists
            data_bytes: Optional bytes data to pass to contract function
            
        Returns:
            List[str]: List of transaction hashes from successful batches
        """
        # Validate function parameters
        if not indexer_addresses:
            logger.warning("No indexers provided to allow. Returning empty list.")
            return []
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        
        # Calculate number of batches to process
        total_indexers = len(indexer_addresses)
        num_batches = (total_indexers + batch_size - 1) // batch_size
        logger.info(f"Processing {total_indexers} indexers in {num_batches} batch(es) of {batch_size}")
        
        try:
            tx_links = []
            # Validate and format private key
            validated_private_key = validate_and_format_private_key(private_key)
            
            # Process each batch
            for i in range(num_batches):
                start_idx = i * batch_size
                end_idx = min(start_idx + batch_size, total_indexers)
                batch_indexers = indexer_addresses[start_idx:end_idx]
                
                logger.info(f"Processing batch {i+1}/{num_batches} with {len(batch_indexers)} indexers")
                
                # Try to send the transaction to the network (uses RPC failover)
                try:
                    tx_hash = self.send_transaction_to_allow_indexers(
                        batch_indexers,
                        validated_private_key,
                        chain_id,
                        contract_function,
                        replace,
                        data_bytes,
                    )
                    tx_links.append(f"https://sepolia.arbiscan.io/tx/{tx_hash}")
                    logger.info(f"Batch {i+1} transaction successful: {tx_hash}")
                
                # If we get an error, log the error and raise an exception
                except Exception as e:
                    logger.error(f"Error processing batch {i+1} due to: {e}")
                    raise

            # Log all transaction links
            for i, tx_link in enumerate(tx_links, 1):
                logger.info(f"Transaction link {i} of {len(tx_links)}: {tx_link}")

            return tx_links

        except KeyValidationError as e:
            logger.error(f"Private key validation failed: {e}")
            raise ValueError(f"Invalid private key: {e}") from e 
