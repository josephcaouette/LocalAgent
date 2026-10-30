# Agent Cluster

A three-node home lab where a local LLM plans, writes, tests and verifies small Python
utilities, then remembers what worked.

| Node | Hardware | Role |
|---|---|---|
| Node 1, 192.168.254.24 | i7-14700K, RTX 4090, 32 GB, Windows 11 + WSL2 | vLLM serving Qwen3.8-27B (4-bit, CUDA graphs, speculative decoding); the GUI and the pipeline |
| Node 2, 192.168.254.25 | Dual Xeon E5-2400 v2, 64 GB ECC, 5 TB volume, Ubuntu 24.04 | The file share (`/mnt/blackboard`, mapped as `Z:\` on Node 1), Redis, Qdrant, the dashboard, the test sandbox |
| Node 3, 192.168.254.26 | MSI laptop, RTX 2070 8 GB, Ubuntu 24.04 | Ollama: `qwen3-embedding:0.6b` embeddings, background memory summaries and the chat fallback (`qwen3.5:9b`) |

## What's in this repository

This repository is the share's root folder on Node 2. `.gitignore` allows only these folders:

- `workspace/`: the code.
  - `config.py`: every setting (addresses, models, limits). Start here.
  - `run_langgraph_pipeline.py`: the agent. Goal in, verified script out.
  - `agent_gui.py`: chat with the models, then dispatch and watch runs.
  - `agent_dashboard.py`: web dashboard on port 8080 (runs as a Docker service).
  - `background_ingest.py`, `reindex_memory.py`, `agent_common.py`: long-term memory and shared helpers.
  - Every other `.py` file is a utility the agent built.
- `docker/`: `docker-compose.yml` (Redis, Qdrant, dashboard) and the sandbox image's Dockerfile.
- `launchers/`: the Windows launch scripts from Node 1's Desktop, Node 1's WSL settings
  (`wslconfig.txt`) and `backup_node2.sh`.
- `config/`: a template for optional Redis and Qdrant passwords. The real `agent_secrets.env`
  is never committed.
- `memory_export/`: the long-term memory (summaries and code) as JSON.

Not tracked: Redis and Qdrant data, per-run scratch folders (`runs/`), logs, and the
file backups in `workspace/.history/`.

## How a run works

1. Pick the target file (the GUI's Target box, a file named in the goal, or a new name).
2. In parallel: search memory for similar past solutions, and brief any other file the goal
   mentions (on Node 1 by default; see `HELPER_BACKEND` in `config.py`).
3. The planner writes steps and 2-4 acceptance checks.
4. The engineer writes the whole file into `runs/<run>/a<N>/`, never straight into the workspace.
5. The file runs as `python3 <file> --test` in a fresh container on Node 2: no network unless
   allowed, read-only workspace, 1 GB of memory, 20 seconds.
6. The verifier judges the output against the acceptance checks.
7. Failures loop back, with a diagnosis step for crashes, up to 3 attempts.
8. On a pass, the old file goes to `workspace/.history/`, the new one is promoted, and it is
   stored in memory.

## Backups

Run `Backup_To_GitHub.bat` on Node 1's Desktop. It copies the launchers to Node 2, exports
memory, commits on Node 2 and pushes. Node 2 pushes with its own key
(`~/.ssh/github_agent_cluster`), registered as a deploy key on this repository only.

## Restoring from scratch

1. **Node 2:** clone this repository into `/mnt/blackboard`, share that folder with Samba as
   `blackboard`, then run `docker compose up -d` in `docker/` (this also builds the sandbox image).
2. **Node 3:** install Ollama, then `ollama pull qwen3.5:9b` and `ollama pull qwen3-embedding:0.6b`.
3. **Node 1:** install vLLM 0.32 in WSL at `~/vllm_env`; the first launch downloads
   `RedHatAI/Qwen3.8-27B-INT4`. Create the `C:\AI\venvs\agent_brain` venv with `openai`,
   `langgraph`, `redis`, `qdrant-client` and `requests`. Map `Z:` to `\\192.168.254.25\blackboard`,
   copy `launchers\*.bat` to the Desktop and `launchers\wslconfig.txt` to `%USERPROFILE%\.wslconfig`.
4. **Memory:** `python Z:\workspace\reindex_memory.py --import Z:\memory_export\agent_solutions.json`
