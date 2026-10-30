"""LangGraph agent pipeline: plan -> write code -> test in a throwaway sandbox -> verify -> promote.

    python run_langgraph_pipeline.py --goal="..." [--target=name.py] [--attach=path ...] [--allow-network]
    python run_langgraph_pipeline.py --goal-file=goal.txt ...     (what the GUI uses)
    python run_langgraph_pipeline.py "goal text"                  (old style, still works)

Flow:
    retriever (Qdrant) + scout (Node 3), in parallel
    -> planner   (implementation steps + 2-4 acceptance checks)
    -> engineer  (writes the file into Z:\\runs\\<run>\\a<N>\\, never into the workspace)
    -> executor  (fresh Docker container on Node 2, no network unless allowed)
    -> verifier  (judges the --test output against the acceptance checks)
    -> finalize  (on pass: back up the old file to .history, promote, store in memory)
Crashes go through the Node 3 error condenser back to the engineer; verifier
rejections go straight back. The live workspace file only changes on a pass.

Exit code: 0 passed, 1 failed after all attempts, 2 stopped by an error.
"""
import argparse
import ast
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from typing import TypedDict

import requests
from langgraph.graph import END, START, StateGraph
from openai import APIConnectionError, APIStatusError, BadRequestError, OpenAI

import config
from agent_common import embed, get_qdrant, ollama_generate

if hasattr(sys.stdout, "reconfigure"):
    # Windows pipes default to cp1252, which crashes on characters like arrows; the GUI reads UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

TICK3 = "```"
PID_FILE = os.path.join(tempfile.gettempdir(), "agent_pipeline.pid")
DEFAULT_GOAL = ("Create a self-contained Python utility named 'cluster_ping.py' that verifies "
                "connectivity across .24, .25, and .26.")

LLM = OpenAI(base_url=config.LLM_BASE_URL + "/v1", api_key="none",
             timeout=config.LLM_TIMEOUT, max_retries=0)
MODEL_ID = config.LLM_MODEL                       # replaced by the served model in connect_llm()
CONTEXT_TOKENS = config.LLM_FALLBACK_CONTEXT      # replaced by vLLM's max_model_len in connect_llm()


class LLMError(Exception):
    """vLLM is unreachable or rejected a request; the run stops."""


class ContextTooSmall(LLMError):
    """The required inputs don't fit in the model's context window."""


class InfraError(Exception):
    """SSH or Docker problem unrelated to the generated code; the run stops."""


class AgentState(TypedDict):
    run_id: str
    task_key: str
    goal: str
    target_file: str
    attachments: str
    attachment_names: list
    allow_network: bool
    existing_code: str
    memory_context: str
    memory_summary: str
    research_brief: str
    plan: str
    checks: list
    code: str
    attempt: int
    status: str
    failure_kind: str
    error: str
    execution_output: str
    execution_stderr: str
    verdict: str


# --------------------------------------------------------------------------- text helpers

def head(text, n):
    text = text or ""
    return text if len(text) <= n else text[:n] + f"\n[... {len(text) - n} more characters]"


def tail(text, n):
    text = text or ""
    return text if len(text) <= n else f"[... {len(text) - n} earlier characters]\n" + text[-n:]


def short(exc, n=300):
    return " ".join(str(exc).split())[:n]


def numbered(items):
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))


def fail(state, kind, message, **extra):
    """Record a failed attempt; the routers decide whether to retry."""
    update = {"status": "FAILED", "failure_kind": kind, "error": message,
              "attempt": state["attempt"] + 1}
    update.update(extra)
    return update


# --------------------------------------------------------------------------- Redis telemetry

_redis = None
_redis_warned = False


def redis_client():
    global _redis
    if _redis is None:
        _redis = config.get_redis()
    return _redis


