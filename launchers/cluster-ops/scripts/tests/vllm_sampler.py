"""Log vLLM load every 10 s (context size, running/waiting requests, waits for KV space, KV use,
preemptions) to a CSV, to see whether memory or speed limits a run. Usage: python vllm_sampler.py OUT.csv HOURS"""
import csv
import re
import sys
import time

import requests

out, hours = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 6
BASE = "http://127.0.0.1:8001"
FIELDS = ["t", "ctx", "running", "waiting", "waiting_capacity", "kv_usage", "preemptions", "drafted", "accepted",
          "gen_tokens"]


def metric(text, name, extra=""):
    m = re.search(rf"^{re.escape(name)}\{{[^}}]*{extra}[^}}]*\}} ([0-9.e+]+)$", text, re.M)
    return float(m.group(1)) if m else ""


with open(out, "a", newline="") as f:
    w = csv.writer(f)
    if f.tell() == 0:
        w.writerow(FIELDS)
    end = time.time() + hours * 3600
    while time.time() < end:
        try:
            ctx = requests.get(BASE + "/v1/models", timeout=5).json()["data"][0]["max_model_len"]
            m = requests.get(BASE + "/metrics", timeout=5).text
            w.writerow([int(time.time()), ctx, metric(m, "vllm:num_requests_running"),
                        metric(m, "vllm:num_requests_waiting"),
                        metric(m, "vllm:num_requests_waiting_by_reason", 'reason="capacity"'),
                        metric(m, "vllm:kv_cache_usage_perc"), metric(m, "vllm:num_preemptions_total"),
                        metric(m, "vllm:spec_decode_num_draft_tokens_total"),
                        metric(m, "vllm:spec_decode_num_accepted_tokens_total"),
                        metric(m, "vllm:generation_tokens_total")])
            f.flush()
        except Exception:
            w.writerow([int(time.time()), "down"] + [""] * (len(FIELDS) - 2))
            f.flush()
        time.sleep(10)
