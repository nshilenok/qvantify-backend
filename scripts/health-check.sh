#!/usr/bin/env bash
set -u

BASE_URL="${QVANTIFY_BASE_URL:-https://app.qvantify.com}"
RAILWAY_URL="${QVANTIFY_RAILWAY_URL:-https://qvantify.up.railway.app}"
PROJECT_ID="${QVANTIFY_PROJECT_ID:-sample_game_funnel_2026_01_14}"

failures=0

print_section() {
  printf "\n== %s ==\n" "$1"
}

request() {
  local name="$1"
  local url="$2"
  shift 2

  local tmp
  tmp="$(mktemp)"
  local code
  code="$(curl -sS -o "$tmp" -w "%{http_code}" "$url" "$@" || true)"

  print_section "$name"
  echo "URL: $url"
  echo "status: $code"

  if [[ "$code" != "200" ]]; then
    echo "body (truncated):"
    head -c 500 "$tmp"
    echo
    rm -f "$tmp"
    failures=$((failures + 1))
    return
  fi

  cat "$tmp"
  echo
  rm -f "$tmp"
}

check_health_json() {
  local label="$1"
  local body="$2"
  python3 - <<PY "$label" "$body" || return 1
import json, sys
label = sys.argv[1]
body = sys.argv[2]
try:
    data = json.loads(body)
except Exception:
    print(f"{label}: invalid JSON")
    raise SystemExit(1)
ok = data.get("ok") is True
db = data.get("db_configured") is True
print(f"{label}: ok={data.get('ok')} db_configured={data.get('db_configured')}")
if not ok or not db:
    raise SystemExit(1)
PY
}

check_project_json() {
  local body="$1"
  python3 - <<PY "$body" || return 1
import json, sys
body = sys.argv[1]
try:
    data = json.loads(body)
except Exception:
    print("project: invalid JSON")
    raise SystemExit(1)
if not isinstance(data, list) or not data:
    print("project: empty result")
    raise SystemExit(1)
print(f"project: ok ({len(data)} row(s))")
PY
}

print_section "Config"
echo "BASE_URL=$BASE_URL"
echo "RAILWAY_URL=$RAILWAY_URL"
echo "PROJECT_ID=$PROJECT_ID"

# Health checks
health_body="$(curl -sS "$BASE_URL/api/health" || true)"
request "BASE /api/health" "$BASE_URL/api/health"
if ! check_health_json "base" "$health_body"; then
  failures=$((failures + 1))
fi

railway_health_body="$(curl -sS "$RAILWAY_URL/api/health" || true)"
request "RAILWAY /api/health" "$RAILWAY_URL/api/health"
if ! check_health_json "railway" "$railway_health_body"; then
  failures=$((failures + 1))
fi

# Project config check (tests DB connectivity + rewrite)
project_body="$(curl -sS -H "projectId: $PROJECT_ID" "$BASE_URL/api/project/" || true)"
request "BASE /api/project/" "$BASE_URL/api/project/" -H "projectId: $PROJECT_ID"
if ! check_project_json "$project_body"; then
  failures=$((failures + 1))
fi

print_section "Summary"
if [[ "$failures" -eq 0 ]]; then
  echo "All checks passed."
  exit 0
fi

echo "Failures: $failures"
exit 1
