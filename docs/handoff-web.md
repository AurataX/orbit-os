# Handoff: build the ORBIT-OS web part (API + dashboard + shell)

For: Codex (or any coding agent). Read `AGENTS.md` first, then this file. The simulator (`backend/orbit/`) is **finished and tested (48 tests)**. Your job is the web layer on top of it. Do not rewrite the simulator.

## 1. Goal in one paragraph
Build a live, interactive dashboard where a presenter runs a seeded workload on a simulated CPU + GPU + RAM + VRAM + disk machine, watches resources being shared and cascading into a crisis, types OS-style commands (`top`, `free`, `dmesg`...) in an in-page terminal, rewinds to a checkpoint, swaps policies, replays the same workload and compares who did better. Everything the user does is shown in a "What you did" log. It must run as **one Python process** and be shareable with a Cloudflare Tunnel.

## 2. Scope
| You build | Path |
|---|---|
| FastAPI layer (thin; calls `orbit`, no simulation logic) | `backend/api.py`, `backend/shell.py`, `backend/requirements.txt`, `backend/tests/test_api.py` |
| Next.js dashboard (TypeScript, App Router, **static export**) | `frontend/` |
| Serve `frontend/out` from FastAPI | `backend/api.py` |
| Run/dev scripts | `Makefile` |

Not yours: `backend/orbit/*`. If you truly need a change there, make the smallest one, add a test, run `PYTHONPATH=. .venv/bin/pytest -q` (must stay green). Section 7 documents the live data and live actions that already exist in the engine.

## 3. What the simulator already gives you (verified API)
```python
from orbit.compare import build_engine, compare, what_if, DEFAULT, RAM_FRAMES, VRAM_FRAMES
from orbit.workload import generate                   # generate(seed, n_tasks=40, span=120) -> list[Task]
from orbit.recorder import Recorder, replay           # Recorder(engine, every=10); .run(until=None) .save() -> tick
                                                      # .rewind(tick) -> NEW Engine copy; replay(engine, cpu=,page=,disk=,place=)
from orbit.metrics import summarize                   # summarize(engine) -> dict of metrics
from orbit.logfmt import dmesg, ps, format_event, SUBSYSTEM, LEVEL
from orbit.cpu_sched import POLICIES                  # {"FCFS","SJF","Priority","RR","MLFQ"}
from orbit.memory import PAGE_POLICIES                # {"FIFO","LRU"}
from orbit.storage import DISK_POLICIES               # {"FCFS","SSTF","SCAN"}
from orbit.placement import PLACERS                   # {"CPU","GPU","ADAPTIVE"}
```
Engine (`engine = build_engine(tasks, cpu="MLFQ", page="LRU", disk="SCAN", place="ADAPTIVE", ram=60, vram=16)`):
- `engine.step()` advances one tick. `engine.run(until=None)` runs to completion or `MAX_TICKS` (6000). `engine.done`, `engine.timed_out`, `engine.now`, `engine.crisis_at` (tick or None).
- `engine.snapshot()` -> `{tick, running, ready, blocked, vram_wait, ram_used, ram_total, vram_used, vram_total, disk_queue, gpu_queue, gpu_running, bus_busy}`.
- `engine.state_of(task)` -> `new | ready | running | blocked:disk | wait:vram | xfer | gpu | done`.
- `engine.tasks` (list of `Task`: `id, kind, arrival, burst, priority, remaining, placement, gpu_work, parallel, vram_need, first_run, finish`), `engine.log` (list of `Event(tick, kind, task_id, info)`, append-only).
- Event kinds: `arrive place run preempt block wake xfer gpu_queue gpu_run finish vram_wait vram_grant crisis policy inject resize kill boost`.
- Task states (`state_of`): `new ready running blocked:disk wait:vram xfer gpu done killed`. `SUBSYSTEM[kind]` -> `sched|nexus|mm|disk|vram|bus|gpu|kernel`; `LEVEL.get(kind,"INFO")` -> `INFO|WARN|CRIT`.
- Workload classes: `interactive, ai, dev, background`.

