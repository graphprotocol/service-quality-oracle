# CI/CD Pipeline

## Workflows

### CI (`ci.yml`)
- **Code Quality**: Custom ruff script, MyPy, syntax validation
- **Docker Build**: Image build and compose validation
- **Runs on**: PRs and pushes to `main`

### Tests (`tests.yml`)
- **Unit/Integration Tests**: Auto-detects and runs tests when they exist
- **Runs on**: PRs and pushes to `main`

### Security (`security.yml`)
- **Daily Scans**: Dependencies (Safety), code security (Bandit), secrets (TruffleHog), Docker (Trivy)
- **Runs on**: Daily 2 AM UTC, PRs, pushes to `main`

### PR Check (`pr-check.yml`)
- **Basic Validation**: Non-empty PR title/description, merge conflict check
- **Runs on**: PRs to `main`

## Local Development

**Before pushing:**
```bash
./scripts/ruff_check_format_assets.sh
```

**Optional checks:**
```bash
mypy src/ --ignore-missing-imports
bandit -r src/
```

## Requirements
- Non-empty PR title/description
- Pass code quality checks (ruff script must not make changes)
- Docker must build successfully
- No merge conflicts

## Tests
Create test files in `tests/` directory - CI will auto-detect and run them. 