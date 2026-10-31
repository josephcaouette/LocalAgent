"""Read the bench log from stdin; print only state/mode changes, errors and the final summary."""
import re
import sys

last = None
for line in sys.stdin:
    line = line.rstrip()
    states = re.findall(r"\((\d+), '(\w+)', '([A-Z]+)'", line)
    mode = re.search(r"\('mode', '?(\w+)'?, (True|False)\)", line)
    if states:
        key = (tuple(states), mode.groups() if mode else None)
        if key != last:
            last = key
            ctx = line.rsplit("| server ctx", 1)[-1].strip() if "| server ctx" in line else "?"
            print(line[:9], " ".join(f"#{i} {lvl} {st}" for i, lvl, st in states),
                  "| mode", mode.group(1) if mode else "?", "switching" if mode and mode.group(2) == "True" else "",
                  "| ctx", ctx, flush=True)
    elif re.search(r"Traceback|Error|Exception|E2E DONE|server context while|PASSED|FAILED", line):
        print(line[:220], flush=True)
