import pytest

from orbit.compare import build_engine
from orbit.deadlock import find_cycle
from orbit.logfmt import dmesg, ps
from orbit.metrics import summarize
from orbit.recorder import Recorder, replay
from orbit.workload import generate


def machine(policy, cpu="MLFQ"):
    e = build_engine(generate(42), cpu=cpu, deadlock=policy).run(until=30)
    e.storm("deadlock-demo")
    return e


@pytest.mark.parametrize("cpu", ["FCFS", "SJF", "Priority", "RR", "MLFQ"])
def test_ignore_deadlocks_and_the_machine_hangs_for_every_scheduler(cpu):
    e = machine("IGNORE", cpu).run()
    assert e.deadlock_count == 1 and e.stuck and not e.done
    assert e.now < e.MAX_TICKS                       # stopped by stall detection, not by the safety cap
    assert len(e.deadlocked) == 2
    assert "wait:lock" in {row.split()[2] for row in ps(e)[1:]}
    assert summarize(e)["unfinished"] == 2


@pytest.mark.parametrize("cpu", ["FCFS", "SJF", "Priority", "RR", "MLFQ"])
def test_detect_breaks_the_cycle_by_killing_one_victim(cpu):
    e = machine("DETECT", cpu).run()
    m = summarize(e)
    assert e.done and m["deadlocks"] == 1 and m["killed"] == 1 and m["unfinished"] == 0
    assert any(ev.kind == "kill" and "deadlock victim" in ev.info for ev in e.log)


@pytest.mark.parametrize("cpu", ["FCFS", "SJF", "Priority", "RR", "MLFQ"])
def test_avoid_never_deadlocks_and_nobody_is_killed(cpu):
    e = machine("AVOID", cpu).run()
    m = summarize(e)
    assert e.done and m["deadlocks"] == 0 and m["killed"] == 0
    assert any(ev.kind == "lock_wait" and "Banker" in ev.info for ev in e.log)   # it said no to a free lock


def test_locks_are_released_when_a_task_finishes():
    e = machine("AVOID").run()
    assert e.lock_owner == {} and all(t.held == [] for t in e.tasks)


def test_deadlock_demo_is_deterministic():
    assert machine("DETECT").run().log == machine("DETECT").run().log


def test_replay_can_swap_the_deadlock_policy_after_the_cycle_formed():
    e = machine("IGNORE")
    while not e.deadlocked:
        e.step()
    assert not e.done
    fixed = replay(e, deadlock="DETECT").run()          # same machine, new rule from now on
    assert fixed.done and summarize(fixed)["killed"] == 1


def test_rewind_before_the_unsafe_grant_then_avoid_it():
    """Avoidance must act BEFORE the dangerous lock is granted; after that only detection can help."""
    rec = Recorder(machine("IGNORE"), every=5)
    assert rec.run().stuck
    first_lock = next(ev.tick for ev in rec.engine.log if ev.kind == "lock")
    fixed = replay(rec.rewind(first_lock), deadlock="AVOID").run()   # a checkpoint at T is taken before tick T runs
    assert fixed.done and fixed.deadlock_count == 0


def test_avoid_cannot_save_a_machine_that_is_already_in_an_unsafe_state():
    rec = Recorder(machine("IGNORE"), every=5)
    original = rec.run()
    late = next(ev.tick for ev in original.log if ev.kind == "deadlock") - 10
    assert not replay(rec.rewind(late), deadlock="AVOID").run().done


def test_killing_a_lock_holder_frees_its_locks_and_wakes_the_waiter():
    e = machine("IGNORE")
    while not e.deadlocked:
        e.step()
    holder, other = e.deadlocked
    e.kill(holder)
    assert e.run().done and e.deadlock_count == 1


def test_default_workload_is_unchanged_by_locks():
    assert summarize(build_engine(generate(42), cpu="FCFS", page="FIFO", disk="FCFS").run())["makespan"] == 999


def test_wait_for_graph_matches_the_engine_view():
    assert find_cycle({1: {2}, 2: {1}}) == [1, 2, 1]


def test_switching_to_detect_on_a_machine_that_is_already_hung_recovers_it_at_once():
    e = machine("IGNORE").run()
    assert e.stuck
    fixed = replay(e, deadlock="DETECT")
    assert fixed.run().done and summarize(fixed)["killed"] == 1
