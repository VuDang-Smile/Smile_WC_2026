#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 scripts/test_google_chat_context.py
python3 scripts/test_workspace_glue.py
python3 scripts/simulate_betting_cases.py
