# Service Quality Oracle

## Overview

This repository implements a Docker container service for the Service Quality Oracle. The oracle consumes data from BigQuery, processes it to determine indexer issuance rewards eligibility, based on a defined threshold algorithm, and posts issuance eligibility data on-chain.

### Key Features

The oracle runs with the following functionality:
- **BigQuery Integration**: Fetches indexer performance data from Google BigQuery
- **Eligibility Processing**: Applies threshold algorithm to determine issuance rewards eligibility based on service quality
- **Blockchain Integration**: Posts issuance eligibility updates to the ServiceQualityOracle contract
- **Slack Notifications**: Sends success/failure notifications for monitoring
- **Docker Deployment**: Containerized and running with health checks
- **Scheduled Execution**: Runs daily at 10:00 UTC
- **RPC Failover**: Automatic failover between multiple RPC providers for reliability

### Monitoring & Notifications

The oracle includes built-in Slack notifications for operational monitoring:

- **Success Notifications**: Sent when oracle runs complete successfully, including transaction details
- **Failure Notifications**: Sent when errors occur, with detailed error information for debugging
- **Simple & Reliable**: Direct notifications from the oracle process itself

For production deployments, container orchestration (Kubernetes) should handle:
- Container health monitoring and restarts
- Resource management and scaling
- Infrastructure-level alerts and monitoring

### Testing Notifications

Test notification functionality:
```bash
# Set webhook URL
export SLACK_WEBHOOK_URL="your_webhook_url"

# Run notification tests
./scripts/test_slack_notifications.py
```

## Configuration

## Eligibility Criteria

Please refer to the [ELIGIBILITY_CRITERIA.md](./ELIGIBILITY_CRITERIA.md) file to view the latest criteria for issuance. We are also posting upcoming criteria in that document.

## Data Flow

The application follows this data flow:

1. **BigQuery Data Acquisition**: The `bigquery_fetch_and_save_indexer_issuance_eligibility_data_finally_return_eligible_indexers` function in `issuance_data_access_helper.py` fetches fresh data from BigQuery, processes it to determine eligibility, and returns the eligibility data list that would then be posted on chain.
   - This function also ensures that data is saved to local files in dated directories for auditing/historical reference over the data retention period.

2. **Blockchain Publication**: The eligible indexers list from step 1 is directly posted on-chain to a smart contract. Batching of transactions is performed if necessary.

## CI/CD Pipeline

Automated quality checks and security scanning via GitHub Actions. Run `./scripts/ruff_check_format_assets.sh` locally before pushing.

For details: [.github/README.md](./.github/README.md)

## Getting Started

### Quick Start with Docker

1. **Clone the repository**:
   ```bash
   git clone https://github.com/graphprotocol/service-quality-oracle.git
   cd service-quality-oracle
   ```

2. **Set up environment variables/config.toml**:

3. **Build and run with Docker Compose**:
   ```bash
   docker-compose up --build -d
   ```

4. **Monitor logs**:
   ```bash
   docker-compose logs -f
   ```

5. **Check health status**:
   ```bash
   docker-compose ps
   ```

### Development Workflow

For contributors working on the codebase:

**Before pushing:**
   ```bash
   # Setup venv
   python3 -m venv venv
   source venv/bin/activate

   # Install requirements
   pip install -r requirements.txt

   # Use the custom ruff script for linting (includes SQL formatting and aggressive linting)
   ./scripts/ruff_check_format_assets.sh
   ```

**Optional checks:**
```bash
mypy src/ --ignore-missing-imports
bandit -r src/
```

> **Note:** The CI/CD pipeline uses the custom `ruff_check_format_assets.sh` script which includes SQL whitespace fixes and more aggressive formatting than standard ruff. 
> 
> Always run this script locally before pushing to avoid CI failures.

## License

[License information to be determined.]

## TODO List (only outstanding TODOs)

### 1. Production Readiness
- [ ] Check error recovery mechanisms to see if they could be improved (RPC failover, retry logic)
- [ ] Verify health check endpoints or processes (Docker healthcheck)

### 2. Testing
- [ ] Create unit tests for all components
- [ ] Create integration tests for the entire pipeline
- [ ] Security review of code and dependencies

### 3. Documentation
- [ ] Documentation of all major components
- [ ] Document operational procedures

### 4. Optimization
- [ ] Optimize dependencies and container setup
- [ ] Ensure unused files, functions & dependencies are removed from codebase