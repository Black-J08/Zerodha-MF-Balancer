#!/bin/bash
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Please run ./setup.sh first."
    exit 1
fi
.venv/bin/python -m mf_balancer.src.main "$@"
