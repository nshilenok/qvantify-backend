# Deploy Weekly Reflections

This file stores one concise retro per deploy cycle.
Use template: `.cursor/skills/qvantify-deploy/references/weekly-reflection.md`

---

## 2026-02-16 UTC - Staging/Production cycle

- Operator: assistant
- Scope: `staging->production`
- Release range: `41cac06` -> `814fafd`

### Outcome

- Final status: `success`
- Domains:
  - `staging.app.qvantify.com` -> `https://qvantify-frontend-ommd0s9u1-nikita-shilenoks-projects.vercel.app`
  - `app.qvantify.com` -> `https://qvantify-frontend-ibzf8jobc-nikita-shilenoks-projects.vercel.app`

### What happened (facts)

- Staging alias was repeatedly hijacked by wrong-context preview deployments (`/interview` returned `404`).
- Runtime gate scripts caught this before promotion.
- Manual redeploy from `frontend/` + re-alias restored staging.
- Promotion executed only after dry-run and runtime checks passed.

Raw evidence location:
- `ops/deploy_journal.md` entries on 2026-02-16:
  - "Post-commit validation caught a fresh bad auto-deploy"
  - "Auto-preview takeover observed again after next push"
  - "Final stabilization before production green signal"
  - "Production promotion execution"
  - "Skill audit + reflection hardening after production go-live"

### Detection quality

- Detection method: automated (`scripts/verify_domain_aliases.py`, `scripts/release_safety_check.py`, promotion dry-run).
- Time-to-detect after bad alias shift: immediate on first verification run.

### Root cause

- Immediate cause: staging alias pointed to previews built with root API-only config, not frontend app runtime.
- System/process cause: insufficient guardrails against wrong-context preview takeover before hardening.

### Prevention changes shipped

- `vercel.json`: `git.deploymentEnabled=false`.
- `scripts/promote_frontend_from_staging.py` fail-fast runtime source validation.
- `scripts/verify_domain_aliases.py` runtime checks (`/interview`, `/api/health`, proxy header).
- Skill/runbook sync rules + weekly reflection template added.

### Recurrence check

- Would same failure recur next week? `low probability`.
- Why: wrong source deployment is now blocked by automated checks and promotion gate.
- Remaining risk: manual alias override by operator outside scripted flow.

### Follow-ups

- [ ] Add CI smoke hook that validates staging alias target immediately after each preview deploy.
