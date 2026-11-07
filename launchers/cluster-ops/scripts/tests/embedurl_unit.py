"""Embeddings go to Node 2 (config.EMBED_URL) and the worker model stays on Node 3
(config.OLLAMA_URL), since the embedding model moved on 2026-11-07. No network: requests.post is
faked. The live checks are embed_compare.py and EMBED_EVAL_URL=... embed_eval.py."""
import sys

sys.path.insert(0, r"Z:\workspace")
import agent_common  # noqa: E402
import config  # noqa: E402

calls = []


class Res:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def fake_post(url, json=None, timeout=None, **kw):
    calls.append((url, json))
    return Res({"embeddings": [[0.1, 0.2]]} if url.endswith("/api/embed") else {"response": " ok "})


agent_common.requests.post = fake_post
vector = agent_common.embed("find primes", "query")
agent_common.ollama_generate("hello")
(embed_url, embed_body), (gen_url, _gen_body) = calls
overridden = config._setting("AGENT_EMBED_URL") is not None
checks = [
    ("EMBED_URL is Node 2's Ollama unless AGENT_EMBED_URL overrides it",
     overridden or config.EMBED_URL == f"http://{config.NODE2_IP}:11434"),
    ("embed() posts to EMBED_URL", embed_url == f"{config.EMBED_URL}/api/embed"),
    ("  with the model, the query prefix and keep_alive",
     embed_body == {"model": config.EMBED_MODEL, "input": config.EMBED_QUERY_PREFIX + "find primes",
                    "keep_alive": config.OLLAMA_KEEP_ALIVE}),
    ("  and returns the first vector", vector == [0.1, 0.2]),
    ("the worker model stays on Node 3 (OLLAMA_URL)",
     gen_url == f"{config.OLLAMA_URL}/api/generate" and config.OLLAMA_URL == f"http://{config.NODE3_IP}:11434"),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
