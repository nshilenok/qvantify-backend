#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f "env.local" ]; then
  set -a
  # shellcheck disable=SC1091
  source "env.local"
  set +a
fi

echo "==> Import check (server.py)"
python3 -c "import server"

echo "==> Branch safety check"
python3 scripts/release_safety_check.py --repo-path . --skip-alias-check

echo "==> API tests (pytest)"
pytest

echo "==> FE tests (Playwright)"
npm run test:e2e

echo "✅ All local release checks passed."
