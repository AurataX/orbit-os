@AGENTS.md

## Claude-specific notes
- Plan first for anything touching more than two files; the approved master plan is summarised in `docs/task.md`.
- Keep `docs/task.md` current: tick items when done, add discovered work.
- Run `PYTHONPATH=. .venv/bin/pytest -q` from `backend/` before saying anything works.
- For dashboard work, follow `docs/design.md` and use the two checked-in Fluid UI references under `docs/design/reference/` for motion, materials, and accessibility.
- Do not commit or deploy unless asked. Do not expose a public tunnel without asking.
- The owner is a student presenting this in a lab: prefer explaining the "why" in short comments and answers.
