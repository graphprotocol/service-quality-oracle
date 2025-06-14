"""
Unit tests for the BlockchainClient.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import requests
from web3 import Web3

from src.models.blockchain_client import BlockchainClient, KeyValidationError

# Mock constants
MOCK_RPC_PROVIDERS = ["http://primary-rpc.com", "http://secondary-rpc.com"]
MOCK_CONTRACT_ADDRESS = "0x" + "a" * 40
MOCK_BLOCK_EXPLORER_URL = "https://arbiscan.io"
MOCK_TX_TIMEOUT_SECONDS = 120
MOCK_PROJECT_ROOT = Path("/tmp/project")
MOCK_PRIVATE_KEY = "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
MOCK_SENDER_ADDRESS = Web3.to_checksum_address("0x" + "c" * 40)
MOCK_ABI = [{"type": "function", "name": "allow", "inputs": []}]


@pytest.fixture
def mock_file():
    """Fixture to mock open() for reading the ABI file."""
    with patch("builtins.open", mock_open(read_data=json.dumps(MOCK_ABI))) as m:
        yield m


@pytest.fixture
def mock_w3():
    """Fixture to mock the Web3 class."""
    with patch("src.models.blockchain_client.Web3") as MockWeb3:
        mock_instance = MockWeb3.return_value
        mock_instance.is_connected.return_value = True
        mock_instance.eth.contract.return_value = MagicMock()

        # Mock account creation from private key
        mock_account = MagicMock()
        mock_account.address = MOCK_SENDER_ADDRESS
        mock_instance.eth.account.from_key.return_value = mock_account

        # Configure to_checksum_address to just return the input
        MockWeb3.to_checksum_address.side_effect = lambda addr: addr

        yield MockWeb3


@pytest.fixture
def mock_slack():
    """Fixture to create a mock SlackNotifier."""
    return MagicMock()


@pytest.fixture
def blockchain_client(mock_w3, mock_slack, mock_file):
    """Fixture to create a BlockchainClient with mocked dependencies."""
    with patch("src.models.blockchain_client.Web3", mock_w3):
        client = BlockchainClient(
            rpc_providers=MOCK_RPC_PROVIDERS,
            contract_address=MOCK_CONTRACT_ADDRESS,
            project_root=MOCK_PROJECT_ROOT,
            block_explorer_url=MOCK_BLOCK_EXPLORER_URL,
            tx_timeout_seconds=MOCK_TX_TIMEOUT_SECONDS,
            slack_notifier=mock_slack,
        )

        # Attach mocks for easy access in tests
        client.mock_w3_instance = client.w3
        client.mock_file = mock_file
        return client


# 1. Initialization and Connection Tests


def test_successful_initialization(blockchain_client: BlockchainClient, mock_w3, mock_file):
    """
    Tests that the BlockchainClient initializes correctly on the happy path.
    """
    # The client is created by the fixture. We just assert on the state.
    client = blockchain_client

    # 2. Assertions
    # Assert ABI was loaded
    mock_file.assert_called_once_with(MOCK_PROJECT_ROOT / "contracts" / "contract.abi.json")

    # Assert Web3 was initialized with the primary RPC
    mock_w3.HTTPProvider.assert_called_with(MOCK_RPC_PROVIDERS[0])
    mock_w3.assert_called_once_with(mock_w3.HTTPProvider.return_value)

    # Assert connection was checked
    client.w3.is_connected.assert_called_once()

    # Assert contract object was created
    client.mock_w3_instance.eth.contract.assert_called_once_with(address=MOCK_CONTRACT_ADDRESS, abi=MOCK_ABI)
    assert client.w3 is not None
    assert client.contract is not None


def test_initialization_fails_if_abi_not_found(mock_w3, mock_slack):
    """
    Tests that BlockchainClient raises an exception if the ABI file cannot be found.
    """
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = FileNotFoundError("ABI not found")
        with pytest.raises(FileNotFoundError, match="ABI not found"):
            with patch("src.models.blockchain_client.Web3", mock_w3):
                BlockchainClient(
                    rpc_providers=MOCK_RPC_PROVIDERS,
                    contract_address=MOCK_CONTRACT_ADDRESS,
                    project_root=MOCK_PROJECT_ROOT,
                    block_explorer_url=MOCK_BLOCK_EXPLORER_URL,
                    tx_timeout_seconds=MOCK_TX_TIMEOUT_SECONDS,
                    slack_notifier=mock_slack,
                )


def test_rpc_failover_mechanism(mock_w3, mock_slack):
    """
    Tests that the client successfully fails over to a secondary RPC if the primary fails.
    """
    # Mock the Web3 instance to simulate the primary RPC failing and the secondary succeeding
    mock_w3_instance = mock_w3()
    mock_w3_instance.is_connected.side_effect = [False, True]

    with patch("builtins.open", mock_open(read_data=json.dumps(MOCK_ABI))):
        with patch("src.models.blockchain_client.Web3", MagicMock(return_value=mock_w3_instance)) as MockWeb3:
            client = BlockchainClient(
                rpc_providers=MOCK_RPC_PROVIDERS,
                contract_address=MOCK_CONTRACT_ADDRESS,
                project_root=MOCK_PROJECT_ROOT,
                block_explorer_url=MOCK_BLOCK_EXPLORER_URL,
                tx_timeout_seconds=MOCK_TX_TIMEOUT_SECONDS,
                slack_notifier=mock_slack,
            )
            # Assertions
            # The HTTPProvider should have been called for both RPCs
            assert MockWeb3.HTTPProvider.call_count == 2
            assert MockWeb3.HTTPProvider.call_args_list[0].args == (MOCK_RPC_PROVIDERS[0],)
            assert MockWeb3.HTTPProvider.call_args_list[1].args == (MOCK_RPC_PROVIDERS[1],)

            # The connection check should have been called twice
            assert mock_w3_instance.is_connected.call_count == 2

            # The client should be connected and pointing to the secondary provider index
            assert client.current_rpc_index == 1


def test_connection_error_if_all_rpcs_fail(mock_w3, mock_slack):
    """
    Tests that a ConnectionError is raised if the client cannot connect to any RPC provider.
    """
    # Mock the Web3 instance to simulate all RPCs failing
    mock_w3_instance = mock_w3()
    mock_w3_instance.is_connected.return_value = False

    with patch("builtins.open", mock_open(read_data=json.dumps(MOCK_ABI))):
        with patch("src.models.blockchain_client.Web3", MagicMock(return_value=mock_w3_instance)):
            with pytest.raises(
                requests.exceptions.ConnectionError, match="Failed to connect to any of the 2 RPC providers."
            ):
                BlockchainClient(
                    rpc_providers=MOCK_RPC_PROVIDERS,
                    contract_address=MOCK_CONTRACT_ADDRESS,
                    project_root=MOCK_PROJECT_ROOT,
                    block_explorer_url=MOCK_BLOCK_EXPLORER_URL,
                    tx_timeout_seconds=MOCK_TX_TIMEOUT_SECONDS,
                    slack_notifier=mock_slack,
                )


# 2. Account and Transaction Logic Tests


def test_setup_transaction_account_success(blockchain_client: BlockchainClient):
    """
    Tests that _setup_transaction_account returns the correct address and formatted key
    for a valid private key.
    """
    with patch(
        "src.models.blockchain_client.validate_and_format_private_key", return_value=MOCK_PRIVATE_KEY
    ) as mock_validate:
        address, key = blockchain_client._setup_transaction_account(MOCK_PRIVATE_KEY)

        mock_validate.assert_called_once_with(MOCK_PRIVATE_KEY)
        blockchain_client.mock_w3_instance.eth.account.from_key.assert_called_once_with(MOCK_PRIVATE_KEY)
        assert address == MOCK_SENDER_ADDRESS
        assert key == MOCK_PRIVATE_KEY


def test_setup_transaction_account_invalid_key(blockchain_client: BlockchainClient):
    """
    Tests that _setup_transaction_account raises KeyValidationError for an invalid key.
    """
    with patch("src.models.blockchain_client.validate_and_format_private_key") as mock_validate:
        mock_validate.side_effect = KeyValidationError("Invalid key")

        with pytest.raises(KeyValidationError, match="Invalid key"):
            blockchain_client._setup_transaction_account("invalid-key")


def test_estimate_transaction_gas_success(blockchain_client: BlockchainClient):
    """
    Tests that _estimate_transaction_gas correctly estimates gas and adds a 25% buffer.
    """
    # Setup
    mock_contract_func = MagicMock()
    # The call chain is contract_func().estimate_gas()
    mock_contract_func.return_value.estimate_gas.return_value = 100_000

    # Action
    gas_limit = blockchain_client._estimate_transaction_gas(
        contract_func=mock_contract_func, indexer_addresses=[], data_bytes=b"", sender_address=MOCK_SENDER_ADDRESS
    )

    # Assertions
    assert gas_limit == 125_000  # 100_000 * 1.25
    mock_contract_func.return_value.estimate_gas.assert_called_once_with({"from": MOCK_SENDER_ADDRESS})


def test_estimate_transaction_gas_failure(blockchain_client: BlockchainClient):
    """
    Tests that _estimate_transaction_gas raises an exception if the RPC call fails.
    """
    # Setup
    mock_contract_func = MagicMock()
    mock_contract_func.return_value.estimate_gas.side_effect = ValueError("RPC Error")

    # Action & Assertion
    with pytest.raises(ValueError, match="RPC Error"):
        blockchain_client._estimate_transaction_gas(
            contract_func=mock_contract_func,
            indexer_addresses=[],
            data_bytes=b"",
            sender_address=MOCK_SENDER_ADDRESS,
        )


def test_determine_transaction_nonce_new(blockchain_client: BlockchainClient):
    """
    Tests that the next available nonce is fetched for a new transaction (replace=False).
    """
    # Setup
    expected_nonce = 10
    blockchain_client.mock_w3_instance.eth.get_transaction_count.return_value = expected_nonce

    # Action
    nonce = blockchain_client._determine_transaction_nonce(MOCK_SENDER_ADDRESS, replace=False)

    # Assertions
    assert nonce == expected_nonce
    blockchain_client.mock_w3_instance.eth.get_transaction_count.assert_called_once_with(MOCK_SENDER_ADDRESS)


def test_determine_transaction_nonce_replace(blockchain_client: BlockchainClient):
    """
    Tests that the nonce of the oldest pending transaction is used for replacement (replace=True).
    """
    # Setup
    # Simulate pending transactions for the sender
    pending_txs = {
        "transactions": [
            {"from": MOCK_SENDER_ADDRESS, "nonce": 15},
            {"from": "0xanotherAddress", "nonce": 16},
            {"from": MOCK_SENDER_ADDRESS, "nonce": 12},  # This is the oldest
        ]
    }
    blockchain_client.mock_w3_instance.eth.get_block.return_value = pending_txs

    # Action
    nonce = blockchain_client._determine_transaction_nonce(MOCK_SENDER_ADDRESS, replace=True)

    # Assertions
    assert nonce == 12
    blockchain_client.mock_w3_instance.eth.get_block.assert_called_once_with("pending", full_transactions=True)


def test_get_gas_prices_success(blockchain_client: BlockchainClient):
    """
    Tests that _get_gas_prices successfully fetches and returns the base and priority fees.
    """
    # Setup
    mock_base_fee = 100_000_000_000  # 100 gwei
    mock_priority_fee = 2_000_000_000  # 2 gwei

    blockchain_client.w3.eth.get_block.return_value = {"baseFeePerGas": hex(mock_base_fee)}
    blockchain_client.w3.eth.max_priority_fee = mock_priority_fee

    # Action
    base_fee, max_priority_fee = blockchain_client._get_gas_prices(replace=False)

    # Assertions
    assert base_fee == mock_base_fee
    assert max_priority_fee == mock_priority_fee


def test_build_transaction_params_standard(blockchain_client: BlockchainClient):
    """
    Tests that transaction parameters are built correctly for a standard transaction.
    """
    # Action
    tx_params = blockchain_client._build_transaction_params(
        sender_address=MOCK_SENDER_ADDRESS,
        nonce=1,
        chain_id=1,
        gas_limit=21000,
        base_fee=100,
        max_priority_fee=10,
        replace=False,
    )

    # Assertions
    assert tx_params["maxFeePerGas"] == 210  # base_fee * 2 + max_priority_fee
    assert tx_params["maxPriorityFeePerGas"] == 10


def test_build_transaction_params_replace(blockchain_client: BlockchainClient):
    """
    Tests that transaction parameters are built with higher gas for a replacement transaction.
    """
    # Action
    tx_params = blockchain_client._build_transaction_params(
        sender_address=MOCK_SENDER_ADDRESS,
        nonce=1,
        chain_id=1,
        gas_limit=21000,
        base_fee=100,
        max_priority_fee=10,
        replace=True,
    )

    # Assertions
    assert tx_params["maxFeePerGas"] == 420  # base_fee * 4 + max_priority_fee * 2
    assert tx_params["maxPriorityFeePerGas"] == 20


def test_send_signed_transaction_success(blockchain_client: BlockchainClient):
    """
    Tests that a signed transaction is sent and its hash is returned on success.
    """
    # Setup
    mock_signed_tx = MagicMock()
    mock_signed_tx.rawTransaction = b"raw_tx_bytes"
    mock_tx_hash = b"tx_hash"
    blockchain_client.mock_w3_instance.eth.send_raw_transaction.return_value = mock_tx_hash
    blockchain_client.mock_w3_instance.eth.wait_for_transaction_receipt.return_value = {"status": 1}

    # Action
    tx_hash_hex = blockchain_client._send_signed_transaction(mock_signed_tx)

    # Assertions
    assert tx_hash_hex == mock_tx_hash.hex()
    blockchain_client.mock_w3_instance.eth.send_raw_transaction.assert_called_once_with(
        mock_signed_tx.rawTransaction
    )
    blockchain_client.mock_w3_instance.eth.wait_for_transaction_receipt.assert_called_once_with(
        mock_tx_hash, MOCK_TX_TIMEOUT_SECONDS
    )


def test_send_signed_transaction_reverted(blockchain_client: BlockchainClient):
    """
    Tests that an exception is raised if the transaction is reverted on-chain.
    """
    # Setup
    mock_signed_tx = MagicMock()
    mock_tx_hash = b"tx_hash"
    blockchain_client.mock_w3_instance.eth.send_raw_transaction.return_value = mock_tx_hash
    blockchain_client.mock_w3_instance.eth.wait_for_transaction_receipt.return_value = {"status": 0}  # Reverted

    # Action & Assertion
    with pytest.raises(Exception, match=f"Transaction failed: {MOCK_BLOCK_EXPLORER_URL}/tx/{mock_tx_hash.hex()}"):
        blockchain_client._send_signed_transaction(mock_signed_tx)


# 3. Orchestration Tests


def test_send_transaction_to_allow_indexers_orchestration(blockchain_client: BlockchainClient):
    """
    Tests that `send_transaction_to_allow_indexers` correctly calls the main execution method.
    """
    # Setup
    blockchain_client._execute_complete_transaction = MagicMock(return_value="tx_hash")

    # Action
    with patch("src.models.blockchain_client.Web3.to_checksum_address", side_effect=lambda x: x):
        tx_hash = blockchain_client.send_transaction_to_allow_indexers(
            indexer_addresses=[MOCK_SENDER_ADDRESS],
            private_key=MOCK_PRIVATE_KEY,
            chain_id=1,
            contract_function="allow",
            replace=False,
        )

    # Assertions
    assert tx_hash == "tx_hash"
    blockchain_client._execute_complete_transaction.assert_called_once()
    call_args = blockchain_client._execute_complete_transaction.call_args.args[0]
    assert call_args["private_key"] == MOCK_PRIVATE_KEY
    assert call_args["indexer_addresses"] == [MOCK_SENDER_ADDRESS]


def test_batch_processing_splits_correctly(blockchain_client: BlockchainClient):
    """
    Tests that the batch processing logic correctly splits a list of addresses
    into multiple transactions based on batch size.
    """
    # Setup
    # Create a list of 5 addresses
    addresses = [f"0x{i}" * 40 for i in range(5)]
    blockchain_client.send_transaction_to_allow_indexers = MagicMock(return_value="tx_hash")

    # Action
    # Use a batch size of 2, which should result in 3 calls (2, 2, 1)
    tx_hashes = blockchain_client.batch_allow_indexers_issuance_eligibility(
        indexer_addresses=addresses,
        private_key=MOCK_PRIVATE_KEY,
        chain_id=1,
        contract_function="allow",
        batch_size=2,
    )

    # Assertions
    assert len(tx_hashes) == 3
    assert blockchain_client.send_transaction_to_allow_indexers.call_count == 3
    # Check the contents of each call
    assert blockchain_client.send_transaction_to_allow_indexers.call_args_list[0][0][0] == addresses[0:2]
    assert blockchain_client.send_transaction_to_allow_indexers.call_args_list[1][0][0] == addresses[2:4]
    assert blockchain_client.send_transaction_to_allow_indexers.call_args_list[2][0][0] == addresses[4:5]


def test_batch_processing_halts_on_failure(blockchain_client: BlockchainClient):
    """
    Tests that the batch processing halts immediately if one of the transactions fails.
    """
    # Setup
    addresses = [f"0x{i}" * 40 for i in range(5)]
    # Simulate failure on the second call
    blockchain_client.send_transaction_to_allow_indexers = MagicMock(
        side_effect=["tx_hash_1", Exception("RPC Error"), "tx_hash_3"]
    )

    # Action & Assertion
    with pytest.raises(Exception, match="RPC Error"):
        blockchain_client.batch_allow_indexers_issuance_eligibility(
            indexer_addresses=addresses,
            private_key=MOCK_PRIVATE_KEY,
            chain_id=1,
            contract_function="allow",
            batch_size=2,
        )

    # Assertions
    # The method should have only been called twice (the first success, the second failure)
    assert blockchain_client.send_transaction_to_allow_indexers.call_count == 2
