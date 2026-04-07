#!/bin/bash
# Sovereign CLI Launcher
# Automatically hooks into the workspace virtual environment where Textual is installed.

VENV_PATH="../Living mind/.venv/bin/python3"

if [ -f "$VENV_PATH" ]; then
    "$VENV_PATH" cli_ledger.py
else
    echo "Error: Virtual environment not found at $VENV_PATH"
    echo "Please ensure the Living mind workspace is located next to living-mind-cortex."
fi
