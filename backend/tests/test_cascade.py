import copy

from orbit.compare import build_engine
from orbit.cpu_sched import MLFQ
from orbit.engine import Engine
from orbit.workload import generate


def cpu_work(e):
    return sum(t.burst - t.gpu_work for t in e.tasks)  # what is left for the CPU after GPU offload


def test_everything_still_finishes_with_memory_disk_vram_gpu():
    for cpu in ("FCFS", "RR", "MLFQ"):
        for place in ("CPU", "GPU", "ADAPTIVE"):
            e = build_engine(generate(3), cpu, "LRU", "SCAN", place).run()
            assert e.done
            assert e.busy_ticks == cpu_work(e)  # faults never lose or add CPU work


def test_page_faults_block_tasks_and_slow_the_run():
    tasks = generate(3)
    plain = Engine(copy.deepcopy(tasks), MLFQ()).run()
    full = build_engine(tasks, "MLFQ", "LRU", "SCAN", "CPU").run()
    assert any(ev.kind == "block" for ev in full.log)
    assert full.now > plain.now  # I/O stalls cost time


def test_tiny_ram_causes_more_faults():
    tasks = generate(3)
    small = build_engine(tasks, ram=20).run()
    big = build_engine(tasks, ram=200).run()
    assert small.pager.faults > big.pager.faults


def test_vram_pressure_stalls_gpu_tasks():
    e = build_engine(generate(3), place="GPU", vram=8).run()  # room for ONE AI task
    assert e.gpu_stall_ticks > 0
    assert any(ev.kind == "vram_wait" for ev in e.log)


def test_gpu_path_is_cpu_then_bus_then_gpu():
    e = build_engine(generate(3), place="GPU").run()
    task = next(t for t in e.tasks if t.placement == "gpu")
    kinds = [ev.kind for ev in e.log if ev.task_id == task.id]
    assert kinds.index("xfer") < kinds.index("gpu_queue") < kinds.index("gpu_run") < kinds.index("finish")
    assert e.bus.busy_ticks > 0 and e.gpu.busy_ticks > 0


def test_interactive_tasks_never_use_the_gpu():
    e = build_engine(generate(3), place="GPU").run()
    assert all(t.placement == "cpu" for t in e.tasks if t.kind == "interactive")


def test_adaptive_logs_its_reason_and_mixes_devices():
    e = build_engine(generate(42), place="ADAPTIVE").run()
    places = [ev for ev in e.log if ev.kind == "place"]
    assert places and all("estimates" in ev.info for ev in places)
    assert len({t.placement for t in e.tasks if t.vram_need}) > 1


def test_crisis_is_marked_when_disk_queue_explodes():
    e = build_engine(generate(42), "FCFS", "FIFO", "FCFS", "ADAPTIVE").run()
    assert e.crisis_at is not None
    assert any(ev.kind == "crisis" and ev.tick == e.crisis_at for ev in e.log)


def test_thrashing_run_is_capped_not_hung():
    e = build_engine(generate(42), "FCFS", "FIFO", "FCFS", "CPU", ram=30).run()  # tasks keep evicting each other
    assert e.timed_out and e.now == e.MAX_TICKS
    assert not e.done


def test_cascade_run_is_deterministic():
    tasks = generate(9)
    a = build_engine(tasks).run()
    b = build_engine(tasks).run()
    assert a.log == b.log


def test_mlfq_does_not_demote_on_io_wake():
    e = build_engine(generate(3), place="CPU").run()
    woke = {ev.task_id for ev in e.log if ev.kind == "wake"}
    preempted = {ev.task_id for ev in e.log if ev.kind == "preempt"}
    never_preempted = woke - preempted
    assert never_preempted and all(e.sched.level[i] == 0 for i in never_preempted)