def _redis_value(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    if value is None:
        return ""
    if isinstance(value, str) and len(value) > 20000:
        return value[:20000] + "\n...[truncated]"
    return value


def report(state, **fields):
    """Write progress to this run's task record and to the 'latest run' record."""
    global _redis_warned
    data = {k: _redis_value(v) for k, v in fields.items()}
    data["updated_at"] = int(time.time())
    try:
        pipe = redis_client().pipeline()
        pipe.hset(state["task_key"], mapping=data)
        pipe.expire(state["task_key"], config.TASK_TTL_SECONDS)
        pipe.hset(config.LATEST_KEY, mapping=data)
        pipe.execute()
    except Exception as e:
        if not _redis_warned:
            print(f"[!] Redis telemetry unavailable ({short(e)}); continuing without it.")
            _redis_warned = True


def register_task(state):
    now = int(time.time())
    try:
        pipe = redis_client().pipeline()
        pipe.delete(config.LATEST_KEY)
        pipe.zadd(config.TASK_INDEX_KEY, {state["task_key"]: now})
        pipe.zremrangebyrank(config.TASK_INDEX_KEY, 0, -(config.TASK_INDEX_MAX + 1))
        pipe.execute()
    except Exception:
        pass  # report() below prints the warning once
    report(state, run_id=state["run_id"], goal=state["goal"], target_file=state["target_file"],
           status="RUNNING", phase="starting", attempt=1, started_at=now,
           allow_network=state["allow_network"], plan="", checks=[], output="",
           execution_output="", verdict="", memory_sync="")


# --------------------------------------------------------------------------- vLLM access

def connect_llm():
    """Check vLLM is up and learn the served model name and its context length."""
    global MODEL_ID, CONTEXT_TOKENS
    try:
        data = requests.get(config.LLM_BASE_URL + "/v1/models", timeout=5).json()
    except Exception as e:
        raise LLMError(f"vLLM is not reachable at {config.LLM_BASE_URL} ({short(e)}). "
                       "Start it with Launch_GUI.bat.")
    cards = data.get("data") or []
    if not cards:
        raise LLMError("vLLM is running but reports no models.")
    card = next((c for c in cards if c.get("id") == config.LLM_MODEL), cards[0])
    if card.get("id") != config.LLM_MODEL:
        print(f"[i] vLLM serves '{card.get('id')}', not '{config.LLM_MODEL}'; using the served model.")
    MODEL_ID = card["id"]
    CONTEXT_TOKENS = int(card.get("max_model_len") or config.LLM_FALLBACK_CONTEXT)


TEMPLATE_KWARGS = {"enable_thinking": config.LLM_ENABLE_THINKING}


def count_tokens(messages):
    """Exact prompt size from vLLM's /tokenize; falls back to a conservative estimate."""
    try:
        res = requests.post(config.LLM_BASE_URL + "/tokenize",
                            json={"model": MODEL_ID, "messages": messages,
                                  "add_generation_prompt": True,
                                  "chat_template_kwargs": TEMPLATE_KWARGS},
                            timeout=20)
        res.raise_for_status()
        return int(res.json()["count"])
    except Exception:
        return sum(len(m["content"]) for m in messages) // 3 + 32


def block(title, text, trim=0, keep="head", min_chars=0, code=False):
    """One prompt section. trim > 0 means it may be shortened to fit the context
    window (higher numbers are shortened first); trim=0 sections are never cut."""
    return {"title": title, "text": text or "", "trim": trim, "keep": keep,
            "min": min_chars, "code": code}


def render(blocks):
    parts = []
    for b in blocks:
        if not b["text"].strip():
            continue
        body = f"{TICK3}python\n{b['text']}\n{TICK3}" if b["code"] else b["text"]
        parts.append(f"{b['title']}\n{body}" if b["title"] else body)
    return "\n\n".join(parts)


def cut(text, n_chars, keep):
    if n_chars <= 0:
        return ""
    if len(text) <= n_chars:
        return text
    note = f"[... {len(text) - n_chars} characters cut to fit the context window ...]"
    return text[:n_chars] + "\n" + note if keep == "head" else note + "\n" + text[-n_chars:]


def fit_messages(system, blocks, want_out, min_out, extra_margin=0):
    """Shorten trimmable sections until prompt + answer fit in the context window.
    Returns (messages, max_tokens)."""
    blocks = [dict(b) for b in blocks]
    shortened = []
    for _ in range(16):
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": render(blocks)}]
        used = count_tokens(messages)
        room = CONTEXT_TOKENS - used - 64 - extra_margin
        if room >= want_out:
            max_tokens = want_out
            break
        candidates = [b for b in blocks if b["trim"] > 0 and len(b["text"]) > b["min"]]
        if not candidates:
            if room >= min_out:
                max_tokens = room
                break
            raise ContextTooSmall(
                f"the prompt needs {used} tokens plus at least {min_out} for the answer, "
                f"but the model's context window is {CONTEXT_TOKENS} tokens")
        b = max(candidates, key=lambda x: x["trim"])
        new_len = max(b["min"], len(b["text"]) - int((want_out - room) * 3.5) - 200)
        if new_len < 300 and b["min"] == 0:
            new_len = 0
        if new_len <= b["min"]:
            b["trim"] = 0   # can't shrink this one any further
        b["text"] = cut(b["text"], new_len, b["keep"])
        if b["title"] not in shortened:
            shortened.append(b["title"])
    else:
        raise ContextTooSmall("could not fit the prompt into the context window")
    for title in shortened:
        print(f"    [i] Shortened '{title.rstrip(':')}' to fit the {CONTEXT_TOKENS}-token context window.")
    return messages, max_tokens


def llm_chat(label, system, blocks, want_out, min_out, temperature=None):
    """One chat completion with context budgeting. Returns (text, finish_reason)."""
    for try_no in range(2):
        messages, max_tokens = fit_messages(system, blocks, want_out, min_out,
                                            extra_margin=0 if try_no == 0 else 768)
        try:
            resp = LLM.chat.completions.create(
                model=MODEL_ID, messages=messages, max_tokens=max_tokens,
                temperature=config.LLM_TEMPERATURE if temperature is None else temperature,
                top_p=config.LLM_TOP_P,
                extra_body={"top_k": config.LLM_TOP_K, "chat_template_kwargs": TEMPLATE_KWARGS})
        except BadRequestError as e:
            if try_no == 0:
                print(f"    [!] {label}: vLLM rejected the request ({short(e, 200)}); "
                      "retrying with a smaller prompt.")
                continue
            raise LLMError(f"{label}: vLLM rejected the request: {short(e)}")
        except APIConnectionError as e:
            raise LLMError(f"{label}: lost connection to vLLM at {config.LLM_BASE_URL} ({short(e)})")
        except APIStatusError as e:
            raise LLMError(f"{label}: vLLM returned HTTP {e.status_code}: {short(e)}")
        choice = resp.choices[0]
        # If thinking is on and vLLM has no reasoning parser, drop the reasoning text.
        text = re.sub(r"<think>.*?</think>", "", choice.message.content or "", flags=re.DOTALL)
        return text.strip(), choice.finish_reason
    raise LLMError(f"{label}: request failed")


# --------------------------------------------------------------------------- parsing model replies

_FENCE_OPEN = re.compile(r"^\s*`{3,}\s*([\w+.#-]*)")
_FENCE_CLOSE = re.compile(r"^\s*`{3,}\s*$")


def extract_code(raw):
    """Pull the Python file out of a model reply. Prefers ```python / ```py blocks,
    takes the longest candidate, and tolerates a missing closing fence (cut-off output).
    Returns (code, had_fence)."""
    lines = raw.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        m = _FENCE_OPEN.match(lines[i])
        if m:
            lang = m.group(1).lower()
            body = []
            i += 1
            while i < len(lines) and not _FENCE_CLOSE.match(lines[i]):
                body.append(lines[i])
                i += 1
            blocks.append((lang, "\n".join(body)))
        i += 1
    if not blocks:
        return raw.strip(), False
    python = [b for b in blocks if b[0] in ("python", "py", "python3")]
    untagged = [b for b in blocks if not b[0]]
    pool = python or untagged or blocks
    return max(pool, key=lambda b: len(b[1]))[1].strip("\n"), True


def parse_json_object(text):
    """First JSON object in a reply (tolerates fences, prose and single quotes)."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    for loader in (json.loads, ast.literal_eval):
        try:
            value = loader(m.group(0))
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    return None


# --------------------------------------------------------------------------- files and folders

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-]+\.py$")


def choose_target(goal, explicit, run_id):
    """Pick the workspace file to create or edit. Returns (filename, reason)."""
    if explicit:
        name = os.path.basename(explicit.strip().strip("\"'"))
        if not name.lower().endswith(".py"):
            name += ".py"
        if not _SAFE_NAME.match(name):
            raise ValueError(f"Target '{explicit}' must be a plain file name like my_tool.py "
                             "(letters, digits, _ and -).")
        if name in config.PROTECTED_FILES:
            raise ValueError(f"'{name}' is pipeline infrastructure and can't be a target.")
        return name, "set in the Target box"
    found = []
    for m in re.finditer(r"(?<![\w\-])([A-Za-z0-9_\-]+\.py)\b", goal):
        name = m.group(1)
        if name not in config.PROTECTED_FILES and name not in found:
            found.append(name)
    if found:
        new = [n for n in found if not os.path.exists(os.path.join(config.WORKSPACE, n))]
        if len(found) > 1 and new:
            others = ", ".join(n for n in found if n != new[0])
            return new[0], f"the new file named in the goal; also mentioned: {others}"
        return found[0], "named in the goal"
    return f"task_{run_id.replace('-', '_')}.py", "no file named in the goal, so it gets a new name"


def load_attachments(paths, target):
    """Read attached files (kept separate from the goal). Returns (text, names)."""
    target_path = os.path.normcase(os.path.abspath(os.path.join(config.WORKSPACE, target)))
    parts, names = [], []
    for p in paths:
        name = os.path.basename(p)
        if os.path.normcase(os.path.abspath(p)) == target_path:
            print(f"[i] Attachment {name} is the target file; it is already included in full.")
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                content = f.read(200_000)
        except OSError as e:
            print(f"[!] Could not read attachment {p}: {e}")
            continue
        parts.append(f"--- {name} ---\n{content}")
        names.append(name)
        print(f"[+] Attachment: {name} ({len(content)} characters)")
    return "\n\n".join(parts), names


def stage_dir(state, attempt):
    return os.path.join(config.RUNS_DIR, state["run_id"], f"a{attempt}")


def prune_runs():
    """Keep only the newest KEEP_RUNS per-run scratch folders."""
    try:
        runs = sorted(d for d in os.listdir(config.RUNS_DIR)
                      if re.fullmatch(r"\d{8}-\d{6}", d)
                      and os.path.isdir(os.path.join(config.RUNS_DIR, d)))
    except OSError:
        return
    for d in runs[:-config.KEEP_RUNS]:
        shutil.rmtree(os.path.join(config.RUNS_DIR, d), ignore_errors=True)


def prune_history(stem):
    pattern = re.compile(rf"^{re.escape(stem)}\.\d{{8}}-\d{{6}}\.py$")
    try:
        files = sorted(f for f in os.listdir(config.HISTORY_DIR) if pattern.match(f))
    except OSError:
        return
    for f in files[:-config.KEEP_HISTORY_PER_FILE]:
        try:
            os.remove(os.path.join(config.HISTORY_DIR, f))
        except OSError:
            pass


def promote(state):
    """Copy the verified candidate into the workspace, backing up the old file first."""
    target = state["target_file"]
    staged = os.path.join(stage_dir(state, state["attempt"]), target)
    dest = os.path.join(config.WORKSPACE, target)
    backup = None
    if os.path.exists(dest):
        os.makedirs(config.HISTORY_DIR, exist_ok=True)
        stem = os.path.splitext(target)[0]
        backup = os.path.join(config.HISTORY_DIR, f"{stem}.{time.strftime('%Y%m%d-%H%M%S')}.py")
        shutil.copy2(dest, backup)
        prune_history(stem)
    tmp = dest + ".tmp"
    shutil.copyfile(staged, tmp)
    os.replace(tmp, dest)
    return dest, backup


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def remove_pid_file():
    try:
        with open(PID_FILE) as f:
            mine = f.read().strip() == str(os.getpid())
        if mine:
            os.remove(PID_FILE)
    except OSError:
        pass


# --------------------------------------------------------------------------- sandbox (Node 2)

_INFRA_MARKERS = ("docker: ", "Error response from daemon", "Unable to find image",
                  "ssh: ", "Permission denied (publickey", "Could not resolve hostname",
                  "timeout: failed to run command")


def run_ssh(remote_cmd, timeout):
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", config.SSH_TARGET, remote_cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=timeout)


def check_sandbox():
    """Fail fast, before any LLM work, if Node 2 or the sandbox image isn't ready."""
    try:
        res = run_ssh(f"docker image inspect --format ok {shlex.quote(config.SANDBOX_IMAGE)}", timeout=30)
    except subprocess.TimeoutExpired:
        raise InfraError(f"SSH to {config.SSH_TARGET} timed out.")
    except FileNotFoundError:
        raise InfraError("ssh.exe was not found on this machine.")
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip()[-400:]
        if "No such image" in detail or "No such object" in detail:
            raise InfraError(
                f"the sandbox image '{config.SANDBOX_IMAGE}' is missing on Node 2. Build it with: "
                "ssh server@192.168.254.25 \"cd /mnt/blackboard/docker && docker compose build\"")
        raise InfraError(f"can't run Docker on Node 2 over SSH: {detail}")


def docker_command(name, remote_dir, target, allow_network):
    """A fresh, locked-down container for one test run. Only this attempt's folder is
    writable; the workspace is mounted read-only; no network unless allowed."""
    args = [
        "docker", "run", "--rm", "--pull=never", "--name", name,
        "--network", "bridge" if allow_network else "none",
        "--memory", config.SANDBOX_MEMORY, "--memory-swap", config.SANDBOX_MEMORY,
        "--cpus", str(config.SANDBOX_CPUS), "--pids-limit", str(config.SANDBOX_PIDS),
        "--read-only", "--tmpfs", "/tmp:rw,size=256m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONUNBUFFERED=1",
        "-e", "PYTHONPATH=/work:/workspace",
        "-v", f"{remote_dir}:/work", "-v", f"{config.REMOTE_WORKSPACE}:/workspace:ro",
        "-w", "/work", config.SANDBOX_IMAGE,
        "timeout", "-k", "3", str(config.SANDBOX_TIMEOUT), "python3", target, "--test",
    ]
    cmd = " ".join(shlex.quote(a) for a in args)
    # Run as the share's owner so the script can write to /work. Expanded by the remote shell.
    return cmd.replace("docker run ", 'docker run --user "$(id -u):$(id -g)" ', 1)


# --------------------------------------------------------------------------- graph nodes

def memory_retriever_node(state):
    lines = ["\n[Node: Memory Retriever] Searching Qdrant for similar past solutions..."]
    try:
        vector = embed(state["goal"][:2000], "query")
        hits = get_qdrant().query_points(collection_name=config.COLLECTION_NAME, query=vector,
                                         limit=config.MEMORY_TOP_K, with_payload=True).points
    except Exception as e:
        lines.append(f"--> Memory search skipped: {short(e)}")
        print("\n".join(lines))
        return {"memory_context": "", "memory_summary": ""}
    code_parts, summaries = [], []
    for hit in hits:
        p = hit.payload or {}
        name = p.get("filename", "?")
        if hit.score < config.MEMORY_MIN_SCORE:
            lines.append(f"--> {name}: score {hit.score:.3f} (below {config.MEMORY_MIN_SCORE:.2f}, ignored)")
            continue
        lines.append(f"--> Reusing pattern from {name} (score {hit.score:.3f})")
        summaries.append(f"- {name}: {p.get('summary', '')}")
        code_parts.append(f"--- {name} (built for: {str(p.get('goal', ''))[:200]}) ---\n"
                          f"{str(p.get('code', ''))[:8000]}")
    if not hits:
        lines.append("--> No stored solutions yet.")
    print("\n".join(lines))
    return {"memory_context": "\n\n".join(code_parts), "memory_summary": "\n".join(summaries)}


def research_scout_node(state):
    target = state["target_file"]
    lines = []
    existing = ""
    target_path = os.path.join(config.WORKSPACE, target)
    if os.path.exists(target_path):
        with open(target_path, encoding="utf-8", errors="replace") as f:
            existing = f.read()
        lines.append(f"\n[Node: Research Scout] {target} already exists ({len(existing.splitlines())} lines), "
                     "so this is an edit. The engineer gets the full file.")

    # A short brief on another workspace file the goal mentions (reference material).
    brief = ""
    goal_lower = state["goal"].lower()
    try:
        names = sorted(f for f in os.listdir(config.WORKSPACE) if f.endswith(".py"))
    except OSError:
        names = []
    ref = next((n for n in names
                if n != target and n not in state["attachment_names"]
                and re.search(r"(?<![\w\-])" + re.escape(n.lower()) + r"\b", goal_lower)), None)
    if ref:
        with open(os.path.join(config.WORKSPACE, ref), encoding="utf-8", errors="replace") as f:
            ref_code = f.read()
        ask = ("Extract a concise technical brief (max 6 bullet points) for someone implementing the goal:\n"
               "- Available classes, functions, and signatures worth reusing.\n"
               "- Hardcoded network ports, endpoints, or Redis keys.\n"
               "- Execution constraints (CLI arguments, test flags, environment checks).\n"
               "Return ONLY the bullet points.")
        try:
            if config.HELPER_BACKEND == "node1":
                text, _ = llm_chat(
                    "Scout", "You are a technical research scout. Be concise and factual.",
                    [block(f"Existing file {ref}:", ref_code, trim=2, code=True, min_chars=2000),
                     block("Goal:", state["goal"][:1500]),
                     block("Instructions:", ask)],
                    want_out=500, min_out=200, temperature=0.2)
            else:
                text = ollama_generate(
                    f"You are a technical research scout. Inspect this existing Python file '{ref}':\n\n"
                    f"{TICK3}python\n{ref_code[:12000]}\n{TICK3}\n\n"
                    f"The user wants to accomplish this goal: \"{state['goal'][:1500]}\"\n\n" + ask,
                    temperature=0.1, timeout=60, num_predict=400)
            lines.append(f"\n[Node: Research Scout] Brief on referenced file {ref} "
                         f"({'Node 1' if config.HELPER_BACKEND == 'node1' else 'Node 3'}):\n{text}")
            brief = f"Notes on {ref}:\n{text}"
        except Exception as e:
            lines.append(f"\n[Node: Research Scout] Brief on {ref} skipped ({short(e)}).")
    if lines:
        print("\n".join(lines))
    return {"existing_code": existing, "research_brief": brief}


def planner_node(state):
    print("\n[Node: Architect Planner] Designing the plan and acceptance checks...")
    report(state, phase="planning")
    target = state["target_file"]
    network = ("the sandbox can reach the LAN" if state["allow_network"]
               else "the sandbox has NO network access")
    instructions = (
        "Return ONLY a JSON object, no prose:\n"
        '{"steps": ["...", "..."], "checks": ["...", "..."]}\n'
        "- steps: 3-5 concrete implementation steps.\n"
        f"- checks: 2-4 acceptance checks a reviewer can confirm from the script's stdout and exit "
        f"code when it runs as `python3 {target} --test` in an isolated sandbox ({network}; "
        f"Python {config.SANDBOX_PYTHON} standard library plus {', '.join(config.SANDBOX_PACKAGES)}). "
        "Each check must be specific and observable, e.g. 'prints one line per host with UP or DOWN'. "
        "Don't require services the sandbox can't reach."
    )
    blocks = [
        block("Goal:", state["goal"]),
        block("Target file:", target),
        block(f"Current contents of {target} (this is an edit):", state["existing_code"],
              trim=1, code=True),
        block("Attached files:", state["attachments"], trim=3),
        block("Notes on referenced code:", state["research_brief"], trim=2),
        block("Similar past solutions:", state["memory_summary"], trim=4),
        block("Instructions:", instructions),
    ]
    raw, _ = llm_chat("Planner", "You are a pragmatic software architect who plans small, "
                      "testable Python utilities.", blocks, want_out=1000, min_out=300)
    data = parse_json_object(raw) or {}
    steps = [str(s).strip() for s in data.get("steps") or [] if str(s).strip()]
    checks = [str(c).strip() for c in data.get("checks") or [] if str(c).strip()][:4]
    plan = numbered(steps) if steps else raw
    print("\n" + "=" * 20 + " ARCHITECT EXECUTION PLAN " + "=" * 20)
    print(plan)
    print("Acceptance checks:\n" + (numbered(checks) if checks else "(none parsed; the verifier will judge against the goal)"))
    print("=" * 66)
    report(state, phase="planned", plan=plan, checks=checks)
    return {"plan": plan, "checks": checks}


def engineer_system(state):
    network = ("enabled: the script can reach the LAN (192.168.254.0/24)" if state["allow_network"]
               else "disabled: there is no network in the sandbox, so --test mode must still "
                    "complete when other hosts are unreachable")
    return (
        "You are an expert Python systems programmer for a home-lab cluster.\n"
        "Rules for every script:\n"
        f"- Reply with the COMPLETE file in a single {TICK3}python fenced block and nothing else.\n"
        f"- It must run unattended as `python3 {state['target_file']} --test`: no prompts, no required "
        f"arguments, no GUI, no endless loops. In --test mode it must finish within "
        f"{config.SANDBOX_TIMEOUT} seconds.\n"
        "- In --test mode, print clear evidence for each acceptance check to stdout.\n"
        "- Exit with a non-zero status when something fails. Never hide failures behind broad "
        "try/except blocks, and never fake results (for example hardcoding success instead of "
        "actually checking).\n"
        f"- Use the Python {config.SANDBOX_PYTHON} standard library plus only these installed "
        f"packages: {', '.join(config.SANDBOX_PACKAGES)}.\n"
        "- The script runs in /work, a writable scratch folder. Existing workspace files are "
        "read-only under /workspace. Write any output files to the current folder or /tmp.\n"
        f"- Network is {network}."
    )


def engineer_node(state):
    attempt, target = state["attempt"], state["target_file"]
    fixing = bool(state["error"])
    print(f"\n[Node: Engineer Coder] {'Fixing' if fixing else 'Writing'} {target} "
          f"(attempt {attempt}/{config.MAX_ATTEMPTS})...")
    report(state, phase=f"coding (attempt {attempt}/{config.MAX_ATTEMPTS})", attempt=attempt)

    checks = numbered(state["checks"]) or "(none given; demonstrate the goal clearly)"
    blocks = [
        block("Goal:", state["goal"]),
        block("Target file:", target),
        block("Acceptance checks (the --test run must demonstrate each one):", checks),
        block("Plan:", state["plan"]),
    ]
    existing = state["existing_code"]
    if fixing:
        blocks += [
            block(f"The previous attempt failed (attempt {attempt - 1}):", state["error"],
                  trim=2, keep="tail", min_chars=1500),
            block("Previous version:", state["code"], code=True),
            block(f"Original {target} before your changes:", existing, trim=3, code=True),
            block("Attached files:", state["attachments"], trim=4),
            block("Instructions:", "Fix the problem while still meeting the goal and every "
                  "acceptance check. Don't delete required functionality just to make the error go "
                  "away. Return the complete corrected file."),
        ]
    else:
        blocks += [
            block(f"Current contents of {target}. Modify this file and keep its existing behaviour "
                  "unless the goal says otherwise:", existing, code=True),
            block("Attached files:", state["attachments"], trim=3),
            block("Notes on referenced code:", state["research_brief"], trim=2),
            block("Similar past solutions (reference only):", state["memory_context"], trim=4),
            block("Instructions:", f"Write the complete {target}."),
        ]

    # Leave room for the whole file in the answer; edits need at least the original's size.
    base_tokens = len(state["code"] if fixing else existing) // 3
    min_out = max(1200, base_tokens + 300)
    want_out = max(min_out, base_tokens + 800,
                   min(config.ENGINEER_MAX_OUTPUT, CONTEXT_TOKENS // 2))
    raw, finish = llm_chat("Engineer", engineer_system(state), blocks, want_out, min_out)
    code, _ = extract_code(raw)

    if finish == "length":
        print("[!] The engineer's answer hit the output limit, so the file is incomplete. "
              "Asking for a more compact version.")
        msg = ("Your previous answer was cut off at the output limit, so the file was incomplete. "
               "Write a more compact version: fewer comments, no repeated code, same functionality.")
        if state["error"]:
            msg += "\n\nThe problem you were fixing:\n" + tail(state["error"], 3000)
        return fail(state, "truncated", msg)
    if not code.strip():
        print("[!] The engineer's answer contained no code.")
        return fail(state, "no_code", f"Your answer contained no code. Reply with the complete file "
                                      f"in a {TICK3}python block.")
    try:
        compile(code, target, "exec")
    except SyntaxError as e:
        detail = f"SyntaxError on line {e.lineno}: {e.msg}\n    {(e.text or '').rstrip()}"
        print(f"[!] The generated file doesn't compile: {detail}")
        return fail(state, "syntax", f"The file doesn't compile:\n{detail}", code=code)

    folder = stage_dir(state, attempt)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, target)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(code.rstrip() + "\n")
    print(f"    Candidate ({len(code.splitlines())} lines) staged at {path}")
    return {"code": code, "status": "CODED", "error": "", "failure_kind": ""}


def sandbox_executor_node(state):
    attempt, target = state["attempt"], state["target_file"]
    name = f"agent-{state['run_id']}-a{attempt}"
    remote_dir = f"{config.REMOTE_RUNS_DIR}/{state['run_id']}/a{attempt}"
    network = "LAN network" if state["allow_network"] else "no network"
    print(f"\n[Node: Sandbox Executor] Running {target} --test in a fresh container on Node 2 "
          f"({network}, {config.SANDBOX_TIMEOUT}s limit)...")
    report(state, phase=f"testing (attempt {attempt}/{config.MAX_ATTEMPTS})")
    started = time.time()
    try:
        res = run_ssh(docker_command(name, remote_dir, target, state["allow_network"]),
                      timeout=config.SANDBOX_TIMEOUT + 45)
    except subprocess.TimeoutExpired:
        try:
            run_ssh(f"docker rm -f {name}", timeout=30)
        except Exception:
            pass
        msg = (f"The run didn't finish within {config.SANDBOX_TIMEOUT} seconds and was killed. "
               "--test mode must exit on its own: no endless loops, no waiting for input or network.")
        print(f"[!] {msg}")
        return fail(state, "runtime", msg)
    elapsed = time.time() - started
    out, err, rc = res.stdout or "", res.stderr or "", res.returncode
    if rc in (125, 126, 127, 255) and any(m in err for m in _INFRA_MARKERS):
        raise InfraError(f"the sandbox container couldn't start (exit {rc}): {err.strip()[-600:]}")

    print(f"    Exit code {rc} after {elapsed:.1f}s")
    if out.strip():
        print("    --- stdout ---\n" + tail(out.rstrip(), 3000))
    if err.strip():
        print("    --- stderr ---\n" + tail(err.rstrip(), 3000))

    if rc == 124 or (rc == 137 and elapsed >= config.SANDBOX_TIMEOUT):
        return fail(state, "runtime",
                    f"The script ran longer than {config.SANDBOX_TIMEOUT} seconds and was stopped. "
                    "--test mode must finish quickly on its own (no endless loops, no waiting for "
                    f"input).\nSTDOUT (tail):\n{tail(out, 1500)}\nSTDERR (tail):\n{tail(err, 1500)}")
    if rc == 137:
        return fail(state, "runtime", f"The script was killed (exit 137), most likely by the "
                                      f"{config.SANDBOX_MEMORY} memory limit.\nSTDERR (tail):\n{tail(err, 1500)}")
    if rc != 0:
        return fail(state, "runtime",
                    f"Exit code {rc}.\nSTDERR:\n{tail(err, 4000)}\nSTDOUT (tail):\n{tail(out, 1500)}")
    if "Traceback (most recent call last)" in err:
        return fail(state, "runtime",
                    "The script exited with code 0 but printed a traceback, so an exception was caught "
                    "and hidden, or a thread crashed. Let real errors fail the run.\nSTDERR:\n"
                    + tail(err, 4000))
    report(state, phase=f"verifying (attempt {attempt}/{config.MAX_ATTEMPTS})", execution_output=out)
    return {"status": "EXECUTED", "execution_output": out, "execution_stderr": err}


def verifier_node(state):
    attempt, target = state["attempt"], state["target_file"]
    print("\n[Node: Verifier] Checking the test output against the acceptance checks...")
    network = ("Network access was DISABLED in the sandbox, so failed connections to other hosts are "
               "expected and fine when the script reports them clearly."
               if not state["allow_network"] else "Network access was enabled in the sandbox.")
    instructions = (
        "Reply with ONLY this JSON object:\n"
        '{"pass": true or false, "failed_checks": ["..."], "reason": "one or two sentences"}\n'
        "Fail the run if the output lacks evidence for any acceptance check, if results are faked "
        "(for example hardcoded success instead of actually checking), or if errors are being "
        "swallowed. Judge only what the goal and checks require; don't fail for style or wording."
    )
    blocks = [
        block("Goal:", state["goal"]),
        block("Acceptance checks:", numbered(state["checks"]) or "(none; judge against the goal)"),
        block(f"Test run: python3 {target} --test finished with exit code 0.", network),
        block("STDOUT:", state["execution_output"] or "(empty)", trim=2, keep="tail", min_chars=1500),
        block("STDERR:", state["execution_stderr"], trim=3, keep="tail"),
        block("Script source:", state["code"], trim=4, code=True, min_chars=2000),
        block("Instructions:", instructions),
    ]
    raw, _ = llm_chat("Verifier", "You are a strict QA reviewer. You decide whether a script's test "
                      "run really demonstrates its goal. Reply with JSON only.",
                      blocks, want_out=400, min_out=150, temperature=0.0)
    data = parse_json_object(raw)
    if data is None or "pass" not in data:
        m = re.search(r'"?pass"?\s*[:=]\s*(true|false)', raw, re.IGNORECASE)
        if m:
            data = {"pass": m.group(1).lower() == "true", "reason": raw[:300]}
        else:
            print("    [!] The verifier's reply wasn't valid JSON; accepting the run "
                  "(exit code 0, no traceback).")
            data = {"pass": True, "reason": "verifier reply unreadable; accepted on exit code"}
    passed = data.get("pass") in (True, "true", "True", 1)
    reason = str(data.get("reason") or "").strip()
    failed = [str(c) for c in (data.get("failed_checks") or []) if str(c).strip()]
    verdict = ("PASS" if passed else "FAIL") + (f": {reason}" if reason else "")
    if failed and not passed:
        verdict += "\nFailed checks: " + "; ".join(failed)
    print(f"    Verdict: {verdict}")
    if passed:
        return {"status": "PASSED", "verdict": verdict}
    return fail(state, "verify",
                "The script ran, but a reviewer found it doesn't meet the acceptance checks.\n"
                f"{verdict}\nMake the --test run show real, computed results for every check.",
                verdict=verdict)


def error_condenser_node(state):
    raw_error = state["error"]
    where = "Node 1" if config.HELPER_BACKEND == "node1" else "Node 3"
    print(f"\n[Node: Error Condenser] Diagnosing the failure on {where} "
          f"(attempt {state['attempt'] - 1})...")
    report(state, phase=f"diagnosing (attempt {state['attempt'] - 1}/{config.MAX_ATTEMPTS})")
    ask = ("Give a concise diagnosis:\n"
           "1. Exact line number and exception type, or which check failed.\n"
           "2. Root cause (why it failed).\n"
           "3. The exact logical fix required.\n"
           "Keep it under 5 sentences. Don't write replacement code.")
    try:
        if config.HELPER_BACKEND == "node1":
            diagnosis, _ = llm_chat(
                "Condenser", "You are an expert Python debugger. A script failed inside a Linux container.",
                [block("What the script should do:", state["goal"][:1500]),
                 block("Acceptance checks:", numbered(state["checks"])),
                 block("Failing code:", state["code"], trim=2, code=True, min_chars=3000),
                 block("Error output:", raw_error, trim=1, keep="tail", min_chars=1500),
                 block("Instructions:", ask)],
                want_out=400, min_out=150, temperature=0.2)
        else:
            diagnosis = ollama_generate(
                "You are an expert runtime debugger. A Python script failed inside a Linux container.\n"
                f"What the script should do: {state['goal'][:600]}\n\n"
                f"Failing code:\n{TICK3}python\n{head(state['code'], 14000)}\n{TICK3}\n\n"
                f"Error output:\n{tail(raw_error, 5000)}\n\n" + ask,
                temperature=0.1, timeout=60, num_predict=300)
    except Exception as e:
        print(f"-> Condenser skipped ({short(e)}); the engineer gets the raw error.")
        return {}
    print(f"-> Diagnosis ({where}):\n{diagnosis}")
    return {"error": f"DIAGNOSIS:\n{diagnosis}\n\nRAW ERROR (tail):\n{tail(raw_error, 2500)}"}


def finalize_node(state):
    target = state["target_file"]
    if state["status"] == "PASSED":
        dest, backup = promote(state)
        print(f"\n[+] PASSED on attempt {state['attempt']}. Promoted {target} to {dest}")
        if backup:
            print(f"    Previous version saved as {backup}")
        report(state, status="PASSED", phase="done", attempt=state["attempt"],
               output=state["execution_output"], execution_output=state["execution_output"],
               verdict=state["verdict"])
        dispatch_ingest(state)
        return {}
    print(f"\n[x] FAILED after {config.MAX_ATTEMPTS} attempts. {target} in the workspace was not changed.")
    for n in range(config.MAX_ATTEMPTS, 0, -1):
        candidate = os.path.join(stage_dir(state, n), target)
        if os.path.exists(candidate):
            print(f"    Last candidate kept for inspection: {candidate}")
            break
    report(state, status="FAILED", phase="gave up", attempt=config.MAX_ATTEMPTS,
           output=state["error"], execution_output=state["error"], verdict=state["verdict"])
    return {}


def dispatch_ingest(state):
    """Store the verified script in Qdrant memory in a detached background process."""
    worker = os.path.join(config.WORKSPACE, "background_ingest.py")
    if not os.path.exists(worker):
        return
    job_path = os.path.join(config.RUNS_DIR, state["run_id"], "ingest_job.json")
    job = {"target_file": state["target_file"], "goal": state["goal"], "checks": state["checks"],
           "verdict": state["verdict"], "task_key": state["task_key"]}
    try:
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f)
        os.makedirs(config.LOG_DIR, exist_ok=True)
        log_path = os.path.join(config.LOG_DIR, "ingest.log")
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
        with open(log_path, "a", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, worker, "--job", job_path], cwd=config.WORKSPACE,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                             creationflags=flags, close_fds=True)
        print(f"[*] Storing {state['target_file']} in long-term memory in the background "
              f"(log: {log_path}).")
    except Exception as e:
        print(f"[!] Couldn't start memory ingestion: {e}")


