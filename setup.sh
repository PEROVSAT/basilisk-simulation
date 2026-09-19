#!/usr/bin/env bash
# Compatibility wrapper. Prefer: make shell  /  make run SCRIPT=...
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "${1:-}" == "--rebuild" ]]; then
  make image
  shift
fi

exec make shell
