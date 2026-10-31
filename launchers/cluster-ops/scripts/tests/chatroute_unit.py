"""Automatic chat model: Node 1 normally, Node 3 while a run's heartbeat is fresh (no model calls)."""
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import agent_gui as g  # noqa: E402

root = tk.Tk()
root.withdraw()
app = g.AgentControlGUI(root, write_pid=False)
app._chat_worker = lambda *a, **k: None          # don't call any model
r = config.get_redis(decode_responses=True)
fake = "unit-chatroute"


def picks():
    out = {}
    for i, label in enumerate(g.CHAT_MODELS):
        app.chat_backend.current(i)
        out[label.split(" - ")[0]] = app._backend()
    return out


def last_info():
    text = app.chat_view.get("1.0", tk.END)
    return "Node 3 answers until it finishes" in text


try:
    real = [m for m in r.zrange(config.ACTIVE_KEY, 0, -1) if m != fake]
    print("idle:      ", "(skipped: a real run is going, so Automatic correctly picks Node 3)" if real else picks())
    r.zadd(config.ACTIVE_KEY, {fake: time.time()})   # a run's heartbeat
    print("run going: ", picks())
    app.chat_backend.current(0)
    app._start_chat_request([{"role": "user", "content": "hi"}], "chat")
    print("note shown once:", last_info(), end=" | ")
    app.chat_busy = False
    before = app.chat_view.get("1.0", tk.END).count("Node 3 answers")
    app._start_chat_request([{"role": "user", "content": "again"}], "chat")
    print("not repeated:", app.chat_view.get("1.0", tk.END).count("Node 3 answers") == before)
finally:
    r.zrem(config.ACTIVE_KEY, fake)
print("after run: ", picks())
root.destroy()
