"""In-memory web sessions around the existing engine and recorder."""
import copy
from collections import deque
from dataclasses import dataclass, field
from threading import RLock

from orbit.compare import DEFAULT, RAM_FRAMES, VRAM_FRAMES, build_engine
from orbit.cpu_sched import POLICIES
from orbit.locks import DEADLOCK_POLICIES
from orbit.logfmt import LEVEL, SUBSYSTEM, format_event
from orbit.memory import PAGE_POLICIES
from orbit.metrics import p95, summarize
from orbit.placement import PLACERS
from orbit.recorder import Recorder, replay
from orbit.storage import DISK_POLICIES
from orbit.workload import generate

REGISTRIES = {"cpu": POLICIES, "page": PAGE_POLICIES, "disk": DISK_POLICIES, "place": PLACERS,
              "deadlock": DEADLOCK_POLICIES}
LIVE = {
    "inject": "inject", "storm": "storm", "resize": "resize",
    "kill": "kill", "boost": "boost",
}


def validate_policies(choices):
    for key, name in choices.items():
        if name not in REGISTRIES.get(key, {}):
            raise ValueError(f"Unknown policy {key}={name}; choose from {', '.join(REGISTRIES.get(key, {}))}")
    return choices


def policies(engine):
    return {
        "cpu": engine.sched.name, "page": engine.pager.policy.name,
        "disk": engine.disk.policy.name, "place": engine.placer.name, "deadlock": engine.deadlock.name,
    }


def config_for(seed=42, n_tasks=40, ram=RAM_FRAMES, vram=VRAM_FRAMES, **choices):
    if not 1 <= n_tasks <= 200:
        raise ValueError("Tasks must be between 1 and 200")
    if not 1 <= ram <= 200 or not 0 <= vram <= 64:
        raise ValueError("RAM must be 1–200 frames and VRAM 0–64 frames")
    return dict(seed=seed, n_tasks=n_tasks, ram=ram, vram=vram, **(DEFAULT | validate_policies(choices)))


def task_row(engine, task):
    return dict(pid=task.id, kind=task.kind, state=engine.state_of(task), placement=task.placement,
                priority=task.priority, burst=task.burst, left=task.remaining)


def event_rows(engine, since=None):
    kinds = {task.id: task.kind for task in engine.tasks}
    start = 0 if since is None else max(0, since - engine.log_base)
    return [
        dict(index=index, tick=ev.tick, kind=ev.kind, subsystem=SUBSYSTEM[ev.kind],
             level=LEVEL.get(ev.kind, "INFO"), pid=ev.task_id if ev.task_id >= 0 else None,
             task_kind=kinds.get(ev.task_id), info=ev.info, text=format_event(ev, kinds))
        for index, ev in enumerate(engine.log[start:], engine.log_base + start)
    ]


class WebRecorder(Recorder):
    def save(self):
        # Log entries are append-only. Share their objects, with a separate list per checkpoint.
        engine = self.engine
        self.checkpoints[engine.now] = copy.deepcopy(engine, {id(ev): ev for ev in engine.log})
        return engine.now


@dataclass
class Branch:
    recorder: Recorder
    parent: str | None = None
    rewound_to: int | None = None
    journal: list = field(default_factory=list)
    pending: deque = field(default_factory=deque)
    checkpoints_at: dict = field(default_factory=lambda: {0: 0})
    manual: set = field(default_factory=set)
    policy_effects: list = field(default_factory=list)

    @property
    def engine(self):
        return self.recorder.engine

    @property
    def done(self):
        return self.engine.done and not self.pending

    def save(self):
        tick = self.recorder.save()
        self.checkpoints_at[tick] = len(self.journal)
        return tick

    def summary(self):
        engine = self.engine
        if self.done or engine.timed_out:
            return summarize(engine) if engine.now else summarize_at_zero(engine)
        return None


