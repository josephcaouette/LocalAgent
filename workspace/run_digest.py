"""Plain-English summaries ("digests") of finished runs, written by Node 1 while the queue is idle.

The Agent Cluster window starts this when nothing is running or queued. It summarizes each finished
run that has no digest yet (newest first) from its Redis record and a condensed pipeline.log, and
saves the result in the record's `digest` field, which the Runs tab shows as "Summary". It stops as
soon as a pipeline run starts, and a Redis lock keeps two windows from doing the same work.

Usage: python run_digest.py --pending [--limit N]   or   python run_digest.py --run RUN_ID
"""
import argparse
import os
import re
import sys
import time

import requests
from openai import OpenAI

import config

LOCK_KEY = "workflow:digest_lock"
FINISHED = {"PASSED", "FAILED", "STOPPED", "ERROR"}
KEY_LINE = re.compile(
    r"^\[Node|^-> |^\s+Candidate \d|^\s+--- Candidate|^\s*\[[ix!+]\]|^\s+\[[i!]\]|FAIL|Referee|"
    r"Head-to-head|Panel for|Winner|Not caught|Corrected|failed with exactly|CORRECTION|"
    r"Mutant|planted bugs|Accuracy:|=== ")
SYSTEM = ("You summarize automated coding runs for the person who started them. You are accurate and "
          "brief, and you only report what the log and record show.")
INSTRUCTIONS = (
    "Write a short summary of this run in exactly this shape (plain text, no headings beyond these labels):\n"
    "Result: one sentence: the outcome, on which attempt, how long it took, and what was built. Use the "
    "record's status exactly: PASSED, FAILED (it gave up), STOPPED (someone stopped it by hand, which is "
    "not a failure) or ERROR (a problem stopped it).\n"
    "What happened: 2-5 short bullets in order: what failed, what fixed it, and which safeguards made a "
    "difference (re-tests, corrected examples or spec, critic findings, mutation testing). Attribute each "
    "judgment to the step that made it ('the diagnosis blamed the test', 'a reviewer reported...') rather "
    "than stating it as fact: the pipeline's own conclusions are sometimes wrong, and a later step may "
    "have overturned an earlier one.\n"
    "Time: one sentence on where most of the time went.\n"
    "Worth checking: anything the person should look at (assumptions in the spec, a version kept after "
    "an error, a low mutation score, warnings), or 'Nothing stands out.' For a FAILED run, name the "
    "checks that still failed on the last attempt and say that either the code or that check's "
    "hand-computed expected value may be wrong (tests are often the wrong side); the best attempt is "
    "saved as final_<file> in the run folder.\n"
    "Stay under 160 words. Don't invent anything that isn't in the record or the log.")


def condensed_log(run_id, limit=18000):
    """The lines of pipeline.log that tell the story (steps, results, warnings), shortened."""
    path = os.path.join(config.RUNS_DIR, run_id, "pipeline.log")
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return ""
    kept, last = [], None
    for ln in lines:
        if KEY_LINE.search(ln) and ln != last:
            kept.append(ln.rstrip()[:300])
            last = ln
    text = "\n".join(kept)
    if len(text) > limit:          # keep the start (plan) and most of the end (how it finished)
        text = text[:limit // 3] + "\n[... middle of the log left out ...]\n" + text[-(limit * 2 // 3):]
    return text


def record_text(rec):
    keep = ("status", "profile", "attempt", "elapsed_s", "target_file", "verdict", "mutation_score",
            "regression_checks", "phase")
    if not rec.get("elapsed_s"):        # a stopped or crashed run never saved its time
        try:
            rec = dict(rec, elapsed_s=f"{int(rec['updated_at']) - int(rec['started_at'])} (start to last update)")
        except (KeyError, ValueError):
            pass
    lines = [f"{k}: {rec[k]}" for k in keep if rec.get(k)]
    for k in ("timings", "tokens"):
        if rec.get(k):
            lines.append(f"{k}: {rec[k][:600]}")
    goal = (rec.get("goal") or "")[:1500]
    return f"Goal: {goal}\n" + "\n".join(lines)


def model_id():
    res = requests.get(config.LLM_BASE_URL + "/v1/models", timeout=10)
    res.raise_for_status()
    return res.json()["data"][0]["id"]


def write_digest(client, model, r, run_id):
    key = config.TASK_KEY_PREFIX + run_id
    rec = r.hgetall(key)
    log = condensed_log(run_id)
    if not rec or not log:
        return False
    resp = client.chat.completions.create(
        model=model, max_tokens=700, temperature=0.3,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": f"{record_text(rec)}\n\nLog (key lines):\n{log}\n\n{INSTRUCTIONS}"}],
        extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    text = re.sub(r"<think>.*?</think>", "", resp.choices[0].message.content or "", flags=re.S).strip()
    if not text:
        return False
    r.hset(key, mapping={"digest": text, "digest_at": int(time.time())})
    return True


def pending(r, limit):
    out = []
    for key in r.zrevrange(config.TASK_INDEX_KEY, 0, 199):
        rec = r.hmget(key, "status", "digest")
        run_id = key.split(":")[-1]
        if (rec[0] in FINISHED and not rec[1]
                and os.path.exists(os.path.join(config.RUNS_DIR, run_id, "pipeline.log"))):
            out.append(run_id)
        if len(out) >= limit:
            break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pending", action="store_true", help="summarize finished runs that have no digest")
    ap.add_argument("--run", help="summarize this run (again)")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)
    r = config.get_redis(decode_responses=True, timeout=5)
    me = f"{os.getpid()} {os.getppid()}"     # the window knows the parent: a venv launcher
    if not r.set(LOCK_KEY, me, nx=True, ex=900):
        print("Another window is already writing digests.")
        return 0
    try:
        todo = [args.run] if args.run else (pending(r, args.limit) if args.pending else [])
        if not todo:
            print("No runs need a digest.")
            return 0
        try:
            client, model = OpenAI(base_url=config.LLM_BASE_URL + "/v1", api_key="local"), model_id()
        except Exception as e:
            print(f"Node 1's model isn't reachable ({e}); trying again next time.")
            return 0
        done = 0
        for run_id in todo:
            if not args.run and config.active_runs(r):
                print("A run started; stopping so it has Node 1 to itself.")
                break
            r.expire(LOCK_KEY, 900)
            t0 = time.time()
            try:
                ok = write_digest(client, model, r, run_id)
            except Exception as e:
                print(f"{run_id}: failed ({str(e)[:200]})")
                continue
            done += ok
            print(f"{run_id}: {'digest written' if ok else 'nothing to summarize'} ({time.time() - t0:.0f}s)")
        print(f"Wrote {done} digest(s).")
        return 0
    finally:
        if r.get(LOCK_KEY) == me:
            r.delete(LOCK_KEY)


if __name__ == "__main__":
    sys.exit(main())
