import copy

from orbit.cpu_sched import FCFS, MLFQ, SJF, RoundRobin
from orbit.engine import Engine
from orbit.models import Task
from orbit.workload import generate


def textbook():
    # classic example: arrivals 0,1,2 with bursts 8,4,2
    return [Task(0, "dev", 0, 8, 2), Task(1, "dev", 1, 4, 2), Task(2, "dev", 2, 2, 2)]


def avg_wait(e):
    return sum(t.wait for t in e.tasks) / len(e.tasks)


def test_fcfs_textbook():
    e = Engine(textbook(), FCFS()).run()
    assert [t.finish for t in e.tasks] == [8, 12, 14]
    assert round(avg_wait(e), 2) == 5.67  # waits are 0, 7, 10


def test_sjf_beats_fcfs_on_wait():
    fcfs = Engine(textbook(), FCFS()).run()
    sjf = Engine(textbook(), SJF()).run()
    assert avg_wait(sjf) < avg_wait(fcfs)


def test_round_robin_preempts():
    e = Engine(textbook(), RoundRobin(2)).run()
    assert any(ev.kind == "preempt" for ev in e.log)
    assert all(t.finish is not None for t in e.tasks)


def test_all_work_is_done():
    for policy in (FCFS(), SJF(), RoundRobin(4), MLFQ()):
        e = Engine(generate(1), policy).run()
        assert e.busy_ticks == sum(t.burst for t in e.tasks)


def test_deterministic_replay():
    tasks = generate(7)
    a = Engine(copy.deepcopy(tasks), MLFQ()).run()
    b = Engine(copy.deepcopy(tasks), MLFQ()).run()
    assert a.log == b.log


def test_same_seed_same_workload():
    assert generate(5) == generate(5)
