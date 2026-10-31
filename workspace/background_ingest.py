"""Store a verified script in long-term memory (Qdrant) after a run passes.

Started by the pipeline as a detached background process:
    python background_ingest.py --job Z:\\runs\\<run>\\ingest_job.json
The old form still works:  python background_ingest.py <file.py> [goal]
Output is appended to logs\\ingest.log.

What gets embedded is a description (goal, summary, tags) with config.EMBED_DOCUMENT_PREFIX,
not the code itself. The code is kept in the payload. The code comes from the run's own copy
(Z:\\runs\\<run>\\final_<file>) when the job names one, so a later run that changes the same
workspace file can't swap in different code.
"""
import argparse
import json
import os
import sys
import time
import uuid

import config
from agent_common import embed, get_qdrant, memory_text, ollama_generate

TICK3 = "```"


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def summarize(target, goal, code):
    """Ask Node 3 for a short summary and tags; fall back to defaults."""
    summary = f"Utility created for: {goal[:300]}"
    tags = ["python", "cluster-utility"]
    prompt = (
        "You are a technical documentation assistant.\n"
        f"Analyze this verified Python script '{target}', built for the goal: \"{goal[:1500]}\".\n\n"
        f"Code:\n{TICK3}python\n{code[:16000]}\n{TICK3}\n\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        '{"summary": "1-2 sentences on what this utility does and how it runs.", '
        '"tags": ["tag1", "tag2", "tag3"]}'
    )
    try:
        reply = ollama_generate(prompt, temperature=0.2, json_mode=True, timeout=120, num_predict=300)
        parsed = json.loads(reply or "{}")
        summary = str(parsed.get("summary") or summary).strip()
        new_tags = parsed.get("tags")
        if isinstance(new_tags, list):
            tags = [str(t).strip() for t in new_tags if str(t).strip()][:8] or tags
    except Exception as e:
        log(f"Summary step failed ({e}); using defaults.")
    return summary, tags


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Store a verified script in Qdrant memory.")
    p.add_argument("--job", help="ingest_job.json written by the pipeline")
    p.add_argument("target", nargs="?", help="file name in the workspace (old style)")
    p.add_argument("goal", nargs="?", default="", help="goal text (old style)")
    args = p.parse_args()
    if args.job:
        with open(args.job, encoding="utf-8") as f:
            job = json.load(f)
    elif args.target:
        job = {"target_file": args.target, "goal": args.goal}
    else:
        p.print_help()
        return 0

    target = os.path.basename(job["target_file"])
    goal = job.get("goal", "")
    path = job.get("code_file") or ""
    if not path or not os.path.exists(path):
        path = os.path.join(config.WORKSPACE, target)
    if not os.path.exists(path):
        log(f"{path} doesn't exist; nothing stored.")
        return 1
    with open(path, encoding="utf-8", errors="replace") as f:
        code = f.read()

    log(f"Ingesting {target}...")
    summary, tags = summarize(target, goal, code)
    try:
        vector = embed(memory_text(target, goal, summary, tags), "document")
    except Exception as e:
        log(f"Embedding failed ({e}); nothing stored.")
        return 1

    # One memory entry per file: a later passing run for the same file replaces it.
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, target))
    try:
        from qdrant_client.http import models
        client = get_qdrant()
        if not client.collection_exists(config.COLLECTION_NAME):
            client.create_collection(
                config.COLLECTION_NAME,
                vectors_config=models.VectorParams(size=len(vector), distance=models.Distance.COSINE))
        client.upsert(collection_name=config.COLLECTION_NAME, points=[models.PointStruct(
            id=point_id, vector=vector, payload={
                "filename": target, "goal": goal, "summary": summary, "tags": tags, "code": code,
                "checks": job.get("checks", []), "verdict": job.get("verdict", ""),
                "embed_model": config.EMBED_MODEL, "updated_at": int(time.time()),
            })])
    except Exception as e:
        log(f"Qdrant upsert failed ({e}).")
        return 1
    log(f"Stored {target} in '{config.COLLECTION_NAME}': {summary} (tags: {', '.join(tags)})")

    try:
        r = config.get_redis(decode_responses=True)
        msg = f"Cataloged {target} into Qdrant"
        task_key = job.get("task_key")
        if task_key:
            r.hset(task_key, "memory_sync", msg)
            # Only touch the 'latest run' record if no newer run has started since.
            if r.hget(config.LATEST_KEY, "run_id") == task_key.rsplit(":", 1)[-1]:
                r.hset(config.LATEST_KEY, "memory_sync", msg)
        else:
            r.hset(config.LATEST_KEY, "memory_sync", msg)
    except Exception as e:
        log(f"Redis update failed ({e}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
