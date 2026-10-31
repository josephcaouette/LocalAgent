import heapq
class CycleError(ValueError):
    def __init__(self, cycle):
        super().__init__(f"cycle: {cycle}")
        self.cycle = cycle
def order(deps):
    nodes = set(deps) | {d for ds in deps.values() for d in ds}
    need = {n: set(deps.get(n, ())) for n in nodes}
    users = {n: set() for n in nodes}
    for n, ds in need.items():
        for d in ds:
            users[d].add(n)
    ready = [n for n in nodes if not need[n]]; heapq.heapify(ready); out = []
    while ready:
        n = heapq.heappop(ready); out.append(n)
        for u in users[n]:
            need[u].discard(n)
            if not need[u]:
                heapq.heappush(ready, u)
    if len(out) == len(nodes):
        return out
    left = {n for n in nodes if n not in out}          # walk dependencies until a node repeats
    start = min(left); path = [start]; seen = {start: 0}
    while True:
        nxt = min(d for d in deps.get(path[-1], ()) if d in left)
        if nxt in seen:
            return_cycle = path[seen[nxt]:] + [nxt]
            raise CycleError(return_cycle)
        seen[nxt] = len(path); path.append(nxt)
