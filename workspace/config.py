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
ENGINEER_MAX_OUTPUT = 12000    # upper limit on tokens for one generated file; a file is also kept to
                               # half the context window (8,192 tokens at 16k, so this matters at 32k)
LLM_ENABLE_THINKING = False    # Qwen3.x reasons step by step before answering unless this is off.
                               # Off is several times faster; models without the switch ignore it.
LLM_TEMPERATURE = 0.7          # sampling values from the Qwen3.8 model card (non-thinking mode)
LLM_TOP_P = 0.8
LLM_TOP_K = 20
# Where the pipeline lets the model think before answering (slower, better). Thinking calls use
# the model card's thinking-mode sampling (temperature 0.6, top_p 0.95) and get up to the
# accuracy level's think_tokens of extra room (THINK_TOKENS is the default). The engineer's
# thinking is set per accuracy level below.
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

# --- Accuracy levels (the GUI's Low / Medium / High / Ultra / MAX selector, or --accuracy) -----
# candidates:      versions the engineer writes per attempt; all are tested, the best one wins.
# think_engineer:  "retries" = think only when fixing a failure, "always", or "never".
# think_tokens:    most hidden thinking per call (always capped so the answer still fits).
# diverse:         on the first attempt each candidate is told to take a different approach.
# tester:          a separate call writes an independent acceptance test from the goal (it never
#                  sees the code); candidates must pass it as well as their own --test.
# judges:          independent verifier votes the winner needs a majority of.
# critic_rounds:   after a pass, reviewers look for bugs the tests missed; up to this many fix
#                  rounds. If a fix doesn't pass in time, the earlier passing version is kept.
# repeat_tests:    runs of a passing test; a later failure means randomness or timing problems.
# exclusive:       the run has the GPU to itself (the GUI queue starts nothing beside it).
# research_default: the GUI ticks "Research the web first" when this level is chosen.
# Ultra and MAX only (see LEVEL_DEFAULTS for what the other levels use):
# server:          "long" = the Agent Cluster window switches vLLM to the 32k preset for the run.
# spec_review:     a reviewer turns the plan into a precise spec and fixes plan, checks, interface.
# reference_tests: the tester also compares against a simple reference and checks properties.
# differential:    passing candidates answer the same probe inputs; a referee settles disputes.
# critics:         reviewers per round (with different focuses).
# critic_proof:    every reviewer claim must come with a test that shows it; proven ones are kept.
# adversary:       a second independent tester tries to break the script.
# head_to_head:    when several candidates pass, a judge compares the top two side by side.
# mutation:        deliberate small bugs check that the tests catch them; the tests get stronger.
# vary_env:        repeat runs use other time zones, locales and working folders.
# test_timeout:    seconds per test run.   max_checks: acceptance checks the planner may write.
# A run ends as soon as a candidate passes (and the reviewers are satisfied), or when attempts
# or time run out.
LEVEL_DEFAULTS = {"server": None, "spec_review": False, "reference_tests": False, "differential": False,
                  "critics": 1, "critic_proof": False, "adversary": False, "head_to_head": False,
                  "mutation": False, "vary_env": False, "test_timeout": SANDBOX_TIMEOUT, "max_checks": 4}
RUN_PROFILES = {
    "low": {"max_attempts": 3, "candidates": 2, "time_limit_s": 30 * 60, "think_engineer": "retries",
            "think_tokens": THINK_TOKENS, "diverse": False, "tester": False, "judges": 1,
            "critic_rounds": 0, "repeat_tests": 1, "exclusive": False, "research_default": False},
    "medium": {"max_attempts": 8, "candidates": 3, "time_limit_s": 12 * 3600, "think_engineer": "always",
               "think_tokens": THINK_TOKENS, "diverse": False, "tester": False, "judges": 1,
               "critic_rounds": 0, "repeat_tests": 3, "exclusive": False, "research_default": False},
    "high": {"max_attempts": 10, "candidates": 4, "time_limit_s": 12 * 3600, "think_engineer": "always",
             "think_tokens": 10000, "diverse": True, "tester": True, "judges": 3,
             "critic_rounds": 2, "repeat_tests": 3, "exclusive": True, "research_default": True},
    "ultra": {"max_attempts": 12, "candidates": 4, "time_limit_s": 12 * 3600, "think_engineer": "always",
              "think_tokens": 16000, "diverse": True, "tester": True, "judges": 3,
              "critic_rounds": 3, "repeat_tests": 3, "exclusive": True, "research_default": True,
              "server": "long", "spec_review": True, "reference_tests": True, "differential": True,
              "critics": 1, "critic_proof": True, "vary_env": True, "test_timeout": 60, "max_checks": 6},
    "max": {"max_attempts": 16, "candidates": 5, "time_limit_s": 24 * 3600, "think_engineer": "always",
            "think_tokens": 16000, "diverse": True, "tester": True, "judges": 5,
            "critic_rounds": 4, "repeat_tests": 5, "exclusive": True, "research_default": True,
            "server": "long", "spec_review": True, "reference_tests": True, "differential": True,
            "critics": 2, "critic_proof": True, "adversary": True, "head_to_head": True,
            "mutation": True, "vary_env": True, "test_timeout": 60, "max_checks": 6},
}
DEFAULT_ACCURACY = "low"
LEGACY_PROFILES = {"normal": "low", "overnight": "medium"}   # names stored by older runs
LONG_CONTEXT_PRESET = "Long context (32k, about half speed)"  # the window's preset for server "long"


def accuracy_level(name):
    """Map a stored profile name (including the old 'normal'/'overnight') to a level name."""
    name = (name or "").strip().lower()
    name = LEGACY_PROFILES.get(name, name)
    return name if name in RUN_PROFILES else DEFAULT_ACCURACY


def level_settings(name):
    """Every setting of a level, with LEVEL_DEFAULTS filling in what it doesn't set."""
    return {**LEVEL_DEFAULTS, **RUN_PROFILES[accuracy_level(name)]}


KEEP_HISTORY_PER_FILE = 20 # backups kept per file in .history

# How many runs the GUI's queue runs at the same time. vLLM serves them together, filling the GPU
# while the other run plans or checks. Test: 3 runs took 5.6 min start to finish (8 min summed).
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
