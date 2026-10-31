"""Prompt fitting with thinking: extras are cut first, then thinking shrinks before the spec is cut."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import run_langgraph_pipeline as p  # noqa: E402

p.CONTEXT_TOKENS = 32768
p.count_tokens = lambda messages, kw=None: sum(len(m["content"]) for m in messages) // 3
p._SHORTENED_NOTED.add("never print")      # keep output short


def fix_prompt():
    return [p.block("Goal:", "g" * 1500), p.block("Spec:", "s" * 9000, trim=3),
            p.block("The previous attempt failed:", "e" * 7500, trim=2, keep="tail", min_chars=1500),
            p.block("Previous version:", "c" * 15000, code=True), p.block("Web notes:", "w" * 3000, trim=4)]


answer_min, think = 8500, 16000
want, mn = answer_min + think, 5300 + 2000
for soft in (0, think // 2):
    blocks = fix_prompt()
    msgs, max_tokens = p.fit_messages("sys", blocks, want, mn, soft=soft)
    text = msgs[1]["content"]
    print(f"soft={soft:>5}: max_tokens={max_tokens} thinking budget={min(think, max_tokens - answer_min)} | "
          f"spec kept={text.count('s') * 100 // 9000}% failure report kept={text.count('e') * 100 // 7500}% "
          f"web kept={text.count('w') * 100 // 3000}%")
