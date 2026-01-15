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

## 3.1 Staging → Production Workflow (Manual Promotion)

This repo uses a **staging branch** for verification, then **manual promotion** to production via merge.

### Local checks (run before every push)

```bash
./scripts/local-release-checks.sh
```

Optional one-time setup to auto-run checks on every `git push`:

```bash
./scripts/install-git-hooks.sh
```

### Branch flow

1. Run local checks.
2. Push to `staging` (auto-deploys staging).
3. Verify staging with the smoke checklist below.
4. Merge `staging` → `main` to deploy production.

### Railway staging setup

- Create a **staging service/environment** that tracks the `staging` branch.
- Keep the existing production service on `main`.
- Mirror env vars (same keys as prod, per current policy).
  - **Warning:** using production keys in staging means staging actions can affect production data. Treat staging as read-only unless you intentionally want to modify prod.

### Vercel staging setup

- Create a second Vercel project (e.g. `qvantify-staging`) that deploys from the `staging` branch.
- Keep the production project tied to `main`.
- Mirror env vars (same keys as prod, per current policy).
  - **Warning:** using production keys in staging means staging actions can affect production data. Treat staging as read-only unless you intentionally want to modify prod.
- **Staging preview URL**: use the latest Vercel Preview deployment for the `staging` branch.
  - Vercel preview URLs change on each deployment. If you need a stable staging URL, set a Preview domain in Vercel.

### Staging smoke checklist (before promotion)

- `GET /api/health` returns `200`
- `POST /api/share/<token>/login` does **not** return `Missing SECRET_KEY`
- `GET /results/` serves the Results UI

### Promotion checklist

- Local checks passed
- Staging smoke checklist passed
- Merge `staging` → `main`

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




