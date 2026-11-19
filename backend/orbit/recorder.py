"""Checkpoint / rewind / counterfactual replay.

The engine holds only plain data, so a checkpoint is just a deep copy.
Rewinding hands back a NEW engine copy; the original run stays untouched,
so "before" and "after" can be compared side by side.
"""
import copy

from .cpu_sched import POLICIES as CPU_POLICIES
from .engine import Engine
from .memory import PAGE_POLICIES
from .placement import PLACERS
from .storage import DISK_POLICIES


class Recorder:
    def __init__(self, engine: Engine, every: int = 10):
        self.engine = engine
        self.every = every
        self.checkpoints: dict[int, Engine] = {}
        self.save()

    def save(self) -> int:
        self.checkpoints[self.engine.now] = copy.deepcopy(self.engine)
        return self.engine.now

    def run(self, until: int | None = None) -> Engine:
        e = self.engine
        while not e.done and e.now < e.MAX_TICKS and (until is None or e.now < until):
            e.step()
            if e.now % self.every == 0:
                self.save()
        return e

    def rewind(self, tick: int) -> Engine:
        """A fresh engine at the latest checkpoint at or before `tick`."""
        at = max(t for t in self.checkpoints if t <= tick)
        return copy.deepcopy(self.checkpoints[at])


def replay(engine: Engine, cpu=None, page=None, disk=None, place=None) -> Engine:
    """Swap policies on a (rewound) engine. The past is kept; the new policy rules from now on.

    Placement only affects tasks that have not arrived yet (already-placed tasks keep their device).
    """
    if cpu:
        new = CPU_POLICIES[cpu]()
        for task in engine.sched.ready:          # hand the ready queue over, order preserved
            new.add(task)
        engine.emit("policy", info=f"cpu {engine.sched.name} -> {new.name}")
        engine.sched = new
    if page and engine.pager:
        new = PAGE_POLICIES[page]()
        engine.emit("policy", info=f"page {engine.pager.policy.name} -> {new.name}")
        engine.pager.policy = new
    if disk and engine.disk:
        new = DISK_POLICIES[disk]()
        engine.emit("policy", info=f"disk {engine.disk.policy.name} -> {new.name}")
        engine.disk.policy = new
    if place and engine.placer:
        new = PLACERS[place]()
        engine.emit("policy", info=f"placement {engine.placer.name} -> {new.name} (for tasks arriving later)")
        engine.placer = new
    return engine
