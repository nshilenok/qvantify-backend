# Project Scope & Features (Qvantify Fullstack)

This file is the **source of truth** for what we expect to work and how we test it end-to-end after changes.

## Product Features

### 1. Interview / Conversation Flow (Web)
- **Frontend**: Next.js App Router app in `frontend/` (deployed to Vercel). `/` redirects to `/interview`, preserving query params.
- **API proxy**: `/api/*` requests are proxied by `frontend/app/api/[...path]/route.ts` to the Flask backend on Railway (`QVANTIFY_RAILWAY_URL`).
- **Project config load**: `GET /api/project` returns project UI config (labels, theme, consent copy, etc.).
- **Respondent creation**: `POST /api/respondent` creates a respondent row and returns a UUID.
- **Interview initialization**: `GET /api/interview` returns the first assistant response (or continues flow).
- **Ongoing conversation**:
  - `POST /api/reply` (JSON) stores user + assistant messages into `records` and returns `{response,status,answers}`.
  - `POST /api/reply` (streaming SSE over fetch) when client sends `Accept: text/event-stream` or JSON `{stream:true}`:
    - streams `{"type":"delta","delta":"..."}` events
    - ends with `{"type":"final","response":"...","status":"open|closed","answers":[...]}`.
- **OpenAI gpt-5.***: `max_tokens` is translated to `max_completion_tokens` to avoid 400 errors.
- **Topic switching**: `topic.py` advances topics using `topics` + `topics_log`.
- **Progress bar**: a 2px top line on the respondent interview UI shows `current_topic_index / total_topics`, using the project primary color and updating after `/api/interview` and `/api/reply` (only renders when progress data is present).
- **Session inactivity auto-close**: open sessions are marked closed when no **user input** is received for 10 minutes (checks `records.role='user'` and updates the latest `topics_log` entry). Configure with `SESSION_INACTIVITY_MINUTES`.
- **Abort behavior**: clicking Abort sends the user to the Success screen and does not offer a restart CTA for that session.
- **Abort copy override**: if a project sets `abort_title` and/or `abort_message`, those values replace the Success title/message when the user aborted.
- **Voice input (feature-flagged)**:
  - **Feature flag**: `projects.voice_enabled` (boolean, default `false`). When `false`:
    - Mic UI is not shown (no change to existing sessions).
    - `POST /api/voice-transcribe/` returns `404` to avoid leaking feature presence.
  - **UI placement**: mic icon button is rendered next to the Reply/Send button inside the input pill.
  - **Flow**:
    - Click mic -> browser requests microphone permission.
    - While recording: input container glows and mic icon switches to a red stop square.
    - Click stop -> upload the recorded audio clip to backend -> backend transcribes full clip -> returns text.
    - Transcript is appended to any existing draft text (no auto-clear).
  - **Capture tuning**: request `echoCancellation`, `noiseSuppression`, and `autoGainControl` for better distance pickup.
  - **UX helpers**:
    - Idle helper: "Tap the mic to record. Tap again to stop."
    - Processing helper: "Turning your voice into text..."
    - Permission errors: inline helper text (e.g. "Microphone permission not granted.").
  - **Fallbacks**:
    - If `MediaRecorder` is unavailable (some mobile browsers): allow uploading/recording an audio clip via file input (`accept="audio/*" capture`) and transcribe that file.
    - If not HTTPS/secure context: show "Microphone requires HTTPS." and keep mic disabled.
  - **Backend API**: `POST /api/voice-transcribe/` (multipart) with:
    - headers: `projectId`, `uuid`
    - body: `audio` file + optional `language` (ISO‑639‑1)
    - response: `{text}` or `{error}`.
  - **Backend config**: `VOICE_TRANSCRIPTION_MODEL` (default `whisper-1`), `VOICE_MAX_BYTES` (default 15MB).

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
- **Frontend without DB**: Next routes (`/interview`, `/results/*`) should render (loading/error states) even if DB is down.