Quick check the layer works: `cd backend && python3 -m orbit.compare --seed 42 --rewind cpu=MLFQ page=LRU disk=SCAN`.

## 4. API contract (implement in `backend/api.py`)
FastAPI, JSON, in-memory sessions (dict by id). All reads open; **all mutating routes require header `X-Orbit-Token`** equal to env `ORBIT_TOKEN` when that env var is set (needed because the app is exposed through a public tunnel). Add CORS for `http://localhost:3000` in dev only.

| Method + route | Body / query | Returns |
|---|---|---|
| `GET /api/options` | | `{cpu:[..], page:[..], disk:[..], place:[..], defaults:{..}, ram:60, vram:16}` from the registries above |
| `POST /api/sessions` | `{seed, n_tasks?, cpu?, page?, disk?, place?, ram?, vram?}` | `{id, frame}` |
| `GET /api/sessions/{id}/frame` | | current **frame** (below) |
| `POST /api/sessions/{id}/step` | `{n}` (1..500) | frame (events since last frame included) |
| `WS /api/sessions/{id}/stream` | client sends `{"type":"play","speed":N}` (ticks/sec 1..200), `{"type":"pause"}` | server pushes a frame per batch; stops at `done`/`timed_out` |
| `POST /api/sessions/{id}/checkpoint` | | `{tick}` (uses `Recorder.save()`) |
| `POST /api/sessions/{id}/rewind` | `{tick}` | new active branch; frame. Old branch stays readable |
| `POST /api/sessions/{id}/replay` | `{cpu?,page?,disk?,place?}` | frame (applies `orbit.recorder.replay` to the active branch) |
| `POST /api/sessions/{id}/finish` | | runs active branch to the end; returns `{summary}` |
| `GET /api/sessions/{id}/branches` | | `[{id,label,rewound_to,policies,summary}]` for before/after compare |
| `GET /api/sessions/{id}/dmesg` | `?grep=&tail=` | `{lines:[str]}` (use `orbit.logfmt.dmesg`) |
| `GET /api/sessions/{id}/ps` | | `{rows:[{pid,kind,state,placement,priority,burst,left}]}` (structured; the terminal formats it) |
| `POST /api/sessions/{id}/shell` | `{line}` | `{output:[str], frame?}` (section 6) |
| `GET /api/sessions/{id}/actions` | | action log (below) |
| `GET /api/sessions/{id}/export` | | JSON: config, actions, structured log, summaries |
| `GET /api/compare` | `?seed=&tasks=` | `compare(seed, tasks)` as-is: `{cpu:[rows], page:[rows], disk:[rows], place:[rows]}` |
| `GET /api/whatif` | `?seed=&base=cpu:FCFS,page:FIFO,disk:FCFS&alt=cpu:MLFQ,page:LRU,disk:SCAN` | `{crisis_at, rewound_to, original: summary, replayed: summary, policy_log:[str]}` or `404` if no crisis |

Errors: `400` for unknown policy/command with a readable `detail`; never a stack trace.

### Frame (what the UI renders every update)
```json
{
  "snapshot": { "tick":48, "running":7, "ready":5, "blocked":4, "vram_wait":1, "ram_used":60, "ram_total":60,
                "vram_used":12, "vram_total":16, "disk_queue":18, "gpu_queue":1, "gpu_running":6, "bus_busy":true },
  "status": { "done":false, "timed_out":false, "crisis_at":48, "policies":{"cpu":"MLFQ","page":"LRU","disk":"SCAN","place":"ADAPTIVE"},
              "branch":"main" },
  "tasks": [ { "id":7, "kind":"interactive", "state":"running", "placement":"cpu", "priority":0, "burst":4, "left":2 } ],
  "events": [ { "tick":48, "kind":"crisis", "subsystem":"kernel", "level":"CRIT", "pid":null, "task_kind":null,
                "info":"disk queue=18 >= 16", "text":"[   48] kernel CRIT crisis ..." } ],
  "summary": null
}
```
`events` = only events produced since the previous frame of that session (track an index). `summary` is filled by `summarize()` once `done` or `timed_out`.

