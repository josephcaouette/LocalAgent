"""Compare embedding models on the pipeline's memory-retrieval job (goal -> stored utility)."""
import math
import sys

import requests

OLLAMA = "http://192.168.254.26:11434"

DOCS = [  # (filename, goal it was built for, summary, tags)
    ("primes_report.py", "Create primes_report.py that finds primes below 100", "Finds all prime numbers below 100 with a sieve of Eratosthenes and prints them, their count and their sum. Test mode checks the results.", "primes, sieve, math"),
    ("cluster_ping.py", "Check the cluster services", "Checks TCP connectivity and latency to cluster services (SSH, Redis, Qdrant, dashboard, Ollama) on three nodes and prints a status table. Exits 1 if a critical service is down.", "network, tcp, monitoring"),
    ("log_level_stats.py", "Count log levels in a log file", "Reads a log file, counts lines per log level and lists the three most frequent ERROR messages. Test mode generates a sample log with known counts.", "logs, parsing, statistics"),
    ("file_hasher.py", "Hash files in a folder", "Calculates MD5 and SHA256 checksums for every file in a folder and prints a table.", "hashing, checksums, files"),
    ("sys_audit.py", "Audit this machine", "Reports CPU core count, hostname, disk space and memory using only the standard library.", "system, hardware, audit"),
    ("storage_analyzer.py", "Analyze disk usage", "Walks a directory tree and reports the largest files and the total size of each folder.", "disk, storage, filesystem"),
    ("system_uptime.py", "Show uptime", "Reports system uptime and load averages read from /proc.", "uptime, load, linux"),
    ("network_monitor.py", "Monitor network traffic", "Samples /proc/net/dev to measure throughput per network interface in bytes per second.", "network, bandwidth, interfaces"),
    ("redis_key_report.py", "Report Redis keys", "Connects to Redis, scans keys with SCAN, and prints key counts and memory usage per key prefix.", "redis, database, keys"),
    ("csv_dedupe.py", "Clean a CSV", "Removes duplicate rows from a CSV file based on chosen key columns and writes a cleaned copy.", "csv, data cleaning"),
    ("json_validator.py", "Validate JSON files", "Validates JSON files against a simple schema and reports errors with line numbers.", "json, validation, schema"),
    ("port_scanner.py", "Scan ports", "Scans a range of TCP ports on one host using threads and lists the open ports.", "network, ports, security"),
]
QUERIES = [  # (goal, expected filename or None for 'nothing relevant')
    ("Update primes_report.py so it also prints the sum of the primes", "primes_report.py"),
    ("Write a script that lists prime numbers up to 1000 and how many there are", "primes_report.py"),
    ("Check whether Redis, Qdrant and Ollama are reachable on the cluster and show latency", "cluster_ping.py"),
    ("Summarize an application log: how many warnings and errors, and the most common error", "log_level_stats.py"),
    ("Compute SHA-256 checksums of every file in a directory", "file_hasher.py"),
    ("Show how much RAM and how many CPU cores this machine has", "sys_audit.py"),
    ("Find the biggest files under a folder", "storage_analyzer.py"),
    ("Measure bandwidth on each network interface", "network_monitor.py"),
    ("Count Redis keys per prefix and how much memory they use", "redis_key_report.py"),
    ("Find which TCP ports are open on 192.168.254.25", "port_scanner.py"),
    ("Convert Markdown files in a folder to HTML", None),
    ("Resize every JPEG image in a folder to 800 pixels wide", None),
    ("Generate a random secure password", None),
]


def doc_body(goal, summary, tags):
    return f"Goal: {goal}\nSummary: {summary}\nTags: {tags}"


MODELS = {
    "nomic-embed-text": (
        lambda q: "search_query: " + q,
        lambda f, g, s, t: f"search_document: File: {f}\n" + doc_body(g, s, t)),
    "qwen3-embedding:0.6b": (
        lambda q: "Instruct: Given a programming task, retrieve a stored Python utility that solves a similar task\nQuery:" + q,
        lambda f, g, s, t: f"File: {f}\n" + doc_body(g, s, t)),
    "qwen3-embedding:4b": (
        lambda q: "Instruct: Given a programming task, retrieve a stored Python utility that solves a similar task\nQuery:" + q,
        lambda f, g, s, t: f"File: {f}\n" + doc_body(g, s, t)),
    "embeddinggemma-2:270m": (
        lambda q: "task: search result | query: " + q,
        lambda f, g, s, t: f"title: {f} | text: " + doc_body(g, s, t)),
}


def embed(model, texts):
    r = requests.post(f"{OLLAMA}/api/embed", json={"model": model, "input": texts, "keep_alive": "2m"}, timeout=300)
    r.raise_for_status()
    return r.json()["embeddings"]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


models = sys.argv[1:] or list(MODELS)
for name in models:
    qf, df = MODELS.get(name) or next(v for k, v in MODELS.items() if name.split(':')[0] == k.split(':')[0])
    try:
        dvec = embed(name, [df(*d) for d in DOCS])
        qvec = embed(name, [qf(q) for q, _ in QUERIES])
    except Exception as e:
        print(f"{name}: skipped ({e})")
        continue
    correct, right_scores, wrong_best, none_best = 0, [], [], []
    for (q, want), qv in zip(QUERIES, qvec):
        scores = sorted(((cos(qv, dv), d[0]) for d, dv in zip(DOCS, dvec)), reverse=True)
        if want is None:
            none_best.append(scores[0][0])
            continue
        if scores[0][1] == want:
            correct += 1
        right_scores.append(next(s for s, f in scores if f == want))
        wrong_best.append(max(s for s, f in scores if f != want))
    lo_right, hi_wrong = min(right_scores), max(wrong_best + none_best)
    print(f"{name:<24} top-1 {correct}/10 | right: min {lo_right:.3f} mean {sum(right_scores)/len(right_scores):.3f} | "
          f"best wrong: max {max(wrong_best):.3f} mean {sum(wrong_best)/len(wrong_best):.3f} | "
          f"unrelated goals: max {max(none_best):.3f} | gap {lo_right - hi_wrong:+.3f}")
