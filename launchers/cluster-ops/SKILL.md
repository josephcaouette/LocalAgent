---
name: cluster-ops
description: >-
  How to operate, change, test, benchmark and back up the user's 3-node home-lab agent cluster (Node 1 Windows/WSL RTX 4090 running vLLM, the LangGraph pipeline and the "Agent Cluster" Tk window; Node 2 Ubuntu with the Z: file share, Redis, Qdrant, SearXNG and the Docker sandbox; Node 3 laptop with Ollama). Use this skill for ANY work touching Z:\workspace, Z:\runs, Z:\launchers, C:\AI\cluster_launcher, run_langgraph_pipeline.py, agent_gui.py, config.py, the accuracy levels (Low/Medium/High/Ultra/MAX), vLLM presets, sandbox containers, pipeline runs, benchmarks, the README, or the GitHub backup, even when the user just says "the cluster", "the agent", "the pipeline", "my runs" or "the window" without naming files.
---

# Operating the agent cluster

The user built a local multi-agent coding pipeline. It turns a goal into a tested Python script by
planning, writing several candidates in parallel, testing them in a Docker sandbox, judging and
reviewing them. This skill holds the layout, the routine procedures and the house rules, so you
don't have to rediscover them. Verify anything that looks stale (a path, a function name) before
relying on it: the code keeps changing.

## Cluster map

| Node | Address | Role |
|---|---|---|
| Node 1 "Brain" | 192.168.254.24 (this PC, Windows 11 + WSL Ubuntu-24.04) | RTX 4090; vLLM (in WSL) at `http://127.0.0.1:8001` (use 127.0.0.1, not localhost); runs the pipeline and the Agent Cluster window |
| Node 2 "Blackboard" | 192.168.254.25, SSH `server@192.168.254.25` (key auth, BatchMode works) | File share `/mnt/blackboard` = `Z:\` on Node 1; Redis; Qdrant :6333 (memory); SearXNG :8888; Docker sandbox (image `agent-sandbox:latest`); the Git repo |
| Node 3 "Worker" | 192.168.254.26 | RTX 2070 laptop; Ollama (chat helper, memory summaries) |

Key paths:
- `Z:\workspace\` — pipeline code (`run_langgraph_pipeline.py`, `agent_gui.py`, `config.py`,
  `research.py`, `agent_dashboard.py`, `background_ingest.py`) and the scripts the agent produced.
  `config.py` holds every address and setting; read it rather than guessing.
- `Z:\runs\<run_id>\` — per-run folders: `pipeline.log`, `a<attempt>c<candidate>\` (code, tests,
  `model_reply.txt` for cut-off or broken replies), `proofs-r<n>\`, `mut-<n>\`. Newest 30 kept.
- `C:\AI\cluster_launcher\cluster_launcher.py` — the combined "Agent Cluster" window (it embeds
  agent_gui's tabs). A copy lives in `Z:\launchers\cluster_launcher\`; keep the two identical
  (`diff -q` them) because only the Z: copy is backed up.
- Python: `/c/AI/venvs/agent_brain/Scripts/python.exe` (has pyflakes, langgraph, openai, redis).
- vLLM log: `\\wsl.localhost\Ubuntu-24.04\home\moltjr\vllm_last.log`. Presets: **Fast** 16k
  context (MTP, ~104 tok/s single) and **Long context** 32k (~54 tok/s single, ~270 tok/s with 6
  requests). The window's queue switches to 32k for Ultra/MAX runs and back afterwards (~40 s each).
- Redis keys: `workflow:task:<run_id>` (hash: status, phase, profile, timings, tokens, verdict,
  spec, mutation_score...), `workflow:langgraph:001` (latest run), `workflow:active` (heartbeats;
  stale after 120 s). In Python: `config.get_redis(decode_responses=True)`,
  `config.active_runs(r)` (needs the client).
- `%TEMP%\agent_gui.pid` belongs to the user's open window; `%TEMP%\agent_pipeline_<run>.pid` to runs.
- This skill lives at `%USERPROFILE%\.claude\skills\cluster-ops\`; `Backup_To_GitHub.bat` copies it
  to `Z:\launchers\cluster-ops\` for the repo. When you change the skill, copy it there too (or run
  the backup) so the GitHub copy stays current.

## Shell notes (Node 1)

- Use Git Bash with `/z/...` and `/c/...` paths; the working directory resets after each command,
  so use absolute paths. `taskkill //F //T //PID n` (doubled slashes in Git Bash).