### Action log
Server-side list per session. Every mutating call appends `{tick, action, params, effect}`. `effect` is a short measured string, e.g. `"disk queue 18 -> 6 after 20 ticks"`; compute it by comparing `snapshot` before/after (queue length, faults, ready count) at the next frame, or leave `null` until measured. Rewind/replay actions must be recorded too.

## 5. Frontend (Next.js in `frontend/`)
Follow `docs/design.md` for tokens, layout, motion and accessibility. Visual reference: `docs/design/reference/havenmed-dashboard.png` (borrow layout language: left sidebar, soft pastel rounded cards, gauge, smooth line chart, dark-mode toggle; **not** its content or branding). Motion/material rules: `docs/design/reference/fluid-master-brief.md` and `fluid-visual-direction.md`; apply the motion contract, do not install animation libraries unless needed (CSS first; Motion only if layout/gesture continuity is required).

Stack: Next.js App Router + TypeScript, `output: 'export'` in `next.config`, `NEXT_PUBLIC_API` base URL (empty in production = same origin). Charts: a small SVG chart or one light library; no heavy dashboards kit. Fonts: Inter.

### Screens
1. **Dashboard (Machine)**: top bar (seed, 4 policy pickers, Run/Pause/Step, speed, Checkpoint, Rewind, Compare). Stat cards: Tick, Tasks done, CPU util, Crisis. Hero card "Machine" showing CPU, GPU, Bus, RAM, VRAM, Disk as linked blocks with live gauges/queues; the cascade (RAM pressure -> disk -> CPU idle, VRAM full -> GPU stall) highlights as links when thresholds are crossed.
2. **Resource sharing**: shared time axis lanes for CPU, GPU, Bus, Disk coloured by workload class (build client-side from frames); "who used what" share bars per resource; RAM/VRAM ownership map (see section 7 for data). Click a task -> **Task inspector** (PCB card: class, state, placement and the NEXUS reason from its `place` event, burst/left, its events).
3. **Terminal + kernel log** (drawer docked bottom or right): ORBIT shell (section 6), `dmesg`-style live log with level colouring and filter chips by subsystem (sched, nexus, mm, disk, vram, bus, gpu, kernel); "Why?" button on an event highlights the cause chain using neighbouring events of the same pid (block -> wake, place -> xfer -> gpu_queue -> gpu_run -> finish).
4. **Timeline**: scrubber under the main chart; checkpoints as dots, crisis as a coral flag; dragging picks a tick, **Rewind here** calls rewind, **Replay with...** opens the policy picker.
5. **Compare**: `GET /api/compare` tables per dimension, best value per column highlighted, sortable; "Before vs after" panel from branches / `whatif` with a delta column (e.g. makespan 999 -> 421, avg wait 401 -> 128).
6. **What you did** (right rail, visible on every screen): the action log, newest first, with the measured effect.
7. **Challenge mode** (stretch): pick the policy you think wins, run `/api/compare`, reveal result.

### Quality rules
- Do not re-render the whole tree per tick: keep frames in a ref/store, update only changed cards; throttle chart updates to animation frames.
- Late responses must not overwrite newer intent (ignore stale responses by request id).
- Light and dark theme, `prefers-reduced-motion` respected, keyboard operable controls, visible focus, contrast >= 4.5:1, colour is never the only signal (crisis has an icon + text).
- Workload colours are fixed everywhere: interactive = violet, AI = blue, dev = olive/butter, background = grey. Status: ok = mint, warn = amber, crisis = coral.
- Honest empty/pending/error states (backend down, run finished, run timed out = "thrashing, stopped at 6000 ticks", unfinished tasks).
- Every card shows real simulator data. No fake revenue/patients/greeting widgets.

