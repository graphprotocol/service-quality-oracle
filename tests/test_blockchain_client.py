"""
Unit tests for the BlockchainClient.
"""

# TODO: Test successful initialization and connection to primary RPC.
# TODO: Test failure to load contract ABI raises an error.
# TODO: Test RPC failover mechanism by mocking a failing primary provider.
# TODO: Test connection error when all RPC providers are unavailable.
# TODO: Test `_setup_transaction_account` with both valid and invalid private keys.
# TODO: Test `_estimate_transaction_gas` returns a buffered gas estimate on success.
# TODO: Test `_estimate_transaction_gas` raises an exception on RPC call failure.
# TODO: Test `_determine_transaction_nonce` for a new transaction (replace=False).
# TODO: Test `_determine_transaction_nonce` for a replacement transaction (replace=True).
# TODO: Test `_get_gas_prices` successfully fetches base and priority fees.
# TODO: Test `_build_transaction_params` for both standard and replacement gas prices.
# TODO: Test `_send_signed_transaction` on success, including waiting for the receipt.
# TODO: Test `_send_signed_transaction` on a reverted transaction.
# TODO: Test `send_transaction_to_allow_indexers` with a mocked `_execute_complete_transaction`.
# TODO: Test `batch_allow_indexers_issuance_eligibility` correctly splits addresses into batches.
# TODO: Test `batch_allow_indexers_issuance_eligibility` halts if one batch fails.
