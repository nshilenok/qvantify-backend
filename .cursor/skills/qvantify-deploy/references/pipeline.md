# Qvantify Deployment Runbook (Detailed)

## Hard rules

- Never create new Vercel projects. Only `qvantify-frontend` is valid for app domains.
- Public domains must stay stable:
  - `staging.app.qvantify.com`
  - `app.qvantify.com`
- Root `vercel.json` must keep `git.deploymentEnabled=false` to stop wrong-context auto-preview takeover.
- Frontend deploys are manual from `frontend/` only.
- Every deploy attempt (staging/prod) must be appended to `ops/deploy_journal.md` with raw output and timestamps.

## 1) Preflight

```bash
./scripts/local-release-checks.sh
python3 scripts/release_safety_check.py --repo-path .
```

## 2) Checkpoint before risky operations

```bash
python3 scripts/create_checkpoint.py --name "<release-name>"
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json"
```

## 3) Frontend staging deploy

```bash
vercel link --cwd frontend --project qvantify-frontend --scope nikita-shilenoks-projects --yes
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <preview-url> staging.app.qvantify.com --scope nikita-shilenoks-projects
```

## 4) Runtime verification (protection-aware)

Use `vercel curl` for protected deployments. Path must be relative and deployment is provided via `--deployment`.

```bash
python3 scripts/verify_domain_aliases.py
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/api/health' --deployment https://<staging-deploy>.vercel.app -- --include --silent --show-error
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/interview?interview=swipking2&external_id=staging_smoke_probe' --deployment https://<staging-deploy>.vercel.app -- --silent --show-error --location --output /dev/null --write-out 'STATUS:%{http_code}\n'
```

Expected:
- `/api/health` is `200`,
- `x-qvantify-proxy-base` for staging is `https://qvantify-staging.up.railway.app`,
- `/interview?...` is `200`.

## 5) Common failure mode: staging alias points to wrong-context preview

Symptom:
- `python3 scripts/verify_domain_aliases.py` fails with `/interview?... status=404`.

Fix:
```bash
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <new-preview-url> staging.app.qvantify.com --scope nikita-shilenoks-projects
python3 scripts/verify_domain_aliases.py
```

## 6) Promotion readiness gate (must pass)

```bash
python3 scripts/release_safety_check.py --repo-path . --allow-divergence
python3 scripts/promote_frontend_from_staging.py
```

The dry-run promotion script validates runtime on the source staging deployment and must fail if source is invalid.

## 7) Promote frontend staging -> production

```bash
python3 scripts/promote_frontend_from_staging.py --apply
python3 scripts/verify_domain_aliases.py
```

## 8) Rollback

```bash
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json" --apply
```

## 9) Skill/documentation sync rule (mandatory)

If workflow changes or a new failure mode appears, update in the same cycle:
- `.cursor/skills/qvantify-deploy/SKILL.md`
- `.cursor/skills/qvantify-deploy/references/pipeline.md`
- `deployment_guide.md`
- `scope.md`

## 10) Weekly reflection (mandatory)

After deploy completion (and before closing the incident/release cycle):

1) Append full raw timeline to `ops/deploy_journal.md`.
2) Complete one reflection entry using:
   - `.cursor/skills/qvantify-deploy/references/weekly-reflection.md`
3) Record prevention deltas:
   - script guardrails added/updated,
   - new checks in runbook/skill,
   - unresolved risks for next cycle.

If no failure happened, still file a short "no incidents" reflection entry.
