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
- **Zero known bugs at promotion.** If any bug is identified during the session — even "pre-existing" — it must be fixed and tested before promotion to production. No exceptions.
- **Rollback first, fix second.** If ANY production verification fails after promotion, immediately rollback (step 10). Never push hotfixes to main in a loop. Fix on staging, re-test the full smoke suite, then re-promote.
- **Both code paths tested.** Every staging and production verification must test both non-streaming (`POST /api/reply/`) and streaming (`POST /api/reply/` with `stream:true` + `Accept: text/event-stream`). The automated smoke test (`scripts/staging_smoke_test.sh`) enforces this.
- **Multi-user tested.** Every staging and production verification must run 2+ concurrent respondents against the same project to catch cross-user contamination. The automated smoke test enforces this.

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

### Git worktree blocks `git checkout main`
The `main` branch is checked out in a git worktree, so `git checkout main && git merge staging` will fail. Use `git push origin staging:main` instead to update main remotely.

### Railway silent deploy failure
Railway may silently fail to redeploy after a normal `git push`. The health endpoint keeps returning the old commit hash indefinitely. This has occurred multiple times (2026-03-06). If the health version hasn't updated within 90 seconds of a push, push an empty commit to re-trigger:
```bash
git commit --allow-empty --author="nikitashilenok <nshilenok@gmail.com>" -m "Trigger Railway redeploy"
git push origin staging        # or staging:main for production
```
Always poll health after push — never assume Railway deployed.

### gpt-5.4+ requires Responses API
OpenAI gpt-5.4 and later models reject `/v1/chat/completions` when function tools are combined with `reasoning_effort`. The error is:
```
Function tools with reasoning_effort are not supported for gpt-5.4 in /v1/chat/completions. Please use /v1/responses instead.
```
When switching models to gpt-5.4+, ensure:
1. `api = 'openai'` (not openrouter)
2. `openai_transport = 'responses'` in the projects table
3. Code callers pass `allow_responses=True` to the `LLM()` constructor

The code auto-detects gpt-5.4+ via `_should_use_responses()`, but the DB flag is the primary gate.

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

**After pushing, poll health until the version updates** (Railway may silently fail to deploy — see Known Issues):
```bash
# Poll every 30s; if still stale after 90s, push an empty commit
curl -s https://qvantify-staging.up.railway.app/api/health
```
Expected: `version` field matches the short SHA of the pushed commit. If still stale after 90 seconds, push an empty commit to re-trigger (see "Railway silent deploy failure" above).

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

### 4b) Interview smoke test (MANDATORY — blocking gate)

Runs 2 respondents per project, tests BOTH non-streaming and streaming code paths, checks for raw tool call text, premature close, and cross-user contamination:
```bash
./scripts/staging_smoke_test.sh https://qvantify-staging.up.railway.app
```
This tests `swipking2` and `Swipking3` (both gpt-5.4 / medium as of 2026-03-06). **Do NOT proceed to promotion if this fails.**

### 5) Browser verification (supplementary)

Optional after the smoke test passes. Useful for catching JS hydration failures, auth walls, and rendering issues that API tests cannot detect:

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

Commit any pending changes (skill updates, journal entries) first — safety check requires a clean tree:
```bash
git add -A && git commit --author="nikitashilenok <nshilenok@gmail.com>" -m "<message>"
python3.12 scripts/release_safety_check.py --repo-path . --allow-divergence
python3.12 scripts/promote_frontend_from_staging.py
```

`promote_frontend_from_staging.py` is expected to fail fast if staging source runtime is invalid.

### 8) Promote to production (only after user confirms staging is good)

Frontend promotion:
```bash
python3.12 scripts/promote_frontend_from_staging.py --apply
```

Backend promotion — push staging to main (Railway auto-deploys production from `main`):
```bash
git push origin staging:main
```
Note: if `main` is checked out in a git worktree, `git checkout main` will fail. Use `git push origin staging:main` to update main remotely without checking it out.

Push staging too if there were new commits (journal/skill updates):
```bash
git push origin staging
```

### 9) Verify production

Run in parallel:
```bash
python3.12 scripts/verify_domain_aliases.py
curl -s "https://app.qvantify.com/api/health"
curl -s -o /dev/null -w 'STATUS:%{http_code}\n' "https://app.qvantify.com/interview?interview=swipking2&external_id=prod_smoke_probe"
```

Expected:
- Domain aliases: production → new deploy, staging → previous staging deploy.
- `/api/health` → 200 with `x-qvantify-proxy-base: https://qvantify.up.railway.app` and `version` matching the promoted commit.
- `/interview?...` → 200.

Note: Railway production may take 30-60 seconds to deploy after push. If the version hasn't updated after 90 seconds, push an empty commit to re-trigger (see "Railway silent deploy failure" in Known Issues).

### 9b) Production smoke test (MANDATORY — rollback trigger)

Replay the **exact same** smoke test against production:
```bash
./scripts/staging_smoke_test.sh https://qvantify.up.railway.app
```
**If this fails → immediately rollback (step 10). Do NOT push fixes to main.**

### 9c) Browser verification (optional)

```
Launch browser-use subagent → navigate to app.qvantify.com/interview?interview=swipking2&external_id=prod_smoke_probe → screenshot → report.
```

### 10) Rollback (use IMMEDIATELY if step 9b fails)

Frontend rollback:
```bash
python3.12 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json" --apply
```

Backend rollback — push the previous good main commit:
```bash
git push origin <previous-main-sha>:main --force
```

After rollback, fix on staging, re-run full smoke test (`staging_smoke_test.sh`), then re-promote. **Never fix-forward on production.**

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