# --------------------------------------------------------------------------- graph

def route_after_engineer(state):
    if state["status"] == "CODED":
        return "executor"
    return "finalize" if state["attempt"] > config.MAX_ATTEMPTS else "engineer"


def route_after_executor(state):
    if state["status"] == "EXECUTED":
        return "verifier"
    return "finalize" if state["attempt"] > config.MAX_ATTEMPTS else "condenser"


def route_after_verifier(state):
    if state["status"] == "PASSED":
        return "finalize"
    return "finalize" if state["attempt"] > config.MAX_ATTEMPTS else "engineer"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("retriever", memory_retriever_node)
    g.add_node("scout", research_scout_node)
    g.add_node("planner", planner_node)
    g.add_node("engineer", engineer_node)
    g.add_node("executor", sandbox_executor_node)
    g.add_node("verifier", verifier_node)
    g.add_node("condenser", error_condenser_node)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "retriever")            # retriever and scout run in parallel
    g.add_edge(START, "scout")
    g.add_edge(["retriever", "scout"], "planner")
    g.add_edge("planner", "engineer")
    g.add_conditional_edges("engineer", route_after_engineer, ["executor", "engineer", "finalize"])
    g.add_conditional_edges("executor", route_after_executor, ["verifier", "condenser", "finalize"])
    g.add_conditional_edges("verifier", route_after_verifier, ["finalize", "engineer"])
    g.add_edge("condenser", "engineer")
    g.add_edge("finalize", END)
    return g.compile()


