# Architecture

## Overview
```
 Browser dashboard (React)  <--WS/HTTP-->  FastAPI (api.py)  -->  orbit/ simulator (stdlib only)
        served as static files by FastAPI itself (one process)
```
Public access for demos: `cloudflared tunnel` -> `localhost:8000`.

## Simulator modules (`backend/orbit/`)
| Module | Responsibility | Status |
|---|---|---|
| `models.py` | `Task`, `Event`, workload class constants and priorities | done |
| `workload.py` | `generate(seed, n_tasks, span)` seeded scenario | done |
| `cpu_sched.py` | `Scheduler` base + FCFS, SJF, Priority, RR, MLFQ; `POLICIES` registry | done |
| `engine.py` | `Engine.step()/run()`: arrivals, dispatch, quantum, completion, event log | done |
| `metrics.py` | `summarize(engine)` -> comparable dict | done |
| `compare.py` | run all policies on the same seed, print table | done |
| `memory.py` | `Pager` (FIFO/LRU over an OrderedDict), `count_faults`, `VRAM` all-or-nothing pool | done |
| `storage.py` | `Disk` queue + head, FCFS/SSTF/SCAN, service = 1 + seek//25 ticks | done |
| (cascade) | no separate module: coupling lives in `engine.py` (`_page_fault`, `_get_vram`, `_release_vram`, `_watch_crisis`) | done |
| `deadlock.py` | `safe_sequence`, `request_resources` (Banker's), `find_cycle` (wait-for graph); standalone, not yet wired into the engine | done (wiring phase 3/5) |
| `gpu.py` | `GPU` (non-preemptive queue), `Bus` (one copy at a time), `split()` = Amdahl-style CPU/GPU division of a task | done |
| `placement.py` | NEXUS: `AlwaysCPU`, `AlwaysGPU`, `Adaptive` (finish-time estimates, reason logged) | done |
| `recorder.py` | `Recorder` (checkpoint every K ticks, `rewind`), `replay()` swaps CPU/page/disk/placement policies | done |
| `logfmt.py` | `dmesg` kernel-style log (subsystem, level, reason) and `ps` process table; CLI | done |

## Policy interface
A policy is a small object; the engine never knows policy names.
- CPU: `add(task)`, `pick() -> Task|None`, `quantum(task) -> int|None`
- Memory: `choose_victim(frames) -> page`
- Disk: `next_request(queue, head) -> request`
- Placement: `decide(task, machine_state) -> cpu|gpu|hybrid`

Registries (`POLICIES` etc.) map names to classes so the API and UI can list and select them.

## Engine tick (one step)
1. admit arrivals -> `sched.add`
2. disk tick -> finished I/O wakes blocked tasks -> `sched.wake` (no MLFQ demotion)
3. dispatch: pick a task; if it is an AI task and VRAM is full it parks in `vram_wait`; touch this tick's page, and on a fault submit a disk request and block (then pick another task)
4. execute 1 tick of work
5. completion (releases VRAM, grants waiters) or quantum expiry (`sched.requeue`, MLFQ demotes)
6. advance `now`, mark `crisis` if the disk queue reaches `CRISIS_QUEUE` (16)

Time advances only in `Engine.step()`.

## Determinism contract
- Single `random.Random(seed)` created in `workload.generate`; the engine itself uses no randomness.
- Integer ticks; ties broken by `(arrival, id)` everywhere.
- Test `test_deterministic_replay`: same inputs => equal `Event` lists.

## Checkpoint / replay
- Engine holds only plain data, so `copy.deepcopy(engine)` is a full checkpoint.
- `Recorder` stores `{tick: engine_copy}` every K ticks (K configurable) plus the append-only event log.
- Rewind: `engine = deepcopy(checkpoints[t])`. Replay: set a new policy object on the copy (policies carry their own ready-queue state, so the swap re-adds ready tasks to the new policy) and `run()`.
- Compare: metrics of the original run vs. the replayed run.

## Web session and API

`backend/api.py` serves the routes in [the web handoff](handoff-web.md#4-api-contract-implement-in-backendapipy). Each session serializes engine mutations and holds an active branch plus its earlier branches. `backend/session.py` uses the engine and recorder for stepping, checkpoints and policy swaps. When a recorded branch is replayed, previously recorded live changes are reapplied at the same ticks. Policies at the checkpoint are carried forward, and new selections on the fork govern the replay. If the changed policy makes an action invalid (for example, a task has already finished), the action log records the skip.

One WebSocket connection controls playback, with any other connections receiving frames. Revisions let a client merge HTTP and WebSocket data without rolling the display back. Each socket tracks its own absolute event cursor. HTTP clients can use `since` for independent reads or omit it to use the session cursor. Read-only shell commands use the same engine state as the dashboard.

Next.js exports static files to `frontend/out`. The dashboard renders compact frames by default and asks for ownership and device details while Resources is open. The lane percentages describe observed frames and the CPU utilization card reports measured busy ticks.

## Deployment

Run `make install`, `make build`, and `make serve` from the project root. For separate development servers use `make dev-api` and `make dev-ui`. See [the demo runbook](demo.md) for token-protected access and the tunnel.

## Testing
`backend/tests/`: textbook scheduler cases, "all work done" invariant, determinism, (later) Banker's safe/unsafe, page-replacement textbook strings (e.g. Belady's anomaly for FIFO), replay equality up to checkpoint.
