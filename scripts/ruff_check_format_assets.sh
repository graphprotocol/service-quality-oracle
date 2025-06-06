#!/bin/bash
# This is a script to run ruff linting/formatting on the codebase. It is used to ensure that the codebase is clean and formatted correctly, applying automatic fixes where possible.


# Check if the script is being run from the repository root
if [ ! -f "requirements.txt" ]; then
    echo "Error: Please run this script from the repository root"
    exit 1
fi

# Run ruff check with auto-fix first (including unsafe fixes for typing annotations)
echo "Running ruff check with auto-fix..."
ruff check src tests scripts --fix --unsafe-fixes --show-fixes

# Run ruff format
echo "Running ruff format..."
ruff format src tests scripts

# Fix SQL-specific whitespace issues after ruff (only trailing whitespace, avoid blank line removal)
echo "Fixing SQL trailing whitespace issues in BigQuery provider..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - Only fix trailing whitespace after SQL keywords
    find src/models -name "*.py" -type f -exec sed -i '' -E 's/([A-Z]+) +$/\1/g' {} \;
else
    # Linux (CI environment) - Only fix trailing whitespace after SQL keywords
    find src/models -name "*.py" -type f -exec sed -i -E 's/([A-Z]+) +$/\1/g' {} \;
fi
echo "SQL whitespace issues fixed!"

# Show remaining issues (mainly line length issues that need manual intervention)
echo -e "\n\nRemaining issues that need manual attention:"
ruff check src tests scripts --select E501 --statistics

echo "Linting/formatting complete! All auto-fixable issues have been resolved."
echo "Manually review and fix any remaining line length issues if desired."