## 6. The ORBIT shell (`backend/shell.py`, rendered in the terminal drawer)
Pure function `run_command(session, line) -> list[str]`; no side effects beyond the session. Unknown command -> `orbit: command not found: x (try help)`.

| Command | Does | Backed by |
|---|---|---|
| `help` | list commands | static |
| `new --seed 42 --cpu MLFQ --page LRU --disk SCAN --place ADAPTIVE [--ram N --vram N]` | new session state | `build_engine` |
| `step [n]` | advance n ticks (default 1) | `engine.step()` |
| `run [until]` | run to end or tick | `Recorder.run` |
| `top` / `ps` | process table at current tick | `ps()` / `state_of` |
| `free` | RAM and VRAM used/total, faults so far | `snapshot`, `pager.faults` |
| `iostat` | disk queue, head position, busy ticks, head movement | `snapshot`, `disk.*` |
| `gpustat` | GPU running pid, GPU queue, bus busy, GPU/bus busy ticks | `snapshot`, `gpu.*`, `bus.*` |
| `dmesg [grep] [tail]` | kernel log | `dmesg()` |
| `checkpoint` | save checkpoint, print tick | `Recorder.save` |
| `rewind <tick>` | fork a branch at nearest checkpoint <= tick | `Recorder.rewind` |
| `set cpu=X page=Y disk=Z place=W` | swap policies on the active branch (alias of replay) | `replay()` |
| `compare` | policy tables for the session seed | `compare()` |
| `whatif cpu=MLFQ page=LRU disk=SCAN` | crisis -> rewind -> swap -> replay summary | `what_if()` |
| `clear` | clear terminal | client |
Format `top`, `free`, `iostat`, `gpustat` like their Unix namesakes (fixed-width, header row). Example:
```
orbit> free
              total   used   free   faults
RAM(frames)      60     60      0      296
VRAM(frames)     16     12      4        -
```
Commands issued in the terminal go through the same session code as the buttons, so they appear in the action log and update the dashboard.

## 7. Live data and live actions (BUILT, 48 tests; use them, do not mock)
All of this exists in `backend/orbit/engine.py` and is tested in `backend/tests/test_live_actions.py`.

**Detailed snapshot**: `engine.snapshot(detail=True)` = the compact keys plus
`ram_frames: [[task_id, page], ...]` (oldest first = next FIFO victim), `vram_held: {task_id: frames}` (JSON turns keys into strings), `bus_task: id|null`, `disk: {head, current:{task,track}|null, queue:[{task,track}]}`. Use it for the RAM/VRAM ownership map, the disk-head view and the bus lane. It is heavier than the compact form: expose it as `GET /api/sessions/{id}/frame?detail=1` and request it only while the Resource-sharing screen is open.

**Live actions** (call between ticks; each raises `ValueError` with a readable message on bad input -> return `400`):
| Method | Engine call | Notes |
|---|---|---|
| `POST /api/sessions/{id}/inject` `{kind, n}` | `engine.inject(kind, n)` | kind in `interactive|ai|dev|background`, n 1..50; tasks arrive at the current tick; returns new pids |
| `POST /api/sessions/{id}/storm` `{name}` | `engine.storm(name)` | `ai-burst` (4 AI), `compile-storm` (8 dev), `swap-storm` (6 dev + 6 background, RAM pressure) |
| `POST /api/sessions/{id}/resize` `{ram?, vram?}` | `engine.resize(ram=, vram=)` | shrinking RAM evicts pages at once; VRAM held is never taken back; tasks whose VRAM need can never fit fall back to the CPU (logged) |
| `POST /api/sessions/{id}/kill` `{pid}` | `engine.kill(pid)` | works in any state; frees its RAM pages and VRAM; counted as `killed`, not completed |
| `POST /api/sessions/{id}/boost` `{pid, priority}` | `engine.boost(pid, priority)` | lower number = more important; only the Priority scheduler reads it (the log says so; show that hint in the UI) |

