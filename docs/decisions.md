# Decisions (short ADRs)

## D1 — Python for the simulator (accepted)
The course expects Python, it is fast to write and easy to explain. Core is stdlib-only so there are no hidden dependencies.

## D2 — Tick-based discrete simulation (accepted)
Integer ticks give exact determinism, simple reasoning and easy checkpointing. Event-queue simulation is more general but harder to explain.

## D3 — Checkpoint = `deepcopy` (accepted)
Simplest correct snapshot. Cost is fine at this scale (tens of tasks, hundreds of ticks). Revisit only if a profile shows it hurts.

## D4 — One process serves API and UI (accepted)
FastAPI mounts the built frontend. One command to run, one thing to tunnel, no CORS.

## D5 — Demo via local run + Cloudflare Tunnel (accepted)
Free, instant public URL, no deploy pipeline. Cloud Run stays optional. Cloudflare Pages rejected: no Python backend.

## D6 — Core slice first (accepted)
CPU + memory/VRAM + storage + deadlock + replay first; CPU/GPU placement is phase 5 so the OS fundamentals are solid before the research layer.

## D7 — Policies behind small interfaces (accepted)
Engine never names policies; registries map names to classes. This makes "swap policy and replay" trivial and testable.

## D8 — Scheduler has three entry points (resolved in phase 2)
`add` (new task), `requeue` (quantum used up; MLFQ demotes), `wake` (I/O or VRAM wait over; no demotion). Test: `test_mlfq_does_not_demote_on_io_wake`.

## D9 — Default machine sized for visible but survivable pressure (resolved)
Seed 42, RAM 60 frames, VRAM 16, disk 1 + seek//25 ticks gives ~80% CPU utilisation, ~350 faults, a disk crisis mid-run. A first tuning with a slower disk and the old 38%-utilisation setup made every CPU policy look identical because the disk was the only bottleneck. Constants live in `compare.py` (`RAM_FRAMES`, `VRAM_FRAMES`) and `storage.py`.

## D10 — Next.js for the dashboard (accepted)
Owner prefers Next.js. Use static export (`output: 'export'`) so there is no Node server at demo time; FastAPI serves the files. Python remains the only backend.

## D11 — Rank policies by interactive p95 *turnaround* (accepted)
`response` (first dispatch) hid I/O stalls: disk FCFS looked best on response while makespan was 70% worse. We keep both columns but rank by turnaround.

## D13 — GPU offload is an Amdahl model, not instruction-level (accepted)
Idea from the owner: many OS tasks are data-parallel and could run on the GPU while today they use the CPU. We model it as a per-class `parallel` fraction: parallel work runs `GPU_SPEED`x faster, serial work on a GPU costs `SERIAL_PENALTY` per unit, copying over a shared bus costs ticks, VRAM is limited. We do NOT simulate individual instructions or threads; say so in the viva. Interactive tasks have parallel=0 and stay on the CPU (copy cost > work).

## D14 — Offloading is never free of RAM pressure (accepted)
First version gave a GPU task a 1-tick CPU launch, so it touched almost no pages and "all-GPU" looked 4x faster than CPU-only, partly because the disk cascade vanished. Now the CPU part also stages `1 + vram_need//2` input pages in RAM before the bus copy.

## D15 — Thrash livelock is real, so runs are capped (accepted)
FCFS + FIFO + 30 RAM frames never finishes: tasks evict each other's freshly loaded pages. `MAX_TICKS = 6000` stops the run; metrics report `unfinished`. This is a demo-worthy phenomenon, not a bug.

## D16 — A checkpoint is taken after a tick completes (note)
Events stamped with tick T come from the step that starts at `now == T`, so they belong AFTER the checkpoint at T. Compare history with `tick < checkpoint`.

## D12 — Priority policy is not a fair rival (note)
Task priority is derived from workload class, so Priority "knows" which tasks are interactive. MLFQ must discover it. Say this when presenting the table.

## D17 — Deadlock is a policy, and only appears when asked for
Tasks may carry `locks` (db, cache, log), taken in order and held until finish (hold-and-wait). The engine observes: each tick it builds the wait-for graph and runs `find_cycle`. The policy decides what to do: IGNORE (nothing; the machine hangs, detected by `Engine.stuck`), DETECT (kill the victim with the least work done), AVOID (Banker's algorithm over the locks). The seed workload has no locks, so every earlier number (999 -> 421) is unchanged; the `deadlock-demo` storm injects two jobs that take db/cache in opposite order. Honest limit: AVOID must act before the unsafe grant. Rewind to before it and switch to AVOID, or switch to DETECT after the hang.
