import json

import pytest

from orbit.compare import build_engine
from orbit.cpu_sched import Priority
from orbit.engine import Engine
from orbit.logfmt import dmesg, ps
from orbit.metrics import summarize
from orbit.models import Task
from orbit.recorder import Recorder
from orbit.workload import generate


def machine(**kw):
    return build_engine(generate(42), **kw)


# ---- detailed snapshot -------------------------------------------------
def test_detail_snapshot_shows_who_owns_what_and_is_json_safe():
    e = machine().run(until=60)
    snap = e.snapshot(detail=True)
    assert len(snap["ram_frames"]) == snap["ram_used"]
    assert all(len(f) == 2 for f in snap["ram_frames"])
    assert sum(snap["vram_held"].values()) == snap["vram_used"]
    assert snap["disk"]["head"] >= 0 and isinstance(snap["disk"]["queue"], list)
    json.dumps(snap)                                    # the API will send this as-is
    assert "ram_frames" not in e.snapshot()             # the cheap form stays cheap


# ---- inject ---------------------------------------------------------------
def test_inject_adds_tasks_that_arrive_now_and_finish():
    e = machine().run(until=50)
    n = len(e.tasks)
    ids = e.inject("ai", 3)
    assert len(e.tasks) == n + 3 and len(set(t.id for t in e.tasks)) == n + 3
    e.step()
    assert {ev.task_id for ev in e.log if ev.kind == "arrive" and ev.tick == 50} >= set(ids)
    assert e.run().done


def test_inject_is_deterministic():
    def run():
        e = machine().run(until=50)
        e.storm("swap-storm")
        return e.run()
    assert run().log == run().log


def test_inject_and_storm_reject_bad_input():
    e = machine()
    for bad in (lambda: e.inject("gaming", 1), lambda: e.inject("ai", 0), lambda: e.storm("nope")):
        with pytest.raises(ValueError):
            bad()


def test_swap_storm_causes_more_page_faults():
    calm = machine().run()
    stormy = machine().run(until=50)
    stormy.storm("swap-storm")
    stormy.run()
    assert stormy.pager.faults > calm.pager.faults


# ---- resize -----------------------------------------------------------------
def test_shrinking_ram_evicts_immediately():
    e = machine().run(until=60)
    assert e.pager.frames == 60 and len(e.pager.resident) > 30
    e.resize(ram=30)
    assert len(e.pager.resident) <= 30 and e.pager.frames == 30
    assert any(ev.kind == "resize" and "RAM 60 -> 30" in ev.info for ev in e.log)
    assert e.run().done


def test_growing_vram_grants_waiters():
    e = machine(place="GPU", vram=8)
    while not e.vram_wait and not e.done:
        e.step()
    assert e.vram_wait
    e.resize(vram=64)
    assert not e.vram_wait
    assert e.run().done


def test_shrinking_vram_below_need_falls_back_to_cpu_instead_of_starving():
    e = machine(place="GPU").run(until=60)
    e.resize(vram=2)                                   # nothing fits any more
    assert e.run().done
    assert any(ev.kind == "place" and "falling back" in ev.info for ev in e.log)


def test_resize_rejects_nonsense():
    with pytest.raises(ValueError):
        machine().resize(ram=0)


# ---- kill ----------------------------------------------------------------------
def test_kill_works_in_every_process_state_and_the_run_still_finishes():
    seen = set()
    for tick in (20, 40, 60, 80, 120):
        e = machine(place="GPU", vram=12).run(until=tick)
        victims = {}
        for t in e.tasks:
            if t.finish is None:
                victims.setdefault(e.state_of(t), t)       # one victim per state
        for state, task in victims.items():
            e.kill(task.id)
            seen.add(state)
            assert e.state_of(task) == "killed"
            assert all(key[0] != task.id for key in e.pager.resident)   # RAM freed
            assert task.id not in e.vram.held                            # VRAM freed
        assert e.run().done, f"stuck after killing {sorted(victims)} at tick {tick}"
    assert {"ready", "blocked:disk", "new"} <= seen, seen


def test_killed_tasks_are_reported_not_counted_as_completed():
    e = machine().run(until=60)
    victim = next(t for t in e.tasks if t.finish is None)
    e.kill(victim.id)
    m = summarize(e.run())
    assert m["killed"] == 1 and m["unfinished"] == 0
    assert "killed" in {row.split()[2] for row in ps(e)[1:]}


def test_kill_rejects_unknown_or_finished_pid():
    e = machine().run()
    with pytest.raises(ValueError):
        e.kill(9999)
    with pytest.raises(ValueError):
        e.kill(e.tasks[0].id)


# ---- boost ------------------------------------------------------------------------
def test_boost_changes_who_runs_first_under_priority_scheduling():
    tasks = [Task(i, "dev", 0, 5, 2) for i in range(3)]
    e = Engine(tasks, Priority())
    e.step()                                                 # all three arrive, pid 0 starts
    e.boost(2, -1)
    e.run()
    finish_order = sorted(tasks, key=lambda t: t.finish)
    assert [t.id for t in finish_order] == [0, 2, 1]           # 0 was already running; boosted 2 beats 1


def test_boost_rejects_unknown_pid():
    with pytest.raises(ValueError):
        machine().boost(9999, 0)


# ---- log retention -------------------------------------------------------------------
def test_log_is_bounded_and_absolute_index_is_preserved():
    full = machine().run()
    small = machine()
    small.log_limit = 100
    small.run()
    assert len(small.log) <= 110 and small.log_base > 0
    assert small.log_base + len(small.log) == len(full.log)   # nothing lost from the count
    assert small.log == full.log[-len(small.log):]            # and what is kept is the newest tail


# ---- everything together ---------------------------------------------------------------
def test_actions_survive_checkpoint_and_rewind_and_render_in_the_log():
    rec = Recorder(machine(), every=10)
    rec.run(until=50)
    rec.engine.storm("ai-burst")
    rec.engine.resize(ram=40)
    rec.run(until=70)
    rewound = rec.rewind(70)
    rewound.kill(next(t.id for t in rewound.tasks if t.finish is None))
    rewound.boost(next(t.id for t in rewound.tasks if t.finish is None), 0)
    assert rewound.run().done
    text = "\n".join(dmesg(rewound))
    for kind in ("inject", "resize", "kill", "boost"):
        assert f" {kind} " in text
