# Interview UI Constraints

- Interview screens must only render elements backed by project strings: question title, question text, input field, reply button, mic button, abort button, and progress bar.
- Do not add project name headers, question counters, extra labels, frames, or shadows.

# Model Configuration Constraints

- gpt-5.4 and later OpenAI models require the Responses API (`/v1/responses`) when using function tools with `reasoning_effort`. They will reject `/v1/chat/completions` with a 400 error.
- When switching any project to gpt-5.4+, always set all three: `model`, `api = 'openai'`, and `openai_transport = 'responses'`.
- Code callers must pass `allow_responses=True` to the `LLM()` constructor for interview and analysis paths.

# Deployment Governance (Strict)

- Never promote, merge, or push changes to `main` without explicit confirmation from the user in the current conversation.
- Default release path is: validate on `staging` first, then wait for user approval, then promote to `main`/production.
