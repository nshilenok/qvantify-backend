# Project Scope & Features (Qvantify Fullstack)

This file is the **source of truth** for what we expect to work and how we test it end-to-end after changes.

## Product Features

### 1. Interview / Conversation Flow (Web)
- **Frontend**: Pre-built static web bundle served from `static/` by `server.py`.
- **Project config load**: `GET /api/project/` returns project UI config (labels, theme, consent copy, etc.).
- **Respondent creation**: `POST /api/respondent/` creates a respondent row and returns a UUID.
- **Interview initialization**: `GET /api/interview/` returns the first assistant response (or continues flow).
- **Ongoing conversation**: `POST /api/reply/` stores user + assistant messages into `records`.
- **Topic switching**: `topic.py` advances topics using `topics` + `topics_log`.

### 2. Health & Bring-up Diagnostics
- **Health endpoint**: `GET /api/health` returns:
  - `ok`: server is up
  - `db_configured`: whether DB env vars are present (no connection attempt)
  - `db_config_error`: why DB config is missing/invalid (if any)
- **Debug endpoint**: `GET /api/debug/?key=...` reports whether AI keys are set (never exposes values).
- **Frontend without DB**: Static routes (`/`, `/static/...`) must work even if DB is down.

## Technical Architecture

### Backend
- **Flask app**: `server.py` serves both frontend + API.
- **DB**: `database.py` (psycopg2) with env-only config in `credentials.py` (loads `env.local`/`.env` via `python-dotenv`).

### Database (Supabase Postgres)
- **Schema source**: `database_schema.sql`
- **Core tables for interview flow**:
  - `projects`, `respondents`, `records`, `topics`, `topics_log`, `usage_stats`

## Environment Configuration

### Local env file
- Use `env.local` (not committed). Template: `env.example`.

### DB Connectivity Notes (Supabase IPv6 vs IPv4)
- Supabase **direct DB host** `db.<project_ref>.supabase.co` resolves to **IPv6** by default.
- If your runtime/network is **IPv6-incompatible**, you must use:
  - **Supavisor / pooler (session mode)** connection string (IPv4-compatible), or
  - **Dedicated IPv4 add-on** (paid) for direct connections.

## Test Checklist (Local)

### A. Server boots + frontend serves

```bash
cd "/Users/nikitashilenok/Documents/vibecoding projects/qvantify-fullstack"
source .venv/bin/activate
PORT=5055 python server.py
```

- Expect:
  - `GET http://127.0.0.1:5055/` → `200`
  - `GET http://127.0.0.1:5055/api/health` → `200`

### B. DB-required endpoints behave correctly
- If DB is not configured or unreachable, DB-required endpoints should return `503 Database unavailable` (not crash).

### C. Interview flow (requires DB + AI keys)
- Prereqs:
  - DB schema present
  - Project row + topics seeded for a `projectId`
  - `OPENAI_API_KEY` set
- Test flow:
  - Create respondent → initialize interview → send a reply → verify `records` rows are created
