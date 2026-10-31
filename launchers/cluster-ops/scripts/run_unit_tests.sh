#!/bin/bash
# Fast pipeline checks: static check, graph build, and the unit tests (no model calls; retest_unit
# and compare_unit use the Node 2 sandbox briefly). Run from Git Bash on Node 1.
PY=/c/AI/venvs/agent_brain/Scripts/python.exe
T="$(cd "$(dirname "$0")/tests" && pwd)"
cd /z/workspace || { echo "Z: is not connected"; exit 1; }
fail=0
echo "== pyflakes"; $PY -m pyflakes run_langgraph_pipeline.py agent_gui.py agent_dashboard.py config.py research.py \
  background_ingest.py agent_common.py reindex_memory.py sync_memory.py cluster_ping.py \
  /c/AI/cluster_launcher/cluster_launcher.py && echo ok || fail=1
echo "== graph"; $PY -c "import run_langgraph_pipeline as p; p.build_graph(); print('ok')" 2>&1 | tail -1
for t in rescue softfail consensus fit finish testfix compare retest; do
  echo "== $t"; timeout 300 $PY "$T/${t}_unit.py" 2>&1 | grep -vE '^\s*$|^\[Node|^    ' | tail -8 || fail=1
done
exit $fail