Each of these writes an event (`inject`, `resize`, `kill`, `boost`) into the kernel log AND must be appended to the action log. Machine-size sliders: RAM 10..200 frames, VRAM 0..64.

**Log retention**: `engine.log` keeps the newest `engine.log_limit` (10000) events; `engine.log_base` = how many older events were dropped. Absolute event index = `log_base + position`; use that for the "events since last frame" cursor so trimming never breaks streaming.

Dropped from the earlier plan: nothing is mocked any more, so no `adapter.ts` is needed.

## 8. Run, build, deploy
```
# dev
make install
make dev-api
make dev-ui                             # second terminal, browser at http://localhost:3000
# demo (one process)
make build                              # -> frontend/out
orbit_demo_token="$(openssl rand -hex 24)"
printf '%s' "$orbit_demo_token" | pbcopy # macOS, paste into dashboard Settings
ORBIT_TOKEN="$orbit_demo_token" make serve
cloudflared tunnel --url http://localhost:8000 # second terminal, see demo.md
```
`requirements.txt`: `fastapi`, `uvicorn[standard]`, plus `httpx` for tests. Do not add other backend dependencies without a reason. Do not start a public tunnel yourself.

## 9. Acceptance criteria (definition of done)
1. `pytest` green (existing 48 + your `test_api.py`: create session, step, frame shape, checkpoint, rewind, replay, branches, dmesg, shell commands, compare, token enforcement on a mutating route, unknown policy -> 400).
2. Start a session with seed 42, run it live at 20 ticks/s: gauges and queues move, crisis flag appears (seed 42, `FCFS/FIFO/FCFS/ADAPTIVE` crisis at tick 48).
3. In the terminal: `top`, `free`, `iostat`, `gpustat`, `dmesg nexus 10` print sensible output and match the dashboard.
4. Rewind to tick ~40, `set cpu=MLFQ page=LRU disk=SCAN`, finish: Compare shows before vs after (expect makespan about 999 -> 421; numbers come from the API, never hard-coded).
5. "What you did" shows every action above with tick and effect.
6. `npm run build` produces a static export that FastAPI serves at `/`; works through the tunnel on a phone-width screen (no horizontal scroll), light and dark.
7. A thrashing config (`cpu=FCFS page=FIFO disk=FCFS place=CPU`, `ram=30`) shows the honest "stopped at 6000 ticks, N unfinished" state instead of hanging.
8. No console errors; no unhandled promise rejections; backend errors surface as readable messages.

## 10. Do not
- Reimplement scheduling/paging/disk logic in the API or UI.
- Hard-code metrics, tables or "winners"; always render what the API returns.
- Change policy names or metric keys (the UI reads them as-is: `avg_wait, inter_p95_resp, inter_p95_turn, makespan, unfinished, killed, cpu_util_%, page_faults, disk_busy, head_moved, gpu_stall, gpu_busy, bus_busy, crisis_at`).
- Claim real-OS or real-GPU measurements anywhere in the UI. Label it "simulated".
- Add auth systems, databases or accounts. In-memory sessions only.

## 11. Suggested order
1. `api.py` skeleton + `/options`, sessions, frame, step, compare + tests.
2. Dashboard shell + stat cards + Machine card with live frames (polling `step` first, WS after).
3. Terminal + `shell.py` + dmesg panel.
4. Checkpoint/rewind/replay + timeline + branches + Compare page + action log.
5. Resource-sharing lanes, ownership map, task inspector, and the Stress / Machine controls (section 7 is real data).
6. Polish: dark mode, reduced motion, accessibility pass, static export served by FastAPI, runbook check from `docs/demo.md`.
Report at the end: what passed, what you mocked, what you could not verify.
