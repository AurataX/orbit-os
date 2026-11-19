"""Locks and deadlock policies.

A task may need several exclusive locks (db, cache, log). It takes them one at a time and keeps
each until it finishes: hold-and-wait. Two tasks that take the same two locks in opposite order
can wait for each other forever. That is a deadlock.

The engine only OBSERVES: every tick it builds the wait-for graph and looks for a cycle.
What to DO about it is the policy:
  IGNORE  do nothing (the "ostrich" algorithm); the tasks in the cycle never finish
  DETECT  find the cycle, then recover by terminating the cheapest victim
  AVOID   Banker's algorithm: refuse a request if granting it could lead to a deadlock
"""
from .deadlock import request_resources

LOCK_NAMES = ("db", "cache", "log")


class Ignore:
    name = "IGNORE"

    def refuse(self, engine, task, lock) -> str | None:
        """Why this free lock must NOT be granted right now (None = go ahead)."""
        return None

    def resolve(self, engine, members: list[int]) -> None:
        engine.emit("deadlock", info=f"{self.name}: nobody intervenes, pids {members} wait forever")


class Detect(Ignore):
    name = "DETECT"

    def resolve(self, engine, members):
        tasks = {t.id: t for t in engine.tasks}
        victim = min(members, key=lambda pid: (tasks[pid].burst - tasks[pid].remaining, pid))  # least work lost
        engine.kill(victim, "deadlock victim: least work lost")


class Avoid(Ignore):
    name = "AVOID"

    def resolve(self, engine, members):
        engine.emit("deadlock", info=f"AVOID only prevents; pids {members} are already deadlocked and stay stuck")

    def refuse(self, engine, task, lock):
        """Banker's algorithm over the locks (one unit each): grant only if a safe order still exists."""
        live = [t for t in engine.tasks if t.locks and t.finish is None and t.arrival <= engine.now]
        available = [0 if name in engine.lock_owner else 1 for name in LOCK_NAMES]
        allocation = [[int(engine.lock_owner.get(name) == t.id) for name in LOCK_NAMES] for t in live]
        need = [[int(name in t.locks and name not in t.held) for name in LOCK_NAMES] for t in live]
        request = [int(name == lock) for name in LOCK_NAMES]
        if request_resources(live.index(task), request, available, allocation, need):
            return None
        return "Banker's: granting it could lead to deadlock"


DEADLOCK_POLICIES = {"IGNORE": Ignore, "DETECT": Detect, "AVOID": Avoid}
