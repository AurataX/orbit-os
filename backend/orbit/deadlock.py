"""Deadlock tools: Banker's algorithm (avoidance) and wait-for-graph cycle detection.

Vectors are lists of ints, one slot per resource type (e.g. CPU slot, VRAM, disk channel).
"""


def _fits(need: list[int], work: list[int]) -> bool:
    return all(n <= w for n, w in zip(need, work))


def safe_sequence(available, allocation, need) -> list[int] | None:
    """Return an order in which every process can finish, or None if the state is unsafe."""
    work = list(available)
    done = [False] * len(allocation)
    order = []
    while len(order) < len(allocation):
        for i, finished in enumerate(done):
            if not finished and _fits(need[i], work):
                work = [w + a for w, a in zip(work, allocation[i])]  # i finishes, returns its resources
                done[i] = True
                order.append(i)
                break
        else:
            return None
    return order


def request_resources(i, request, available, allocation, need) -> bool:
    """Banker's: grant only if the resulting state is still safe. Mutates the state when granted."""
    if not _fits(request, need[i]) or not _fits(request, available):
        return False
    new_avail = [a - r for a, r in zip(available, request)]
    new_alloc = [row[:] for row in allocation]
    new_need = [row[:] for row in need]
    new_alloc[i] = [a + r for a, r in zip(new_alloc[i], request)]
    new_need[i] = [n - r for n, r in zip(new_need[i], request)]
    if safe_sequence(new_avail, new_alloc, new_need) is None:
        return False
    available[:] = new_avail
    allocation[:] = new_alloc
    need[:] = new_need
    return True


def find_cycle(wait_for: dict[str, set[str]]) -> list[str] | None:
    """Wait-for graph {who: {whom they wait for}}. A cycle means deadlock."""
    visiting, visited = [], set()

    def dfs(node):
        if node in visiting:
            return visiting[visiting.index(node):] + [node]
        if node in visited:
            return None
        visiting.append(node)
        for nxt in sorted(wait_for.get(node, ())):
            cycle = dfs(nxt)
            if cycle:
                return cycle
        visiting.pop()
        visited.add(node)
        return None

    for start in sorted(wait_for):
        cycle = dfs(start)
        if cycle:
            return cycle
    return None
