from orbit.memory import FIFO, LRU, VRAM, count_faults
from orbit.storage import FCFS, SCAN, SSTF, Request

BELADY = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
TEXTBOOK = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]


def test_fifo_belady_anomaly():
    assert count_faults(BELADY, 3, FIFO()) == 9
    assert count_faults(BELADY, 4, FIFO()) == 10  # more frames, MORE faults


def test_lru_textbook_string():
    assert count_faults(TEXTBOOK, 3, LRU()) == 12
    assert count_faults(TEXTBOOK, 3, FIFO()) == 15


def test_vram_all_or_nothing():
    v = VRAM(10)
    assert v.alloc(1, 8)
    assert not v.alloc(2, 4)   # only 2 free
    v.release(1)
    assert v.alloc(2, 4)


def head_movement(policy, start, tracks):
    queue = [Request(i, i, t) for i, t in enumerate(tracks)]
    head, direction, total = start, 1, 0
    while queue:
        req, direction = policy.pick(queue, head, direction)
        queue.remove(req)
        total += abs(req.track - head)
        head = req.track
    return total


TRACKS = [98, 183, 37, 122, 14, 124, 65, 67]  # classic textbook queue, head at 53


def test_disk_policies_textbook():
    assert head_movement(FCFS(), 53, TRACKS) == 640
    assert head_movement(SSTF(), 53, TRACKS) == 236
    assert head_movement(SCAN(), 53, TRACKS) == 299  # up first, reverse at 183
