"""Same example-checker job as node3_ab.py, written by Node 1 (27B, no thinking) for comparison."""
import re
import sys
import time

sys.path.insert(0, r"Z:\workspace")
from openai import OpenAI  # noqa: E402
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402
from node3_ab import PLANS, run_in_sandbox  # noqa: E402

client = OpenAI(base_url=config.LLM_BASE_URL + "/v1", api_key="local")
model = client.models.list().data[0].id
trials = int(sys.argv[1]) if len(sys.argv) > 1 else 1
tally = []
for task, (goal, spec) in PLANS.items():
    for i in range(trials):
        t0 = time.time()
        r = client.chat.completions.create(model=model, max_tokens=3000, temperature=0.2, messages=[
            {"role": "user", "content": f"Goal:\n{goal}\n\nSpec:\n{spec}\n\n{p.EXAMPLE_INSTRUCTIONS}"}],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        code, _ = p.extract_code(r.choices[0].message.content or "")
        out, err = run_in_sandbox(code) if code.strip() else ("", "no code")
        ex1 = re.search(r"^(AGREE|DISAGREE)\s+ex1\b", out, re.M | re.I)
        ex2 = re.search(r"^(AGREE|DISAGREE)\s+ex2\b", out, re.M | re.I)
        if ex1 and ex2:
            v = "correct" if ex1.group(1).upper() == "DISAGREE" and ex2.group(1).upper() == "AGREE" else "wrong verdict"
        else:
            v = "crash/unlabelled: " + (out.strip().splitlines() or [err.strip().splitlines()[-1] if err.strip() else "?"])[0][:80]
        tally.append(v)
        print(f"Node 1  {task:8} #{i + 1}: {v:20} {time.time() - t0:4.0f}s, {r.usage.completion_tokens} tokens, "
              f"{len(code.splitlines())} lines", flush=True)
print(f"Node 1: {tally.count('correct')}/{len(tally)} correct")
