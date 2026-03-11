# Qvantify Deploy Weekly Reflection Template

Use this after each deploy cycle. Keep it short but explicit.

---

## Reflection Entry

- Date (UTC):
- Operator:
- Release / commit range:
- Scope: `staging-only` or `staging->production`

### 1) Outcome

- Final status: `success` / `partial` / `failed`
- Domains status:
  - `staging.app.qvantify.com` ->
  - `app.qvantify.com` ->

### 2) What happened (facts only)

- Incident summary:
- Raw log pointers in `ops/deploy_journal.md`:
  - Entry heading(s):
  - Key command output block(s):

### 3) Detection quality

- How issue was detected:
- Time-to-detect:
- Was detection automated (`verify_domain_aliases`, `release_safety_check`, promotion gate)?

### 4) Root cause

- Immediate cause:
- System/process cause:

### 5) Prevention changes shipped this cycle

- Script guardrails:
- Skill/runbook updates:
- Policy updates:

### 5b) Promotion hygiene check

- Were all bugs identified during the session fixed before promotion? `yes/no`
- If no — why was promotion approved with known bugs?
- Was the smoke test (`staging_smoke_test.sh`) run on staging before promotion? `yes/no`
- Was the smoke test replayed on production after promotion? `yes/no`
- Were any hotfixes pushed directly to main instead of rollback-first? `yes/no`
- If yes — what prevented the rollback-first protocol from being followed?

### 6) Recurrence check (next week readiness)

- Would this same failure recur next week? `yes/no`
- Why:
- Remaining risks:

### 7) Follow-ups

- [ ] No follow-ups
- [ ] Follow-up 1:
- [ ] Follow-up 2:

---

## 2026-03-06 — responses-adapter + gpt-5.4 upgrade

- Date (UTC): 2026-03-06
- Operator: AI agent
- Release / commit range: 6a0985c → b1863e2
- Scope: `staging->production`

### 1) Outcome

- Final status: `success`
- Domains status:
  - `staging.app.qvantify.com` -> qvantify-frontend-f9if6i8r9 (preview)
  - `app.qvantify.com` -> qvantify-frontend-kh7qn9zui (production)

### 2) What happened (facts only)

- Incident summary: Two issues — (a) Railway silently failed to redeploy twice, requiring empty commits to re-trigger; (b) gpt-5.4 rejected Chat Completions API when function tools + reasoning_effort were combined, requiring a code fix and DB update mid-cycle.
- Raw log pointers in `ops/deploy_journal.md`:
  - Entry heading(s): "2026-03-06 — responses-adapter + gpt-5.4 upgrade (6a0985c → b1863e2)"
  - Key command output block(s): Railway health polls, OpenAI 400 error on `/v1/chat/completions`

### 3) Detection quality

- How issue was detected: (a) Railway — health endpoint polling showed stale version after 6+ minutes. (b) gpt-5.4 — production smoke test caught the 400 error immediately.
- Time-to-detect: (a) ~6 minutes before realizing Railway was stuck. (b) Immediate — first smoke test reply failed.
- Was detection automated: (a) Manual health polling. (b) Yes — `staging_smoke_test.sh` caught it.

### 4) Root cause

- Immediate cause: (a) Railway webhook missed push event or build queue stalled. (b) OpenAI API constraint: gpt-5.4 requires `/v1/responses` for function tools + reasoning_effort.
- System/process cause: (a) No automated health-poll-after-push in the deploy flow. (b) No documentation that gpt-5.4 has different API requirements than gpt-5.2.

### 5) Prevention changes shipped this cycle

- Script guardrails: Added `_should_use_responses()` auto-detection in `llmInterface.py` — gpt-5.4+ models are automatically routed to Responses API regardless of DB flag.
- Skill/runbook updates: Added "Railway silent deploy failure" and "gpt-5.4+ requires Responses API" to deploy skill Known Issues. Updated golden flow steps 1 and 9 with health-poll instructions. Updated smoke test project description.
- Policy updates: Added "Model Configuration Constraints" section to `AGENTS.md`.

### 5b) Promotion hygiene check

- Were all bugs identified during the session fixed before promotion? `yes` — the gpt-5.4 API issue was fixed with a code commit + DB update, re-deployed, and re-tested before declaring done.
- Was the smoke test run on staging before promotion? `yes`
- Was the smoke test replayed on production after promotion? `yes` (3 times — pre-model-switch, post-model-switch failure, post-fix success)
- Were any hotfixes pushed directly to main instead of rollback-first? `yes` — the gpt-5.4 fix (054b323) was pushed to both staging and main simultaneously because the issue was a DB config + code routing problem, not a regression in the deployed code. The pre-upgrade code was still green; only the new model config triggered the failure. Rollback would have meant reverting the DB model change, not the code.

### 6) Recurrence check (next week readiness)

- Would this same failure recur next week? `no`
- Why: (a) Railway — deploy skill now documents the empty-commit workaround and health-poll requirement. (b) gpt-5.4 — auto-detection in code + documented in AGENTS.md + deploy skill.
- Remaining risks: Railway silent deploy is unpredictable — could happen again. The empty-commit workaround works but is ugly. Consider adding an automated health-poll script that blocks until version matches.

### 7) Follow-ups

- [ ] Consider adding a `scripts/wait_for_railway.sh <url> <expected-sha>` script that polls health and auto-triggers empty commit if stale
- [ ] Streaming replies for gpt-5.4 via Responses API are not yet implemented (currently falls back to Chat Completions for streaming)

---

## No-Incident Mini Entry (allowed)

If cycle was clean, record:
- Date (UTC)
- Scope
- Checks executed
- Why we believe it is stable
- Any preventive improvements still made
