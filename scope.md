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
- **OpenAI gpt-5.***: `max_tokens` is translated to `max_completion_tokens` to avoid 400 errors.
- **Topic switching**: `topic.py` advances topics using `topics` + `topics_log`.
- **Session inactivity auto-close**: open sessions are marked closed when no **user input** is received for 10 minutes (checks `records.role='user'` and updates the latest `topics_log` entry). Configure with `SESSION_INACTIVITY_MINUTES`.
- **Abort behavior**: clicking Abort sends the user to the Success screen and does not offer a restart CTA for that session.
- **Abort copy override**: if a project sets `abort_title` and/or `abort_message`, those values replace the Success title/message when the user aborted.

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
- **Abort copy**:
  - `abort_title`: `Aborted`
  - `abort_message`: `You have aborted the interview. Please restart the interview and complete it. If you encounter any problems please reach to our support.`

### 4. Regression Test Matrix (API + FE)
- **API (pytest)**:
  - `/api/project/`, `/api/respondent/`, `/api/interview/`, `/api/reply/` (JSON) happy path
  - `/api/reply/` streaming path: receives multiple deltas and a final event
  - Wrong/missing `interview` id behavior
- **FE (Playwright, live backend)**:
  - Targets `QVANTIFY_E2E_BASE_URL` (production/staging), no API mocking
  - Interview flow: load project, create respondent, initialize interview, send reply, refresh mid-session
  - Abort flow: clicking Abort shows `abort_title`/`abort_message` when provided and hides restart CTA
  - Results share: share login endpoint must **not** return `Missing SECRET_KEY` (live health check)
  - Runs on desktop + mobile viewports
- **FE (Playwright, mocked UI contract)**:
  - Results Portal admin/share tests run only on local static build (mocked API responses)

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
  - `POST /api/admin/projects/<project_id>/sessions/delete` → delete sessions by ids or by filters (supports select-all with exclusions)
  - `GET|POST /api/admin/projects/<project_id>/share_links` → create/list customer links (returns password only at creation)
  - `POST /api/admin/projects/<project_id>/share_links/<link_id>/revoke` → revoke link
  - `GET /api/admin/projects/<project_id>/export?...` → export filtered matches (CSV/JSON)
  - `POST /api/admin/projects/<project_id>/analyze_stale?inactive_minutes=10` → generate persona labels + findings summaries for stale/closed sessions

#### 5.1.1 Share Results Modal (Admin)
- **Entry point**: `Share` button in the project results header.
- **Modal content**:
  - Toggle to **Enable sharing** (creates an active share link + password).
  - When enabled: displays **Local link**, **Web link**, and **Password** in read-only fields.
- **Copy Local**, **Copy Web**, and **Copy Password** actions (each copies its field).
  - **Regenerate link & password** action (revokes current, creates new).
  - **Disable sharing** (toggle off) revokes any active share links.
- **Behavior**:
  - No label input required (share links are standard, one active at a time).
  - Only active link is shown in the modal; previous links are revoked.

#### 5.1.2 Token Usage (Admin-only)
- **Purpose**: summarize LLM token consumption per project for billing/ops insight.
- **API**: `GET /api/admin/projects/<project_id>/usage`
  - Returns `total` tokens and per-service totals.
  - Returns USD estimate using `TOKEN_USD_PER_1K` rate (default `$0.01`).
  - Service mapping:
    - `core` → **Interviews**
    - `results_portal` → **Summary**
- **UI**: project page shows a **Token usage** card:
  - Total tokens (compact formatting: `1.2k`, `2.3M`)
  - USD estimate with the current rate shown
  - Per-service tokens for Interviews + Summary
  - Mini stacked bar chart with percentage split
  - Empty state: shows “No token usage recorded” when totals are zero.

#### 5.1.3 Project Properties (Admin-only)
- **UI**: project page shows a **Project properties** panel listing all project config fields (UI copy + model config).
- **Boolean badges**: true/false fields use clear visual badges, including a dedicated **Welcome screen** status.

#### 5.1.4 Interview Analysis (Auto)
- **Auto-analysis trigger**: runs when a session closes (latest topic status is closed) or via admin stale analysis.
- **Persona label**: 2-4 words, vivid but professional.
- **Findings summary**: 2-3 sentences, narrative and specific (avoid “this interview” phrasing).
- **Skip short sessions**: analysis is skipped when user responses total fewer than **5 words**.

