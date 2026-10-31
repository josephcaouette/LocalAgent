# Agent Cluster

A three-node home lab where a local LLM plans, writes, tests and verifies small Python
utilities, can research the web for them, and remembers what worked.

| Node | Hardware | Role |
|---|---|---|
| Node 1, 192.168.254.24 | i7-14700K, RTX 4090, 32 GB, Windows 11 + WSL2 | vLLM serving Qwen3.8-27B (4-bit, CUDA graphs, speculative decoding); the GUI and the pipeline |
| Node 2, 192.168.254.25 | Dual Xeon E5-2400 v2, 64 GB ECC, 5 TB volume, Ubuntu 24.04 | The file share (`/mnt/blackboard`, mapped as `Z:\` on Node 1), Redis, Qdrant, SearXNG, the dashboard, the test sandbox |
| Node 3, 192.168.254.26 | MSI laptop, RTX 2070 8 GB, Ubuntu 24.04 | Ollama: `qwen3-embedding:0.6b` embeddings, background memory summaries, chat fallback, and page reading while Node 1 is busy (`qwen3.5:9b`) |

## What's in this repository

This repository is the share's root folder on Node 2. `.gitignore` allows only these folders:

- `workspace/`: the code.
  - `config.py`: every setting (addresses, models, limits, run profiles). Start here.
  - `run_langgraph_pipeline.py`: the agent. Goal in, verified script out.
  - `agent_gui.py`: chat with the models (optionally with web search), then dispatch and watch runs.
  - `research.py` and `research_allowlist.txt`: web research and the sites it may read.
  - `agent_dashboard.py`: web dashboard on port 8080 (runs as a Docker service).
  - `background_ingest.py`, `reindex_memory.py`, `agent_common.py`: long-term memory and shared helpers.
  - Every other `.py` file is a utility the agent built.
- `docker/`: `docker-compose.yml` (Redis, Qdrant, SearXNG, dashboard), the sandbox image's
  Dockerfile and SearXNG's settings.
- `launchers/`: the Windows launch scripts from Node 1's Desktop, Node 1's WSL settings
  (`wslconfig.txt`) and `backup_node2.sh`.
- `config/`: a template for optional Redis and Qdrant passwords. Real secrets (`agent_secrets.env`,
  `searxng.env`) are never committed.
- `memory_export/`: the long-term memory (summaries and code) as JSON.

Not tracked: Redis and Qdrant data, per-run scratch folders (`runs/`), logs, and the
file backups in `workspace/.history/`.

## How a run works

1. Pick the target file (the GUI's Target box, a file named in the goal, or a new name).
2. In parallel: search memory for similar past solutions, brief any other file the goal mentions,
   and, if "Research the web first" is ticked, research allowlisted sites.
3. The planner thinks first, then writes steps and 2-4 acceptance checks.
4. The engineer writes several candidate files at once into `runs/<run>/a<attempt>c<candidate>/`,
   never straight into the workspace. It thinks first when fixing a failure.
5. Each candidate runs as `python3 <file> --test` in its own fresh container on Node 2: no network
   unless allowed, read-only workspace, 1 GB of memory, 20 seconds.
6. The verifier thinks first, judges each candidate that ran cleanly, and the best one wins.
7. If none pass, the run loops back (with a diagnosis step for crashes) until it runs out of
   attempts or time.
8. On a pass, the old file goes to `workspace/.history/`, the winner is promoted, and it is
   stored in memory.

**Run profiles** (`RUN_PROFILES` in `config.py`): *normal* is 3 attempts x 2 candidates with a
30-minute cap. *Overnight* (GUI checkbox or `--overnight`) is 8 attempts x 3 candidates, with the
engineer always thinking, and a 12-hour cap. A run stops as soon as a candidate passes.

## Web research

Used by the GUI's "Search the web" option in chat and by the pipeline's "Research the web first".

1. Node 1 writes 2-3 search queries. IP addresses, local paths and emails are stripped first.
2. SearXNG on Node 2 (port 8888) searches. Results outside `research_allowlist.txt` are dropped.
3. Allowlisted pages are fetched with size and time limits and reduced to their main text.
4. A reader extracts what's relevant from each page, in parallel: Node 1 by default, or Node 3
   while a pipeline run is using Node 1.
5. Node 1 writes a short brief that cites its sources.

Every search, fetch and skipped result is logged to `workspace/logs/research.log`. Web text is
treated as untrusted. Generated code never gets internet access: the test sandbox stays offline.
The allowlist starts from OpenAI Codex's published "Common dependencies" preset plus
documentation and Q&A sites; edit it freely.

The same reader condenses large attachments before planning and summarizes long chats.

## Backups

Run `Backup_To_GitHub.bat` on Node 1's Desktop. It copies the launchers to Node 2, exports
memory, commits on Node 2 and pushes. Node 2 pushes with its own key
(`~/.ssh/github_agent_cluster`), registered as a deploy key on this repository only.

## Restoring from scratch

1. **Node 2:** clone this repository into `/mnt/blackboard`, share that folder with Samba as
   `blackboard`, create `config/searxng.env` containing `SEARXNG_SECRET=<random hex>`, then run
   `docker compose up -d` in `docker/` (this also builds the sandbox image).
2. **Node 3:** install Ollama, then `ollama pull qwen3.5:9b` and `ollama pull qwen3-embedding:0.6b`.
3. **Node 1:** install vLLM 0.32 in WSL at `~/vllm_env`; the first launch downloads
   `RedHatAI/Qwen3.8-27B-INT4`. Create the `C:\AI\venvs\agent_brain` venv with `openai`,
   `langgraph`, `redis`, `qdrant-client`, `requests` and `trafilatura`. Map `Z:` to
   `\\192.168.254.25\blackboard`, copy `launchers\*.bat` to the Desktop and
   `launchers\wslconfig.txt` to `%USERPROFILE%\.wslconfig`.
4. **Memory:** `python Z:\workspace\reindex_memory.py --import Z:\memory_export\agent_solutions.json`
