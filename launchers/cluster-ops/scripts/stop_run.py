"""Stop one pipeline run the way the window's Stop button does: end its process tree, remove its PID
file, mark its Redis record STOPPED, and remove its leftover sandbox containers on Node 2.

Usage (Git Bash on Node 1):
    /c/AI/venvs/agent_brain/Scripts/python.exe stop_run.py <run_id> ["reason shown in the Runs tab"]

Only stop runs you started, or that the user asked you to stop.
"""
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, r"Z:\workspace")
import config  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
run_id = sys.argv[1]
reason = sys.argv[2] if len(sys.argv) > 2 else "stopped by hand"

pid_file = os.path.join(tempfile.gettempdir(), f"agent_pipeline_{run_id}.pid")
try:
    pid = open(pid_file).read().strip()
except OSError:
    pid = ""
if pid:
    res = subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, text=True)
    print((res.stdout or res.stderr).strip() or f"taskkill exit {res.returncode}")
    try:
        os.remove(pid_file)
    except OSError:
        pass
else:
    print(f"No PID file for {run_id}; it may have finished already. Cleaning up the record anyway.")

r = config.get_redis(timeout=5)
r.hset(config.TASK_KEY_PREFIX + run_id, mapping={"status": "STOPPED", "phase": reason,
                                                 "updated_at": int(time.time())})
r.zrem(config.ACTIVE_KEY, run_id)
if r.hget(config.LATEST_KEY, "run_id") == run_id.encode():
    r.hset(config.LATEST_KEY, mapping={"status": "STOPPED", "phase": reason})
print("Redis record:", r.hget(config.TASK_KEY_PREFIX + run_id, "status").decode())

res = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", config.SSH_TARGET,
                      f"docker ps -aq --filter name=agent-{run_id} | xargs -r docker rm -f | wc -l"],
                     capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
print("Containers removed:", (res.stdout or "?").strip())
