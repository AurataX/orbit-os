from orbit.deadlock import find_cycle, request_resources, safe_sequence

# Classic textbook state: 5 processes, 3 resource types
AVAILABLE = [3, 3, 2]
MAX = [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]]
ALLOC = [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]]
NEED = [[m - a for m, a in zip(mr, ar)] for mr, ar in zip(MAX, ALLOC)]


def state():
    return list(AVAILABLE), [r[:] for r in ALLOC], [r[:] for r in NEED]


def test_safe_state_has_sequence():
    # first-fit gives 1,3,0,2,4; the textbook shows another valid order (1,3,4,0,2)
    order = safe_sequence(AVAILABLE, ALLOC, NEED)
    work = list(AVAILABLE)
    for i in order:                      # replay it: every process must fit when its turn comes
        assert all(n <= w for n, w in zip(NEED[i], work))
        work = [w + a for w, a in zip(work, ALLOC[i])]
    assert sorted(order) == [0, 1, 2, 3, 4]


def test_safe_request_granted():
    avail, alloc, need = state()
    assert request_resources(1, [1, 0, 2], avail, alloc, need)
    assert avail == [2, 3, 0]


def test_unsafe_request_denied_and_state_untouched():
    avail, alloc, need = state()
    request_resources(1, [1, 0, 2], avail, alloc, need)
    before = (list(avail), [r[:] for r in alloc])
    assert not request_resources(0, [0, 2, 0], avail, alloc, need)  # would be unsafe
    assert (avail, alloc) == before


def test_unsafe_state_detected():
    assert safe_sequence([0, 0, 0], [[1, 0, 0], [0, 1, 0]], [[0, 1, 0], [1, 0, 0]]) is None


def test_wait_for_cycle():
    cycle = find_cycle({"A": {"B"}, "B": {"C"}, "C": {"A"}})
    assert cycle == ["A", "B", "C", "A"]
    assert find_cycle({"A": {"B"}, "B": set()}) is None
