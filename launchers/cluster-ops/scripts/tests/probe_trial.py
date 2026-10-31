"""Trial of Gemini's idea #5: can Node 3 (qwen3.5:9b, no thinking, 8k context) write the probe
file that Ultra and MAX use to compare candidates, in place of Node 1's prober?

Three saved runs from battery set 1 (glob and bowling on Ultra, calc on MAX). Both sources get the
run's goal, spec and interface: Node 1's probe file is the one the run used; Node 3 writes SAMPLES
new ones through the pipeline's own write_probe (same instructions, assembly and checks), with the
model call sent to Node 3. Each probe file then runs in the sandbox on:
- the run's candidates that the reference checker passes: a case where they answer differently is a
  false dispute (in a real run, a referee call on Node 1 for nothing);
- mutants of the final file (one small change each, outside the self-test and main block) that the
  reference checker tells apart from it: the probe file catches a mutant when any answer differs.
Usage: python probe_trial.py [SAMPLES]   (uses Node 3 and the sandbox; Node 1 isn't called)"""
import ast
import glob
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

SAMPLES = int(sys.argv[1]) if len(sys.argv) > 1 else 3
RUNS = {"glob": "20261031-063008", "bowling": "20261031-060246", "calc": "20261031-070215"}
WORK = os.path.join(config.RUNS_DIR, "probe-trial")      # not a run name, so pruning ignores it
REMOTE = "/mnt/blackboard/runs/probe-trial"
SITES, KEEP_MUTANTS, KEEP_CORRECT = 70, 40, 6
SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq, ast.Add: ast.Sub, ast.Sub: ast.Add, ast.And: ast.Or, ast.Or: ast.And}
INTERFACE_ERRORS = {"AttributeError", "NameError", "ImportError", "ModuleNotFoundError"}
STATS = []


def node3_chat(label, system, blocks, want_out, min_out, temperature=None, think=False, think_tokens=None):
    """Stands in for llm_chat: the same prompt, answered by Node 3 without thinking."""
    payload = {"model": config.WORKER_MODEL, "prompt": system + "\n\n" + p.render(blocks), "stream": False,
               "keep_alive": config.OLLAMA_KEEP_ALIVE, "think": False,
               "options": {"temperature": 0.4, "num_ctx": config.OLLAMA_NUM_CTX, "num_predict": 5000}}
    res = requests.post(f"{config.OLLAMA_URL}/api/generate", json=payload, timeout=900)
    res.raise_for_status()
    d = res.json()
    STATS.append({"prompt_tokens": d.get("prompt_eval_count"), "out_tokens": d.get("eval_count"),
                  "secs": round(d.get("total_duration", 0) / 1e9, 1), "done": d.get("done_reason")})
    return d.get("response", ""), ("length" if d.get("done_reason") == "length" else "stop")


def skipped(tree):
    """Nodes in the self-test or the main block: a change there can't change the interface."""
    skip = set()
    for node in ast.walk(tree):
        test = (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and "test" in node.name.lower())
        main = (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__")
        if test or main:
            skip.update(id(n) for n in ast.walk(node))
    return skip


def sites(tree):
    """Every place one small change can go, in a fixed order."""
    skip, out = skipped(tree), []
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Compare):
            out += [(node, i) for i, op in enumerate(node.ops) if type(op) in SWAP]
        elif isinstance(node, (ast.BinOp, ast.BoolOp)) and type(node.op) in SWAP:
            out.append((node, None))
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            out.append((node, None))
    return out


def mutants(source):
    total = len(sites(ast.parse(source)))
    out = {}
    for k in sorted(random.Random(7).sample(range(total), min(total, SITES))):
        tree = ast.parse(source)
        node, i = sites(tree)[k]
        if isinstance(node, ast.Compare):
            node.ops[i] = SWAP[type(node.ops[i])]()
        elif isinstance(node, ast.Constant):
            node.value += 1
        else:
            node.op = SWAP[type(node.op)]()
        out[f"m{k:03d}"] = ast.unparse(tree)
    return out


def sandbox(script, limit=2400):
    """Run a shell script in one sandbox container with the trial folder at /work (read-only)."""
    docker = (f"docker run --rm --network none --memory 1g -e PYTHONDONTWRITEBYTECODE=1 "
              f"-v {REMOTE}:/work:ro -w /work {config.SANDBOX_IMAGE} sh -c {shlex.quote(script)}")
    res = subprocess.run(["ssh", "-o", "BatchMode=yes", config.SSH_TARGET, docker],
                         capture_output=True, text=True, timeout=limit + 120)
    return res.stdout