### 3. Sample Project (Seeded in DB)
- **Project ID**: `sample_game_funnel_2026_01_14`
- **Entry URL**: `/interview?interview=sample_game_funnel_2026_01_14&external_id=sample@user.com` (root `/?interview=...` redirects here)
- **Topics**:
  - `single_question` × 6 (start + 5 sample questions)
  - `auto` (final): asks missing follow-ups and then calls the tool to switch/end when appropriate
- **Success message**: thanks the user and confirms session recording + support follow-up + agreed complement.

### 4. Public Landing Demo: Research Journey (Seeded in DB)
- **Project name**: `Qvantify Demo — Research Journey`
- **Project ID**: `33c9a74a-93ad-4a50-b78b-58bc83533c44`
- **Entry URL (prod)**: `/?interview=33c9a74a-93ad-4a50-b78b-58bc83533c44` (or `/interview?interview=...`)
- **Welcome message**: explicitly states this is a demo interview about the user’s research needs.
- **Topics**:
  - `auto` × 11 (timeline-style continuous discovery / JTBD interview)
  - Starts with: “Tell me about the last time you had to do research” and then goes step-by-step (“what happened next?”)
  - Includes derail correction (clarify + steer back to the concrete timeline)
  - Includes anti-spam / anti-jailbreak behavior: the assistant ends the demo interview and stops asking questions

### 5. SweepKing JTBD Interview (Seeded in DB)
- **Project name**: `SweepKing`
- **Project ID**: `d0aaae3f-b133-4099-a6fb-9509ed750a24`
- **No welcome page**: `skip_welcome=true`
- **Collect email**: `collect_email=false` (uses `external_id` instead)
- **Entry URL example**: `/interview?interview=d0aaae3f-b133-4099-a6fb-9509ed750a24&external_id=sk_user_001` (root `/?interview=...` redirects here)
- **Topics**:
  - `auto` × 25 (one per question)
  - Each topic’s `system` stores: `<question> + "\\n\\nCurrent Theme: <group theme>"`
  - Topic switching happens when the model calls the tool `interview_topic_over({"status":"done"})`
- **Abort copy**:
  - `abort_title`: `Aborted`
  - `abort_message`: `You have aborted the interview. Please restart the interview and complete it. If you encounter any problems please reach to our support.`
- **Voice input**:
  - `voice_enabled`: `true`

### 6. Swipking2 Dopamine Interview (Seeded in DB)
- **Project name**: `Swipking2`
- **Project ID**: `swipking2`
- **No welcome page**: `skip_welcome=true`
- **Collect email**: `collect_email=false` (uses `external_id` instead)
- **Entry URL example**: `/interview?interview=swipking2&external_id=sw2_user_001` (root `/?interview=...` redirects here)
- **Topics**:
  - `auto` × 15 (one per provided theme/question)
  - Each topic `system` starts with: `CURRENT TOPIC: <provided theme>`
  - Each topic `group` stores a very short theme label (not the full topic text)
  - Topic switching happens when the model calls `interview_topic_over({"status":"done"})`
- **Default prompt rules**:
  - each topic should be covered in only a few questions maximum
  - if one question is enough, complete the topic immediately
  - never ask multiple questions in one assistant message
  - do not reinvent/rephrase topic questions; use `CURRENT TOPIC` wording as source
  - if a topic has multiple parts, split into separate one-question turns from exact topic fragments
- **Reply context assembly contract (backend)**:
  - outbound LLM context must include exactly one `system` message: the current topic system + rendered project `default_prompt`
  - outbound history must include only `user` and `assistant` records
  - legacy or DB-stored `system` records must not be replayed into outbound context
  - streaming and non-streaming `/api/reply` paths must use the same context builder
  - regression coverage: `tests/test_api_reply_message_construction.py`
- **Production share-link workflow**:
  - customer results access uses `/results/share/<token>` with a password from `project_share_links`

### 4. Regression Test Matrix (API + FE)
- **API (pytest)**:
  - `/api/project`, `/api/respondent`, `/api/interview`, `/api/reply` (JSON) happy path
  - `/api/reply` streaming path: receives multiple deltas and a final event
  - `/api/project` includes `voice_enabled` (default false)
  - `/api/voice-transcribe` returns 404 when `voice_enabled=false` (feature flag safety)
  - Wrong/missing `interview` id behavior
