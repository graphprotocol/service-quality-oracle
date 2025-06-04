#!/bin/bash
# This is a script to run ruff linting/formatting on the codebase. It is used to ensure that the codebase is clean and formatted correctly, applying automatic fixes where possible.


# Check if the script is being run from the repository root
if [ ! -f "requirements.txt" ]; then
    echo "Error: Please run this script from the repository root"
    exit 1
fi

# Fix SQL whitespace issues before running ruff
echo "Fixing SQL whitespace issues in BigQuery provider..."
find src/models -name "*.py" -type f -exec sed -i '' -E 's/([A-Z]+) +$/\1/g' {} \;
find src/models -name "*.py" -type f -exec sed -i '' -E 's/^( +)$//' {} \;
echo "SQL whitespace issues fixed!"

# Run ruff check with auto-fix, including unsafe fixes for typing annotations
echo "Running ruff check with auto-fix..."
ruff check src tests scripts --fix --unsafe-fixes --show-fixes

# Run ruff format with more aggressive formatting
echo "Running ruff format..."
ruff format src tests scripts

# Show remaining issues (mainly line length issues that need manual intervention)
echo -e "\n\nRemaining issues that need manual attention:"
ruff check src tests scripts --select E501 --statistics

echo "Linting/formatting complete! All auto-fixable issues have been resolved."
echo "Manually review and fix any remaining line length issues if desired."
