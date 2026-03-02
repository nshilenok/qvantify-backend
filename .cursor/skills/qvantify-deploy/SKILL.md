---
name: qvantify-deploy
description: Deploy and promote Qvantify safely using one frontend Vercel project and Railway backends. Use for staging deploys, promotion to production, alias/runtime verification, rollback, and mandatory deploy incident logging + skill updates when process changes.
---

# Qvantify Deploy

## When to use

Use this skill when:
- deploying `staging`,
- promoting validated staging to `production`,
- repairing domain alias drift or wrong-context deploys,
- recording deploy incidents,
- updating deploy workflow documentation after discovering a new failure mode.

## Topology (source of truth)

- Repo: `qvantify-backend` (frontend + backend code, single repo).
- Frontend Vercel project: `qvantify-frontend` (project ID: `prj_T2TJG7dqrYN9GW57DhuXYcnzHPuO`, team: `team_4zW1xalkIvYhynedpunr87SU`).
  - `staging.app.qvantify.com` (preview target).
  - `app.qvantify.com` (production target).
- Legacy Vercel project: `qvantify-fullstack` (never use for app/staging domains).
- Railway backends (auto-deploy from git push):
  - staging: `https://qvantify-staging.up.railway.app` — deploys from `staging` branch
  - production: `https://qvantify.up.railway.app` — deploys from `main` branch

## Non-negotiable policy

- Use only `qvantify-frontend` for public frontend domains.
- Never use temporary public aliases for app traffic.
- Root `vercel.json` keeps `git.deploymentEnabled=false` to prevent wrong-context Git auto-preview takeovers.
- Frontend deploys are manual and run from `frontend/` only.
- Every staging/production attempt is logged append-only in `ops/deploy_journal.md`.

## Known issues & workarounds

### Git author email (Vercel team access)
Vercel requires the git commit author email to be a team member. Use `nshilenok@gmail.com`, **not** `info@shhhp.ai`. If a commit was made with the wrong email, amend before deploying:
```bash
git commit --amend --author="nikitashilenok <nshilenok@gmail.com>" --no-edit
git push origin staging --force
```

### Python version for scripts
System `python3` may be 3.9 which lacks `datetime.UTC`. Always use `python3.12` for deploy scripts:
```bash
python3.12 scripts/create_checkpoint.py --name "<release-name>"
python3.12 scripts/verify_domain_aliases.py
```

### Playwright preflight failures
Local Playwright tests may fail with "Executable doesn't exist" if browser binaries are outdated. This is a local env issue, not a code blocker. Fix with `npx playwright install` in `frontend/`, or proceed if API tests pass and you're deploying to staging.

### Port 4173 conflict
If preflight Playwright fails with "port 4173 already in use", kill the stale process first:
```bash
lsof -ti :4173 | xargs kill -9 2>/dev/null
```

### SSO protection on staging
Vercel SSO protection may block unauthenticated access to staging. If staging returns a login wall instead of the app, disable SSO via the Vercel API:
```bash
node -e "
const fs = require('fs');
const path = require('path');
const home = require('os').homedir();
const auth = JSON.parse(fs.readFileSync(path.join(home, 'Library/Application Support/com.vercel.cli/auth.json'), 'utf8'));
fetch('https://api.vercel.com/v1/projects/prj_T2TJG7dqrYN9GW57DhuXYcnzHPuO?teamId=team_4zW1xalkIvYhynedpunr87SU', {
  method: 'PATCH',
  headers: { Authorization: 'Bearer ' + auth.token, 'Content-Type': 'application/json' },
  body: JSON.stringify({ ssoProtection: null })
}).then(r => r.json()).then(d => console.log('ssoProtection:', JSON.stringify(d.ssoProtection)));
"
```
Re-enable after production promotion if desired.

## Golden flow (must follow)

### 0) Commit & preflight

Preflight requires a clean working tree. Commit all changes first, then run checks.

```bash
git add -A && git commit -m "<descriptive message>"
./scripts/local-release-checks.sh
```
Minimum pass gate: import check + branch safety + API tests (pytest). Playwright failures from missing browsers are non-blocking for staging.

