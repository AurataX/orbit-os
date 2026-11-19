"""Run policies on the exact same workload and print who did better.

    python -m orbit.compare --seed 42                       # one table per policy dimension
    python -m orbit.compare --seed 42 --rewind cpu=MLFQ page=LRU disk=SCAN
                                                            # crisis -> rewind -> swap policies -> replay
"""
import argparse
import copy

from .cpu_sched import POLICIES as CPU_POLICIES
from .engine import Engine
from .gpu import GPU, Bus
from .logfmt import dmesg
from .memory import PAGE_POLICIES, VRAM, Pager
from .metrics import summarize
from .placement import PLACERS
from .recorder import Recorder, replay
from .storage import DISK_POLICIES, Disk
from .workload import generate

RAM_FRAMES, VRAM_FRAMES = 60, 16
DEFAULT = {"cpu": "MLFQ", "page": "LRU", "disk": "SCAN", "place": "ADAPTIVE"}


def build_engine(tasks, cpu="MLFQ", page="LRU", disk="SCAN", place="ADAPTIVE",
                 ram=RAM_FRAMES, vram=VRAM_FRAMES) -> Engine:
    """A fresh machine over its own copy of the tasks (shared by CLI and API)."""
    return Engine(copy.deepcopy(tasks), CPU_POLICIES[cpu](), Pager(ram, PAGE_POLICIES[page]()),
                  Disk(DISK_POLICIES[disk]()), VRAM(vram), GPU(), Bus(), PLACERS[place]())


def compare(seed: int, n_tasks: int = 40) -> dict[str, list[dict]]:
    tasks = generate(seed, n_tasks)
    registries = {"cpu": CPU_POLICIES, "page": PAGE_POLICIES, "disk": DISK_POLICIES, "place": PLACERS}
    tables = {}
    for dimension, names in registries.items():
        rows = []
        for name in names:
            choice = {**DEFAULT, dimension: name}
            rows.append({"policy": name, **summarize(build_engine(tasks, **choice).run())})
        tables[dimension] = sorted(rows, key=lambda r: r["inter_p95_turn"])
    return tables


def what_if(seed: int, base: dict, alt: dict, n_tasks: int = 40, every: int = 10) -> dict | None:
    """Run `base` until it hits a crisis, rewind to just before it, swap in `alt`, replay."""
    rec = Recorder(build_engine(generate(seed, n_tasks), **base), every)
    original = rec.run()
    if original.crisis_at is None:
        return None
    rewound = rec.rewind(original.crisis_at - 1)
    start = rewound.now
    replayed = replay(rewound, **{k: v for k, v in alt.items() if v != base.get(k)}).run()
    return {"crisis_at": original.crisis_at, "rewound_to": start, "original": original, "replayed": replayed}


def show(title: str, rows: list[dict]) -> None:
    cols = list(rows[0])
    widths = {c: max(len(c), 6) + 1 for c in cols}
    print(f"\n{title}")
    print("".join(f"{c:>{widths[c]}}" for c in cols))
    for r in rows:
        print("".join(f"{r[c]:>{widths[c]}}" for c in cols))


def parse_choices(pairs: list[str]) -> dict:
    return {k: v for k, v in (p.split("=") for p in pairs)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tasks", type=int, default=40)
    ap.add_argument("--rewind", nargs="*", metavar="dim=POLICY", help="what-if: policies to swap in after rewind")
    ap.add_argument("--base", nargs="*", default=["cpu=FCFS", "page=FIFO", "disk=FCFS"],
                    metavar="dim=POLICY", help="policies for the original (crisis) run")
    args = ap.parse_args()

    if args.rewind is not None:
        base = {**DEFAULT, **parse_choices(args.base)}
        alt = {**base, **parse_choices(args.rewind)}
        result = what_if(args.seed, base, alt, args.tasks)
        if result is None:
            print("The base run never reached a crisis; try other --base policies.")
            return
        print(f"crisis at tick {result['crisis_at']}; rewound to checkpoint at tick {result['rewound_to']}")
        show("before vs after (same workload, same history up to the checkpoint)", [
            {"policy": "original " + "/".join(base.values()), **summarize(result["original"])},
            {"policy": "replay   " + "/".join(alt.values()), **summarize(result["replayed"])},
        ])
        print("\nkernel log after the swap:")
        print("\n".join(dmesg(result["replayed"], grep="policy")))
        return

    for dimension, rows in compare(args.seed, args.tasks).items():
        others = ", ".join(f"{k}={v}" for k, v in DEFAULT.items() if k != dimension)
        show(f"{dimension.upper()} policy  (others: {others}; best interactive p95 turnaround first)", rows)


if __name__ == "__main__":
    main()
