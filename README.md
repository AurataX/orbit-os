# ORBIT-OS

**Operating-system Resource Balancing & Intelligent Task placement**: a heterogeneous cross-resource OS simulator (CPU, GPU, RAM, VRAM, storage) with deterministic checkpoint / rewind / replay.

Pick a policy, run a seeded workload, hit a resource crisis, rewind, change policy, replay the *same* workload, and compare.

## Run the dashboard

```sh
make install
make test
make build
make serve
```

Open [http://localhost:8000](http://localhost:8000). The [demo runbook](docs/demo.md) covers the seed-42 replay and token-protected tunnel setup.

## Docs
Start with [`AGENTS.md`](AGENTS.md), then `docs/system.md`, `docs/architecture.md`, `docs/design.md`, `docs/task.md`, `docs/demo.md`.

## Status
Phases 1–4 are complete, including the simulator, FastAPI, Next.js dashboard, ORBIT shell, and branch comparison. See [tasks and status](docs/task.md). Run the simulator CLI commands from `backend/`.

```
python3 -m orbit.compare --seed 42                                   # who did better, per policy dimension
python3 -m orbit.compare --seed 42 --rewind cpu=MLFQ page=LRU disk=SCAN   # crisis -> rewind -> swap -> replay
python3 -m orbit.logfmt --seed 42 --grep nexus --tail 20             # kernel log (dmesg)
# deadlock demo: in the shell run  storm deadlock-demo  then  set deadlock=IGNORE|DETECT|AVOID
python3 -m orbit.logfmt --seed 42 --at 60 --ps                       # process table at tick 60
```
