# Deployment Guide

This guide lists everything you need to redeploy the project to Railway (or any other platform) after a shutdown.

## 1. Prerequisites

*   **Supabase Project:** You need a running Supabase project.
*   **Database Schema:** Restore the database schema using `database_schema.sql` in the SQL Editor of your new Supabase project.
*   **Environment Variables:** You must configure the following environment variables in your deployment platform.

## 2. Environment Variables

| Variable | Description | Example / Note |
| :--- | :--- | :--- |
| `DB_HOST` | Database host from Supabase | `db.xyz.supabase.co` |
| `DB_NAME` | Database name | `postgres` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | *Your DB password* |
| `DB_PORT` | Database port | `5432` (Default: 5432) |
| `OPENAI_API_KEY` | OpenAI API Key | `sk-...` |
| `AZURE_OPENAI_KEY` | Azure OpenAI Key | *If using Azure* |
| `OPENAI_PANDA_KEY` | Panda Project Key | *If applicable* |
| `PORT` | Port for the app to run on | `5000` (Provided by Railway automatically) |

## 3. Deployment Steps (Railway)

1.  **New Project:** Create a new project in Railway.
2.  **Connect Repo:** Connect your GitHub repository.
3.  **Variables:** Go to the "Variables" tab and add all the variables listed above.
4.  **Build & Deploy:** Railway should automatically detect the `Procfile` and `Pipfile`/`requirements.txt` and build the application.
    *   **Build Command:** (None usually needed for Python, but if needed: `pip install -r requirements.txt` or `pipenv install`)
    *   **Start Command:** `gunicorn server:app --bind 0.0.0.0:$PORT` (This is already in `Procfile`)

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

