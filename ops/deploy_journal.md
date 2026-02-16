# Deploy Journal (Append-Only, No Redaction)

This file is mandatory for every staging/production deploy cycle.

Rules:
- Append-only: never rewrite previous entries.
- Keep raw command outputs and errors as-is (no sanitizing/no shortening).
- Include exact date/time and timezone for each step.
- Include what was tried, what failed, and what fixed it.

---

## 2026-02-16 (UTC) - Staging deploy incident and recovery

### Context
- Branch: `staging`
- Commit under test: `41cac0660e4458ce68906cce9816b40d79295ba9`
- Goal: deploy and validate interview flow on staging before production promotion.

### Timeline and raw outputs

#### 2026-02-16 12:15:16 GMT - staging domain blocked by protection for generic curl
Command:
```bash
curl -sSI https://staging.app.qvantify.com/api/health
```
Raw output:
```text
HTTP/2 401
cache-control: no-store, max-age=0
content-type: text/html; charset=utf-8
date: Mon, 16 Feb 2026 12:15:16 GMT
server: Vercel
set-cookie: _vercel_sso_nonce=5S0u3kWIeRm1tM25WtCvdrWR; Max-Age=3600; Path=/; Secure; HttpOnly; SameSite=Lax
strict-transport-security: max-age=63072000
x-frame-options: DENY
x-vercel-id: arn1::gbfzm-1771244116082-0f2d9c9fbc3d
content-length: 14516
```

#### 2026-02-16 ~12:15 UTC - Railway CLI auth failure in this shell
Command:
```bash
railway status --json
```
Raw output:
```text
Unable to parse config file, regenerating
Unauthorized. Please login with `railway login`
```

#### 2026-02-16 ~12:15 UTC - Vercel MCP bypass conflict failures
Raw output:
```text
Failed to create shareable URL: Failed to create protection bypass: 409 Conflict
```

#### 2026-02-16 ~12:16 UTC - Incorrect vercel curl usage (full URL)
Command:
```bash
vercel curl https://staging.app.qvantify.com/api/health
```
Raw output:
```text
Error: The <path> argument must be a relative API path (e.g., '/' or '/api/hello'), not a full URL.
To target a specific deployment within the currently linked project, use the --deployment <id|url> flag.
```

#### 2026-02-16 ~12:17 UTC - Incorrect vercel curl flag
Command:
```bash
vercel curl --yes ...
```
Raw output:
```text
Error: unknown or unexpected option: --yes
```

#### 2026-02-16 12:15:12-12:15:23 UTC - Bad staging deployment characteristics (built from repo root)
Deployment: `dpl_7Bg9qgfGvz7NPc1SPc8CD2nemoCq`

Raw build log evidence:
```text
Cloning github.com/nshilenok/qvantify-backend (Branch: staging, Commit: 41cac06)
Running "vercel build"
WARN! Due to `builds` existing in your configuration file, the Build and Development Settings defined in your Project Settings will not apply.
Build Completed in /vercel/output [817ms]
```

Route probes on this deployment returned 404:
```text
ROOT 404
INTERVIEW_SLASH 404
```

#### 2026-02-16 ~12:26 UTC - Recovery: redeploy explicitly from frontend directory
Command:
```bash
vercel link --cwd frontend --project qvantify-frontend --scope nikita-shilenoks-projects --yes
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set qvantify-frontend-l7anqb2zc-nikita-shilenoks-projects.vercel.app staging.app.qvantify.com --scope nikita-shilenoks-projects
```
Raw output (key lines):
```text
Deploying nikita-shilenoks-projects/qvantify-frontend
Preview: https://qvantify-frontend-l7anqb2zc-nikita-shilenoks-projects.vercel.app
Build: Route (app)
Build: ┌ ○ /
Build: ├ ○ /_not-found
Build: ├ ƒ /api/[...path]
Build: ├ ○ /interview
Build: ├ ○ /results
...
Success! https://staging.app.qvantify.com now points to https://qvantify-frontend-l7anqb2zc-nikita-shilenoks-projects.vercel.app
```

#### 2026-02-16 ~12:27-12:28 UTC - Recovery validation succeeded
Command:
```bash
python3 scripts/verify_domain_aliases.py
```
Raw output:
```text
Alias verification passed:
- app.qvantify.com -> https://qvantify-frontend-mu9wyvmzs-nikita-shilenoks-projects.vercel.app (project=qvantify-frontend, target=production)
- staging.app.qvantify.com -> https://qvantify-frontend-l7anqb2zc-nikita-shilenoks-projects.vercel.app (project=qvantify-frontend, target=preview)
```

Command:
```bash
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/api/health' --deployment https://qvantify-frontend-l7anqb2zc-nikita-shilenoks-projects.vercel.app -- --include --silent --show-error
```
Raw output (key lines):
```text
HTTP/2 200
x-qvantify-proxy-base: https://qvantify-staging.up.railway.app
{"db_config_error":null,"db_configured":true,"db_required":false,"ok":true}
```

