"""Tick-based simulation loop. This is the only place simulated time advances.

State lives in plain attributes so the whole engine can be deep-copied
(checkpoint) and resumed with different policies (counterfactual replay).

Memory, disk, VRAM and the GPU are optional. With none of them the engine is a
pure CPU scheduler; with them, resources couple into a cascade:
  page fault -> disk request -> task blocks -> CPU runs someone else (or idles)
  VRAM full  -> GPU/hybrid task waits (GPU stall) until another one finishes
  GPU task   -> CPU launch -> bus copy -> GPU queue -> GPU
Every decision writes an Event with a reason; that is the kernel log.
"""
from .cpu_sched import Scheduler
from .gpu import split, transfer_ticks
import random

from .models import Event, Task
from .storage import track_of
from .workload import HOT_PAGES, STORMS, make_task

CRISIS_QUEUE = 16  # disk requests pending at once => "storage crisis" (normal peak is ~10)
MAX_TICKS = 6000   # safety stop: extreme thrashing (FIFO + tiny RAM) can livelock forever
LOG_LIMIT = 10000  # keep the newest events only; `log_base` counts what was dropped


class Engine:
    MAX_TICKS = MAX_TICKS

    def __init__(self, tasks: list[Task], scheduler: Scheduler, pager=None, disk=None,
                 vram=None, gpu=None, bus=None, placer=None):
        self.tasks = tasks
        self.sched = scheduler
        self.pager, self.disk, self.vram = pager, disk, vram
        self.gpu, self.bus, self.placer = gpu, bus, placer
        self.now = 0
        self.running: Task | None = None
        self.slice_left: int | None = None
        self.busy_ticks = 0
        self.gpu_stall_ticks = 0
        self.crisis_at: int | None = None
        self.blocked: dict[int, Task] = {}   # waiting for disk
        self.vram_wait: list[Task] = []      # waiting for VRAM
        self.log: list[Event] = []
        self.log_limit = LOG_LIMIT
        self.log_base = 0                    # events dropped so far: absolute index = log_base + position
        self.injections = 0                  # makes every injected batch use its own deterministic seed
        self._pending = sorted(tasks, key=lambda t: (t.arrival, t.id))  # not yet arrived

    @property
    def done(self) -> bool:
        return all(t.finish is not None for t in self.tasks)

    def emit(self, kind: str, task_id: int = -1, info: str = "") -> None:
        self.log.append(Event(self.now, kind, task_id, info))
        slack = max(1, self.log_limit // 10)          # trim in chunks, not one event at a time
        if len(self.log) > self.log_limit + slack:
            drop = len(self.log) - self.log_limit
            del self.log[:drop]
            self.log_base += drop

    # ---- one tick -----------------------------------------------------
    def step(self) -> None:
        self._admit()
        self._finish_io()
        self._dispatch()
        task = self.running
        if task:
            task.remaining -= 1
            self.busy_ticks += 1
            if self.slice_left is not None:
                self.slice_left -= 1
        self.gpu_stall_ticks += len(self.vram_wait)
        self.now += 1
        if task:
            self._end_of_tick(task)
        self._tick_devices()
        self._watch_crisis()

    def _end_of_tick(self, task: Task) -> None:
        if task.remaining <= task.gpu_work:          # the CPU part is complete
            self.running = None
            if task.gpu_work == 0:
                self._finish(task)
            else:
                self.bus.submit(task)
                self.emit("xfer", task.id, f"cpu part done, copying {transfer_ticks(task)} ticks to GPU "
                                           f"(bus backlog {self.bus.backlog})")
        elif self.slice_left == 0:
            self.emit("preempt", task.id, "quantum expired")
            self.running = None
            self.sched.requeue(task)

    def _finish(self, task: Task) -> None:
        task.finish = self.now
        self.emit("finish", task.id, f"turnaround={task.turnaround} wait={task.wait}")
        self._release_vram(task)

    def _admit(self) -> None:
        while self._pending and self._pending[0].arrival <= self.now:
            task = self._pending.pop(0)
            self.emit("arrive", task.id, f"{task.kind} burst={task.burst} prio={task.priority}")
            self._place(task)
            self.sched.add(task)

    def _place(self, task: Task) -> None:
        if not (self.placer and self.gpu and task.vram_need):
            return
        task.placement, reason = self.placer.decide(task, self)
        task.gpu_work, task.gpu_left = split(task, task.placement)
        self.emit("place", task.id, f"{task.placement}: {reason}")

    def _finish_io(self) -> None:
        if not self.disk:
            return
        for task_id in self.disk.tick():
            task = self.blocked.pop(task_id, None)
            if task is None:                      # killed while its I/O was in flight
                continue
            self.emit("wake", task_id, "page loaded from disk")
            self.sched.wake(task)

    def _dispatch(self) -> None:
        """Make sure self.running is a task that can really execute this tick."""
        while True:
            if self.running is None:
                task = self.sched.pick()
                if task is None:
                    return
                if not self._get_vram(task):
                    continue
                self.running = task
                self.slice_left = self.sched.quantum(task)
                if task.first_run is None:
                    task.first_run = self.now
                self.emit("run", task.id, f"quantum={self.slice_left or 'until done'} ready={len(self.sched.ready)}")
            if not self._page_fault(self.running):
                return
            self.running = None  # it blocked on the disk; try the next ready task

    def _tick_devices(self) -> None:
        if not self.gpu:
            return
        delivered = self.bus.tick()
        if delivered:
            self.gpu.submit(delivered)
            self.emit("gpu_queue", delivered.id, f"data copied; GPU queue={len(self.gpu.queue)}")
        started, finished = self.gpu.tick()
        if started:
            self.emit("gpu_run", started.id, f"kernel needs {started.gpu_left} ticks (parallel={started.parallel})")
        if finished:
            self._finish(finished)

    # ---- resource coupling ---------------------------------------------
    def _page_fault(self, task: Task) -> bool:
        """Touch this tick's page. On a fault the task blocks until the disk delivers it."""
        if not self.pager or not self.disk:
            return False
        page = task.refs[task.burst - task.remaining]
        key = (task.id, page)
        if not self.pager.access(key):
            return False
        self.disk.submit(task.id, track_of(key))
        self.blocked[task.id] = task
        self.emit("block", task.id, f"page fault page={page} track={track_of(key)} "
                                    f"disk_queue={self.disk.pending} ram={len(self.pager.resident)}/{self.pager.frames}")
        return True

    def _get_vram(self, task: Task) -> bool:
        if not self.vram or task.placement == "cpu" or task.id in self.vram.held:
            return True
        if task.vram_need > self.vram.frames:      # can never fit, so waiting would be forever
            self._fallback_to_cpu(task)
            return True
        if self.vram.alloc(task.id, task.vram_need):
            return True
        self.vram_wait.append(task)
        self.emit("vram_wait", task.id, f"need={task.vram_need} free={self.vram.frames - self.vram.used}")
        return False

    def _release_vram(self, task: Task) -> None:
        if self.vram:
            self.vram.release(task.id)
            self._grant_vram_waiters(f"freed by pid={task.id}")

    def _fallback_to_cpu(self, task: Task) -> None:
        """The GPU path is impossible (VRAM too small): run the whole task on the CPU instead."""
        task.placement, task.gpu_work, task.gpu_left = "cpu", 0, 0
        self.emit("place", task.id, f"cpu: needs {task.vram_need} VRAM frames but the machine only has "
                                    f"{self.vram.frames}; falling back to the CPU")

    def _grant_vram_waiters(self, why: str) -> None:
        while self.vram_wait and self.vram.alloc(self.vram_wait[0].id, self.vram_wait[0].vram_need):
            waiter = self.vram_wait.pop(0)
            self.emit("vram_grant", waiter.id, why)
            self.sched.wake(waiter)

    def _watch_crisis(self) -> None:
        if self.disk and self.crisis_at is None and self.disk.pending >= CRISIS_QUEUE:
            self.crisis_at = self.now
            self.emit("crisis", info=f"disk queue={self.disk.pending} >= {CRISIS_QUEUE}")

    # ---- live actions (the dashboard / shell call these between ticks) ------
    def inject(self, kind: str, n: int = 1) -> list[int]:
        """Spawn n new tasks of a workload class that arrive right now. Deterministic."""
        if kind not in HOT_PAGES:
            raise ValueError(f"unknown workload class {kind!r}; use one of {sorted(HOT_PAGES)}")
        if not 1 <= n <= 50:
            raise ValueError("n must be between 1 and 50")
        self.injections += 1
        rng = random.Random(self.now * 1_000_003 + self.injections)
        first = max((t.id for t in self.tasks), default=-1) + 1
        new = [make_task(rng, first + i, kind, self.now) for i in range(n)]
        self.tasks.extend(new)
        self._pending = sorted(self._pending + new, key=lambda t: (t.arrival, t.id))
        ids = [t.id for t in new]
        self.emit("inject", info=f"{n} {kind} task(s) pids {ids[0]}..{ids[-1]}")
        return ids

    def storm(self, name: str) -> list[int]:
        """A named surge: ai-burst, compile-storm or swap-storm."""
        if name not in STORMS:
            raise ValueError(f"unknown storm {name!r}; use one of {sorted(STORMS)}")
        ids = []
        for kind, n in STORMS[name].items():
            ids += self.inject(kind, n)
        return ids

    def resize(self, ram: int | None = None, vram: int | None = None) -> None:
        """Change machine size live. Shrinking RAM evicts pages; VRAM already held is never taken back."""
        if ram is not None:
            if ram < 1:
                raise ValueError("ram must be at least 1 frame")
            if self.pager:
                old = self.pager.frames
                dropped = self.pager.resize(ram)
                self.emit("resize", info=f"RAM {old} -> {ram} frames, {dropped} pages evicted")
        if vram is not None:
            if vram < 0:
                raise ValueError("vram cannot be negative")
            if self.vram:
                old = self.vram.frames
                self.vram.frames = vram
                over = max(0, self.vram.used - vram)
                self.emit("resize", info=f"VRAM {old} -> {vram} frames" +
                                         (f"; {over} still held, no new grants until released" if over else ""))
                for waiter in [t for t in self.vram_wait if t.vram_need > vram]:   # can never fit now
                    self.vram_wait.remove(waiter)
                    self._fallback_to_cpu(waiter)
                    self.sched.wake(waiter)
                self._grant_vram_waiters("VRAM grew")

    def kill(self, task_id: int) -> None:
        """Terminate a process wherever it is (ready, running, blocked, on the bus or the GPU)."""
        task = next((t for t in self.tasks if t.id == task_id), None)
        if task is None:
            raise ValueError(f"no such pid {task_id}")
        if task.finish is not None:
            raise ValueError(f"pid {task_id} already finished")
        state = self.state_of(task)
        same = lambda t: t is not task
        self.sched.ready = [t for t in self.sched.ready if same(t)]
        self._pending = [t for t in self._pending if same(t)]
        self.vram_wait = [t for t in self.vram_wait if same(t)]
        self.blocked.pop(task_id, None)
        if self.running is task:
            self.running, self.slice_left = None, None
        if self.disk:
            self.disk.queue = [r for r in self.disk.queue if r.task_id != task_id]  # in-flight I/O finishes unnoticed
        if self.bus:
            self.bus.queue = [(t, n) for t, n in self.bus.queue if same(t)]
            if self.bus.current is task:
                self.bus.current, self.bus.left = None, 0
        if self.gpu:
            self.gpu.queue = [t for t in self.gpu.queue if same(t)]
            if self.gpu.current is task:
                self.gpu.current = None
        if self.pager:
            self.pager.free_task(task_id)
        task.killed, task.finish = True, self.now
        self.emit("kill", task_id, f"killed while {state}; its RAM pages and VRAM were freed")
        self._release_vram(task)

    def boost(self, task_id: int, priority: int) -> None:
        """Change a task's priority (lower = more important). Only the Priority scheduler reads it."""
        task = next((t for t in self.tasks if t.id == task_id), None)
        if task is None or task.finish is not None:
            raise ValueError(f"pid {task_id} is not a live process")
        old, task.priority = task.priority, priority
        self.emit("boost", task_id, f"priority {old} -> {priority} (only the Priority scheduler uses it; now: {self.sched.name})")

    # ---- outside views ---------------------------------------------------
    def state_of(self, task: Task) -> str:
        """Process state, like the S column of `ps`."""
        in_ = lambda items: any(x is task for x in items)  # identity, not dataclass equality
        if task.killed:
            return "killed"
        if task.finish is not None:
            return "done"
        if self.running is task:
            return "running"
        if task.id in self.blocked:
            return "blocked:disk"
        if in_(self.vram_wait):
            return "wait:vram"
        if self.bus and (self.bus.current is task or in_(t for t, _ in self.bus.queue)):
            return "xfer"
        if self.gpu and (self.gpu.current is task or in_(self.gpu.queue)):
            return "gpu"
        if in_(self._pending):
            return "new"
        return "ready"

    def snapshot(self, detail: bool = False) -> dict:
        """Gauges for the dashboard. detail=True adds who owns what (for the ownership map and lanes)."""
        snap = {
            "tick": self.now,
            "running": self.running.id if self.running else None,
            "ready": len(self.sched.ready),
            "blocked": len(self.blocked),
            "vram_wait": len(self.vram_wait),
            "ram_used": len(self.pager.resident) if self.pager else 0,
            "ram_total": self.pager.frames if self.pager else 0,
            "vram_used": self.vram.used if self.vram else 0,
            "vram_total": self.vram.frames if self.vram else 0,
            "disk_queue": self.disk.pending if self.disk else 0,
            "gpu_queue": len(self.gpu.queue) if self.gpu else 0,
            "gpu_running": self.gpu.current.id if self.gpu and self.gpu.current else None,
            "bus_busy": bool(self.bus and self.bus.current),
        }
        if detail:
            snap["ram_frames"] = [list(key) for key in self.pager.resident] if self.pager else []  # [task, page], oldest first
            snap["vram_held"] = dict(self.vram.held) if self.vram else {}                           # task -> frames
            snap["bus_task"] = self.bus.current.id if self.bus and self.bus.current else None
            snap["disk"] = {
                "head": self.disk.head,
                "current": {"task": self.disk.current.task_id, "track": self.disk.current.track} if self.disk.current else None,
                "queue": [{"task": r.task_id, "track": r.track} for r in self.disk.queue],
            } if self.disk else None
        return snap

    @property
    def timed_out(self) -> bool:
        return not self.done and self.now >= self.MAX_TICKS

    def run(self, until: int | None = None) -> "Engine":
        """Run to completion, or to `until`. MAX_TICKS stops a thrashing machine that can never finish."""
        while not self.done and self.now < self.MAX_TICKS and (until is None or self.now < until):
            self.step()
        return self
