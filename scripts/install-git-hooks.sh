#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".git" ]; then
  echo "❌ .git directory not found. Run this from a git repo."
  exit 1
fi

HOOK_PATH=".git/hooks/pre-push"

cat > "$HOOK_PATH" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

scripts/local-release-checks.sh
EOF

chmod +x "$HOOK_PATH"
echo "✅ Installed pre-push hook at $HOOK_PATH"
