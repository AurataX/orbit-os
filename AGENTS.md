# AGENTS.md — ORBIT-OS

Read this first. It is the shared brief for any AI agent or new contributor.

## What this project is
**ORBIT-OS** is an Operating Systems **lab project**: a Python simulator of a heterogeneous machine (CPU + GPU + RAM + VRAM + storage) running four workload classes at once (interactive, AI/LLM, developer/compile, background). Resources are coupled: pressure in one cascades into another (RAM full -> swap -> disk queue -> CPU stalls; VRAM full -> GPU stalls). Every run is recorded so we can **checkpoint -> rewind -> change policy -> replay the identical workload -> compare**.

Core question: *how should an OS manage CPU/GPU/memory/storage together when workloads with conflicting needs share one machine?*

Classical algorithms are the foundation. Our research layer adds workload-aware CPU/GPU placement, cross-resource interference analysis, and deterministic counterfactual replay.

## Why it exists (the grader's view)
The simulator is the graded OS work. The web dashboard is only the demo window. Never trade simulator correctness for UI polish. The owner must be able to explain every line in a viva.

## Docs map (read in this order)
1. `docs/system.md` — full brief: goals, scope, requirements, metrics
2. `docs/architecture.md` — modules, data flow, determinism, checkpoint/replay
3. `docs/design.md` — dashboard UI design system
4. `docs/task.md` — roadmap and current status (**update when you finish something**)
5. `docs/demo.md` — how to run and present (local + Cloudflare Tunnel)
5b. `docs/handoff-web.md` — **brief for whoever builds the API + Next.js dashboard + shell** (reference images in `docs/design/reference/`)
6. `docs/decisions.md` — why we chose what we chose
7. `docs/glossary.md` — OS terms used here
8. `docs/init/prompt.md` — the owner's original idea, verbatim

## Layout
```
backend/orbit/   simulator (stdlib only)
backend/tests/   pytest
backend/api.py   FastAPI (phase 4)
frontend/        Next.js (React + TS) dashboard, static export (phase 4)
docs/            everything above
```

## Rules
- **Simple and clean over clever.** Small modules, plain dataclasses, short functions, no abstractions until repetition demands them. No plugin layers, event buses or frameworks inside `orbit/`.
- **Determinism is sacred.** One seeded `random.Random`, integer ticks, no wall-clock, no set/dict-order dependence in the engine. Same seed + policy => identical event log (there is a test).
- **Engine state must stay deep-copyable** (checkpoint = `copy.deepcopy`). Do not store open files, threads, lambdas or generators on engine state.
- **Every policy is swappable** via a small interface (`pick()`, `quantum()`); do not hardcode policy names in the engine.
- **Test what you add.** Textbook examples for classical algorithms; property tests for determinism and "all work gets done".
- **Report honestly.** Never invent benchmark numbers; the comparison table must come from real runs.
- Name is ORBIT-OS (the original prompt also says NEXUS for the placement layer; keep NEXUS only as the placement-module nickname).

## Commands
```
cd backend
python3 -m venv .venv && .venv/bin/pip install pytest      # first time
PYTHONPATH=. .venv/bin/pytest -q                            # tests
python3 -m orbit.compare --seed 42                          # who did better
```

## Status
Phases 1–4 are complete. The stdlib engine has 79 tests (incl. locks and deadlock). The web layer adds a FastAPI session API, live Next.js dashboard, ORBIT shell, action log, and branch comparison with API tests. Run `make test` and see `docs/task.md` for open items.

Known limits (be honest about these): GPU is an Amdahl-style model (parallel fraction + speed factor), not instruction-level; deadlock is simulated with named locks (db/cache/log) and only appears when you inject the `deadlock-demo` storm (the seed workload has no locks); Optimal page replacement not implemented; Priority "knows" the class via task priority; Adaptive placement is a heuristic and does not beat always-GPU on every metric; the event log keeps only the newest 10000 events.
