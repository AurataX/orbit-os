"""Seeded scenario generator: same seed => exactly the same tasks."""
import random

from .models import AI, BACKGROUND, DEV, INTERACTIVE, PRIORITY, Task

# kind -> (share of tasks, (min burst, max burst))
MIX = {
    INTERACTIVE: (0.40, (1, 4)),
    AI: (0.15, (20, 40)),
    DEV: (0.25, (8, 20)),
    BACKGROUND: (0.20, (10, 30)),
}


HOT_PAGES = {INTERACTIVE: 3, AI: 10, DEV: 8, BACKGROUND: 6}  # working-set size per class
# Which classes can use the GPU, and how data-parallel they are. Interactive tasks are tiny and
# latency-sensitive: copying data to the GPU would cost more than the work, so they stay CPU-only.
VRAM_NEED = {AI: 8, DEV: 4, BACKGROUND: 2}
PARALLEL = {INTERACTIVE: 0.0, AI: 0.95, DEV: 0.6, BACKGROUND: 0.5}


def page_refs(rng: random.Random, burst: int, hot: int) -> list[int]:
    """85% of accesses hit the hot set, 15% wander to a colder range (locality)."""
    return [rng.randrange(hot) if rng.random() < 0.85 else rng.randrange(hot, 2 * hot)
            for _ in range(burst)]


# Named surges the dashboard can inject while a run is live: {class: how many tasks}
STORMS = {
    "ai-burst": {AI: 4},
    "compile-storm": {DEV: 8},
    "swap-storm": {DEV: 6, BACKGROUND: 6},   # many big working sets at once => RAM pressure
}


DEADLOCK_STORM = "deadlock-demo"


def make_deadlock_pair(rng: random.Random, first_id: int, arrival: int) -> list[Task]:
    """Two build jobs taking the same two locks in opposite order: the classic deadlock recipe.
    They are CPU-only so the lock story is not mixed up with GPU placement."""
    pair = []
    for i, locks in enumerate((("db", "cache"), ("cache", "db"))):
        task = make_task(rng, first_id + i, DEV, arrival)
        task.locks, task.vram_need = locks, 0
        pair.append(task)
    return pair


def make_task(rng: random.Random, task_id: int, kind: str, arrival: int) -> Task:
    lo, hi = MIX[kind][1]
    burst = rng.randint(lo, hi)
    refs = page_refs(rng, burst, HOT_PAGES[kind])
    return Task(task_id, kind, arrival, burst, PRIORITY[kind], refs, VRAM_NEED.get(kind, 0), PARALLEL[kind])


def generate(seed: int, n_tasks: int = 40, span: int = 120) -> list[Task]:
    rng = random.Random(seed)
    kinds = list(MIX)
    weights = [MIX[k][0] for k in kinds]
    tasks = []
    for i in range(n_tasks):
        kind = rng.choices(kinds, weights)[0]
        tasks.append(make_task(rng, i, kind, rng.randrange(span)))
    return sorted(tasks, key=lambda t: (t.arrival, t.id))
