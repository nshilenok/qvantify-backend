# Qvantify Deployment Runbook (Detailed)

## A) Quick Verify Commands

```bash
python3 scripts/verify_domain_aliases.py
curl -I https://staging.app.qvantify.com/api/health
curl -I https://app.qvantify.com/api/health
```

Expected:
- Staging proxy header points to `https://qvantify-staging.up.railway.app`
- Production proxy header points to `https://qvantify.up.railway.app`

## B) Frontend Staging Deploy

```bash
vercel link --cwd frontend --project qvantify-frontend --scope nikita-shilenoks-projects --yes
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <preview-url> staging.app.qvantify.com
python3 scripts/verify_domain_aliases.py
```

## C) Frontend Production Promote

```bash
python3 scripts/promote_frontend_from_staging.py --apply
python3 scripts/verify_domain_aliases.py
```

## D) Panic-Button Checkpoint + Rollback

Create checkpoint:

```bash
python3 scripts/create_checkpoint.py --name "<release-name>"
```

Dry-run rollback:

```bash
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json"
```

Apply rollback:

```bash
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json" --apply
```

## E) Branch Safety

Before promotion:

```bash
python3 scripts/release_safety_check.py --repo-path .
```

This check blocks promotion when:
- repo is dirty,
- branch divergence is unsafe,
- domain aliases are wrong.
