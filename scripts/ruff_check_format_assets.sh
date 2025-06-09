#!/bin/bash
# This is a script to run ruff linting/formatting on the codebase. It is used to ensure that the codebase is clean and formatted correctly, applying automatic fixes where possible.


# Check if the script is being run from the repository root
if [ ! -f "requirements.txt" ]; then
    echo "Error: Please run this script from the repository root"
    exit 1
fi

# Check if pyproject.toml exists with ruff configuration
if [ ! -f "pyproject.toml" ]; then
    echo "Error: pyproject.toml not found. Make sure it exists with proper ruff configuration"
    exit 1
fi

# Run ruff check with auto-fix first (including unsafe fixes for typing annotations)
echo "Running ruff check with auto-fix..."
ruff check src tests scripts --fix --unsafe-fixes --show-fixes

# Run ruff format with respect to project configuration
echo "Running ruff format..."
ruff format src tests scripts

# Post-process files to ensure custom spacing rules are applied
echo "Applying custom spacing rules with custom formatter..."
find src tests scripts -name "*.py" -print0 | xargs -0 python3 scripts/custom_formatter.py

# Show remaining issues (mainly line length issues that need manual intervention)
echo -e "\n\nRemaining issues that need manual attention:"
ruff check src tests scripts --select E501 --statistics

echo "Linting/formatting complete! All auto-fixable issues have been resolved."
echo "Manually review and fix any remaining line length issues if desired."
