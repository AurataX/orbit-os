"""The ORBIT command parser. Commands only operate on a simulator session."""
import shlex

from orbit.compare import RAM_FRAMES, VRAM_FRAMES, compare, what_if
from orbit.logfmt import dmesg, ps
from orbit.metrics import summarize

from session import config_for, policies, validate_policies

HELP = [
    "new --seed 42 --cpu MLFQ --page LRU --disk SCAN --place ADAPTIVE [--ram N --vram N]",
    "step [n]   run [until]   top / ps   free   iostat   gpustat",
    "dmesg [grep] [tail]   checkpoint   rewind <tick>",
    "set cpu=X page=Y disk=Z place=W deadlock=IGNORE|DETECT|AVOID   compare   whatif ...   clear",
    "storm ai-burst|compile-storm|swap-storm|deadlock-demo",
]
MUTATING = {"new", "step", "run", "checkpoint", "rewind", "set", "storm"}


def words_for(line):
    try:
        words = shlex.split(line)
    except ValueError as exc:
        raise ValueError(f"orbit: {exc}") from exc
    return words or ["help"]


def number(value):
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Expected an integer, got {value!r}") from exc


def choices_for(args, separator="="):
    choices = {}
    for entry in args:
        key, sep, value = entry.partition(separator)
        if not sep or not value or key in choices:
            raise ValueError(f"Expected a unique policy assignment, got {entry!r}")
        choices[key] = value
    return validate_policies(choices)


def run_command(session, line) -> list[str]:
    cmd, *args = words_for(line)
    lengths = {"help": (0, 0), "step": (0, 1), "run": (0, 1), "top": (0, 0), "ps": (0, 0),
               "free": (0, 0), "iostat": (0, 0), "gpustat": (0, 0), "dmesg": (0, 2),
               "checkpoint": (0, 0), "rewind": (1, 1), "set": (1, 4), "compare": (0, 0),
               "whatif": (1, 4), "storm": (1, 1)}
    if cmd in lengths and not lengths[cmd][0] <= len(args) <= lengths[cmd][1]:
        raise ValueError(f"orbit: wrong number of arguments to {cmd} (try help)")
    if cmd in ("compare", "whatif"):
        with session.lock:
            engine = session.engine
            seed, tasks = session.config["seed"], session.config["n_tasks"]
            base = policies(engine) | {"ram": engine.pager.frames, "vram": engine.vram.frames}
        return experiment(cmd, args, seed, tasks, base)
    with session.lock:
        return session_command(session, cmd, args)


def session_command(session, cmd, args):
    engine = session.engine
    match cmd:
        case "help":
            return HELP
        case "new":
            keys = {"seed": "seed", "tasks": "n_tasks", "ram": "ram", "vram": "vram"}
            config = {}
            if len(args) % 2:
                raise ValueError("new expects --option value pairs")
            for name, value in zip(args[::2], args[1::2]):
                key = name.removeprefix("--")
                if name not in {"--" + k for k in (*keys, "cpu", "page", "disk", "place", "deadlock")}:
                    raise ValueError(f"Unknown new option {name!r}")
                config[keys.get(key, key)] = number(value) if key in keys else value
            session.reset(config_for(**config))
            return [f"New simulation · seed {session.config['seed']}"]
        case "step" | "run":
            if cmd == "step":
                n = number(args[0]) if args else 1
                if not 1 <= n <= 500:
                    raise ValueError("Step count must be between 1 and 500")
                until = engine.now + n
            else:
                until = number(args[0]) if args else engine.MAX_TICKS
                if not 0 <= until <= engine.MAX_TICKS:
                    raise ValueError(f"Run target must be between 0 and {engine.MAX_TICKS}")
            session.stop("Playback paused for a shell command")
            session.advance(until, action=cmd, params={"until": until})
            state = " · DEADLOCK: nothing can run" if engine.stuck else " · thrashing cap" if engine.timed_out else " · finished" if session.branch.done else ""
            return [f"Tick {engine.now}{state}"]
        case "top" | "ps":
            return [f"Tick {engine.now}", *ps(engine)]
        case "free":
            s = engine.snapshot()
            return [
                f"{'Frames':<14}{'TOTAL':>8}{'USED':>8}{'FREE':>8}{'FAULTS':>8}",
                f"{'RAM':<14}{s['ram_total']:>8}{s['ram_used']:>8}{s['ram_total'] - s['ram_used']:>8}{engine.pager.faults:>8}",
                f"{'VRAM':<14}{s['vram_total']:>8}{s['vram_used']:>8}{s['vram_total'] - s['vram_used']:>8}{'-':>8}",
            ]
        case "iostat":
            disk = engine.disk
            return ["DEVICE   PENDING     HEAD     BUSY    SEEK",
                    f"disk    {disk.pending:>8}{disk.head:>9}{disk.busy_ticks:>9}{disk.head_moved:>8}"]
        case "gpustat":
            s = engine.snapshot()
            pid = s["gpu_running"] if s["gpu_running"] is not None else "-"
            return ["DEVICE   GPU-PID    QUEUE   BUS-ACTIVE   GPU-TICKS   BUS-TICKS",
                    f"gpu     {pid:>8}{s['gpu_queue']:>9}{str(s['bus_busy']):>13}"
                    f"{engine.gpu.busy_ticks:>12}{engine.bus.busy_ticks:>12}"]
        case "dmesg":
            grep = args[0] if args else None
            tail = number(args[1]) if len(args) == 2 else 40
            if not 1 <= tail <= 10000:
                raise ValueError("Tail must be between 1 and 10000")
            return dmesg(engine, grep, tail) or ["No matching kernel events."]
        case "storm":
            session.stop("Playback paused for the shell command")
            ids = session.change("storm", {"name": args[0]})
            return [f"Storm {args[0]} injected at tick {engine.now}: pids {ids[0]}..{ids[-1]}"]
        case "checkpoint":
            return [f"Checkpoint saved at tick {session.checkpoint()}"]
        case "rewind":
            return [f"Rewound to tick {session.rewind(number(args[0]))} · branch {session.active}"]
        case "set":
            choices = choices_for(args)
            session.stop("Playback paused for the policy change")
            session.change("replay", choices)
            return [f"Policies applied at tick {engine.now}: " + " ".join(f"{k}={v}" for k, v in choices.items())]
        case _:
            raise ValueError(f"orbit: command not found: {cmd} (try help)")


def experiment(cmd, args, seed, tasks, base):
    if cmd == "compare":
        lines = [f"Seed {seed} · {tasks} tasks · default machine ({RAM_FRAMES} RAM / {VRAM_FRAMES} VRAM frames)"]
        for dimension, rows in compare(seed, tasks).items():
            lines.extend([dimension.upper(), "POLICY        INT P95   AVG WAIT    TICKS   UNFINISHED"])
            lines.extend(f"{row['policy']:<12}{row['inter_p95_turn']:>9}{row['avg_wait']:>11}"
                         f"{row['makespan']:>9}{row['unfinished']:>13}" for row in rows)
        return lines

    result = what_if(seed, base, base | choices_for(args), tasks)
    if result is None:
        return ["No crisis occurred in the base run."]
    before, after = (summarize(result[key]) for key in ("original", "replayed"))
    return [f"Fresh run from tick 0 · seed {seed} · {base['ram']} RAM / {base['vram']} VRAM frames",
            f"Crisis at {result['crisis_at']} · checkpoint {result['rewound_to']}",
            "METRIC                 BEFORE      AFTER",
            *(f"{key:<21}{before[key]:>8}{after[key]:>11}" for key in
              ("makespan", "avg_wait", "inter_p95_turn", "unfinished"))]
