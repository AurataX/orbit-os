# System brief — ORBIT-OS

## 1. One-paragraph summary
A Python discrete-event simulator of a modern machine where CPU, GPU, RAM, VRAM and storage are **coupled**, so contention in one resource degrades or breaks another. It runs four workload classes concurrently, records every event, and supports **checkpoint -> rewind -> change policy -> replay -> compare** on the exact same seeded workload. A web dashboard visualises runs and the policy comparison.

## 2. The question we answer
Not "which CPU scheduler is best?" but: *how should an OS manage heterogeneous CPU/GPU/memory/storage resources when workloads with conflicting performance requirements share one machine?*

## 3. Course fit (Operating Systems Lab)
Each OS topic is implemented for real, not mocked:

| OS topic | Where | Algorithms |
|---|---|---|
| CPU scheduling | `cpu_sched.py` | FCFS, SJF, Priority, Round Robin, MLFQ |
| Memory management | `memory.py` | Paging, page tables, page faults, FIFO / LRU / (Optimal as baseline) replacement; separate RAM and VRAM pools |
| Storage / I/O | `storage.py` | Disk queue, FCFS / SSTF / SCAN, swap traffic |
| Deadlock | `deadlock.py` | Banker's algorithm (avoidance), wait-for-graph cycle detection |
| Process lifecycle | `engine.py` | arrive, ready, running, blocked, finished |

Research layer on top: cross-resource cascade model, workload-aware CPU/GPU/hybrid placement (NEXUS), interference analysis, deterministic replay.

## 4. Machine model (simulated)
- **CPU**: N cores (start with 1, then 4), tick-based.
- **GPU**: separate queue, faster on parallel work, needs data in **VRAM**; CPU<->GPU transfer costs ticks.
- **RAM / VRAM**: fixed number of frames; demand paging; overflow goes to swap.
- **Storage**: one disk with a request queue; swap and file reads compete.
- **Time**: integer ticks. No wall-clock anywhere in the engine.

## 5. Workload classes
| Class | Shape | Wants | Hurt by |
|---|---|---|---|
| Interactive | many, short bursts | low response time | long jobs hogging CPU, swap storms |
| AI / LLM | few, long, large VRAM | GPU + big VRAM | VRAM pressure, transfer cost |
| Developer / compile | medium, CPU + disk heavy | throughput | disk contention, RAM pressure |
| Background | long, low priority | eventual progress | starvation |

Workloads come from `workload.py`: same seed => identical tasks.

## 5b. Why the GPU is shared (the NEXUS idea)
Many OS-level jobs (builds, compression, checksums, model inference) are data-parallel but run on the CPU because nobody offloaded them. ORBIT models this with Amdahl's law: each task has a `parallel` fraction. Parallel work is `GPU_SPEED`x faster on the GPU, serial work is slower there, the CPU<->GPU bus copies one task at a time, VRAM is limited and the GPU is non-preemptive. NEXUS picks CPU, GPU or hybrid (CPU does the serial part, GPU the parallel part) from finish-time estimates and logs the numbers. Tiny interactive tasks have parallel = 0, so copying would cost more than the work. This is an abstraction of parallel work, not an instruction-level GPU simulator.

## 6. Cross-resource cascades (the research core)
- RAM pressure -> page faults -> swap I/O -> disk queue grows -> tasks block -> CPU idles / interactive latency spikes.
- VRAM full -> AI task evicts/blocks -> GPU stalls -> work falls back to CPU -> CPU queue grows.
- Resource hold-and-wait across CPU/GPU/VRAM/disk -> possible deadlock (detected or avoided).
A **crisis** is a measurable threshold crossing (e.g. interactive p95 response > limit, or deadlock detected). The recorder marks the tick.

## 7. Record, rewind, replay
1. Run with policy A; every event is logged; periodic checkpoints (`deepcopy` of engine state).
2. On crisis, rewind to a checkpoint before it.
3. Swap policy to B (scheduler, page replacement, disk scheduler, placement) and continue.
4. Compare A vs B on identical history up to the checkpoint and identical future arrivals.

## 8. Functional requirements
- F1 Generate seeded workloads of all four classes.
- F2 Run any CPU policy; all work completes (tested).
- F3 Model RAM/VRAM paging with faults and replacement policy.
- F4 Model disk queue and swap coupling.
- F5 Detect/avoid deadlock.
- F6 Cascade coupling between resources.
- F7 Event log, checkpoint, rewind, policy swap, replay.
- F8 Compare table across policies on one seed.
- F9 API + live dashboard.
- F10 (phase 5) CPU/GPU/hybrid placement + interference report.

## 9. Non-functional requirements
- **Deterministic**: same seed + policy => same log.
- **Explainable**: stdlib-only core, small modules, readable in a viva.
- **Fast**: a 40-task, ~500-tick run in well under a second.
- **Honest**: all reported numbers come from real runs.
- **Demo-able**: one process, one command, public link via tunnel.

## 10. Metrics ("who did better")
avg wait, avg turnaround, **interactive p95 response**, makespan, CPU utilisation; later: page faults, swap I/O ticks, GPU stall ticks, VRAM evictions, deadlocks, starvation count for background tasks.

## 10b. Interactivity and the "What you did" log (phase 4)
Everything the user does changes the simulation and is recorded in a visible action log, so the presenter can say "I did X, the system did Y, result Z".

Things the user can do:
- Pick seed, CPU / page / disk policy; Run, Pause, Step one tick, speed slider
- **Inject**: AI burst, compile storm, swap storm (a burst of interactive + dev tasks)
- **Resize the machine**: shrink RAM or VRAM live to provoke a crisis
- **Change a policy mid-run** (CPU, page replacement, disk) and watch the effect
- Kill a task, boost a task's priority
- Checkpoint now; drag a timeline scrubber to rewind; replay with a different policy
- **Challenge mode**: guess which policy wins on a seed, then reveal the table
- Export the run (JSON log + comparison CSV) for the lab report

Action log entry = `{tick, action, params, effect}` e.g. `t=120 · You shrank RAM 60->30 · faults/100 ticks rose 8 -> 31`. The log is part of the recorded run, so replay reproduces the user's actions too.

## 11. Out of scope
Real kernels, real GPUs, real hardware measurement, multi-machine, security. This is a model; claims are about the model.

## 12. Success criteria
- Policy comparison table reproducible with one command.
- At least one cascade scenario where policy B visibly beats policy A after rewind.
- Tests green; owner can explain each module.
- Live demo works from a laptop through a public link.
