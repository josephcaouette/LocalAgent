#!/bin/bash
# Back up the cluster's code and settings to GitHub. Runs on Node 2, which owns the files.
# Started by Backup_To_GitHub.bat on the Desktop (or by cron, if you schedule it).
# Usage: bash /mnt/blackboard/launchers/backup_node2.sh [GitHub repo address, first run only]
set -e
cd /mnt/blackboard

# 1. Export the memory store (summaries and code, no vectors) so it can be rebuilt from Git
#    with reindex_memory.py. If you turn on a Qdrant API key, add -H "api-key: ..." to curl.
mkdir -p memory_export
if curl -sf --max-time 20 -X POST http://localhost:6333/collections/agent_solutions/points/scroll \
     -H 'Content-Type: application/json' \
     -d '{"limit": 10000, "with_payload": true, "with_vector": false}' -o /tmp/agent_memory.json; then
  python3 - <<'PY'
import json
points = json.load(open("/tmp/agent_memory.json"))["result"]["points"]
points.sort(key=lambda p: str(p["payload"].get("filename", "")))
with open("/mnt/blackboard/memory_export/agent_solutions.json", "w") as f:
    json.dump([{"id": p["id"], "payload": p["payload"]} for p in points], f, indent=1, sort_keys=True)
print(f"Exported {len(points)} memory entries.")
PY
else
  echo "Qdrant didn't answer; keeping the previous memory export."
fi

# 2. First run: connect to the GitHub repository given on the command line.
if [ -n "$1" ] && ! git remote get-url origin >/dev/null 2>&1; then
  repo="${1#*github.com[/:]}"; repo="${repo%/}"; repo="${repo%.git}"
  git remote add origin "git@github-agent-cluster:${repo}.git"
  echo "Connected to github.com/${repo}"
fi

# 3. Commit whatever changed. Only the folders allowed in .gitignore are included.
git add -A
if git diff --cached --quiet; then
  echo "No changes since the last backup."
else
  git commit -q -m "Backup $(date '+%Y-%m-%d %H:%M')"
  echo "Committed $(git log -1 --format='%h: %s')"
fi

# 4. Push.
if git remote get-url origin >/dev/null 2>&1; then
  git push -q -u origin HEAD:main && echo "Pushed to GitHub."
else
  echo "No GitHub repository connected yet; the backup is committed on Node 2 only."
fi
