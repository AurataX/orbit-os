"""RAM paging (FIFO / LRU replacement) and the VRAM pool.

Resident pages live in an OrderedDict. The victim is always the first entry,
so a policy only has to say how a hit reorders it:
  FIFO: never reorder (oldest *loaded* page leaves)
  LRU : move to the end (least recently *used* page leaves)
"""
from collections import OrderedDict


class FIFO:
    name = "FIFO"

    def touch(self, resident: OrderedDict, key) -> None:
        pass


class LRU:
    name = "LRU"

    def touch(self, resident: OrderedDict, key) -> None:
        resident.move_to_end(key)


PAGE_POLICIES = {p.name: p for p in (FIFO, LRU)}


class Pager:
    def __init__(self, frames: int, policy):
        self.frames = frames
        self.policy = policy
        self.resident: OrderedDict = OrderedDict()
        self.faults = 0

    def access(self, key) -> bool:
        """Touch a page. Returns True on a page fault."""
        if key in self.resident:
            self.policy.touch(self.resident, key)
            return False
        self.faults += 1
        if len(self.resident) >= self.frames:
            self.resident.popitem(last=False)  # evict victim
        self.resident[key] = None
        return True


    def resize(self, frames: int) -> int:
        """Change the number of frames. Shrinking evicts victims; returns how many pages were dropped."""
        self.frames = frames
        dropped = 0
        while len(self.resident) > frames:
            self.resident.popitem(last=False)
            dropped += 1
        return dropped

    def free_task(self, task_id: int) -> None:
        """A process exited: its pages leave RAM."""
        for key in [k for k in self.resident if k[0] == task_id]:
            del self.resident[key]


def count_faults(refs: list, frames: int, policy) -> int:
    """Textbook helper: faults for one reference string."""
    pager = Pager(frames, policy)
    for page in refs:
        pager.access(page)
    return pager.faults


class VRAM:
    """GPU memory: a task gets all its frames at once or has to wait."""

    def __init__(self, frames: int):
        self.frames = frames
        self.held: dict[int, int] = {}

    @property
    def used(self) -> int:
        return sum(self.held.values())

    def alloc(self, task_id: int, n: int) -> bool:
        if self.frames - self.used < n:
            return False
        self.held[task_id] = n
        return True

    def release(self, task_id: int) -> None:
        self.held.pop(task_id, None)