def sections(out, keep):
    """{name: last matching line or None} from output made of '== /path/name.py' headers."""
    found, name = {}, None
    for line in out.splitlines():
        if line.startswith("== "):
            name = line[3:].strip()
            found[name] = None
        elif name and line.startswith(keep):
            found[name] = line
    return found


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def trial(task, run_id):
    rec = config.get_redis(decode_responses=True).hgetall(config.TASK_KEY_PREFIX + run_id)
    target, run_dir = rec["target_file"], os.path.join(config.RUNS_DIR, run_id)
    final = open(os.path.join(run_dir, f"final_{target}"), encoding="utf-8").read()
    impls = {"final": final}
    for path in sorted(glob.glob(os.path.join(run_dir, "a*c*", target))):
        impls["c_" + os.path.basename(os.path.dirname(path))] = open(path, encoding="utf-8").read()
    impls.update(mutants(final))

    # 1. Which candidates are correct, and which mutants the reference checker can tell apart.
    for name, code in impls.items():
        write(os.path.join(WORK, task, "check", f"{name}.py"), code)
    files = " ".join(f"/work/{task}/check/{n}.py" for n in impls)
    out = sandbox(f'for f in {files}; do echo "== $f"; timeout 30 python3 /work/battery_checks.py {task} "$f" '
                  f'2>/dev/null | head -1; done')
    score = {}
    for path, line in sections(out, "SCORE").items():
        name = os.path.basename(path)[:-3]
        try:
            a, b = line.split()[1].split("/")
            score[name] = (int(a), int(b))
        except (AttributeError, IndexError, ValueError):
            score[name] = (0, 1)               # hung or crashed: the checker tells it apart
    full = lambda n: n in score and score[n][0] == score[n][1]   # noqa: E731
    assert full("final"), f"{task}: the final file doesn't pass the reference checker: {score.get('final')}"
    correct = [n for n in impls if n.startswith("c_") and full(n)][:KEEP_CORRECT]
    caught_by_checker = [n for n in impls if n.startswith("m") and not full(n)][:KEEP_MUTANTS]
    equivalent = sum(1 for n in impls if n.startswith("m") and full(n))

    # 2. Probe files: Node 1's from the run, Node 3's written now.
    state = {"target_file": target, "goal": rec["goal"], "spec": rec["spec"], "interface": rec["interface"],
             "lvl": config.level_settings("ultra")}
    probes = {"node1": open(os.path.join(run_dir, "a1c1", p.PROBE_FILE), encoding="utf-8").read()}
    real, p.llm_chat = p.llm_chat, node3_chat
    gen = []
    try:
        for s in range(SAMPLES):
            before = len(STATS)
            t0 = time.time()
            full_text = p.write_probe(state)
            gen.append({"sample": s + 1, "usable": bool(full_text), "secs": round(time.time() - t0),
                        "calls": STATS[before:]})
            if full_text:
                probes[f"node3_{s + 1}"] = full_text
    finally:
        p.llm_chat = real

    # 3. Every probe file on the final file, the correct candidates and the told-apart mutants.
    names = ["final"] + correct + caught_by_checker
    for name in names:
        folder = os.path.join(WORK, task, "run", name)
        write(os.path.join(folder, target), impls[name])
        for src, text in probes.items():
            write(os.path.join(folder, f"probe__{src}.py"),
                  text.replace(f"/work/{target}", f"/work/{task}/run/{name}/{target}"))
    # Run each probe from its implementation's folder: in a real run the probe file sits next to the
    # script, so `python3 -m name` or a relative path finds it there.
    out = sandbox(f'for f in /work/{task}/run/*/probe__*.py; do echo "== $f"; (cd "$(dirname "$f")" && '
                  f'timeout 40 python3 "$(basename "$f")" 2>/dev/null | grep "^PROBE-RESULTS:"); done')
    keep = os.path.join(os.environ.get("TEMP", "."), "agent_tests", "probe_trial_files", task)
    os.makedirs(keep, exist_ok=True)
    for src, text in probes.items():                 # for reading afterwards (the trial folder is removed)
        write(os.path.join(keep, f"{src}.py"), text)
    results = {}
    for path, line in sections(out, "PROBE-RESULTS:").items():
        parts = path.split("/")
        results[(parts[-2], parts[-1][len("probe__"):-3])] = (
            json.loads(line[len("PROBE-RESULTS:"):]) if line else None)

    rows = {}
    for src in probes:
        base = results.get(("final", src))
        n = len(base) if base else 0
        iface = sum(1 for r in (base or []) if isinstance(r, dict) and r.get("raised") in INTERFACE_ERRORS)
        answers = [results.get((c, src)) for c in correct]
        broken = sum(1 for a in answers if a is None)
        disputes = sum(1 for i in range(n)
                       if len({json.dumps(a[i], sort_keys=True) for a in answers if a and i < len(a)}) > 1)
        caught = sum(1 for m in caught_by_checker if results.get((m, src)) != base)
        rows[src] = {"cases": n, "ran_on_final": base is not None, "interface_errors": iface,
                     "false_disputes": disputes, "failed_on_correct": broken,
                     "mutants_caught": caught, "mutants": len(caught_by_checker)}
    return {"task": task, "run_id": run_id, "correct_candidates": len(correct),
            "equivalent_mutants": equivalent, "node3_generation": gen, "rows": rows}


if __name__ == "__main__":
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    shutil.copy(os.path.join(HERE, "battery_checks.py"), os.path.join(WORK, "battery_checks.py"))
    report = []
    try:
        for task, run_id in RUNS.items():
            t0 = time.time()
            res = trial(task, run_id)
            report.append(res)
            print(f"\n{task} ({run_id}): {res['correct_candidates']} correct candidates, "
                  f"{res['rows']['node1']['mutants']} mutants the checker tells apart "
                  f"({res['equivalent_mutants']} it can't), {time.time() - t0:.0f}s", flush=True)
            for g in res["node3_generation"]:
                c = g["calls"][-1] if g["calls"] else {}
                print(f"    Node 3 sample {g['sample']}: {'usable' if g['usable'] else 'NOT usable'}, {g['secs']}s, "
                      f"{c.get('prompt_tokens')} prompt + {c.get('out_tokens')} output tokens, {len(g['calls'])} call(s)")
            for src, r in res["rows"].items():
                print(f"    {src:8} cases {r['cases']:3} | caught {r['mutants_caught']:2}/{r['mutants']} mutants | "
                      f"false disputes {r['false_disputes']} | interface errors {r['interface_errors']} | "
                      f"failed on correct code {r['failed_on_correct']}", flush=True)
            with open(os.path.join(HERE, "probe_trial_results.json"), "w", encoding="utf-8") as f:
                json.dump(report, f, indent=1)
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
