# Qvantify Backend

Flask backend for the Qvantify app API. The user-facing frontend is the Next.js app in `frontend/`.

## Overview

- **Backend**: Python + Flask (`server.py`)
- **Frontend**: Next.js App Router in `frontend/` (Vercel)
- **Database**: PostgreSQL (Supabase-compatible). Schema is in `database_schema.sql`.
- **AI**: OpenAI/Azure OpenAI chat completions via `llmInterface.py`

Notes:
- **Vector/embedding search is disabled/removed** (no `pgvector` requirement).

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Railway       │    │   Supabase      │
│   (Next.js)     │◄──►│   (Flask API)   │◄──►│   (PostgreSQL)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   OpenAI API    │
                       │   (gpt-5.2)     │
                       └─────────────────┘
```

## API Endpoints

### Core Endpoints

| Endpoint | Method | Expected | Description |
|----------|--------|--------|-------------|
| `/api/project/` | GET | Yes | Load project configuration |
| `/api/respondent/` | POST | Yes | Create new respondent |
| `/api/interview/` | GET | Yes | Initialize interview |
| `/api/reply/` | POST | Yes | Process user responses |
| `/api/heartbeat/` | GET | Yes | Health check |
| `/api/debug/` | GET | Yes | Debug information |

Status markers above reflect intended behavior, not a live guarantee.

## Database

- **Schema**: `database_schema.sql`
- **Credentials**: configured via environment variables (see below). Do not hardcode secrets in the repo.

## Environment Variables

Required (core app):
- **Database**: set either `DATABASE_URL` **or** `DB_HOST` + `DB_PASSWORD` (and optionally `DB_NAME`/`DB_USER`/`DB_PORT`) in `env.local`.
- **AI**: `OPENAI_API_KEY` (only if you want the LLM features enabled).

Required (Results Portal share links):
- `SECRET_KEY` (signed cookie sessions)
- `SHARE_LINK_ENC_KEY` (Fernet key for encrypting share link token + password)

Optional (only if you use Azure chat / embeddings elsewhere):
- `AZURE_OPENAI_KEY`
- `OPENAI_PANDA_KEY`

Optional:
- `ADMIN_LOCAL_KEY` (enables local-only admin endpoints + Results Portal admin UI)
- `INTERNAL_API_KEY` (enables `/api/debug` + `/api/heartbeat` internal endpoints)
- `NEW_RELIC_LICENSE_KEY` (New Relic; keep out of repo)

Provided by Railway:
- `PORT`

## Deployment

This repo includes a `Procfile` + `start.py`:

- `web: python start.py` (handles Railway `$PORT` safely)
- Dockerfile uses `ENTRYPOINT ["python", "start.py"]`

For a step-by-step redeploy checklist (Railway + Supabase), see `deployment_guide.md`.

## Release Workflow (Staging → Production)

This repo uses **manual promotion** via branches:

1. Run local checks: `./scripts/local-release-checks.sh`
2. Push to `staging` (staging auto-deploys from GitHub)
3. Verify staging (set `QVANTIFY_RAILWAY_URL` in Vercel; see `deployment_guide.md`)
4. Merge `staging` → `main` to deploy production

Staging preview URL:
- Use the latest Vercel Preview deployment for the `staging` branch (Vercel → Deployments → filter by branch).

Deployment policy:
- Never create new Vercel projects. Use `qvantify-frontend` only.
- Never use temporary public domain assignments. Only `app.qvantify.com` and `staging.app.qvantify.com` are valid entry domains.
- Keep both stable domains attached to `qvantify-frontend`.

Optional: install a pre-push hook to enforce local checks:

```bash
./scripts/install-git-hooks.sh
```

## Quick Health Check

Run a single script to validate API health + DB connectivity:

```bash
QVANTIFY_BASE_URL=https://app.qvantify.com \
QVANTIFY_RAILWAY_URL=https://qvantify.up.railway.app \
QVANTIFY_PROJECT_ID=sample_game_funnel_2026_01_14 \
./scripts/health-check.sh
```

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create env.local and fill secrets locally (never commit)
# Then run:
python server.py
```

## Results Portal (Admin + Share Links)

Results routes are served by the Next.js frontend under `frontend/app/results/*`.
The backend provides API and share-link endpoints only.

## 📊 Monitoring

### Health Checks
- **Heartbeat:** `/api/heartbeat/?key=...` (requires `INTERNAL_API_KEY`)
- **Debug Info:** `/api/debug/?key=...` (requires `INTERNAL_API_KEY`)

### Logs
- Available in Railway dashboard
- Comprehensive error logging
- Request/response tracking

## 🔧 Recent Fixes

✅ **Fixed missing function implementations** - `store_message` and `get_chat_history`  
✅ **Added comprehensive error handling** - Better debugging and error responses  
✅ **Improved LLM error handling** - Better OpenAI API error reporting  
✅ **Added debug endpoint** - Environment variable status checking  
✅ **Enhanced logging** - Detailed request/response logging  

## 📁 Project Structure

```
qvantify-fullstack/
├── server.py              # Main Flask application
├── conversationInterface.py # Conversation logic
├── topic.py               # Topic management
├── llmInterface.py        # OpenAI integration
├── database.py            # Database operations
├── credentials.py         # Configuration
├── frontend/              # Next.js frontend app
└── requirements.txt       # Python dependencies
```

## 🚨 Troubleshooting

### Common Issues

1. **500 Internal Server Error**
   - Check Railway logs
   - Verify environment variables are set
   - Check OpenAI API key validity

2. **Database Connection Issues**
   - Verify Supabase credentials
   - Check network connectivity

3. **AI Response Failures**
   - Verify OpenAI API key
   - Check API quota/limits

### Debug Commands
```bash
# Check environment variables (internal-only)
curl "https://<your-host>/api/debug/?key=$INTERNAL_API_KEY"

# Check server health (internal-only)
curl "https://<your-host>/api/heartbeat/?key=$INTERNAL_API_KEY"
```

## Notes

- If you restore to a fresh Supabase project, run `database_schema.sql` first.
- Keep secrets in Railway/Supabase env vars (not in `credentials.py`).
