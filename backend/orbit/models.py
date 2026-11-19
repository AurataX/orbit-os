"""Plain data types shared by every module."""
from dataclasses import dataclass, field

# Workload classes. Lower priority number = more important.
INTERACTIVE, AI, DEV, BACKGROUND = "interactive", "ai", "dev", "background"
PRIORITY = {INTERACTIVE: 0, AI: 1, DEV: 2, BACKGROUND: 3}


@dataclass
class Task:
    id: int
    kind: str
    arrival: int
    burst: int
    priority: int
    refs: list[int] = field(default_factory=list)  # page touched at each CPU tick
    vram_need: int = 0                             # VRAM frames needed if it can use the GPU (0 = CPU only)
    parallel: float = 0.0                          # share of the work that is data-parallel (Amdahl)
    placement: str = "cpu"                         # cpu | gpu | hybrid (decided on arrival)
    gpu_work: int = 0                              # work units that leave the CPU for the GPU
    gpu_left: int = 0                              # GPU ticks still needed once it gets there
    locks: tuple = ()                              # locks it will take, in this order (hold-and-wait)
    held: list = field(default_factory=list)       # locks it holds right now
    remaining: int = field(init=False)
    first_run: int | None = None   # tick of first CPU slice (response time)
    finish: int | None = None
    killed: bool = False           # terminated by the user; finish is set but it did not complete

    def __post_init__(self):
        self.remaining = self.burst

    @property
    def turnaround(self) -> int:
        return self.finish - self.arrival

    @property
    def wait(self) -> int:
        return self.turnaround - self.burst

    @property
    def response(self) -> int:
        return self.first_run - self.arrival


@dataclass
class Event:
    tick: int
    kind: str          # arrive | place | run | preempt | block | wake | xfer | gpu_run | finish | ...
    task_id: int       # -1 for machine-wide events
    info: str = ""     # human-readable reason, shown in the kernel log
