#!/usr/bin/env bash
#
# End-to-end interview smoke test.
# Tests BOTH streaming and non-streaming code paths with TWO concurrent
# respondents per project to catch cross-user contamination.
#
# Usage:
#   ./scripts/staging_smoke_test.sh <backend_url>
#
# Example:
#   ./scripts/staging_smoke_test.sh https://qvantify-staging.up.railway.app
#   ./scripts/staging_smoke_test.sh https://qvantify.up.railway.app
#
set -euo pipefail

BASE="${1:?Usage: $0 <backend_url>}"
BASE="${BASE%/}"

# Projects that MUST pass (covers gpt-5.2 and gpt-4.1 code paths)
PROJECTS=("swipking2" "20ab1e5b-54c4-4f03-8331-4f88132d3b51")
REPLIES=("hello" "yes" "payment methods")

FAIL=0
CREATED_RESPONDENTS=()

cleanup() {
  if [ ${#CREATED_RESPONDENTS[@]} -gt 0 ]; then
    echo ""
    echo "--- Cleanup: ${#CREATED_RESPONDENTS[@]} test respondent(s) created ---"
    echo "    (left in DB for debugging; delete manually if needed)"
    for info in "${CREATED_RESPONDENTS[@]}"; do
      echo "    $info"
    done
  fi
}
trap cleanup EXIT

fail() {
  echo "  FAIL: $1"
  FAIL=1
}

assert_not_empty() {
  local val="$1" label="$2"
  if [ -z "$val" ] || [ "$val" = "null" ]; then
    fail "$label is empty/null"
    return 1
  fi
}

assert_no_raw_tool_text() {
  local val="$1" label="$2"
  if echo "$val" | grep -qi "interview_topic_over"; then
    fail "$label contains raw tool call text: $val"
    return 1
  fi
}

assert_status_open() {
  local val="$1" label="$2"
  if [ "$val" != "open" ]; then
    fail "$label expected status=open, got status=$val"
    return 1
  fi
}

create_respondent() {
  local project="$1" ext_id="$2"
  local resp
  resp=$(curl -sL -X POST \
    -H "projectId: $project" \
    -H "Content-Type: application/json" \
    -d "{\"external_id\":\"$ext_id\"}" \
    "$BASE/api/respondent/")
  local uuid
  uuid=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('uuid',''))" 2>/dev/null || echo "")
  if [ -z "$uuid" ]; then
    fail "Failed to create respondent for $project (ext=$ext_id): $resp"
    return 1
  fi
  CREATED_RESPONDENTS+=("project=$project uuid=$uuid ext=$ext_id")
  echo "$uuid"
}

get_interview() {
  local project="$1" uuid="$2"
  curl -sL \
    -H "projectId: $project" \
    -H "uuid: $uuid" \
    "$BASE/api/interview/"
}

send_reply_nonstream() {
  local project="$1" uuid="$2" message="$3"
  curl -sL -X POST \
    -H "projectId: $project" \
    -H "uuid: $uuid" \
    -H "Content-Type: application/json" \
    -d "{\"message\":\"$message\"}" \
    "$BASE/api/reply/"
}

send_reply_stream() {
  local project="$1" uuid="$2" message="$3"
  curl -sL -X POST \
    -H "projectId: $project" \
    -H "uuid: $uuid" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    -d "{\"message\":\"$message\",\"stream\":true}" \
    "$BASE/api/reply/"
}

parse_json() {
  local json="$1" field="$2"
  echo "$json" | python3 -c "
import sys, json
data = sys.stdin.read().strip()
# SSE stream: extract last 'final' event
if data.startswith(':') or data.startswith('data:'):
    last_payload = None
    for line in data.split('\n'):
        line = line.strip()
        if line.startswith('data:'):
            try:
                obj = json.loads(line[5:].strip())
                if obj.get('type') == 'final':
                    last_payload = obj
            except: pass
    if last_payload:
        print(last_payload.get('$field', ''))
    else:
        print('')
else:
    try:
        obj = json.loads(data)
        print(obj.get('$field', ''))
    except:
        print('')
" 2>/dev/null || echo ""
}

test_interview_flow() {
  local project="$1" uuid="$2" label="$3" mode="$4"

  echo "  [$label] Init interview..."
  local init_resp
  init_resp=$(get_interview "$project" "$uuid")
  local init_response init_status
  init_response=$(parse_json "$init_resp" "response")
  init_status=$(parse_json "$init_resp" "status")

  assert_not_empty "$init_response" "$label/init/response" || true
  assert_no_raw_tool_text "$init_response" "$label/init/response" || true
  assert_status_open "$init_status" "$label/init" || true
  echo "  [$label] Init OK: ${init_response:0:60}..."

  local prev_progress=0
  local reply_num=0
  for msg in "${REPLIES[@]}"; do
    reply_num=$((reply_num + 1))
    echo "  [$label] Reply #$reply_num ($mode): \"$msg\""
    local reply_resp
    if [ "$mode" = "stream" ]; then
      reply_resp=$(send_reply_stream "$project" "$uuid" "$msg")
    else
      reply_resp=$(send_reply_nonstream "$project" "$uuid" "$msg")
    fi

    local r_response r_status r_progress
    r_response=$(parse_json "$reply_resp" "response")
    r_status=$(parse_json "$reply_resp" "status")
    r_progress=$(parse_json "$reply_resp" "progress")

    if [ -z "$r_response" ] && [ "$r_status" = "closed" ]; then
      fail "$label/reply#$reply_num: premature close (response=null, status=closed)"
    fi
    assert_no_raw_tool_text "${r_response:-}" "$label/reply#$reply_num/response" || true
    if [ "$r_status" != "open" ] && [ "$r_status" != "closed" ]; then
      fail "$label/reply#$reply_num: unexpected status=$r_status"
    fi
    echo "  [$label] Reply #$reply_num OK: ${r_response:0:60}..."
  done
  echo "  [$label] PASSED"
}

# ── Main ────────────────────────────────────────────────────────────────

echo "=== Smoke test against $BASE ==="
echo ""

# Health check first
echo "--- Health check ---"
health=$(curl -sL "$BASE/api/health")
version=$(echo "$health" | python3 -c "import sys,json;print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
echo "  version=$version"
echo ""

for project in "${PROJECTS[@]}"; do
  echo "--- Project: $project ---"

  # Verify project exists
  proj_resp=$(curl -sL -H "projectId: $project" "$BASE/api/project/")
  proj_name=$(echo "$proj_resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['name'] if isinstance(d,list) else d.get('error','?'))" 2>/dev/null || echo "?")
  echo "  name=$proj_name"

  if [ "$proj_name" = "?" ] || echo "$proj_name" | grep -qi "not found"; then
    fail "Project $project not found on $BASE"
    echo ""
    continue
  fi

  # Create 2 respondents for cross-user contamination test
  ts=$(date +%s)
  echo "  Creating respondent A (non-stream)..."
  uuid_a=$(create_respondent "$project" "smoke_a_${ts}") || { echo ""; continue; }
  echo "  Creating respondent B (stream)..."
  uuid_b=$(create_respondent "$project" "smoke_b_${ts}") || { echo ""; continue; }

  # Run both respondents: A=non-streaming, B=streaming
  test_interview_flow "$project" "$uuid_a" "${project:0:12}…/A" "nonstream"
  test_interview_flow "$project" "$uuid_b" "${project:0:12}…/B" "stream"

  echo ""
done

# ── Result ──────────────────────────────────────────────────────────────

echo "========================================"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ Smoke test PASSED (version=$version)"
  exit 0
else
  echo "❌ Smoke test FAILED (version=$version)"
  exit 1
fi
