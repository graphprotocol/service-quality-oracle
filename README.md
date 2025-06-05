# Service Quality Oracle


## Overview

This repository implements a Docker container service for the Service Quality Oracle. The oracle consumes data from BigQuery, processes it to determine indexer issuance rewards eligibility, based on a defined threshold algorithm, and posts issuance eligibility data on-chain.

The oracle runs with the following functionality:
- **BigQuery Integration**: Fetches indexer performance data from Google BigQuery
- **Eligibility Processing**: Applies threshold algorithm to determine issuance rewards eligibility based on service quality
- **Blockchain Integration**: Posts issuance eligibility updates to the ServiceQualityOracle contract
- **Docker Deployment**: Containerized and running with health checks
- **Scheduled Execution**: Runs daily at 10:00 UTC
- **RPC Failover**: Automatic failover between multiple RPC providers for reliability


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

1. **Run local quality checks**:
   ```bash
   # Use the custom ruff script (includes SQL formatting and aggressive linting)
   ./scripts/ruff_check_format_assets.sh

   # Type checking
   mypy src/ --ignore-missing-imports

   # Security scanning
   bandit -r src/
   ```

**Note:** The CI/CD pipeline uses the custom `ruff_check_format_assets.sh` script which includes SQL whitespace fixes and more aggressive formatting than standard ruff. Always run this script locally before pushing to avoid CI failures.

## License

[License information to be determined.]


## TODO List (only outstanding TODOs)

### Testing & Quality Assurance
- [ ] Create unit tests for all components
- [ ] Slack monitoring integration
  - [ ] Add notification logic for failed runs so we are aware in a slack channel
  - [ ] Initially we can notify for successful runs too
- [ ] Create integration tests for the entire pipeline
- [ ] Implement mocking for blockchain interactions in test environment
- [ ] Perform security review of code and dependencies
- [ ] Ensure unused files, functions & dependencies are removed from codebase

### Documentation

- [ ] Documentation of all major components
- [ ] Document operational procedures

### Production Readiness
- [ ] Check error recovery mechanisms to see if they could be improved (RPC failover, retry logic)
- [ ] Verify health check endpoints or processes (Docker healthcheck)

