#!/bin/bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
# Kill any existing uvicorn on port 8005
pkill -f "uvicorn.*8005" || true
# Run uvicorn from the root
./.venv/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8005
