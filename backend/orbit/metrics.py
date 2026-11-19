"""Turn a finished Engine into numbers we can compare."""
from statistics import mean

from .engine import Engine
from .models import INTERACTIVE


def p95(values: list[int]) -> int:
    values = sorted(values)
    return values[min(len(values) - 1, int(0.95 * len(values)))] if values else 0


def summarize(e: Engine) -> dict:
    done = [t for t in e.tasks if t.finish is not None and not t.killed]   # killed tasks did not complete
    inter = [t for t in done if t.kind == INTERACTIVE]
    return {
        "avg_wait": round(mean(t.wait for t in done), 1) if done else 0,
        "inter_p95_resp": p95([t.response for t in inter]),      # time to first run
        "inter_p95_turn": p95([t.turnaround for t in inter]),    # what the user feels end to end
        "makespan": e.now,
        "unfinished": sum(1 for t in e.tasks if t.finish is None),
        "killed": sum(1 for t in e.tasks if t.killed),
        "deadlocks": e.deadlock_count,
        "cpu_util_%": round(100 * e.busy_ticks / e.now, 1),
        "page_faults": e.pager.faults if e.pager else 0,
        "disk_busy": e.disk.busy_ticks if e.disk else 0,
        "head_moved": e.disk.head_moved if e.disk else 0,
        "gpu_stall": e.gpu_stall_ticks,
        "gpu_busy": e.gpu.busy_ticks if e.gpu else 0,
        "bus_busy": e.bus.busy_ticks if e.bus else 0,
        "crisis_at": e.crisis_at if e.crisis_at is not None else "-",
    }
