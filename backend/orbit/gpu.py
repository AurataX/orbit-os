"""GPU compute device and the CPU<->GPU transfer bus.

A GPU/hybrid task goes: CPU (launch / serial part) -> bus (copy data) -> GPU queue -> GPU.

Speed model (Amdahl's law in miniature):
  * data-parallel work runs GPU_SPEED units per tick (thousands of threads, same instruction)
  * serial work on a GPU is slow: SERIAL_PENALTY ticks per unit (vs 1 tick on a CPU core)
  * the GPU is non-preemptive, so a long kernel blocks the ones queued behind it
  * the bus moves one task at a time, and copying costs ticks
"""
from .models import Task

GPU_SPEED = 4
SERIAL_PENALTY = 2


def split(task: Task, placement: str) -> tuple[int, int]:
    """(work units that leave the CPU, GPU ticks they need) for a placement choice."""
    if placement == "cpu":
        return 0, 0
    parallel_units = round(task.burst * task.parallel)
    if placement == "hybrid":               # CPU keeps the serial part, GPU takes the parallel part
        gpu_work = min(parallel_units, task.burst - 1)
        return gpu_work, -(-gpu_work // GPU_SPEED)
    # "gpu": the CPU only launches the kernel and stages the input pages in RAM (1 tick + 1 per 2 VRAM frames).
    # The copy to the GPU has to read that data from host memory, so offloading is never free of RAM pressure.
    gpu_work = task.burst - min(task.burst - 1, 1 + task.vram_need // 2)
    par = min(parallel_units, gpu_work)
    return gpu_work, -(-par // GPU_SPEED) + (gpu_work - par) * SERIAL_PENALTY


def transfer_ticks(task: Task) -> int:
    return max(1, task.vram_need // 2)


class Bus:
    def __init__(self):
        self.queue: list[tuple[Task, int]] = []
        self.current: Task | None = None
        self.left = 0
        self.busy_ticks = 0

    @property
    def backlog(self) -> int:
        """Ticks of copying already waiting (used by placement estimates)."""
        return self.left + sum(t for _, t in self.queue)

    def submit(self, task: Task) -> None:
        self.queue.append((task, transfer_ticks(task)))

    def tick(self) -> Task | None:
        """Returns the task whose copy just finished."""
        if self.current is None and self.queue:
            self.current, self.left = self.queue.pop(0)
        if self.current is None:
            return None
        self.busy_ticks += 1
        self.left -= 1
        if self.left > 0:
            return None
        done, self.current = self.current, None
        return done


class GPU:
    def __init__(self):
        self.queue: list[Task] = []
        self.current: Task | None = None
        self.busy_ticks = 0

    @property
    def backlog(self) -> int:
        """Ticks of GPU work already ahead of a newcomer."""
        return sum(t.gpu_left for t in self.queue) + (self.current.gpu_left if self.current else 0)

    def submit(self, task: Task) -> None:
        self.queue.append(task)

    def tick(self) -> tuple[Task | None, Task | None]:
        """Returns (task that just started, task that just finished)."""
        started = None
        if self.current is None and self.queue:
            self.current = started = self.queue.pop(0)
        if self.current is None:
            return None, None
        self.busy_ticks += 1
        self.current.gpu_left -= 1
        if self.current.gpu_left > 0:
            return started, None
        done, self.current = self.current, None
        done.remaining = 0
        return started, done