- **FE (Playwright, mocked UI contract)**:
  - Targets local Next dev server (default `http://127.0.0.1:4173`) with route stubs
  - Interview flow: project load, respondent creation, interview init, reply send, assistant response render
  - Voice input: mic appears when `voice_enabled=true`, denied permission shows inline helper text
  - Results Portal admin/share tests run on mocked API responses (projects list, project detail, share login)
  - Admin topics tables: Topics + Topic logs cards render with sample rows
  - Runs on desktop + mobile viewports
- **FE (Playwright, live backend)**:
  - Optional smoke checks gated by env (e.g. `QVANTIFY_E2E_BASE_URL`)
  - Share login endpoint must **not** return `Missing SECRET_KEY` (live health check)

### 5. Results Portal (Admin + Customer Share Links)

#### 5.1 Admin (Local-only “God Mode”)
- **URL**: `/results/projects`
- **Security model**:
  - Admin APIs are **localhost-only** (requests must come from loopback).
  - Admin APIs are **disabled unless** `ADMIN_LOCAL_KEY` is set (value is not sent to browser; it simply toggles enablement).
- **Admin APIs**:
  - `GET /api/projects` → list projects with session counts
  - `GET /api/projects/<project_id>/sessions` → list sessions with filters + `total`
  - `GET /api/projects/<project_id>/sessions/<respondent_id>?include_system=1` → transcript + metadata
  - `PUT /api/projects/<project_id>/sessions/<respondent_id>/annotation` → session note + like/dislike
  - `PUT /api/projects/<project_id>/records/<record_id>/annotation` → message note + like/dislike
  - `POST /api/projects/<project_id>/sessions/delete` → delete sessions by ids or by filters (supports select-all with exclusions)
  - `GET|POST /api/projects/<project_id>/share_links` → create/list customer links (returns password only at creation)
  - `POST /api/projects/<project_id>/share_links/<link_id>/revoke` → revoke link
  - `GET /api/projects/<project_id>/export?...` → export filtered matches (CSV/JSON)
  - `POST /api/projects/<project_id>/analyze_stale?inactive_minutes=10` → generate persona labels + findings summaries for stale/closed sessions

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
- **API**: `GET /api/projects/<project_id>/usage`
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
- **Voice toggle**: project settings includes a **Voice input** switch that updates `projects.voice_enabled` for the interview UI.

#### 5.1.6 Project Tabs (Admin-only)
- **Tab isolation**: switching tabs hides unrelated panels (Results, Topics, Usage, Settings).
- **Topics tab**: only the topics table + search are visible (no sessions list or transcript).

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

#### 5.1.6 Topics Tables (Admin-only)
- **Purpose**: give admins full visibility into topic configuration and topic execution logs per project.
- **API**:
  - `GET /api/projects/<project_id>/topics` → all topic rows for the project.
  - `GET /api/projects/<project_id>/topics_log` → topic log rows joined by project.
- **Topics table columns**:
  - `id`, `project`, `title`, `group`, `system`, `length`, `sequence`, `topic_type`, `expiration_strategy`, `defined_answers`.
  - `title` is optional; when empty it is derived from the topic `system` prompt using 1–2 words (prefers the `Current Theme:` label when present).
  - `group` is an optional meta label used for higher-level grouping of topics.
- **Topic logs table columns**:
  - `id`, `topic_id`, `user_id`, `started_at`, `status`, `responses`.
- **UI placement**: admin project page, below the transcript card, as two separate cards.
- **UX details**:
  - Each card shows a count summary and a search field (filters client-side).
  - Columns are horizontally scrollable on small screens.
  - ID fields are copyable; long `system` and `defined_answers` values open in a modal for full viewing.

#### 5.1.7 Admin Project Tabs
- **Tabs**: Results, Topics, Usage, Project Settings.
- **Placement**: tabs render in the project header between project metadata and the Share/Export/Refresh actions.
- **Visual style**: horizontal tab strip with an underline divider; active tab appears as a connected sheet (rounded top, border, no bottom border), inactive tabs are muted text on a transparent background with hover surface.
- **Results**: transcript viewer + session notes/likes + summary (current behavior).
- **Topics**: shows Topics + Topic logs cards.
- **Usage**: shows the token usage card (total tokens, cost, and service split).
- **Project Settings**: shows the project properties list previously shown in the sidebar.

