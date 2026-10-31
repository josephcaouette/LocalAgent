"""Which Node 3 model writes better example-checking scripts? Same prompt as the pipeline's example
checker, three plans each with one planted wrong example (ex1) and one right one (ex2). Scripts run
in the Node 2 sandbox. Usage: python node3_ab.py [trials] [model ...]"""
import re
import subprocess
import sys
import time

import requests

sys.path.insert(0, r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

PLANS = {
    "cron": ("Create next_runs.py with next_runs(expr, start, count) for standard 5-field cron expressions "
             "(minute hour day-of-month month day-of-week; *, lists, ranges, steps). When both day-of-month and "
             "day-of-week are restricted, a day matches if EITHER matches (Vixie cron).",
             "Rules: standard cron; dow 0 or 7 = Sunday, 1 = Monday; results are strictly after start.\n"
             "Examples: ex1: next_runs('0 0 1,15 * 1', 2024-01-01 00:00, 5) -> 2024-01-08 00:00, 2024-01-15 00:00, "
             "2024-01-22 00:00, 2024-01-29 00:00, 2024-02-05 00:00. ex2: next_runs('30 9 * * *', 2024-03-10 10:00, 2) "
             "-> 2024-03-11 09:30, 2024-03-12 09:30."),
    "bowling": ("Create bowling.py with score(rolls) for ten-pin bowling: a strike scores 10 plus the next two "
                "rolls, a spare 10 plus the next roll, and the tenth frame gets bonus rolls.",
                "Examples: ex1: score([10, 3, 4] + [0] * 16) -> 31. ex2: score([5, 5] * 10 + [5]) -> 150."),
    "calc": ("Create calc.py with evaluate(expr) for integer arithmetic with + - * /, parentheses and unary "
             "minus; / is integer division that truncates toward zero.",
             "Examples: ex1: evaluate('-7/2') -> -4. ex2: evaluate('2*(3+4)') -> 14."),
}


def run_in_sandbox(code):
    cmd = f"docker run --rm -i --network none --memory 256m {config.SANDBOX_IMAGE} timeout 60 python3 -"
    res = subprocess.run(["ssh", "-o", "BatchMode=yes", config.SSH_TARGET, cmd], input=code.encode(),
                         capture_output=True, timeout=120)
    return res.stdout.decode("utf-8", "replace"), res.stderr.decode("utf-8", "replace")


def trial(model, goal, spec):
    prompt = f"Goal:\n{goal}\n\nSpec:\n{spec}\n\n{p.EXAMPLE_INSTRUCTIONS}"
    t0 = time.time()
    r = requests.post(f"{config.OLLAMA_URL}/api/generate", timeout=300, json={
        "model": model, "prompt": prompt, "stream": False, "think": False, "keep_alive": -1,
        "options": {"temperature": 0.2, "num_ctx": config.OLLAMA_NUM_CTX, "num_predict": 3000}}).json()
    code, _ = p.extract_code(r.get("response", ""))
    secs = time.time() - t0
    if not code.strip():
        return "no code", secs
    try:
        compile(code, "x.py", "exec")
    except SyntaxError:
        return "syntax", secs
    if p.static_problems(code, "x.py"):
        return "undefined name", secs
    out, _err = run_in_sandbox(code)
    ex1 = re.search(r"^(AGREE|DISAGREE)\s+ex1\b", out, re.M | re.I)
    ex2 = re.search(r"^(AGREE|DISAGREE)\s+ex2\b", out, re.M | re.I)
    lines = re.findall(r"^(?:AGREE|DISAGREE)\b.*$", out, re.M)
    if not lines:
        return "crash", secs
    if ex1 and ex2:
        right = ex1.group(1).upper() == "DISAGREE" and ex2.group(1).upper() == "AGREE"
        return ("correct" if right else "wrong verdict"), secs
    return f"unlabelled ({len(lines)} lines)", secs


if __name__ == "__main__":
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    models = sys.argv[2:] or [config.WORKER_MODEL, "qwen2.5-coder:7b"]
    tally = {}
    for model in models:
        for task, (goal, spec) in PLANS.items():
            for i in range(trials):
                verdict, secs = trial(model, goal, spec)
                tally.setdefault(model, []).append(verdict)
                print(f"{model:18} {task:8} #{i + 1}: {verdict:16} {secs:4.0f}s", flush=True)
    for model, verdicts in tally.items():
        print(f"{model}: {verdicts.count('correct')}/{len(verdicts)} correct | {verdicts}")
