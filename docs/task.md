# Tasks & status

Legend: [x] done, [ ] todo. Update as you go.

## Phase 0 — Setup
- [x] Read original idea (`docs/init/prompt.md`) and agree plan
- [x] Folder layout, `.gitignore`, venv + pytest
- [x] Project docs (AGENTS, CLAUDE, README, system, architecture, design, task, demo, decisions, glossary)

## Phase 1 — CPU engine (DONE)
- [x] `models.py`, `workload.py` (seeded)
- [x] Schedulers: FCFS, SJF, Priority, RR, MLFQ
- [x] `engine.py` tick loop + event log
- [x] `metrics.py`, `compare.py` CLI
- [x] Tests: textbook FCFS, SJF<FCFS wait, RR preempts, all work done, determinism, same-seed workload (6 passing)

## Phase 2 — Memory, storage, cascade, deadlock (DONE, 22 tests total)
- [x] Tasks carry page-reference strings (85% hot-set locality) and `vram_need`
- [x] `memory.py`: Pager FIFO/LRU, VRAM pool; tests: Belady's anomaly (9 vs 10), LRU textbook string (12 vs 15 faults)
- [x] `storage.py`: Disk + FCFS/SSTF/SCAN; textbook head movement 640 / 236 / 299
- [x] Blocked state: fault -> disk request -> block -> wake (MLFQ no longer demotes on wake: `requeue` vs `wake`)
- [x] Cascade in `engine.py`: page faults -> disk queue -> CPU idle; VRAM full -> AI task waits (GPU stall)
- [x] `deadlock.py`: Banker's (textbook safe/unsafe cases) + wait-for-graph cycle detection
- [x] Metrics: faults, disk busy, head movement, GPU stall, crisis tick, interactive p95 response AND turnaround
- [x] Crisis marker: disk queue >= 16 (normal peak ~10)
- [ ] Optimal page replacement as a baseline (needs future knowledge; refs are already known per task)
- [ ] Wire deadlock detection into the engine (needs tasks that hold-and-wait on several resources)
- [ ] Starvation metric for background tasks

## Phase 3 — GPU, placement, kernel log, record / rewind / replay (DONE, 32 tests)
- [x] `gpu.py`: GPU device, transfer bus, parallel-fraction split (Amdahl); VRAM held across CPU -> bus -> GPU
- [x] `placement.py` (NEXUS): AlwaysCPU / AlwaysGPU / Adaptive with estimates written to the log
- [x] Kernel log: every event has subsystem, level and a reason; `python -m orbit.logfmt` (dmesg) and `--ps` (process table)
- [x] `recorder.py`: periodic checkpoints (deepcopy), rewind, `replay()` swapping cpu/page/disk/placement
- [x] Tests: same-policy replay == original; rewound log == recorded past; original untouched; what-if shares history
- [x] `python -m orbit.compare --rewind ...`: crisis -> rewind -> swap -> replay (seed 42: 999 -> 421 ticks, avg wait 401 -> 128)
- [x] Safety cap `MAX_TICKS` for thrash livelocks (FIFO + 30 frames never finishes); `unfinished` metric
- [ ] Tune Adaptive estimates (always-GPU still wins interactive p95 on seed 42)

## Phase 3b — Live data and live actions (DONE, 48 tests total)
- [x] `snapshot(detail=True)`: RAM frame owners, VRAM held, bus task, disk head/current/queue
- [x] `inject(kind, n)` and `storm(name)` (ai-burst, compile-storm, swap-storm), deterministic
- [x] `resize(ram, vram)`: shrinking RAM evicts; VRAM too small => tasks fall back to the CPU (found by a failing test: they starved forever)
- [x] `kill(pid)` from any state (frees RAM and VRAM, in-flight disk I/O ignored); `boost(pid, priority)`
- [x] Log retention: newest 10000 events, `log_base` keeps absolute indexes; new `killed` metric and state

## Phase 4 — API and dashboard (DONE)
- [x] FastAPI in-memory sessions, token-protected writes, WebSocket playback, checkpoint/fork/replay, and seeded comparison
- [x] Next.js dashboard, static export served from `frontend/out` by FastAPI
- [x] ORBIT shell, filterable kernel log, PID event chains, and server-side "What you did" log
- [x] Machine/cascade, gauges, queues, event feed, timeline, sampled resource lanes, memory ownership, and task inspector
- [x] Live stress, resize, priority, and termination controls backed by the engine
- [x] Branch delta comparison, sortable policy tables, challenge mode, JSON and CSV export
- [x] Light/dark, reduced motion, and phone-width layout
- [x] API tests and local Chromium demo verification
- [ ] Verify the public tunnel on a physical phone when hosting the demo

## Phase 5 — Placement and polish
- [ ] Interference analysis report (which class slowed which, per resource)
- [ ] Multi-core CPU option
- [ ] Wire Banker's / wait-for graph into the engine
- [ ] `Dockerfile` (optional Cloud Run)
- [ ] Demo script rehearsed (`docs/demo.md`)
- [ ] Viva notes: one page per module

## Open questions for the owner
- Does the course give a required algorithm list or marking scheme?
- Single-core or multi-core CPU in the demo?
- Report/PPT needed alongside the code?
- Default workload is overloaded (~99.5% util, makespan 562); spread arrivals for a moderate-load scenario?

## Known notes
- `prompt.md` names the placement layer NEXUS; the project is ORBIT-OS.
