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

## No-Incident Mini Entry (allowed)

If cycle was clean, record:
- Date (UTC)
- Scope
- Checks executed
- Why we believe it is stable
- Any preventive improvements still made
