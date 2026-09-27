#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${APP_PYTHON:-python3}" "$PROJECT_DIR/bootstrap.py"