- Windows Python can't open paths over ~260 characters: the session scratchpad path is too long for
  `python script.py`, so put helper scripts somewhere short (for example this skill's folder).
- `nvidia-smi.exe` works from Git Bash for reading clocks, power and temperatures. Never change
  GPU, power or system settings yourself; the user does that.
- To watch a long run, wait in the background (`until grep -q ... pipeline.log; do sleep 10; done`)
  rather than polling, and filter logs to state changes (see `scripts/tests/milestones.py`).

## The pipeline in one paragraph

Levels (config `RUN_PROFILES`): Low 2 candidates/30 min, Medium 3/12 h, High 4 diverse + independent
tests + 3 judges + critic (16k server), Ultra 4 + spec review + reference tests + candidate comparison
+ proven critics (32k), MAX 5 + adversarial tester + head-to-head + 2 critics x 4 rounds + mutation
testing (32k, 24 h). Graph nodes: retriever, scout, web, planner (+spec review), engineer (+tester,
adversary, prober in parallel), executor, verifier, condenser, retest, critic, mutation, finalize.
CLI: `run_langgraph_pipeline.py --goal-file F --target T --accuracy LEVEL [--no-memory --no-ingest]`.
A running pipeline has its code loaded already; edits only affect runs started afterwards.

## Procedures

### Check on a run
Read `Z:\runs\<run_id>\pipeline.log` (grep for `\[Node|Candidate [0-9]|->|\[i\]|\[!\]|FAIL`) and the
Redis record. `status` is PASSED, FAILED, ERROR, STOPPED or RUNNING (LOST in the GUI when the
heartbeat is stale).

### Stop a run cleanly
`python scripts/stop_run.py <run_id> "reason"` — ends the process tree, removes the PID file, marks
the record STOPPED, removes its containers. Only for runs you started or the user asked to stop.

### Before committing pipeline changes
Run `bash scripts/run_unit_tests.sh` (pyflakes on all infrastructure files, graph build, unit tests;
no model calls, brief sandbox use). Write a unit test with a fake `llm_chat`/`llm_complete` for any
new pipeline behaviour (copy the pattern in `scripts/tests/*_unit.py`). For GUI or queue changes,
an end-to-end run through the window is the real test: `scripts/tests/ultra_max_e2e.py smoke`
(Ultra, MAX and Low on small tasks; about an hour) drives a hidden ClusterWindow.

### Benchmark a level
`scripts/tests/ultra_max_e2e.py bench` (Ultra + MAX on a cron parser) or `bench-max`, run in the
background with output to a log. They pass `--no-memory --no-ingest` so results stay comparable and
don't pollute memory. Check the results with `scripts/tests/cron_check.py <file>` (42 cases against a
brute-force reference) and `CRON_PATHS=<file> python scripts/tests/cron_edge.py` (10 day-of-month /
day-of-week OR-rule cases). The runs promote their output into `Z:\workspace` (cron_bench_*.py):
delete those afterwards so they aren't committed. Record results in the README's accuracy section.

### Commit and push
The repo is `/mnt/blackboard` on Node 2 (remote `josephcaouette/LocalAgent`, push works from there).
1. Copy the window code to `Z:\launchers\cluster_launcher\` if it changed.
2. Write the message to a file ending with the line
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (or whatever attribution the session
   specifies), `scp` it to Node 2's `/tmp/`, then on Node 2:
   `git add -A -- <the files you changed> && git commit -q -F /tmp/msg.txt`. Check `git status`
   first so nothing unexpected (benchmark outputs, a user's file) gets in.
3. `bash /mnt/blackboard/launchers/backup_node2.sh` — exports Qdrant memory to `memory_export/`,
   commits anything else allowed by `.gitignore` as "Backup <date>", and pushes.
Commit only when the user asked for it (a standing "sync GitHub" request counts).

## House rules

- **Desktop stays clean.** No copies of workspace files or .bat launchers on the Desktop; canonical
  copies are `Z:\workspace` and `Z:\launchers` (the user archived old ones into
  "Old Local Agent Stuff").
- **Never handle passwords.** Steps needing sudo or the share password are done by the user in a
  window you open for them. Don't repeat a password even if it appears in the conversation.
- **Secrets stay out of Git:** `config/agent_secrets.env`, `config/searxng.env` (only `*.example`
  files are tracked). The user's email is for identification only, never in commits or requests.
- **Sandbox stays offline by default;** web research reads only allowlisted sites
  (`research_allowlist.txt`), queries are sanitized, and web text is untrusted data.
- Explain changes plainly; the user wants to understand trade-offs (they ask "what do you think?")
  and usually approves with "Yes, all of it" after you lay out a plan and options.

## Reading the pipeline's messages

| Message | Meaning / first thing to check |
|---|---|
| `Shortened '...' to fit the ... context window` | Prompt + thinking + answer didn't fit. Extras are cut first, then thinking shrinks to half its budget before the spec or failure report is cut. Normal on 16k with big files |
| `cut off at N tokens: about X of thinking, Y of answer` | A reply hit its limit. Thinking that runs past its budget spills into the answer; the engineer then finishes such candidates "from their own notes". See `model_reply.txt` in the candidate folder |
| `N of M candidates, written independently ..., failed with exactly the same result` | Independent candidates agreeing against an expectation usually means the expectation (spec example, check, or test) is wrong, not the code |
| `CORRECTION (found while testing ...)` in the spec | The diagnosis fixed a wrong spec example; later steps follow it |
| `exited with code 0 but printed lines reporting failed checks` | An independent test printed FAIL lines; it counts as failed |
| `its container was gone; starting a fresh one` | Pre-started container missing; harmless, costs a few seconds. Frequent occurrences mean a naming clash between steps |
| `A later step failed ..., but a version had already passed; keeping it` | The safety net saved a passing version after an error |

Lessons from the benchmarks (2026-10-31): the shared spec is a single point of failure (one wrong
worked example or invented limit reaches every candidate); hand-computed expected values are the
most common source of false failures; High is usually enough for mid-size tasks, Ultra/MAX add
insurance (Ultra ~2x and MAX ~4x High's tokens).
