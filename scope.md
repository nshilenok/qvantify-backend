# Project Scope & Features (Qvantify Fullstack)

This file is the **source of truth** for what we expect to work and how we test it end-to-end after changes.

## Product Features

### 1. Interview / Conversation Flow (Web)
- **Frontend**: Pre-built static web bundle served from `static/` by `server.py`.
- **Project config load**: `GET /api/project/` returns project UI config (labels, theme, consent copy, etc.).
- **Respondent creation**: `POST /api/respondent/` creates a respondent row and returns a UUID.
- **Interview initialization**: `GET /api/interview/` returns the first assistant response (or continues flow).
- **Ongoing conversation**:
  - `POST /api/reply/` (JSON) stores user + assistant messages into `records` and returns `{response,status,answers}`.
  - `POST /api/reply/` (streaming SSE over fetch) when client sends `Accept: text/event-stream` or JSON `{stream:true}`:
    - streams `{"type":"delta","delta":"..."}` events
    - ends with `{"type":"final","response":"...","status":"open|closed","answers":[...]}`.
- **OpenAI gpt-5.***: responses use a fixed default token budget in code (mapped to `max_completion_tokens`).
- **Topic switching**: `topic.py` advances topics using `topics` + `topics_log`.

### 2. Health & Bring-up Diagnostics
- **Health endpoint**: `GET /api/health` returns:
  - `ok`: server is up
  - `db_configured`: whether DB env vars are present (no connection attempt)
  - `db_config_error`: why DB config is missing/invalid (if any)
- **Debug endpoint**: `GET /api/debug/?key=...` reports whether AI keys are set (never exposes values).
  - Also reports `openai_key_valid` via a tiny request (no key exposure).
- **Internal key**:
  - `/api/debug` and `/api/heartbeat` require `INTERNAL_API_KEY` (passed as `?key=...`).
  - If `INTERNAL_API_KEY` is unset, these endpoints are disabled (return `404`).
- **Frontend without DB**: Static routes (`/`, `/static/...`) must work even if DB is down.

### 3. Sample Project (Seeded in DB)
- **Project ID**: `sample_game_funnel_2026_01_14`
- **Entry URL**: `/?interview=sample_game_funnel_2026_01_14&external_id=sample@user.com`
- **Topics**:
  - `single_question` × 6 (start + 5 sample questions)
  - `auto` (final): asks missing follow-ups and then calls the tool to switch/end when appropriate
- **Success message**: thanks the user and confirms session recording + support follow-up + agreed complement.

### 5. SweepKing JTBD Interview (Seeded in DB)
- **Project name**: `SweepKing`
- **Project ID**: `d0aaae3f-b133-4099-a6fb-9509ed750a24`
- **No welcome page**: `skip_welcome=true`
- **Collect email**: `collect_email=false` (uses `external_id` instead)
- **Entry URL example**: `/?interview=d0aaae3f-b133-4099-a6fb-9509ed750a24&external_id=sk_user_001`
- **Topics**:
  - `auto` × 25 (one per question)
  - Each topic’s `system` stores: `<question> + "\\n\\nCurrent Theme: <group theme>"`
  - Topic switching happens when the model calls the tool `interview_topic_over({"status":"done"})`

### 4. Regression Test Matrix (API + FE)
- **API (pytest)**:
  - `/api/project/`, `/api/respondent/`, `/api/interview/`, `/api/reply/` (JSON) happy path
  - `/api/reply/` streaming path: receives multiple deltas and a final event
  - Wrong/missing `interview` id behavior
- **FE (Playwright)**:
  - Desktop + mobile viewports
  - Full journey: enter via URL with `external_id`, chat across topic types, end on Success screen
  - Alternative scenarios: refresh mid-session, restart session, “existing” behavior as defined (new respondent if only external_id repeats)

### 5. Results Portal (Admin + Customer Share Links)

#### 5.1 Admin (Local-only “God Mode”)
- **URL**: `/results/admin`
- **Security model**:
  - Admin APIs are **localhost-only** (requests must come from loopback).
  - Admin APIs are **disabled unless** `ADMIN_LOCAL_KEY` is set (value is not sent to browser; it simply toggles enablement).
- **Admin APIs**:
  - `GET /api/admin/projects` → list projects with session counts
  - `GET /api/admin/projects/<project_id>/sessions` → list sessions with filters + `total`
  - `GET /api/admin/projects/<project_id>/sessions/<respondent_id>?include_system=1` → transcript + metadata
  - `PUT /api/admin/projects/<project_id>/sessions/<respondent_id>/annotation` → session note + like/dislike
  - `PUT /api/admin/projects/<project_id>/records/<record_id>/annotation` → message note + like/dislike
  - `GET|POST /api/admin/projects/<project_id>/share_links` → create/list customer links (returns password only at creation)
  - `POST /api/admin/projects/<project_id>/share_links/<link_id>/revoke` → revoke link
  - `GET /api/admin/projects/<project_id>/export?...` → export filtered matches (CSV/JSON)
  - `POST /api/admin/projects/<project_id>/analyze_stale?inactive_minutes=10` → generate persona labels + findings summaries for stale/closed sessions

