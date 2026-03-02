# Interview UI Constraints

- Interview screens must only render elements backed by project strings: question title, question text, input field, reply button, mic button, abort button, and progress bar.
- Do not add project name headers, question counters, extra labels, frames, or shadows.

# Deployment Governance (Strict)

- Never promote, merge, or push changes to `main` without explicit confirmation from the user in the current conversation.
- Default release path is: validate on `staging` first, then wait for user approval, then promote to `main`/production.