#### 5.2 Customer View (Read-only Share Link)
- **URL**: `/results/share/<token>`
- **Auth model**:
  - Customer enters a password once; server sets a **signed httpOnly cookie** (requires `SECRET_KEY`).
  - Customer can **view** results, **export**, and add **session-level like/dislike + notes**.
  - Customer can mark/unmark sessions as **seen** from the session header; this state persists in DB per project (`respondents.is_seen`).
- **Rate-limit audit fallback**:
  - If `project_share_login_attempts` is missing/unavailable, login still works (rate limit + audit skipped, server logs a warning).
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
- **Session timestamps**: each sidebar row shows a full local date/time stamp (e.g. `17 feb 2025 17:30`) plus a relative time label (e.g. `27 min ago`).
- **Sidebar layout**: on desktop, **Sessions** and **Project properties** stack in the left column so the transcript panel stays aligned and no middle-column gap appears.
- **Sidebar height**: in share view on desktop, the Sessions card fills available page height and the list scrolls inside the card.
- **Session sorting**: sessions can be ordered by latest/oldest activity, responses count, and external_id A-Z/Z-A.
- **Status badges**: sessions show **Open/Closed** state in the sidebar and in the session header.
- **Seen state UX**:
  - Session header includes an eye action to mark/unmark seen.
  - Session rows can display a Seen badge.
  - Filter toggle `Hide sessions marked as seen` excludes seen sessions via `hide_seen=1`.
- **Projects list**: each project card shows a copyable interview link with a test `external_id` baked into the URL.
- **Project header**: results page shows copyable Project ID and participation link (`/?interview=<project_id>&external_id=sample@user.com`).
- **Search + filters layout**: full-width panel above session list + transcript (admin + share).
- **Search**: full-width search input above sessions + transcripts (searches transcripts, persona, external_id, session id, notes).
- **Quick toggles (share view)**:
  - `Hide empty interviews` enforces `responses_min=1` and persists in localStorage by share token.
  - `Hide sessions marked as seen` hides sessions marked seen in DB.
- **Design preview**: `/results/sample` is a static UI appetizer page to validate the minimal light direction (no data fetching).
- **Filters (pro builder)**:
  - Filter rows start with a **property selector**, then show only applicable operators/inputs.
  - Text operators (External ID + Note): exists / not exists / equals / not equals / contains / not contains.
  - Rating: is (liked / neutral / disliked).
  - Date operators: after / before / between / last 7 days / last 30 days / this week / this month.
  - Responses count operators: at least / at most / between / equals.
  - Any filter should **drill down** results (no highlight-only behavior).
- **Match snippets**: show matched snippet in the session list when search is active.
- **Session note preview**: session cards expose custom note preview (first 100 chars + `...` when truncated).
- **Body**: messenger-style transcript; system prompts hidden by default (admin can toggle).
- **Transcript cleanup**: empty/blank messages are suppressed (no placeholder bubbles).
- **Topic separators**: transcript inserts centered grey separators for the initial topic and any topic changes, using the topic label/title from `records.topic`.
- **Group separators**: transcript inserts a filled highlight separator when the topic `group` changes (shown once per group).
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
  - `GET /results/projects` serves the Next.js Results Portal
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
  - Customer share view: `Hide empty interviews` hides zero-response sessions and remains enabled after reload.
  - Customer share view: `Hide sessions marked as seen` removes seen sessions from list.
  - Customer share view: marking seen persists across reload and is shared at project level.
  - Customer share view: sidebar note preview truncates to 100 chars + `...` for long notes.
  - Transcript shows topic separator chips when topics change (admin + share)
  - Topics table shows `title` values (short labels derived from `system`)

## Technical Architecture

### Frontend
- **Next.js app**: `frontend/` (App Router) provides `/interview` and `/results` experiences.
- **Root redirect**: `/` redirects to `/interview` while preserving query params.
- **API proxy**: `frontend/app/api/[...path]/route.ts` proxies `/api/*` to Railway (`QVANTIFY_RAILWAY_URL`) and sets `x-qvantify-proxy-base` for traceability.
- **Legacy static removed**: no `static/` frontend bundle remains in this repo.

