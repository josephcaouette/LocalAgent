"""Helpers shared by the pipeline, the ingest worker and the reindex script."""
import requests

import config


def ollama_generate(prompt, *, temperature=0.1, json_mode=False, timeout=60, num_predict=None):
    """Run the Node 3 worker model. num_ctx and keep_alive are always sent with the
    same values, so Ollama never reloads the model or lets it expire."""
    options = {"temperature": temperature, "num_ctx": config.OLLAMA_NUM_CTX}
    if num_predict:
        options["num_predict"] = num_predict
    payload = {
        "model": config.WORKER_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "options": options,
    }
    if config.WORKER_THINK is not None:
        payload["think"] = config.WORKER_THINK
    if json_mode:
        payload["format"] = "json"
    res = requests.post(f"{config.OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
    res.raise_for_status()
    return res.json().get("response", "").strip()


def embed(text, kind):
    """Embed text with the Node 3 embedding model. kind="query" for searches,
    kind="document" for stored items; each gets the prefix set in config.py."""
    prefix = {"query": config.EMBED_QUERY_PREFIX, "document": config.EMBED_DOCUMENT_PREFIX}[kind]
    res = requests.post(
        f"{config.OLLAMA_URL}/api/embed",
        json={"model": config.EMBED_MODEL, "input": prefix + text,
              "keep_alive": config.OLLAMA_KEEP_ALIVE},
        timeout=60,
    )
    res.raise_for_status()
    vectors = res.json().get("embeddings") or []
    if not vectors or not vectors[0]:
        raise RuntimeError("Ollama returned an empty embedding")
    return vectors[0]


def memory_text(filename, goal, summary, tags):
    """The text embedded for a stored solution: what it does, not its code."""
    tag_text = ", ".join(str(t) for t in (tags or []))
    return f"File: {filename}\nGoal: {str(goal)[:1500]}\nSummary: {summary}\nTags: {tag_text}"


def get_qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(
        host=config.QDRANT_HOST, port=config.QDRANT_PORT,
        api_key=config.QDRANT_API_KEY, https=False, timeout=10,
    )
