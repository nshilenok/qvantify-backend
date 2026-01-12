# Qvantify Backend

Flask backend for the Qvantify app (serves API + the built React build from `static/`).

## Overview

- **Backend**: Python + Flask (`server.py`)
- **Frontend**: prebuilt static assets served from `static/`
- **Database**: PostgreSQL (Supabase-compatible). Schema is in `database_schema.sql`.
- **AI**: OpenAI/Azure OpenAI chat completions via `llmInterface.py`

Notes:
- **Vector/embedding search is disabled/removed** (no `pgvector` requirement).

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Railway       │    │   Supabase      │
│   (React Web)   │◄──►│   (Flask App)   │◄──►│   (PostgreSQL)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   OpenAI API    │
                       │   (GPT-4)      │
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

Required:
- `DB_HOST`
- `DB_NAME` (default: `postgres`)
- `DB_USER`
- `DB_PASSWORD`
- `DB_PORT` (default: `5432`)
- `OPENAI_API_KEY` (if using OpenAI chat completions)

Optional (only if you use Azure chat / embeddings elsewhere):
- `AZURE_OPENAI_KEY`
- `OPENAI_PANDA_KEY`

Provided by Railway:
- `PORT`

## Deployment

This repo includes a `Procfile`:

- `web: gunicorn server:app --bind 0.0.0.0:$PORT`

For a step-by-step redeploy checklist (Railway + Supabase), see `deployment_guide.md`.

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create env.local from env.example and fill secrets locally (never commit)
# Then run:
python server.py
```

## 📊 Monitoring

### Health Checks
- **Heartbeat:** `/api/heartbeat/?key=3yTgJUQnPjs4L`
- **Debug Info:** `/api/debug/?key=3yTgJUQnPjs4L`

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
├── static/                # Frontend build files
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
# Check environment variables
curl "https://web-production-1f4a3.up.railway.app/api/debug/?key=3yTgJUQnPjs4L"

# Check server health
curl "https://web-production-1f4a3.up.railway.app/api/heartbeat/?key=3yTgJUQnPjs4L"
```

## Notes

- If you restore to a fresh Supabase project, run `database_schema.sql` first.
- Keep secrets in Railway/Supabase env vars (not in `credentials.py`).
