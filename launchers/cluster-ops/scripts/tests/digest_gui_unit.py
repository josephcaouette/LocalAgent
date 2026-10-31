"""Idle digests from the window: start when idle, stop (and free the lock) when a run launches."""
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
r = config.get_redis(decode_responses=True)


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.05)


before = sum(1 for k in r.zrevrange(config.TASK_INDEX_KEY, 0, 199) if r.hget(k, "digest"))
app._pump_queue()
print("worker started when idle:", app._digest_proc is not None and app._digest_proc.poll() is None)
pump(6)
lock = r.get("workflow:digest_lock")
app._stop_digest()                       # what a launch does
print("killed on launch:", app._digest_proc is None, "| lock freed:", lock is not None and r.get("workflow:digest_lock") is None,
      "| due again:", app._digest_due)
app._pump_queue()                        # idle again: picks up where it stopped
t0 = time.time()
while app._digest_proc is not None and app._digest_proc.poll() is None and time.time() - t0 < 300:
    pump(2)
after = sum(1 for k in r.zrevrange(config.TASK_INDEX_KEY, 0, 199) if r.hget(k, "digest"))
print(f"digests: {before} before, {after} after (worker exit {app._digest_proc.returncode if app._digest_proc else '?'})")
print("log tail:", open(os.path.join(config.LOG_DIR, "digest.log"), encoding="utf-8").read().strip().splitlines()[-1])
root.destroy()
