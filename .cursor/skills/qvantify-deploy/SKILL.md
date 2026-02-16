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

- Repo: `qvantify-backend` (frontend + backend code).
- Frontend Vercel project: `qvantify-frontend`.
  - `staging.app.qvantify.com` (preview target).
  - `app.qvantify.com` (production target).
- Legacy Vercel project: `qvantify-fullstack` (never use for app/staging domains).
- Railway backends:
  - staging: `https://qvantify-staging.up.railway.app`
  - production: `https://qvantify.up.railway.app`

## Non-negotiable policy

- Use only `qvantify-frontend` for public frontend domains.
- Never use temporary public aliases for app traffic.
- Root `vercel.json` keeps `git.deploymentEnabled=false` to prevent wrong-context Git auto-preview takeovers.
- Frontend deploys are manual and run from `frontend/` only.
- Every staging/production attempt is logged append-only in `ops/deploy_journal.md`.

## Golden flow (must follow)

### 0) Preflight checks

```bash
./scripts/local-release-checks.sh
python3 scripts/release_safety_check.py --repo-path .
```

### 1) Create rollback checkpoint before risky steps

```bash
python3 scripts/create_checkpoint.py --name "<release-name>"
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json"
```

### 2) Deploy staging from `frontend/`

```bash
vercel link --cwd frontend --project qvantify-frontend --scope nikita-shilenoks-projects --yes
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <preview-url> staging.app.qvantify.com --scope nikita-shilenoks-projects
```

### 3) Verify runtime (protection-aware)

Use `vercel curl` with relative path + `--deployment`; do not rely on plain `curl` for protected staging.

```bash
python3 scripts/verify_domain_aliases.py
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/api/health' --deployment https://<staging-deploy>.vercel.app -- --include --silent --show-error
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/interview?interview=swipking2&external_id=staging_smoke_probe' --deployment https://<staging-deploy>.vercel.app -- --silent --show-error --location --output /dev/null --write-out 'STATUS:%{http_code}\n'
```

Expected:
- `/api/health` status `200`,
- `x-qvantify-proxy-base: https://qvantify-staging.up.railway.app`,
- `/interview?...` status `200`.

### 4) If staging fails with wrong-context preview (common failure)

Signal:
- `/interview?...` returns `404` on latest staging alias/deploy.

Recovery:
```bash
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <new-preview-url> staging.app.qvantify.com --scope nikita-shilenoks-projects
python3 scripts/verify_domain_aliases.py
```

### 5) Promotion readiness gate

```bash
python3 scripts/release_safety_check.py --repo-path . --allow-divergence
python3 scripts/promote_frontend_from_staging.py
```

`promote_frontend_from_staging.py` is expected to fail fast if staging source runtime is invalid.

### 6) Promote to production (only after green signal)

```bash
python3 scripts/promote_frontend_from_staging.py --apply
python3 scripts/verify_domain_aliases.py
```

### 7) Rollback command (one step)

```bash
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json" --apply
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

## Reference

- Full runbook: `references/pipeline.md`
