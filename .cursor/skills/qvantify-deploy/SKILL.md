---
name: qvantify-deploy
description: Deploy and promote Qvantify safely using the single frontend Vercel project and Railway backend environments. Use when deploying staging, promoting staging to production, verifying domain aliases, recovering from alias drift, or performing one-command rollback with a checkpoint snapshot.
---

# Qvantify Deploy

## System Map (baby-language)

- Repo `qvantify-backend` = full codebase (frontend + backend).
- Vercel project `qvantify-frontend` = real web domains:
  - `staging.app.qvantify.com`
  - `app.qvantify.com`
- Vercel project `qvantify-fullstack` = legacy only. Do not use it for app/staging domains.
- Railway:
  - staging backend: `https://qvantify-staging.up.railway.app`
  - production backend: `https://qvantify.up.railway.app`

## Simple Flow

```mermaid
flowchart LR
  localCode["Local code"] --> stagingDeploy["Deploy frontend/ to staging domain"]
  stagingDeploy --> stagingQa["Check staging.app.qvantify.com"]
  stagingQa --> promoteProd["Promote same staging deploy"]
  promoteProd --> prodLive["app.qvantify.com live"]
```

## Safety-First Flow

```mermaid
flowchart TD
  checkpoint["Create checkpoint tags + snapshot"] --> deployStaging["Deploy staging"]
  deployStaging --> verifyAlias["Verify app/staging aliases"]
  verifyAlias --> promote["Promote staging to production"]
  promote --> verifyProd["Verify production health"]
  verifyProd --> done["Done"]
  verifyProd --> rollback["Run rollback script with snapshot"]
```

## Commands

### 1) Create checkpoint before risky changes

```bash
python3 scripts/create_checkpoint.py --name "<date-or-release>"
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<date-or-release>.json"
```

### 2) Deploy frontend to staging

```bash
vercel link --cwd frontend --project qvantify-frontend --scope nikita-shilenoks-projects --yes
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <preview-url> staging.app.qvantify.com
python3 scripts/verify_domain_aliases.py
```

### 3) Promote staging frontend to production

```bash
python3 scripts/promote_frontend_from_staging.py --apply
python3 scripts/verify_domain_aliases.py
```

### 4) One-command rollback

```bash
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<name>.json" --apply
```

## Mandatory Rules

### Project policy (non-negotiable)
- Never create new Vercel projects. Use only the existing `qvantify-frontend` project.
- Never use temporary domain assignments. Only `app.qvantify.com` and `staging.app.qvantify.com` are valid public entry domains.
- Keep stable domain ownership on `qvantify-frontend` only. App/staging domains must never be attached to `qvantify-fullstack` or any other project.

### Deployment policy
- Always deploy frontend from `frontend/` using `vercel link --project qvantify-frontend`.
- Always keep `app.qvantify.com` and `staging.app.qvantify.com` on `qvantify-frontend-*` deployments.
- Never alias app/staging domains to `qvantify-fullstack`.
- Always create a checkpoint before branch realignment or production promotion.

## Reference

- Full runbook: `references/pipeline.md`
