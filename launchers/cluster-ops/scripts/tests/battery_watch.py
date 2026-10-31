"""Filter battery.log: print each run as it finishes, plus errors and the end."""
import re
import sys

seen = {}
for line in sys.stdin:
    for num, task, state in re.findall(r"#(\d+) (\S+) (QUEUED|RUNNING|PASSED|FAILED|ERROR|STOPPED|LOST)", line):
        if state in ("PASSED", "FAILED", "ERROR", "STOPPED", "LOST") and seen.get(num) != state:
            print(f"{line[:9]} #{num} {task} {state}", flush=True)
        seen[num] = state
    if re.search(r"Traceback|BATTERY DONE|digests|SCORE|could not", line):
        print(line.rstrip()[:240], flush=True)
