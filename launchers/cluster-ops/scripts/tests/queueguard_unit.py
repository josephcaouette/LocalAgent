"""The window's queue and runs it didn't start (no model calls, no real switching). Opening the Agent
Cluster window during a test battery used to switch vLLM back to the normal server within seconds (the
launcher saw the 32k server, the window's own queue was empty), killing the battery's Ultra run. Now
another process's run holds Node 1: nothing starts beside it, the server isn't switched under it, and
the switch back waits until Node 1 has had no run at all for SWITCH_BACK_QUIET_S."""
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import agent_gui as g  # noqa: E402

ACTIVE, switches, launched, digests, stops = [], [], [], [], []
config.active_runs = lambda client: list(ACTIVE)
config.get_redis = lambda **k: None
root = tk.Tk()
root.withdraw()
app = g.AgentControlGUI(root, write_pid=False)
app.server_hook = lambda want, done: None
app._switch_server = lambda want, job: switches.append(want)
app._maybe_digest = lambda: digests.append(1)
app._stop_digest = lambda: stops.append(1)


class Busy:
    """A summary worker that is still running."""

    def poll(self):
        return None


def fake_launch(job):
    job["state"], job["run_id"] = "RUNNING", f"mine-{job['id']}"
    launched.append(job["id"])
    return True


app._launch = fake_launch


def reset(mode, jobs=(), active=()):
    app.jobs[:] = [dict(j) for j in jobs]
    ACTIVE[:] = list(active)
    for record in (switches, launched, digests, stops):
        record.clear()
    app._server_mode, app._switching, app._quiet_since, app._recheck_pending = mode, False, None, False
    app._long_is_mine, app._digest_due, app._digest_proc = False, False, None


checks = []
reset("long", active=["battery-run"])
app._pump_queue()
checks += [("window opened on the 32k server during another run: no switch", switches == []),
           ("  and it looks again later", app._recheck_pending)]

reset("long")
app._pump_queue()
checks.append(("Node 1 just went quiet: no switch yet", switches == [] and app._quiet_since is not None))
app._quiet_since = time.time() - g.SWITCH_BACK_QUIET_S - 1
app._pump_queue()
checks.append(("quiet long enough: back to the normal server", switches == ["normal"]))

reset("long")
app._pump_queue()
ACTIVE[:] = ["battery-next-run"]                     # a battery starts its next run seconds later
app._pump_queue()
checks.append(("a run starting in the quiet period resets it", app._quiet_since is None and switches == []))

low = {"id": 1, "level": "low", "state": "QUEUED", "run_id": None}
reset("normal", [low], active=["battery-run"])
app._pump_queue()
checks.append(("a queued run waits for another process's run", launched == [] and app._recheck_pending))
reset("normal", [low])
app._pump_queue()
checks.append(("  and starts once Node 1 is free", launched == [1]))

ultra = {"id": 2, "level": "ultra", "state": "QUEUED", "run_id": None}
reset("normal", [ultra], active=["battery-run"])
app._pump_queue()
checks.append(("an Ultra run doesn't switch the server under another run", switches == [] and launched == []))
reset("normal", [ultra])
app._pump_queue()
checks.append(("  and switches to 32k once Node 1 is free", switches == ["long"]))

mine = {"id": 3, "level": "low", "state": "RUNNING", "run_id": "mine-3"}
reset("normal", [mine, dict(low, id=4)], active=["mine-3"])
app._pump_queue()
checks.append(("this window's own run isn't 'another run'", launched == [4]))

# The window that put vLLM on 32k switches back as soon as its own queue is empty (set 3's battery
# window waited the quiet period instead and was closed before it, so no run got a summary).
reset("long")
app._long_is_mine = True
app._pump_queue()
checks.append(("its own 32k switch: back to normal at once when its queue is empty", switches == ["normal"]))
reset("long", active=["battery-run"])
app._long_is_mine = True
app._pump_queue()
checks.append(("  but not while another process's run is going", switches == []))
reset("long", [ultra])                  # found on 32k, then its own Ultra run starts on it
app._pump_queue()
app.jobs[0]["state"] = "PASSED"
app._pump_queue()
checks.append(("  and running its own Ultra run on a 32k server it found counts as its own",
               app._long_is_mine and switches == ["normal"]))

# Run summaries use Node 1's GPU: they wait for other processes' runs and stop when one starts.
reset("normal", active=["battery-run"])
app._digest_due = True
app._pump_queue()
checks.append(("summaries wait while another process's run is going", digests == [] and app._recheck_pending))
reset("normal")
app._digest_due = True
app._pump_queue()
checks.append(("  and start once Node 1 is free", digests == [1]))
reset("normal", active=["battery-next-run"])
app._digest_proc = Busy()
app._pump_queue()
checks.append(("a summary in progress stops when another process's run starts", stops == [1] and digests == []))

ok = True
for name, good in checks:
    ok &= bool(good)
    print(("PASS " if good else "FAIL ") + name)
print("ALL PASS" if ok else "SOME FAILED")
root.destroy()
