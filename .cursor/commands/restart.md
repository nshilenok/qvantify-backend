# Restart local environment (BE + FE)

Run these in separate terminals:

```bash
# Backend (Flask)
pkill -f "server.py" || true
PORT=5059 .venv/bin/python server.py
```

```bash
# Frontend (Results UI)
pkill -f "vite" || true
cd results-ui
npm run dev
```