#### 5.1.1 Share Results Modal (Admin)
- **Entry point**: `Share` button in the project results header.
- **Modal content**:
  - Toggle to **Enable sharing** (creates an active share link + password).
  - When enabled: displays **Share URL** and **Password** in read-only fields.
  - **Copy URL & Password** action (copies both values in one click).
  - **Regenerate link & password** action (revokes current, creates new).
  - **Disable sharing** (toggle off) revokes any active share links.
- **Behavior**:
  - No label input required (share links are standard, one active at a time).
  - Only active link is shown in the modal; previous links are revoked.

#### 5.2 Customer View (Read-only Share Link)
- **URL**: `/results/share/<token>`
- **Auth model**:
  - Customer enters a password once; server sets a **signed httpOnly cookie** (requires `SECRET_KEY`).
  - Customer can **view** results and **export**, but cannot edit anything.
- **Share APIs**:
  - `GET /api/share/<token>/info` → project name (for login UX)
  - `POST /api/share/<token>/login` → password gate
  - `GET /api/share/<token>/sessions` → filtered list (no system prompts)
  - `GET /api/share/<token>/sessions/<respondent_id>` → transcript (no system prompts)
  - `GET /api/share/<token>/export?...` → export filtered matches (CSV/JSON)

#### 5.3 UI Expectations (per project)
- **Theme**: light UI, clean white/gray surfaces, subtle borders, high readability.
- **Header**: logo-only branding using Qvantify SVG; no title/subname.
- **Left sidebar**: sessions grouped by day, sorted latest, quick info (persona label, time, answer count, external_id). Show session/respondent ID with copy.
- **Search**: single global search bar (transcripts + persona + external_id + session id + notes).
- **Filters (pro builder)**:
  - external_id operators (exists / does not exist / equals / not equals / contains / not contains)
  - Rating (like / neutral / dislike)
  - Notes contains
  - Date range (after/before) based on last activity timestamp
  - Any filter should **drill down** results (no highlight-only behavior)
- **Match snippets**: when search is active, show matched text snippet in the session list with a tooltip.
- **Body**: messenger-style transcript; system prompts hidden by default (admin can toggle).
- **Actions**:
  - **Session-level** like/dislike only
  - **Notes** auto-save live with visible status
  - No per-message actions
- **Export**:
  - Modal confirmation with counts for **Filtered** and **All**
  - CSV export is **record-level** with project + respondent + record columns, excludes system prompts
- **Share**: Share modal is the only share UI; no inline label field or create button on the page.

#### 5.4 Test Checklist (Local)
- Prereqs:
  - `ADMIN_LOCAL_KEY` set (enables admin)
  - `SECRET_KEY` set (share-link sessions)
  - DB configured (`DATABASE_URL` or `DB_HOST` + `DB_PASSWORD`)
  - (Optional) `INTERNAL_API_KEY` set (enables `/api/debug` + `/api/heartbeat`)
- Tests:
  - `GET /results/admin` serves the Results Portal SPA
  - Admin can list projects and open a project results page
  - Filters work: search, external_id ops, date range
  - Transcript viewer hides system prompts by default; toggle shows them
  - Admin can edit: session note + like/dislike; message note + like/dislike
  - Admin can create a share link, copy URL + password
  - Admin can disable sharing (active link revoked)
  - Admin can regenerate link + password in the share modal
  - Customer can login via share URL, view results read-only, export CSV

## Technical Architecture

### Backend
- **Flask app**: `server.py` serves both frontend + API.
- **DB**: `database.py` (psycopg2) with env-only config in `credentials.py` (loads `env.local`/`.env` via `python-dotenv`).
- **Vercel routing**: `/api/*` (with and without trailing slash) rewrites to Railway backend; `/` serves `static/index.html`.

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

## Operational Runbook (Prod)

### A. Railway bring-up (API 502 or `$PORT` errors)
- Ensure Railway uses the repo `Dockerfile` and **does not** override the start command with `$PORT`.
- Expected runtime:
  - `Dockerfile` uses `ENTRYPOINT ["python", "start.py"]`
  - `Procfile` uses `web: python start.py`
- If you see `Error: '$PORT' is not a valid port number`:
  - Clear the Railway **Start Command** override, or set it to `python start.py`
  - Redeploy

### B. DB config missing
- `/api/health` should show `db_configured=true`.
- Set `DATABASE_URL` and `DB_SSLMODE=require` in Railway variables.

### C. OpenAI 400 errors
- Symptom: `/api/reply/` returns 500 with an unsupported token-parameter error (verify OpenAI config and token budget mapping).
- Fix: ensure `max_completion_tokens` is used for `gpt-5.*` models (already handled in `llmInterface.py`).

### D. One-command recovery check
- Script: `./scripts/health-check.sh`
- Uses: `QVANTIFY_BASE_URL`, `QVANTIFY_RAILWAY_URL`, `QVANTIFY_PROJECT_ID`

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
