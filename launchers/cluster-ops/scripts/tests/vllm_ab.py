"""A/B of vLLM settings for MAX-shaped load on the 32k server. For each config it restarts vLLM
(the same way the Agent Cluster window does), runs three phases, and records time, tokens/s,
preemptions and peak KV use:
  1. one long thinking request (like planning or a critic)
  2. eight at once sharing a long prompt prefix (like 5 candidates + tester + adversary + prober)
  3. five short ones (like the judges)
At the end it restarts vLLM with the user's saved settings. Usage: python vllm_ab.py [config ...]
Results: vllm_ab_results.json next to this file. Don't run while a pipeline run is going."""
import copy
import json
import os
import re
import subprocess
import sys
import threading
import time

import requests
from openai import OpenAI

sys.path.insert(0, r"C:\AI\cluster_launcher")
import cluster_launcher as cl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://127.0.0.1:8001"
LONG = cl.PRESETS[cl.LONG_PRESET]


def cfg(**changes):
    v = copy.deepcopy(LONG)
    v.update(changes)
    return v


CONFIGS = {        # explicit values: the preset itself moved from 0.90 to 0.92 after the first A/B
    "current (0.90, no MTP)": cfg(gpu_util=0.90, mtp=False),
    "0.92": cfg(gpu_util=0.92, mtp=False),
    "MTP + 0.92": cfg(gpu_util=0.92, mtp=True),
    "MTP + 0.92 + 4096 batch": cfg(gpu_util=0.92, mtp=True, extra="--max-num-batched-tokens 4096"),
    "0.92 + 4096 batch": cfg(gpu_util=0.92, mtp=False, extra="--max-num-batched-tokens 4096"),
}

GOAL = ("Create a Python module with next_runs(expr, start, count) for standard 5-field cron expressions "
        "(minute hour day-of-month month day-of-week) supporting *, lists, ranges and steps, with the Vixie "
        "rule that a day matches if either day field matches when both are restricted, input validation "
        "with clear errors, and a --test mode with many hand-checked cases.")
SPEC = ("Spec. " + " ".join(f"Rule {i}: field {i % 5} accepts values in its range, comma lists, a-b ranges and "
                           f"/n steps; malformed text raises ValueError naming the field; examples are listed "
                           f"with exact expected outputs and every edge case is described in detail." for i in range(60)))


def stop():
    cl.run_quiet(["wsl", "-u", "root", "bash", "-c",
                  "fuser -k -9 8001/tcp >/dev/null 2>&1; pkill -9 -f '[v]llm serve' >/dev/null 2>&1"])
    for _ in range(40):
        if not cl.port_open("127.0.0.1", 8001, 0.5):
            return
        time.sleep(0.5)


def start(v, timeout=420):
    stop()
    cl.run_quiet(["wsl", "bash", "-c", "rm -f ~/vllm_last.log"])
    subprocess.Popen(["wsl", "bash", "-c", cl.vllm_script(v)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(cl, "NO_WINDOW", 0) | getattr(cl, "NEW_GROUP", 0))
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if requests.get(BASE + "/v1/models", timeout=3).ok:
                return time.time() - t0
        except Exception:
            pass
        time.sleep(3)
    return None


def log_tail():
    r = subprocess.run(["wsl", "bash", "-c", "grep -E 'GPU KV cache size|Error|error' ~/vllm_last.log | tail -5"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def metric(name, extra=""):
    try:
        m = re.search(rf"^{re.escape(name)}\{{[^}}]*{extra}[^}}]*\}} ([0-9.e+]+)$",
                      requests.get(BASE + "/metrics", timeout=3).text, re.M)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


def phase(client, model, prompts, max_tokens, think_budget):
    """Send prompts at once; return wall time, generated tokens, preemptions, peak KV use and waits."""
    pre0, peak, waits, stop_flag = metric("vllm:num_preemptions_total"), [0.0], [0], threading.Event()

    def sampler():
        while not stop_flag.is_set():
            peak[0] = max(peak[0], metric("vllm:kv_cache_usage_perc"))
            waits[0] = max(waits[0], int(metric("vllm:num_requests_waiting")))
            time.sleep(2)
    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    results = [None] * len(prompts)

    def one(i):
        r = client.chat.completions.create(
            model=model, max_tokens=max_tokens, temperature=0.6,
            messages=[{"role": "user", "content": prompts[i]}],
            extra_body={"chat_template_kwargs": {"enable_thinking": True}, "thinking_token_budget": think_budget})
        results[i] = r.usage.completion_tokens
    t0 = time.time()
    threads = [threading.Thread(target=one, args=(i,)) for i in range(len(prompts))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    secs = time.time() - t0
    stop_flag.set()
    th.join(timeout=5)
    toks = sum(x or 0 for x in results)
    return {"secs": round(secs, 1), "tokens": toks, "tok_s": round(toks / secs, 1),
            "preemptions": int(metric("vllm:num_preemptions_total") - pre0),
            "peak_kv": round(peak[0], 2), "max_waiting": waits[0]}


def run_config(name, v):
    print(f"\n=== {name}: starting vLLM...", flush=True)
    up = start(v)
    if up is None:
        print(f"    did not start: {log_tail()}", flush=True)
        return {"config": name, "started": False, "log": log_tail()}
    kv = log_tail()
    print(f"    ready in {up:.0f}s | {kv.splitlines()[0] if kv else ''}", flush=True)
    client = OpenAI(base_url=BASE + "/v1", api_key="local")
    model = client.models.list().data[0].id
    phase(client, model, ["Say OK."], 20, 64)                       # warm up
    out = {"config": name, "started": True, "ready_s": round(up), "kv_line": kv.splitlines()[0] if kv else ""}
    task = f"{GOAL}\n\n{SPEC}\n\n"
    out["1 single thinking"] = phase(client, model, [task + "Plan the module step by step, then list the acceptance checks."],
                                     6000, 4000)
    out["2 eight at once"] = phase(client, model, [task + f"Approach {k}: write the complete module." for k in range(8)],
                                   14000, 10000)
    code = "def f(x):\n    return x + 1\n" * 300
    out["3 five judges"] = phase(client, model, [f"Review this code for the goal.\n{GOAL}\n{code}\nVote {k}: PASS or FAIL?"
                                                 for k in range(5)], 1500, 1000)
    out["total_s"] = round(sum(out[k]["secs"] for k in out if k[0].isdigit()), 1)
    for k in [k for k in out if k[0].isdigit()]:
        print(f"    {k:18} {out[k]}", flush=True)
    print(f"    total {out['total_s']}s", flush=True)
    return out


if __name__ == "__main__":
    chosen = sys.argv[1:] or list(CONFIGS)
    path = os.path.join(HERE, "vllm_ab_results.json")
    try:                                  # keep earlier configs' results; a re-run replaces its own
        results = json.load(open(path))
    except (OSError, ValueError):
        results = []
    try:
        for name in chosen:
            res = run_config(name, CONFIGS[name])
            results = [r for r in results if r.get("config") != res.get("config")] + [res]
            with open(path, "w") as f:
                json.dump(results, f, indent=1)
    finally:
        saved = cl.load_settings()["vllm"]
        print("\nRestoring the saved settings...", flush=True)
        print("    ready" if start(saved) else "    RESTORE FAILED: start vLLM from the window", flush=True)