### Backend
- **Flask app**: `server.py` serves the API on Railway.
- **DB**: `database.py` (psycopg2) with env-only config in `credentials.py` (loads `env.local`/`.env` via `python-dotenv`).

### Database (Supabase Postgres)
- **Schema source**: `database_schema.sql`
- **Core tables for interview flow**:
  - `projects`, `respondents`, `records`, `topics`, `topics_log`, `usage_stats`

## Environment Configuration

### Local env file
- Use `env.local` (not committed).

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

### A. Frontend + API boot

- **Frontend (Next.js)**:
  - `cd frontend`
  - `npm run dev -- --port 4173`
  - Expect `http://127.0.0.1:4173/interview?interview=<project_id>&external_id=sample@user.com` to render
- **Backend (Flask API)**:
  - `cd ..`
  - `source .venv/bin/activate`
  - `PORT=5055 python server.py`
  - Expect `GET http://127.0.0.1:5055/api/health` → `200`

### B. DB-required endpoints behave correctly
- If DB is not configured or unreachable, DB-required endpoints should return `503 Database unavailable` (not crash).

### C. Interview flow (requires DB + AI keys)
- Prereqs:
  - DB schema present
  - Project row + topics seeded for a `projectId`
  - `OPENAI_API_KEY` set
- Test flow:
  - Create respondent → initialize interview → send a reply → verify `records` rows are created

### D. E2E (Playwright)
- `npx playwright test` (starts the Next dev server on `4173`)
- Expect 12 passed, 2 skipped (live-share check requires env)

## Release Workflow (Local-only Checks + Staging)

- Run `./scripts/local-release-checks.sh` before every push.
- Run `python3 scripts/release_safety_check.py --repo-path .` before promotion.
- (Optional) Install the pre-push hook once: `./scripts/install-git-hooks.sh`
- Deploy incident logging is mandatory:
  - Append every staging/production attempt to `ops/deploy_journal.md`.
  - Keep date/time + raw command outputs/errors without redaction.
- Deploy skill synchronization is mandatory:
  - If deploy workflow/checks change, update `.cursor/skills/qvantify-deploy/SKILL.md` and `.cursor/skills/qvantify-deploy/references/pipeline.md` in the same change cycle.
  - Do not close a deployment incident until skill docs are updated.
- Frontend ownership and policy:
  - `qvantify-frontend` serves both `staging.app.qvantify.com` and `app.qvantify.com`.
  - Never create a new Vercel project for frontend delivery.
  - Never use temporary public domain assignments; only stable app/staging domains are allowed.
  - Git auto-deploy from root context is disabled (`vercel.json` -> `git.deploymentEnabled=false`) to avoid wrong-folder preview takeover.
  - Frontend deploy is manual from `frontend/` only.
- Runtime validation is mandatory before promotion:
  - Use `vercel curl --cwd frontend ... --deployment https://<staging-deploy>.vercel.app` for protected staging checks.
  - Verify `/interview?...` returns `200` and `/api/health` returns `200` with `x-qvantify-proxy-base: https://qvantify-staging.up.railway.app`.
- Release flow:
  - Push to `staging` -> deploy frontend from `frontend/` to `staging.app.qvantify.com` -> verify staging -> merge `staging` -> `main` -> promote the same staging frontend deployment to `app.qvantify.com`.
- Rollback safety:
  - Create checkpoint before risky changes: `python3 scripts/create_checkpoint.py --name "<release-name>"`.
  - Use snapshot rollback command if needed: `python3 scripts/rollback_domains.py --snapshot "ops/checkpoints/checkpoint-<release-name>.json" --apply`.

## Engineering Guardrails (Agent Rules)

- Project-level guardrails are intentionally minimal and centralized.
- Python policy baseline:
  - Keep backend changes compatible with Python `3.11` (matches `Dockerfile` and CI).
  - Use `requirements.txt` with `pip` for dependency management unless an explicit migration is requested.
- Interview screen UI constraints remain governed by `AGENTS.md`.
