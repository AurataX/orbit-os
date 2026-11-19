"""Kernel-style views of a run: `dmesg` (event log) and `ps` (process table).

    python -m orbit.logfmt --seed 42 --grep nexus --tail 20       # dmesg
    python -m orbit.logfmt --seed 42 --at 120 --ps                # process table at tick 120
"""
import argparse

from .engine import Engine

SUBSYSTEM = {
    "arrive": "sched", "run": "sched", "preempt": "sched", "finish": "sched",
    "place": "nexus", "block": "mm", "wake": "disk",
    "vram_wait": "vram", "vram_grant": "vram", "xfer": "bus",
    "gpu_queue": "gpu", "gpu_run": "gpu", "crisis": "kernel", "policy": "kernel",
    "inject": "kernel", "resize": "mm", "kill": "sched", "boost": "sched",
    "lock": "lock", "lock_wait": "lock", "lock_grant": "lock", "deadlock": "lock",
}
LEVEL = {"vram_wait": "WARN", "crisis": "CRIT", "kill": "WARN", "lock_wait": "WARN", "deadlock": "CRIT"}


def format_event(ev, kinds: dict[int, str]) -> str:
    who = f"pid={ev.task_id} ({kinds[ev.task_id]})" if ev.task_id >= 0 else ""
    level = LEVEL.get(ev.kind, "INFO")
    return f"[{ev.tick:5}] {SUBSYSTEM[ev.kind]:<6} {level:<4} {ev.kind:<10} {who:<22} {ev.info}".rstrip()


def dmesg(engine: Engine, grep: str | None = None, tail: int | None = None) -> list[str]:
    kinds = {t.id: t.kind for t in engine.tasks}
    lines = [format_event(ev, kinds) for ev in engine.log]
    if grep:
        lines = [ln for ln in lines if grep in ln]
    return lines[-tail:] if tail else lines


def ps(engine: Engine) -> list[str]:
    """Process table: what the OS keeps about every process (the PCB)."""
    rows = [f"{'PID':>4} {'CLASS':<12} {'STATE':<13} {'PLACE':<7} {'PRIO':>4} {'BURST':>5} {'LEFT':>5}"]
    for t in sorted(engine.tasks, key=lambda t: t.id):
        rows.append(f"{t.id:>4} {t.kind:<12} {engine.state_of(t):<13} {t.placement:<7} "
                    f"{t.priority:>4} {t.burst:>5} {t.remaining:>5}")
    return rows


def main() -> None:
    from .compare import DEFAULT, build_engine  # here, not at the top: compare imports this module
    from .workload import generate

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    for key, value in DEFAULT.items():
        ap.add_argument(f"--{key}", default=value)
    ap.add_argument("--at", type=int, help="stop at this tick")
    ap.add_argument("--grep")
    ap.add_argument("--tail", type=int)
    ap.add_argument("--ps", action="store_true")
    args = ap.parse_args()
    engine = build_engine(generate(args.seed), args.cpu, args.page, args.disk, args.place).run(args.at)
    print("\n".join(ps(engine) if args.ps else dmesg(engine, args.grep, args.tail)))


if __name__ == "__main__":
    main()
