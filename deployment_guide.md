# Deployment Guide

This guide lists everything you need to redeploy the project to Railway (or any other platform) after a shutdown.

## 1. Prerequisites

*   **Supabase Project:** You need a running Supabase project.
*   **Database Schema:** Restore the database schema using `database_schema.sql` in the SQL Editor of your new Supabase project.
*   **Environment Variables:** You must configure the following environment variables in your deployment platform.

## 2. Environment Variables

| Variable | Description | Example / Note |
| :--- | :--- | :--- |
| `DATABASE_URL` | Preferred Supabase connection string | **Use Supavisor/pooler** if IPv6 is an issue |
| `DB_SSLMODE` | SSL mode for Postgres | `require` |
| `DB_HOST` | Database host from Supabase | `db.xyz.supabase.co` (optional if `DATABASE_URL` set) |
| `DB_NAME` | Database name | `postgres` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | *Your DB password* |
| `DB_PORT` | Database port | `5432` (Default: 5432) |
| `OPENAI_API_KEY` | OpenAI API Key | `sk-...` |
| `AZURE_OPENAI_KEY` | Azure OpenAI Key | *If using Azure* |
| `OPENAI_PANDA_KEY` | Panda Project Key | *If applicable* |
| `PORT` | Port for the app to run on | **Provided by Railway automatically** (do not set manually) |

## 3. Deployment Steps (Railway)

1.  **New Project:** Create a new project in Railway.
2.  **Connect Repo:** Connect your GitHub repository.
3.  **Variables:** Go to the "Variables" tab and add all the variables listed above.
4.  **Build & Deploy:** Railway uses the `Dockerfile` in this repo.
    *   **Build Command:** Not required (Dockerfile installs deps).
    *   **Start Command:** **Leave empty** (Dockerfile uses `ENTRYPOINT ["python", "start.py"]`).
        - If you *must* set it, use: `python start.py`
        - **Do not** set `gunicorn ... $PORT` (it will fail when `$PORT` isn’t expanded).

## 3.1 Staging -> Production Workflow (Safe Promotion)

This repo uses one frontend Vercel project and two backend Railway environments.

### Naming map (non-technical)

- GitHub repo `qvantify-backend` = full codebase (frontend + backend).
- Vercel project `qvantify-frontend` = only real frontend domains:
  - `staging.app.qvantify.com`
  - `app.qvantify.com`
- Vercel project `qvantify-fullstack` = legacy/static only, never used for app/staging domains.
- Railway:
  - staging backend = `https://qvantify-staging.up.railway.app`
  - production backend = `https://qvantify.up.railway.app`

### Local checks (run before every push)

```bash
./scripts/local-release-checks.sh
python3 scripts/release_safety_check.py --repo-path .
```

Optional one-time setup to auto-run checks on every `git push`:

```bash
./scripts/install-git-hooks.sh
```

### Branch flow

1. Run local checks.
2. Push to `staging`.
3. Deploy frontend from `frontend/` to `staging.app.qvantify.com`.
4. Verify staging with smoke checklist.
5. Merge `staging` -> `main`.
6. Promote exact staging frontend deployment to production domain.

### Frontend deploy commands

Deploy to staging:

```bash
vercel link --cwd frontend --project qvantify-frontend --scope nikita-shilenoks-projects --yes
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set <preview-url> staging.app.qvantify.com
python3 scripts/verify_domain_aliases.py
```

Promote staging frontend to production:

```bash
python3 scripts/promote_frontend_from_staging.py --apply
python3 scripts/verify_domain_aliases.py
```

### Panic-button checkpoint and rollback

Before risky promotions:

```bash
python3 scripts/create_checkpoint.py --name "<release-name>"
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json"
```

If rollback is needed:

```bash
python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json" --apply
```

### Staging smoke checklist (before promotion)

- `GET /api/health` returns `200`
- `POST /api/share/<token>/login` does **not** return `Missing SECRET_KEY`
- `GET /results/` serves the Results UI

### Promotion checklist

- Local checks passed
- Staging smoke checklist passed
- `python3 scripts/release_safety_check.py --repo-path .` passed
- Merge `staging` -> `main`
- Frontend production promotion completed

## 4. Database Restoration

1.  Open your Supabase Dashboard.
2.  Go to **SQL Editor**.
3.  Open `database_schema.sql` from this repository.
4.  Copy the content and run it in the SQL Editor to recreate all tables and types.

## 5. Verification

Once deployed:
*   Check `scope.md` to ensure all features are accounted for.
*   Visit the application URL.
*   Check logs for any "Database error" or "Connection refused" messages.

### Quick Health Check Script

Use the recovery script to confirm API + DB:

```bash
QVANTIFY_BASE_URL=https://app.qvantify.com \
QVANTIFY_RAILWAY_URL=https://qvantify.up.railway.app \
QVANTIFY_PROJECT_ID=sample_game_funnel_2026_01_14 \
./scripts/health-check.sh
```

## 6. Railway CLI (Project Token)

If you have a **Railway project token**, you can use the CLI without logging in:

```bash
export RAILWAY_TOKEN=xxxx
railway status --json
railway logs --service "qvantify backend" --environment production --lines 50 --json
railway variables --service <service_id> --environment <env_id> --kv
```




