"""Shared settings for the agent cluster. Edit hosts, models and limits here.

Imported by the pipeline, GUI, ingest worker, dashboard and reindex script, so
a change here applies everywhere.

Secrets (Redis password, Qdrant API key) are read from environment variables or
from ../config/agent_secrets.env, i.e. Z:\\config on Windows and
/mnt/blackboard/config on Node 2. That folder is outside the workspace, so
sandboxed code can't read it.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env_file(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


_SECRETS = _load_env_file(os.path.join(_HERE, "..", "config", "agent_secrets.env"))


def _setting(name, default=None):
    return os.environ.get(name) or _SECRETS.get(name) or default


# --- Nodes -------------------------------------------------------------------
NODE1_IP = "192.168.254.24"   # Brain: RTX 4090, vLLM, GUI, pipeline
NODE2_IP = "192.168.254.25"   # Blackboard: Redis, Qdrant, sandbox, file share
NODE3_IP = "192.168.254.26"   # Worker: RTX 2070, Ollama

# --- Paths (Windows view of the share) ----------------------------------------
WORKSPACE = _setting("AGENT_WORKSPACE", _HERE)               # Z:\workspace
RUNS_DIR = os.path.normpath(os.path.join(WORKSPACE, "..", "runs"))  # Z:\runs
HISTORY_DIR = os.path.join(WORKSPACE, ".history")            # backups before overwrite
LOG_DIR = os.path.join(WORKSPACE, "logs")

# --- Paths on Node 2 (same share, Linux view) ---------------------------------
SSH_TARGET = "server@" + NODE2_IP
REMOTE_ROOT = "/mnt/blackboard"
REMOTE_WORKSPACE = REMOTE_ROOT + "/workspace"
REMOTE_RUNS_DIR = REMOTE_ROOT + "/runs"

# --- Redis (task telemetry) ---------------------------------------------------
REDIS_HOST = _setting("AGENT_REDIS_HOST", NODE2_IP)
REDIS_PORT = 6379
REDIS_PASSWORD = _setting("AGENT_REDIS_PASSWORD")
TASK_KEY_PREFIX = "workflow:task:"
TASK_INDEX_KEY = "workflow:tasks"          # sorted set of task keys, score = start time
LATEST_KEY = "workflow:langgraph:001"      # copy of the most recent run (GUI reads this)
TASK_TTL_SECONDS = 30 * 24 * 3600          # task records expire after 30 days
TASK_INDEX_MAX = 500
ACTIVE_KEY = "workflow:active"             # sorted set: run_id -> last heartbeat (every 30 s)
ACTIVE_STALE_S = 120                       # a run with no heartbeat for this long is gone

# --- Qdrant (long-term memory) ------------------------------------------------
QDRANT_HOST = _setting("AGENT_QDRANT_HOST", NODE2_IP)
QDRANT_PORT = 6333
QDRANT_API_KEY = _setting("AGENT_QDRANT_API_KEY")
COLLECTION_NAME = "agent_solutions"
MEMORY_MIN_SCORE = 0.63    # cosine score needed to reuse a stored solution. In a 13-goal test with
                           # qwen3-embedding:0.6b, right matches scored 0.707 or more (average 0.768)
                           # and the best wrong match 0.566. Tune from the scores the retriever logs.
MEMORY_TOP_K = 3

# --- vLLM on Node 1 (planner / engineer / verifier) ---------------------------
LLM_BASE_URL = "http://127.0.0.1:8001"   # not "localhost": Windows tries IPv6 first and each
                                         # new connection to WSL then waits ~2 s before falling back
LLM_MODEL = "RedHatAI/Qwen3.8-27B-INT4"   # if vLLM serves another model, the pipeline uses that one
LLM_FALLBACK_CONTEXT = 8192    # used only if vLLM doesn't report max_model_len
LLM_TIMEOUT = 1200             # seconds per request (two runs share the GPU, so allow slow ones)
ENGINEER_MAX_OUTPUT = 8000     # upper limit on tokens for one generated file
LLM_ENABLE_THINKING = False    # Qwen3.x reasons step by step before answering unless this is off.
                               # Off is several times faster; models without the switch ignore it.
LLM_TEMPERATURE = 0.7          # sampling values from the Qwen3.8 model card (non-thinking mode)
LLM_TOP_P = 0.8
LLM_TOP_K = 20
# Where the pipeline lets the model think before answering (slower, better). Thinking calls use
# the model card's thinking-mode sampling (temperature 0.6, top_p 0.95) and get THINK_TOKENS of
# extra room. The engineer's thinking is set per run profile below.
THINK_PLANNER = True
THINK_VERIFIER = True
THINK_TOKENS = 5000

# --- Ollama on Node 3 (scout / condenser / ingest summaries / embeddings) ------
# Who does the pipeline's helper jobs (the scout's brief on referenced files and the diagnosis
# of failed test runs): "node1" uses the main vLLM model, which is faster and stronger here;
# "node3" uses WORKER_MODEL. Embeddings, background memory summaries and the GUI's chat
# fallback always use Node 3.
HELPER_BACKEND = "node1"
OLLAMA_URL = f"http://{NODE3_IP}:11434"
WORKER_MODEL = "qwen3.5:9b"          # was qwen2.5-coder:7b
WORKER_THINK = False       # Qwen3.5 reasons step by step unless this is False. Use None for models
                           # without a thinking mode (such as qwen2.5-coder), which reject the option.
EMBED_MODEL = "qwen3-embedding:0.6b" # was nomic-embed-text. Changing it changes the vector size:
                                     # run reindex_memory.py afterwards to rebuild the memory store.
                                     # Ollama keeps it on Node 3's CPU next to qwen3.5:9b (8 GB GPU);
                                     # that's fine at ~70 ms per call. With qwen3.5:4b both fit on the GPU.
# Text added in front of what gets embedded. Qwen3-Embedding wants a task instruction on queries
# and nothing on stored documents. (nomic-embed-text used "search_query: " / "search_document: ".)
EMBED_QUERY_PREFIX = ("Instruct: Given a programming task, retrieve a stored Python utility that "
                      "solves a similar task\nQuery:")
EMBED_DOCUMENT_PREFIX = ""
OLLAMA_NUM_CTX = 8192      # keep identical everywhere (incl. Restart_Node3_Worker.bat) or Ollama reloads the model
OLLAMA_KEEP_ALIVE = -1     # sent with every request; -1 keeps models loaded indefinitely

# --- Web research (research.py) -------------------------------------------------
SEARXNG_URL = f"http://{NODE2_IP}:8888"    # self-hosted SearXNG (docker-compose service)
RESEARCH_ALLOWLIST_FILE = os.path.join(WORKSPACE, "research_allowlist.txt")
READER_BACKEND = "auto"    # who reads pages, long attachments and long chats: "auto" = Node 1,
                           # or Node 3 while a pipeline run is using Node 1; or "node1" / "node3"
RESEARCH_MAX_PAGES = 5     # pages read per research request
RESEARCH_FETCH_TIMEOUT = 15
RESEARCH_MAX_PAGE_BYTES = 2_000_000
RESEARCH_MAX_PAGE_CHARS = 60_000
ATTACHMENT_COMPRESS_CHARS = 24_000   # attachments larger than this in total get condensed by the reader

# --- Sandbox (fresh container per test run on Node 2) -------------------------
SANDBOX_IMAGE = "agent-sandbox:latest"     # built from Z:\docker\sandbox\Dockerfile
SANDBOX_PYTHON = "3.11"
SANDBOX_PACKAGES = ["requests", "redis", "psutil", "yaml"]   # import names; keep in sync with the Dockerfile
SANDBOX_TIMEOUT = 20       # seconds the script may run
SANDBOX_MEMORY = "1g"
SANDBOX_CPUS = 2
SANDBOX_PIDS = 128
KEEP_RUNS = 30             # per-run scratch folders kept in Z:\runs

# --- Run profiles (GUI "Overnight run" checkbox, or --overnight) ----------------
# candidates: how many versions the engineer writes at once; all are tested and the verifier
# picks the best. think_engineer: "retries" = think only when fixing a failure, "always", "never".
# A run stops as soon as a candidate passes, or when attempts or time run out.
RUN_PROFILES = {
    "normal":    {"max_attempts": 3, "candidates": 2, "time_limit_s": 30 * 60,
                  "think_engineer": "retries"},
    "overnight": {"max_attempts": 8, "candidates": 3, "time_limit_s": 12 * 3600,
                  "think_engineer": "always"},
}
KEEP_HISTORY_PER_FILE = 20 # backups kept per file in .history

# How many runs the GUI's queue runs at the same time. vLLM serves them together, so two runs
# finish close to twice as many tasks per hour as one, each about 10-15% slower.
MAX_PARALLEL_RUNS = 2

# Test containers are started while the engineer writes, so a test doesn't wait ~7 s for one
# (Docker on Node 2's HDD array). Each container is still used for one test and then removed.
SANDBOX_PREWARM = True

# --- Dashboard ----------------------------------------------------------------
DASHBOARD_PORT = 8080
DASHBOARD_URL = f"http://{NODE2_IP}:{DASHBOARD_PORT}"
DASHBOARD_MAX_TASKS = 50

# Infrastructure files the pipeline must never overwrite.
PROTECTED_FILES = {
    "run_langgraph_pipeline.py", "agent_gui.py", "agent_dashboard.py",
    "background_ingest.py", "config.py", "agent_common.py", "reindex_memory.py", "research.py",
}


def get_redis(decode_responses=False, timeout=3):
    """Redis client with short timeouts so callers never hang when Node 2 is down."""
    import redis
    return redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, db=0,
        decode_responses=decode_responses,
        socket_connect_timeout=timeout, socket_timeout=timeout,
    )


def active_runs(client):
    """run_ids of pipeline runs that sent a heartbeat recently (killed runs drop out)."""
    import time
    cutoff = time.time() - ACTIVE_STALE_S
    client.zremrangebyscore(ACTIVE_KEY, 0, cutoff)
    ids = client.zrangebyscore(ACTIVE_KEY, cutoff, "+inf")
    return [i.decode() if isinstance(i, bytes) else i for i in ids]
