"""One disk with a request queue and a head position (tracks 0..199).

Service time of a request = 1 tick + seek distance // 25.
Policies pick the next request: FCFS, SSTF (shortest seek first), SCAN
(sweep one way, reverse when nothing is ahead; the "LOOK" flavour).
"""
from dataclasses import dataclass

TRACKS = 200


@dataclass
class Request:
    seq: int
    task_id: int
    track: int


def track_of(key: tuple[int, int]) -> int:
    """Where a (task, page) lives on disk. Deterministic, spread across the platter."""
    task_id, page = key
    return (task_id * 37 + page * 11) % TRACKS


class FCFS:
    name = "FCFS"

    def pick(self, queue, head, direction):
        return queue[0], direction


class SSTF:
    name = "SSTF"

    def pick(self, queue, head, direction):
        return min(queue, key=lambda r: (abs(r.track - head), r.seq)), direction


class SCAN:
    name = "SCAN"

    def pick(self, queue, head, direction):
        ahead = [r for r in queue if (r.track - head) * direction >= 0]
        if not ahead:
            direction = -direction
            ahead = [r for r in queue if (r.track - head) * direction >= 0]
        return min(ahead, key=lambda r: (abs(r.track - head), r.seq)), direction


DISK_POLICIES = {p.name: p for p in (FCFS, SSTF, SCAN)}


class Disk:
    def __init__(self, policy):
        self.policy = policy
        self.head = 0
        self.direction = 1
        self.queue: list[Request] = []
        self.current: Request | None = None
        self.left = 0
        self.seq = 0
        self.busy_ticks = 0
        self.head_moved = 0

    @property
    def pending(self) -> int:
        return len(self.queue) + (self.current is not None)

    def submit(self, task_id: int, track: int) -> None:
        self.queue.append(Request(self.seq, task_id, track))
        self.seq += 1

    def tick(self) -> list[int]:
        """Advance one tick. Returns ids of tasks whose I/O just completed."""
        if self.current is None and self.queue:
            self._start_next()
        if self.current is None:
            return []
        self.busy_ticks += 1
        self.left -= 1
        if self.left > 0:
            return []
        done, self.current = self.current.task_id, None
        return [done]

    def _start_next(self) -> None:
        req, self.direction = self.policy.pick(self.queue, self.head, self.direction)
        self.queue.remove(req)
        distance = abs(req.track - self.head)
        self.head_moved += distance
        self.head = req.track
        self.current = req
        self.left = 1 + distance // 25