# --------------------------------------------------------------------------- main

def parse_args(argv):
    p = argparse.ArgumentParser(description="Run the LangGraph agent pipeline once.")
    p.add_argument("goal_text", nargs="?", help="goal text (old style)")
    p.add_argument("--goal", help="goal text")
    p.add_argument("--goal-file", help="read the goal from a UTF-8 text file")
    p.add_argument("--target", help="workspace file to create or edit, e.g. my_tool.py")
    p.add_argument("--attach", action="append", default=[], help="file to include as context (repeatable)")
    p.add_argument("--allow-network", action="store_true", help="give the sandbox LAN access")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.goal_file:
        with open(args.goal_file, encoding="utf-8") as f:
            goal = f.read().strip()
    else:
        goal = (args.goal or args.goal_text or DEFAULT_GOAL).strip()
    if not goal:
        print("[!] The goal is empty.")
        return 2
    run_id = time.strftime("%Y%m%d-%H%M%S")
    try:
        target, why = choose_target(goal, args.target, run_id)
    except ValueError as e:
        print(f"[!] {e}")
        return 2

    write_pid_file()
    state: AgentState = {
        "run_id": run_id, "task_key": config.TASK_KEY_PREFIX + run_id, "goal": goal,
        "target_file": target, "attachments": "", "attachment_names": [],
        "allow_network": bool(args.allow_network), "existing_code": "", "memory_context": "",
        "memory_summary": "", "research_brief": "", "plan": "", "checks": [], "code": "",
        "attempt": 1, "status": "INIT", "failure_kind": "", "error": "",
        "execution_output": "", "execution_stderr": "", "verdict": "",
    }
    print("=== Starting LangGraph Autonomous Pipeline ===")
    print(f"Run {run_id} | target: {target} ({why}) | sandbox network: "
          f"{'on' if args.allow_network else 'off'}")
    register_task(state)
    try:
        connect_llm()
        print(f"Model: {MODEL_ID} | context window: {CONTEXT_TOKENS} tokens")
        check_sandbox()
        state["attachments"], state["attachment_names"] = load_attachments(args.attach, target)
        prune_runs()
        final = build_graph().invoke(state, {"recursion_limit": 80})
    except (LLMError, InfraError) as e:
        print(f"\n[x] Run stopped: {e}")
        report(state, status="ERROR", phase="stopped", output=str(e), execution_output=str(e))
        return 2
    except KeyboardInterrupt:
        print("\n[x] Run cancelled.")
        report(state, status="ERROR", phase="cancelled")
        return 2
    except Exception:
        tb = traceback.format_exc()
        print(f"\n[x] Pipeline crashed:\n{tb}")
        report(state, status="ERROR", phase="crashed", output=tb, execution_output=tb)
        return 2
    finally:
        remove_pid_file()
    print("=== LangGraph Pipeline Complete ===")
    return 0 if final.get("status") == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
