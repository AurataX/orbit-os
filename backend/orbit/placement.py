"""NEXUS: where should a task run? CPU, GPU, or a CPU+GPU hybrid.

decide(task, engine) -> (placement, reason). The reason lands in the kernel log.
Only tasks that can use the GPU (vram_need > 0) are ever asked.

ADAPTIVE compares three rough finish-time estimates, in ticks:
  CPU-part = CPU work x (1 + tasks already ready)       (fair share of a busy CPU)
  GPU-part = VRAM wait + bus backlog + copy + GPU backlog + GPU ticks for this task
  total    = CPU-part + GPU-part
and picks the smallest. They are estimates, not promises; the log shows the numbers.
"""
from .gpu import split, transfer_ticks

VRAM_WAIT_GUESS = 30  # ticks we assume a task waits for VRAM when the pool is full


class AlwaysCPU:
    name = "CPU"

    def decide(self, task, engine):
        return "cpu", "policy keeps every task on the CPU"


class AlwaysGPU:
    name = "GPU"

    def decide(self, task, engine):
        return "gpu", f"policy offloads everything (parallel={task.parallel})"


class Adaptive:
    name = "ADAPTIVE"

    def decide(self, task, engine):
        ready = len(engine.sched.ready)
        free = engine.vram.frames - engine.vram.used if engine.vram else 0
        vram_wait = 0 if free >= task.vram_need else VRAM_WAIT_GUESS * (len(engine.vram_wait) + 1)
        path = vram_wait + engine.bus.backlog + transfer_ticks(task) + engine.gpu.backlog

        def finish(placement):
            gpu_work, gpu_ticks = split(task, placement)
            gpu_part = path + gpu_ticks if gpu_work else 0
            return (task.burst - gpu_work) * (1 + ready) + gpu_part

        est = {p: finish(p) for p in ("cpu", "gpu", "hybrid")}
        best = min(est, key=lambda p: (est[p], p))
        detail = " ".join(f"{p}={v}" for p, v in est.items())
        return best, f"parallel={task.parallel} estimates {detail}; ready={ready} vram_free={free}"


PLACERS = {p.name: p for p in (AlwaysCPU, AlwaysGPU, Adaptive)}
