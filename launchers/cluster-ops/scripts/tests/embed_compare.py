"""Compare two embedding servers on the memory store's own texts, e.g. after moving the model.

    python embed_compare.py [URL_A] [URL_B]          (defaults: Node 3, then config.EMBED_URL)

For every stored entry it rebuilds the text reindex_memory.py embeds, embeds it on both servers,
and prints the cosine between the two and against the stored vector; then it times a goal-length
query on each. Read-only: nothing is written to Qdrant. If B agrees with the stored vectors as
closely as A does, the store needs no reindex."""
import math
import sys
import time

sys.path.insert(0, r"Z:\workspace")
import requests  # noqa: E402

import config  # noqa: E402
from agent_common import get_qdrant, memory_text  # noqa: E402

A = sys.argv[1] if len(sys.argv) > 1 else f"http://{config.NODE3_IP}:11434"
B = sys.argv[2] if len(sys.argv) > 2 else getattr(config, "EMBED_URL", f"http://{config.NODE2_IP}:11434")


def embed(url, text):
    t = time.time()
    res = requests.post(f"{url}/api/embed", timeout=300, json={
        "model": config.EMBED_MODEL, "input": text, "keep_alive": config.OLLAMA_KEEP_ALIVE})
    res.raise_for_status()
    return res.json()["embeddings"][0], time.time() - t


def cos(u, v):
    return sum(a * b for a, b in zip(u, v)) / math.sqrt(sum(a * a for a in u) * sum(b * b for b in v))


points, _ = get_qdrant().scroll(config.COLLECTION_NAME, limit=1000, with_payload=True, with_vectors=True)
print(f"A = {A}\nB = {B}\n{len(points)} stored entries")
ab, a_st, b_st, ta, tb = [], [], [], [], []
for p in points:
    pl = p.payload or {}
    text = config.EMBED_DOCUMENT_PREFIX + memory_text(pl.get("filename", ""), pl.get("goal", ""),
                                                      pl.get("summary") or pl.get("description", ""),
                                                      pl.get("tags"))
    va, sa = embed(A, text)
    vb, sb = embed(B, text)
    ab.append(cos(va, vb))
    a_st.append(cos(va, p.vector))
    b_st.append(cos(vb, p.vector))
    ta.append(sa)
    tb.append(sb)
    print(f"  {pl.get('filename', '?'):<28} A-B {ab[-1]:.6f}  A-stored {a_st[-1]:.6f}  B-stored {b_st[-1]:.6f}"
          f"  ({len(text)} chars: A {sa:.2f} s, B {sb:.2f} s)")
print(f"lowest cosine: A-B {min(ab):.6f}, A-stored {min(a_st):.6f}, B-stored {min(b_st):.6f}")
print(f"seconds per stored text: A {sum(ta) / len(ta):.2f}, B {sum(tb) / len(tb):.2f}")

goal = max((str((p.payload or {}).get("goal", "")) for p in points), key=len)[:2000]
query = config.EMBED_QUERY_PREFIX + goal
for name, url in (("A", A), ("B", B)):
    times = [embed(url, query)[1] for _ in range(3)]
    print(f"goal-length query ({len(query)} chars) on {name}: " + ", ".join(f"{t:.2f} s" for t in times))
