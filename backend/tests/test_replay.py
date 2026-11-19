from orbit.compare import build_engine, what_if
from orbit.logfmt import dmesg, ps
from orbit.metrics import summarize
from orbit.recorder import Recorder, replay
from orbit.workload import generate

BASE = {"cpu": "FCFS", "page": "FIFO", "disk": "FCFS", "place": "ADAPTIVE"}
ALT = {"cpu": "MLFQ", "page": "LRU", "disk": "SCAN", "place": "ADAPTIVE"}


def test_replay_with_same_policy_reproduces_the_original_run():
    rec = Recorder(build_engine(generate(42), **BASE), every=10)
    original = rec.run()
    again = rec.rewind(100).run()
    assert again.log == original.log
    assert summarize(again) == summarize(original)


def test_rewind_restores_the_past_exactly():
    rec = Recorder(build_engine(generate(42), **BASE), every=10)
    original = rec.run()
    rewound = rec.rewind(97)
    assert rewound.now == 90                                   # latest checkpoint <= 97
    past = [ev for ev in original.log if ev.tick < 90]
    assert rewound.log == past                                 # exactly the recorded past, nothing more


def test_rewind_does_not_disturb_the_original():
    rec = Recorder(build_engine(generate(42), **BASE), every=10)
    original = rec.run()
    before = list(original.log)
    rec.rewind(50).run()
    assert original.log == before


def test_what_if_shares_history_and_changes_the_future():
    r = what_if(42, BASE, ALT)
    assert r is not None
    original, replayed = r["original"], r["replayed"]
    cut = r["rewound_to"]
    # a checkpoint is taken AFTER tick `cut` finished, so events stamped `cut` belong to the next step
    same_past = lambda e: [ev for ev in e.log if ev.tick < cut and ev.kind != "policy"]
    assert same_past(original) == same_past(replayed)
    assert any(ev.kind == "policy" for ev in replayed.log)
    assert summarize(replayed) != summarize(original)
    assert summarize(replayed)["inter_p95_turn"] < summarize(original)["inter_p95_turn"]


def test_replay_swaps_ready_queue_without_losing_tasks():
    rec = Recorder(build_engine(generate(42), **BASE), every=10)
    rec.run(until=60)
    rewound = rec.rewind(60)
    queued = len(rewound.sched.ready)
    replay(rewound, cpu="RR")
    assert rewound.sched.name == "RR" and len(rewound.sched.ready) == queued
    assert rewound.run().done


def test_kernel_log_and_ps_are_readable():
    e = build_engine(generate(42)).run(until=120)
    lines = dmesg(e)
    assert lines and lines[0].startswith("[") and "arrive" in lines[0]
    assert any("nexus" in ln and "estimates" in ln for ln in lines)
    table = ps(e)
    assert table[0].startswith(" PID") and len(table) == len(e.tasks) + 1
    assert {"running", "ready", "done"} & {row.split()[2] for row in table[1:]}