Command:
```bash
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/interview?interview=swipking2&external_id=stg_smoke_001' --deployment https://qvantify-frontend-l7anqb2zc-nikita-shilenoks-projects.vercel.app -- --silent --show-error --location --output /dev/null --write-out 'SWIPKING2 %{http_code}\n'
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/interview?interview=d0aaae3f-b133-4099-a6fb-9509ed750a24&external_id=stg_smoke_002' --deployment https://qvantify-frontend-l7anqb2zc-nikita-shilenoks-projects.vercel.app -- --silent --show-error --location --output /dev/null --write-out 'SWEEPKING %{http_code}\n'
vercel curl --cwd frontend --scope nikita-shilenoks-projects '/interview?interview=sample_game_funnel_2026_01_14&external_id=stg_smoke_003' --deployment https://qvantify-frontend-l7anqb2zc-nikita-shilenoks-projects.vercel.app -- --silent --show-error --location --output /dev/null --write-out 'SAMPLE %{http_code}\n'
```
Raw output:
```text
SWIPKING2 200
SWEEPKING 200
SAMPLE 200
```

### Root cause summary
- A staging deployment existed that was effectively built from the wrong context (repo root behavior with `builds` warning), causing interview routes to fail.
- Alias/ready checks alone were insufficient; runtime checks were required.
- Generic `curl` to protected staging domain is misleading due Vercel auth (401) unless using bypass-aware tooling.

### Hardening done in code
- `scripts/verify_domain_aliases.py` now verifies runtime:
  - `/interview?...` returns 200 via `vercel curl`
  - `/api/health` returns 200
  - header `x-qvantify-proxy-base` matches expected backend per domain
- This turns previous silent failure mode into a fast failing pre-promotion check.

### 2026-02-16 (UTC) - Post-commit validation caught a fresh bad auto-deploy

After commit `240db903448b89bb3db6ddd7acee4e76bfeb8130` reached `staging`, Vercel auto-created:
- `dpl_tagGcr2nJ5N4ZW64heizWvZMipND`
- url: `qvantify-frontend-6bf4obicf-nikita-shilenoks-projects.vercel.app`

The hardened verifier immediately failed with raw error:
```text
ERROR: Interview route check failed. domain=staging.app.qvantify.com deployment=https://qvantify-frontend-6bf4obicf-nikita-shilenoks-projects.vercel.app path=/interview?interview=swipking2&external_id=staging_smoke_probe status=404
```

`release_safety_check.py` also failed (by design) because alias runtime validation failed:
```text
ERROR: Domain alias check failed.
ERROR: Interview route check failed. domain=staging.app.qvantify.com deployment=https://qvantify-frontend-6bf4obicf-nikita-shilenoks-projects.vercel.app path=/interview?interview=swipking2&external_id=staging_smoke_probe status=404

Branch divergence: {"main_ahead": 9, "staging_ahead": 2}
```

Recovery actions:
```bash
vercel deploy --cwd frontend --local-config frontend/vercel.json --target=preview --yes
vercel alias set qvantify-frontend-ma9rgvezt-nikita-shilenoks-projects.vercel.app staging.app.qvantify.com --scope nikita-shilenoks-projects
python3 scripts/verify_domain_aliases.py
python3 scripts/release_safety_check.py --repo-path . --allow-divergence
```

Recovery evidence (raw):
```text
Alias verification passed:
- app.qvantify.com -> https://qvantify-frontend-mu9wyvmzs-nikita-shilenoks-projects.vercel.app (project=qvantify-frontend, target=production)
- staging.app.qvantify.com -> https://qvantify-frontend-ma9rgvezt-nikita-shilenoks-projects.vercel.app (project=qvantify-frontend, target=preview)

Release safety check passed.
```

Current staging deploy after recovery:
- `dpl_GjtBFHbBFDvDAD3eHKR549UKgMye`
- `https://qvantify-frontend-ma9rgvezt-nikita-shilenoks-projects.vercel.app`
- alias: `staging.app.qvantify.com`

### 2026-02-16 (UTC) - Auto-preview takeover observed again after next push

After pushing next commit to `staging`, `staging.app.qvantify.com` was reassigned to:
- `dpl_HMpbmSinp6ni8gE7nXvuBavM63hk`
- `https://qvantify-frontend-p4pv7eify-nikita-shilenoks-projects.vercel.app`

Raw inspect evidence:
```text
"url": "qvantify-frontend-p4pv7eify-nikita-shilenoks-projects.vercel.app",
"aliases": [
  "staging.app.qvantify.com",
  "qvantify-frontend-git-staging-nikita-shilenoks-projects.vercel.app"
]
...
"vercelConfig": {
  "builds": [
    { "src": "api/[...path].cjs", "use": "@vercel/node" }
  ]
}
```

This deployment used root API-only config and is not a valid interview frontend deployment.

Promotion guard check now fails fast (expected behavior):
```text
ERROR: Source staging deployment failed runtime validation: path=/interview?interview=swipking2&external_id=promotion_source_probe status=404 deployment=https://qvantify-frontend-p4pv7eify-nikita-shilenoks-projects.vercel.app
```

Hardening actions applied:
- `scripts/promote_frontend_from_staging.py` now validates source staging runtime (`/interview` + `/api/health` + `x-qvantify-proxy-base`) before promotion.
- Root `vercel.json` now includes:
```json
"git": { "deploymentEnabled": false }
```
to stop Git auto-deploy preview takeovers from root context.