def summarize_at_zero(engine):
    """The engine summary assumes a positive elapsed time."""
    snapshot = copy.copy(engine)
    snapshot.now = 1
    return summarize(snapshot) | {"makespan": 0}


class Session:
    def __init__(self, config):
        self.lock = RLock()
        self.actions = []
        self.action_version = 0
        self.controller = None
        self.speed = None
        self.play_started = None
        self.revision = 0
        self.generation = -1
        self.reset(config)

    def reset(self, config):
        engine = build_engine(generate(config["seed"], config["n_tasks"]),
                              **{key: val for key, val in config.items() if key not in ("seed", "n_tasks")})
        self.stop()
        self.config = config
        self.generation += 1
        self.branches = {"main": Branch(WebRecorder(engine))}
        self.active = "main"
        self.cursor = 0
        self.actions.clear()
        self.record(0, "new", config, f'{len(engine.tasks)} tasks seeded · {config["ram"]} RAM frames')
        self.revision += 1

    @property
    def branch(self):
        return self.branches[self.active]

    @property
    def engine(self):
        return self.branch.engine

    def record(self, tick, action, params, effect, branch=None):
        self.actions.append(dict(tick=tick, action=action, params=params, effect=effect, branch=branch or self.active))
        self.action_version += 1
        return self.actions[-1]

    def stop(self, reason=None):
        if self.controller is not None and reason:
            tick = self.engine.now
            self.record(tick, "pause", {}, f"{reason} · tick {self.play_started} → {tick}")
        self.controller = self.speed = self.play_started = None

    def checkpoint(self):
        tick = self.branch.save()
        self.branch.manual.add(tick)
        self.record(tick, "checkpoint", {}, f"Saved machine state at tick {tick}")
        self.revision += 1
        return tick

    def rewind(self, tick):
        current = self.branch
        if not 0 <= tick <= current.engine.now:
            raise ValueError(f"Rewind tick must be between 0 and {current.engine.now}")
        engine = current.recorder.rewind(tick)
        at = engine.now
        cut = current.checkpoints_at[at]
        branch = Branch(WebRecorder(engine), self.active, at, current.journal[:cut],
                        deque([*current.journal[cut:], *current.pending]))
        branch.recorder.checkpoints.update({t: e for t, e in current.recorder.checkpoints.items() if t < at})
        branch.checkpoints_at = {t: n for t, n in current.checkpoints_at.items() if t <= at}
        branch.manual = {t for t in current.manual if t <= at}
        self.stop("Playback paused for rewind")
        self.active = f"branch-{len(self.branches)}"
        self.branches[self.active] = branch
        self.cursor = engine.log_base + len(engine.log)
        self.record(at, "rewind", {"tick": tick}, f"Tick {current.engine.now} → {at} · original branch kept")
        self.revision += 1
        return at

    def change(self, action, params, branch_id=None, inherited=False):
        branch_id = branch_id or self.active
        branch = self.branches[branch_id]
        engine = branch.engine
        tick = engine.now
        before = engine.snapshot()
        previous_policies = policies(engine)
        if action == "replay":
            validate_policies(params)
            if not params:
                raise ValueError("Choose at least one policy to apply")
            replay(engine, **params)
            effect = ", ".join(f"{key} {previous_policies[key]} → {name}" for key, name in params.items())
        else:
            args = dict(params)
            if "pid" in args:
                args["task_id"] = args.pop("pid")
            result = getattr(engine, LIVE[action])(**args)
            after = engine.snapshot()
            match action:
                case "inject" | "storm":
                    effect = f"{len(result)} tasks queued for admission · PID {result[0]}–{result[-1]}"
                case "resize":
                    effect = (f"RAM {before['ram_total']} → {after['ram_total']}, "
                              f"VRAM {before['vram_total']} → {after['vram_total']} frames · "
                              f"{before['ram_used'] - after['ram_used']} RAM pages evicted")
                case "kill":
                    effect = (f"PID {params['pid']} killed · RAM {before['ram_used']} → {after['ram_used']} "
                              f"and VRAM {before['vram_used']} → {after['vram_used']} used")
                case "boost":
                    effect = engine.log[-1].info
        entry = self.record(tick, f"replayed {action}" if inherited else action, params, effect, branch_id)
        if action == "replay":
            # A fork repeats future workload changes, leaving future policy choices to the operator.
            branch.policy_effects.append((entry, effect, before["disk_queue"], engine.pager.faults))
        else:
            branch.journal.append((tick, action, dict(params)))
        self.revision += 1
        return result if action in ("inject", "storm") else None

    def advance(self, until, branch_id=None, action=None, params=None):
        branch_id = branch_id or self.active
        branch = self.branches[branch_id]
        engine = branch.engine
        start = engine.now
        faults = engine.pager.faults
        while True:
            while branch.pending and branch.pending[0][0] == engine.now:
                tick, kind, args = branch.pending.popleft()
                try:
                    self.change(kind, args, branch_id, inherited=True)
                except ValueError as exc:
                    self.record(tick, f"skipped {kind}", args, str(exc), branch_id)
            if branch.done or engine.stuck or engine.now >= engine.MAX_TICKS or engine.now >= until:
                break
            engine.step()
            if engine.now % branch.recorder.every == 0:
                branch.save()
        if engine.now > start and branch.policy_effects:
            for entry, effect, queue, faults_before in branch.policy_effects:
                entry["effect"] = (f"{effect} · after {engine.now - entry['tick']} ticks, "
                                   f"disk queue {queue} → {engine.disk.pending}, "
                                   f"faults {faults_before} → {engine.pager.faults}")
            branch.policy_effects.clear()
            self.action_version += 1
        if branch_id == self.active and (branch.done or engine.timed_out):
            self.stop("Playback stopped: deadlock, nothing can run" if engine.stuck else "Playback stopped at the tick cap" if engine.timed_out else "Playback completed the branch")
        if action:
            self.record(start, action, params or {}, (
                f"Tick {start} → {engine.now} · page faults {faults} → {engine.pager.faults}"
            ), branch_id)
        self.revision += 1

    def frame(self, detail=False, since=None, branch_id=None):
        branch_id = branch_id or self.active
        branch = self.branches[branch_id]
        engine = branch.engine
        end = engine.log_base + len(engine.log)
        events = event_rows(engine, self.cursor if since is None and branch_id == self.active else since)
        if since is None and branch_id == self.active:
            self.cursor = end
        tasks = []
        for task in engine.tasks:
            row = task_row(engine, task)
            del row["pid"]
            tasks.append(dict(id=task.id, **row))
        responses = [t.response for t in engine.tasks if t.kind == "interactive" and t.first_run is not None]
        return {
            "snapshot": engine.snapshot(detail),
            "status": dict(done=branch.done, timed_out=engine.timed_out, crisis_at=engine.crisis_at,
                           policies=policies(engine), branch=branch_id, playing=branch_id == self.active and self.controller is not None,
                           checkpoints=sorted(branch.recorder.checkpoints), manual=sorted(branch.manual)),
            "metrics": dict(cpu_util=round(100 * engine.busy_ticks / max(1, engine.now), 1),
                            busy_ticks=engine.busy_ticks, page_faults=engine.pager.faults,
                            inter_p95_resp=p95(responses) if responses else None),
            "tasks": tasks, "events": events, "summary": branch.summary(),
            "cursor": end, "log_base": engine.log_base, "revision": self.revision,
            "generation": self.generation, "action_count": len(self.actions), "action_version": self.action_version,
            "config": self.config,
        }

    def branch_rows(self):
        return [
            dict(id=key, label="Original" if key == "main" else f"Replay {key.split('-')[-1]}",
                 parent=branch.parent, rewound_to=branch.rewound_to, tick=branch.engine.now,
                 policies=policies(branch.engine), summary=branch.summary())
            for key, branch in self.branches.items()
        ]
