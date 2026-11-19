"""Classical CPU scheduling policies.

Every policy answers two questions for the engine:
  pick()            -> which ready task runs next
  quantum(task)     -> how many ticks it may run before being preempted (None = until done)
A preempted task comes back through add().
"""
from .models import Task


class Scheduler:
    name = "base"

    def __init__(self):
        self.ready: list[Task] = []

    def add(self, task: Task) -> None:
        """A task becomes ready for the first time."""
        self.ready.append(task)

    def requeue(self, task: Task) -> None:
        """A running task used its whole quantum and was preempted."""
        self.add(task)

    def wake(self, task: Task) -> None:
        """A blocked task (disk / VRAM wait) is ready again. Not a quantum overrun."""
        self.add(task)

    def pick(self) -> Task | None:
        if not self.ready:
            return None
        task = min(self.ready, key=self.key)
        self.ready.remove(task)
        return task

    def key(self, task: Task):
        raise NotImplementedError

    def quantum(self, task: Task) -> int | None:
        return None


class FCFS(Scheduler):
    name = "FCFS"

    def key(self, task):
        return (task.arrival, task.id)


class SJF(Scheduler):
    name = "SJF"

    def key(self, task):
        return (task.remaining, task.id)


class Priority(Scheduler):
    name = "Priority"

    def key(self, task):
        return (task.priority, task.arrival, task.id)


class RoundRobin(Scheduler):
    name = "RR"

    def __init__(self, q: int = 4):
        super().__init__()
        self.q = q

    def pick(self):  # plain FIFO queue: preempted tasks go to the back
        return self.ready.pop(0) if self.ready else None

    def quantum(self, task):
        return self.q


class MLFQ(Scheduler):
    """3 levels with growing quanta. Tasks that burn a whole quantum sink a level,
    so short interactive work stays on top without us knowing burst lengths."""
    name = "MLFQ"
    QUANTA = (2, 4, 8)

    def __init__(self):
        super().__init__()
        self.level: dict[int, int] = {}

    def add(self, task):
        self.level.setdefault(task.id, 0)
        super().add(task)

    def requeue(self, task):
        # burned a full quantum => sink one level. Waking from I/O does NOT demote.
        self.level[task.id] = min(self.level[task.id] + 1, len(self.QUANTA) - 1)
        super().add(task)

    def key(self, task):
        return (self.level[task.id], task.arrival, task.id)

    def quantum(self, task):
        return self.QUANTA[self.level[task.id]]


POLICIES = {cls.name: cls for cls in (FCFS, SJF, Priority, RoundRobin, MLFQ)}
