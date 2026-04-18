#!/usr/bin/env bash
# run.sh — Setup and run the Edge Favorites Cleaner
# Usage: ./run.sh [arguments to pass to bookmark_cleaner.py]
# Example: ./run.sh favorites_4_18_26.html --threads 10 --timeout 15

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
SCRIPT="$SCRIPT_DIR/bookmark_cleaner.py"

echo ""
echo "================================================"
echo "  Edge Favorites Cleaner & Organizer"
echo "================================================"
echo ""

# ── Find Python 3 ─────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found. Please install Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PYTHON_VERSION"

# ── Check bookmark_cleaner.py exists ──────────────────────────────────────
if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: bookmark_cleaner.py not found in $SCRIPT_DIR"
    exit 1
fi

# ── Create virtual environment if it doesn't exist ────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
    echo "Virtual environment created at: $VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# ── Activate virtual environment ──────────────────────────────────────────
echo "Activating virtual environment..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── Install/upgrade dependencies ──────────────────────────────────────────
echo "Installing dependencies..."
# Note: pip self-upgrade is skipped — it can fail inside a venv on newer Python versions
pip install requests openai python-dotenv --quiet
echo "Dependencies ready."

# ── Prompt for input file if not provided ─────────────────────────────────
if [ $# -eq 0 ]; then
    echo ""
    read -rp "Enter the path to your favorites HTML file: " INPUT_FILE
    if [ -z "$INPUT_FILE" ]; then
        echo "ERROR: No input file provided."
        exit 1
    fi
    set -- "$INPUT_FILE"
fi

# ── Run the script ─────────────────────────────────────────────────────────
echo ""
echo "Running bookmark_cleaner.py $*"
echo ""

python "$SCRIPT" "$@"
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "Done."
else
    echo "Script exited with code $EXIT_CODE."
fi

exit $EXIT_CODE