### 1) Push backend to Railway (parallel with frontend)

Railway auto-deploys the staging backend when the `staging` branch is pushed:
```bash
git push origin staging
```
If the commit was amended (e.g. author fix), use `--force`.

### 2) Create rollback checkpoint

```bash
python3.12 scripts/create_checkpoint.py --name "<release-name>"
```

### 3) Deploy frontend to Vercel

```bash
vercel link --cwd frontend --project qvantify-frontend --scope nikita-shilenoks-projects --yes
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <preview-url> staging.app.qvantify.com --scope nikita-shilenoks-projects
```

Steps 1-3 can overlap: push backend, create checkpoint, and link+deploy frontend in parallel where possible.

### 4) Verify runtime

Run all three in parallel:
```bash
python3.12 scripts/verify_domain_aliases.py
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/api/health' --deployment https://<staging-deploy>.vercel.app -- --include --silent --show-error
curl -s -o /dev/null -w 'STATUS:%{http_code}\n' "https://staging.app.qvantify.com/interview?interview=swipking2&external_id=staging_smoke_probe"
```

Expected:
- Domain aliases: staging → new deploy, production → previous deploy.
- `/api/health` → 200 with `x-qvantify-proxy-base: https://qvantify-staging.up.railway.app`.
- `/interview?...` → 200 (plain curl works when SSO protection is disabled).

### 5) Browser verification (mandatory)

Always verify via a browser-use subagent after curl checks pass. This catches JS hydration failures, auth walls, and rendering issues that curl cannot detect:

```
Launch browser-use subagent → navigate to staging.app.qvantify.com/interview?interview=swipking2&external_id=staging_smoke_probe → screenshot → report what's visible.
```

### 6) If staging fails with wrong-context preview (common failure)

Signal: `/interview?...` returns `404` on latest staging alias/deploy.

Recovery:
```bash
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <new-preview-url> staging.app.qvantify.com --scope nikita-shilenoks-projects
python3.12 scripts/verify_domain_aliases.py
```

### 7) Promotion readiness gate

```bash
python3.12 scripts/release_safety_check.py --repo-path . --allow-divergence
python3.12 scripts/promote_frontend_from_staging.py
```

`promote_frontend_from_staging.py` is expected to fail fast if staging source runtime is invalid.

### 8) Promote to production (only after user confirms staging is good)

```bash
python3.12 scripts/promote_frontend_from_staging.py --apply
python3.12 scripts/verify_domain_aliases.py
```

### 9) Rollback command (one step)

```bash
python3.12 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json" --apply
```

## Mandatory deploy incident logging

For every staging/production cycle, append to `ops/deploy_journal.md`:
- date/time/timezone per step,
- raw command outputs and raw errors,
- attempts, failures, and final recovery path.

Never rewrite previous entries (append-only).

## Mandatory skill maintenance contract

If deploy process changes or a new failure mode appears, update in the same work cycle:
- `.cursor/skills/qvantify-deploy/SKILL.md`,
- `.cursor/skills/qvantify-deploy/references/pipeline.md`,
- `deployment_guide.md` and `scope.md` when policy/checklist changes.

Do not mark deployment workflow as "done" until these docs are updated.

## Weekly reflection ritual (mandatory)

After each deploy cycle (staging-only or staging->production), complete a short retro:

1) Append raw timeline in `ops/deploy_journal.md`.
2) Fill weekly reflection entry using template:
   - `.cursor/skills/qvantify-deploy/references/weekly-reflection.md`
3) Confirm prevention updates are explicit:
   - script guardrails,
   - skill/runbook updates,
   - rollback and detection coverage.

Minimum reflection questions:
- Which failure mode happened?
- Why detection was late or fast?
- What now prevents recurrence next week?
- What remains risky?

## Reference

- Full runbook: `references/pipeline.md`
- Weekly reflection template: `references/weekly-reflection.md`
- Vercel auth token location: `~/Library/Application Support/com.vercel.cli/auth.json`
- Vercel project ID: `prj_T2TJG7dqrYN9GW57DhuXYcnzHPuO`
- Vercel team ID: `team_4zW1xalkIvYhynedpunr87SU`