#### 5.1.5 Interview Deletion (Admin-only)
- **Selection model**:
  - Admin can select individual sessions from the left sidebar.
  - **Select all on page** toggles the current list view.
  - **Select all matching filters** selects every session across pages for the current filter set.
  - Optional exclusions are supported after selecting all (deselect any row).
- **Bulk delete action**:
  - UI shows **Delete X selected interviews** in the project header.
  - Confirmation modal summarizes the count and warns the action is permanent.
  - Deletion removes respondents, records, topic logs, interview summaries, and usage rows.

#### 5.2 Customer View (Read-only Share Link)
- **URL**: `/results/share/<token>`
- **Auth model**:
  - Customer enters a password once; server sets a **signed httpOnly cookie** (requires `SECRET_KEY`).
  - Customer can **view** results, **export**, and add **session-level like/dislike + notes**.
- **Share APIs**:
  - `GET /api/share/<token>/info` → project name (for login UX)
  - `POST /api/share/<token>/login` → password gate
  - `GET /api/share/<token>/sessions` → filtered list (no system prompts)
  - `GET /api/share/<token>/sessions/<respondent_id>` → transcript (no system prompts)
  - `GET /api/share/<token>/export?...` → export filtered matches (CSV/JSON)

#### 5.3 UI Expectations (per project)
- **Theme**: light UI, clean white/gray surfaces, subtle borders, high readability.
- **Primary accent**: brand purple (#684EAD) for highlights, focus, and key CTAs.
- **Header**: logo-only branding using Qvantify SVG in brand purple for visibility on light backgrounds; no title/subname.
- **Left sidebar**: sessions grouped by day, sorted latest, quick info (persona label, time, answer count, external_id). Show session/respondent ID with copy.
- **Session sorting**: sessions can be ordered by latest/oldest activity, responses count, and external_id A-Z/Z-A.
- **Status badges**: sessions show **Open/Closed** state in the sidebar and in the session header.
- **Projects list**: each project card shows a copyable interview link with a test `external_id` baked into the URL.
- **Project header**: results page shows copyable Project ID and participation link (`/?interview=<project_id>&external_id=sample@user.com`).
- **Search + filters layout**: full-width panel above session list + transcript (admin + share).
- **Search**: full-width search input above sessions + transcripts (searches transcripts, persona, external_id, session id, notes).
- **Design preview**: `/results/sample` is a static UI appetizer page to validate the minimal light direction (no data fetching).
- **Filters (pro builder)**:
  - Filter rows start with a **property selector**, then show only applicable operators/inputs.
  - Text operators (External ID + Note): exists / not exists / equals / not equals / contains / not contains.
  - Rating: is (liked / neutral / disliked).
  - Date operators: after / before / between / last 7 days / last 30 days / this week / this month.
  - Responses count operators: at least / at most / between / equals.
  - Any filter should **drill down** results (no highlight-only behavior).
- **Match snippets**: show matched snippet in the session list when search is active.
- **Body**: messenger-style transcript; system prompts hidden by default (admin can toggle).
- **Transcript cleanup**: empty/blank messages are suppressed (no placeholder bubbles).
- **Actions**:
  - **Session-level** like/dislike only
  - **Notes** auto-save live with visible status
  - **Transcript copy**: hover any message bubble to reveal a Copy action
  - **Narrative summary copy**: hover the summary text to reveal Copy
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
  - `GET /results/sample` serves the design preview page
  - Admin can list projects and open a project results page
- Project results header shows copy buttons for Project ID + participation link
  - Token usage card shows total + interviews + summary and chart
- Search works: global search input filters sessions + match snippets
- Filters work: property selector + operators (text, rating, date, responses)
  - Transcript viewer hides system prompts by default; toggle shows them
  - Admin can edit: session note + like/dislike; message note + like/dislike
- Admin can select sessions and delete them (single, page, or all matching filters)
- Session like/dislike updates instantly and confirms save with blink
  - Admin can create a share link, copy URL + password
  - Admin can disable sharing (active link revoked)
  - Admin can regenerate link + password in the share modal
  - Customer can login via share URL, view results read-only, export CSV
- Customer share view: notes autosave works and no client-side runtime errors

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
- Symptom: `/api/reply/` returns 500 and logs show `Unsupported parameter: 'max_tokens'`.
- Fix: ensure `max_completion_tokens` is used for `gpt-5.*` models (already handled in `llmInterface.py`).

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
