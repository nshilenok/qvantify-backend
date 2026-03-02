# Backlog

| # | Project | Default | Item |
|---|---------|---------|------|
| 1 | `swipking3` | `cta_restart = "Restart"` | Success screen shows a Restart button after interview completion. Should not be shown for this research project — needs to be cleared. |
| 2 | `all` | `cta_restart` (repurposed) | Introduce a dedicated `success_cta` column in `projects` table for the success screen button label. Default value: empty string (no button shown). Wire up `SuccessScreen.tsx`, `ProjectConfig` type, and `GET /api/project/` query to use the new column instead of `cta_restart`. |
| 3 | `all` | n/a | ~~**FIXED** — Topic switch dropped conversation history: `provideInitialResponse` was building an empty LLM context (system-only) on topic change. Fixed by replacing manual `history = []` + append with `buildModelMessages()`, which returns the full user/assistant history. Regression test added.~~ |
