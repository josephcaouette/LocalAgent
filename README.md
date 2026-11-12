# Agent Cluster

A three-node home lab where a local LLM plans, writes, tests and verifies small Python
utilities, can research the web for them, remembers what worked, and explains its results.

| Node | Hardware | Role |
|---|---|---|
| Node 1, 192.168.254.24 | i7-14700K, RTX 4090, 32 GB, Windows 11 + WSL2 | vLLM serving Qwen3.8-27B (4-bit, CUDA graphs, speculative decoding); the Agent Cluster window and the pipeline |
| Node 2, 192.168.254.25 | Dual Xeon E5-2620 v2, 128 GB ECC, 5 TB RAID volume, Ubuntu 24.04 | The file share (`/mnt/blackboard`, mapped as `Z:\` on Node 1), Redis, Qdrant, SearXNG, the web dashboard, the test sandbox, and the embedding model for memory (`qwen3-embedding:0.6b` in Ollama, on the CPU) |
| Node 3, 192.168.254.26 | MSI laptop, RTX 2070 8 GB, Ubuntu 24.04 | Ollama (`qwen3.5:9b`): background memory summaries, chat fallback, and page reading while Node 1 is busy |

## Contents

1. [Quick start](#quick-start)
2. [What's in this repository](#whats-in-this-repository)
3. [The Agent Cluster window](#the-agent-cluster-window)
4. [Accuracy levels](#accuracy-levels)
5. [How a run works](#how-a-run-works)
6. [Web research](#web-research)
7. [Long-term memory](#long-term-memory)
8. [config.py reference](#configpy-reference)
9. [Where the time and hardware go](#where-the-time-and-hardware-go)
10. [Web dashboard](#web-dashboard)
11. [Backups](#backups)
12. [Restoring from scratch](#restoring-from-scratch)
13. [Troubleshooting](#troubleshooting)

## Quick start

1. Double-click **Agent Cluster** on Node 1's Desktop.
2. On the **Model server** tab, press **Start everything**. vLLM loads (about a minute) and Node 3's
   models warm up.
3. On the **Chat** tab, talk the task through. Press **Make task from chat** to fill in the task.
4. On the **Task & Queue** tab, check it, pick an **accuracy level** (Low to MAX), and press
   **Dispatch Run**.
5. When the run finishes, press **Talk about result**. The model explains what it built, how to
   run it and what to install first.

## What's in this repository

This repository is the share's root folder on Node 2. `.gitignore` allows only these folders:

- `workspace/`: the code.
  - `config.py`: every setting (addresses, models, limits, accuracy levels). See the reference below.
  - `run_langgraph_pipeline.py`: the agent. Goal in, verified script out.
  - `agent_gui.py`: the Chat, Task & Queue and Runs tabs (embedded in the Agent Cluster window; also
    runs on its own as a fallback).
  - `research.py` and `research_allowlist.txt`: web research and the sites it may read.
  - `agent_dashboard.py`: web dashboard on port 8080 (runs as a Docker service on Node 2).
  - `background_ingest.py`, `reindex_memory.py`, `agent_common.py`: long-term memory and shared helpers.
  - `run_digest.py`: the plain-English run summaries Node 1 writes while the queue is idle.
  - Every other `.py` file is a utility the agent built, apart from the first prototypes of
    2026-10-27, kept for reference: `run_crew_pipeline.py` (CrewAI), `run_agent_loop.py`,
    `run_agent_loopOLD.py` and `sync_memory.py`.
- `docker/`: `docker-compose.yml` (Redis, Qdrant, SearXNG, dashboard), the sandbox image's
  Dockerfile and SearXNG's settings.
- `launchers/`: the Agent Cluster window (`cluster_launcher/`), the fallback `.bat` files, Node 1's
  WSL settings (`wslconfig.txt`), `backup_node2.sh`, and `cluster-ops/`: the Claude Code skill for
  this cluster (layout, procedures, house rules, unit tests and benchmark scripts). It's installed
  at `%USERPROFILE%\.claude\skills\cluster-ops\`, and `Backup_To_GitHub.bat` copies it here.
- `config/`: a template for optional Redis and Qdrant passwords. Real secrets (`agent_secrets.env`,
  `searxng.env`) are never committed.
- `memory_export/`: the long-term memory (summaries and code) as JSON.

Not tracked: Redis and Qdrant data, per-run folders (`runs/`), logs, and the file backups in
`workspace/.history/`.

## The Agent Cluster window

One window for everything: `launchers/cluster_launcher/cluster_launcher.py`, installed on Node 1 at
`C:\AI\cluster_launcher` with an **Agent Cluster** shortcut on the Desktop. It lives on `C:` so it
opens even when `Z:` isn't connected. The Chat, Task & Queue and Runs tabs come from
`Z:\workspace\agent_gui.py`: until `Z:` is connected they show a **Connect Z:** button, and they load
by themselves as soon as it is.

```
+-----------------------------------------------------------------------------+
| Node 1 * vLLM ready (16k) * GPU 22.9/24 GB 63°C * Z: | Node 2 * Redis * ... |  <- status strip
| Running 1, 2 queued     Node 2 connected                       [Dispatch Run]|  <- run queue
+-- Chat | Task & Queue | Runs | Model server | Cluster ------------------------+
|                              (selected tab)                                 |
+-- Activity ---------------------------------------------------- [Show more] -+
```

### Status strip

Refreshes every 5 seconds. Green is working, red is down, grey is unknown. The Cluster tab shows
the same items in full (for example which models Node 3 has loaded).

| Node | Item | What it checks |
|---|---|---|
| 1 | vLLM | Whether the model server answers on port 8001, and its context size |
| 1 | GPU | Memory used and temperature. About 22-23 GB used is normal while vLLM runs: it reserves memory up front |
| 1 | Z: | Whether the share from Node 2 is connected. The agent tabs need it |
| 2 | Redis, Qdrant, SearXNG, Dashboard, Share | Run records, long-term memory, the search engine, the web dashboard, the Samba share |
| 3 | Ollama | Node 3's model server and how many models it has loaded |

The second row is the run queue: how many runs are going or waiting, runs started outside this
window, and **Dispatch Run**.

### Chat tab

Talk a task through before running it. Chatting never changes files.

- **Model:** **Automatic** (the default) uses Node 1, except while a pipeline run is going: then
  Node 3 answers, so chatting doesn't slow the run, and a line in the chat says so. Pick **Node 1**
  (the 27B model, best, ~104 tokens/s) to use it anyway, or **Node 3** (the 9B model; it makes more
  mistakes) for when Node 1 is off.
- **Think step by step:** the model reasons privately first. Better for design and debugging;
  slower (it may write 1,000-5,000 hidden tokens first).
- **Search the web:** researches first (see [Web research](#web-research)) and answers with
  numbered sources.
- **Include attachments:** adds the Task tab's attached files to the conversation.
- **Make task from chat:** turns the conversation into a goal, target file and network setting on
  the Task tab, for you to check before dispatching.
- **Explain latest run:** opens a result chat about the newest finished run.
- **New chat**, **Stop**.
- Long chats are summarized automatically when they'd overflow the context window: the newest
  messages stay word for word, older ones become a summary, and a line tells you when.

**Talking about a result.** **Talk about result** (Task & Queue tab), **Talk about this run** or a
double-click (Runs tab), or **Explain latest run** opens a chat that already knows the run: goal,
plan, interface, acceptance checks, the verdict, the test output and the final code.

- **Passed runs:** the model explains what it built, exactly how to run it on this PC, how to use
  it, what the test proved and what it couldn't, and its limitations.
- **Failed runs:** it explains what went wrong, whether the code is usable, and what to change for
  the next run.

The window also checks the code's imports against your Python and lists anything missing, so the
model gives the exact `pip install` command. To ask for changes, describe them and press **Make
task from chat**: the new task edits the same file.

### Task & Queue tab

- **Goal:** what you want built. Be specific about behaviour and how `--test` should prove it.
- **Target file:** the file to create or edit. Blank means the file named in the goal, or a new
  name. Core files like `config.py` are protected.
- **Allow LAN network in sandbox:** for scripts that must reach other machines on your network.
  The internet is never reachable from tests.
- **Accuracy:** Low, Medium, High, Ultra or MAX (see [Accuracy levels](#accuracy-levels)). The line
  next to it summarizes what the chosen level does. Choosing High, Ultra or MAX also ticks web
  research; untick it if the task doesn't need it.
- **Research the web first:** web research before planning. Good for unfamiliar libraries,
  protocols or standards; adds 1-3 minutes.
- **Attachments:** files given to the agent as reference. Large ones are condensed first.
- **Queue:** **Dispatch Run** adds the task to the queue.
  - Up to two Low or Medium runs go at once (`MAX_PARALLEL_RUNS`). A High, Ultra or MAX run waits
    until nothing else is running, then has the GPU to itself. Before an Ultra or MAX run, vLLM
    switches to the 32k server, and back when none are left. The queue keeps its order.
  - Runs started outside this window (a second window, a test battery, the command line) count as
    well: nothing from the queue starts beside them and vLLM isn't switched under them. A window that
    put vLLM on 32k for its own runs switches back as soon as its queue is empty; one that found it
    on 32k waits until Node 1 has had no run at all for two minutes, because a battery may start its
    next run seconds after the last one ends. Run summaries wait for other processes' runs too, since
    they use the GPU. (Before, a window opened during a test battery could switch vLLM back to 16k
    under the battery's Ultra run.)
  - Each run has its own log: select it in the list.
  - **Stop / remove** stops a running task (its record is marked stopped and its test containers
    removed) or takes a waiting one out of the queue.
  - **Talk about result** opens the result chat. **Clear finished** tidies the list.

### Runs tab

Every recorded run, newest first, from Redis (records are kept 30 days). It refreshes every 10
seconds while open.

- **List:** start time, status, target, accuracy level, how long it took, attempts and goal.
  - Statuses: PASSED, FAILED, ERROR (stopped by a problem, such as vLLM being down), RUNNING,
    STOPPED (by you or Reset), and LOST (its process ended without finishing, for example when the
    PC restarted mid-run). Greyed-out PLANNED and COMPLETED records come from the pipeline's first
    version.
- **Details:** a plain-English **Summary** of the run (see below), settings, the current phase,
  **time per step**, **tokens generated** per role, the goal, plan, checks, interface (High), verdict
  and output.
- **Summaries:** whenever nothing is running or queued, Node 1 writes a short summary of each
  finished run that doesn't have one yet: the result, what happened and which safeguards made a
  difference, where the time went, and anything worth checking. They take a few seconds each, run in
  the background (`run_digest.py`, log in `workspace\logs\digest.log`), and stop the moment a run
  starts. The summary reports what each step concluded; a step's conclusion can be wrong.
- **Buttons:** **Talk about this run**, **Open file** (in an editor), **Run it** (runs the file on
  this PC in a console window, after asking; it installs missing packages with pip first),
  **Re-run this goal** (loads the goal, level and settings into the Task tab), **Show full log**
  (the run's `pipeline.log`) and **Open run folder** (every candidate of every attempt).

### Model server tab

Loads any model on Node 1 or Node 3, with its settings, from one place.

**Node 1 (vLLM).** Every vLLM setting as a form. Changes apply the next time you press **Start** or
**Restart vLLM**; **Save settings** remembers them. vLLM runs without a window of its own: its log
shows at the bottom of this tab (the status-check lines are hidden), and it keeps running when you
close the window.

To load another model, type its Hugging Face name (`owner/model`) in **Model** and press **Check
model**. That reads the model's details from Hugging Face without downloading anything and fills in
settings that suit it:

- speculative decoding (MTP) and text-only stay on only for Qwen3.5 and later, which have the parts
  they use;
- the reasoning parser follows the model family: `qwen3`, `deepseek_r1` for R1 distills and QwQ, or
  none;
- the context length is capped at the longest the model supports.

The line under the form says what changed, how big the weights are, whether they're already
downloaded, whether they fit the 4090 (weights above ~19 GB won't), and whether the model is gated.
Change anything you like, then press Start or Restart vLLM. A model that isn't downloaded yet asks
first, with its size. A gated one (Llama, Gemma) needs its license accepted on huggingface.co and a
login in WSL: `~/vllm_env/bin/hf auth login`. GGUF-only repos don't work in vLLM; they can run on
Node 3. Models that started are added to the Model list. The pipeline, chat and research all use
whatever vLLM serves, and the chat's model list renames itself. One exception: Ultra and MAX runs
still switch Node 1 to the **Long context (32k)** preset, which is the Qwen3.8 model, and back
afterwards.

**Node 3 (Ollama).** Below the vLLM buttons:

| Setting | Default | What it does |
|---|---|---|
| Model | qwen3.5:9b | Any Ollama name: `llama3.1:8b`, `hf.co/owner/repo:Q4_K_M`. Must be a chat model |
| Context | 8192 | Tokens per request; more uses more of the 2070's 8 GB |
| GPU layers | auto | How many layers go on the GPU; fewer leave VRAM free, the rest runs on the CPU (slower) |
| Thinking | Off (faster) | For models that can think. Ignored, and never sent, for models that can't |

**Check model** says whether Node 3 has the model, how big it is, whether it fits the GPU, its
longest context and whether it can think. For a model Node 3 doesn't have, it gives the
ollama.com download size. **Load on Node 3** asks before any download, unloads the old model, loads
the new one and reports how much of it sits on the GPU. It then saves the choice in
`Z:\config\node3_model.json`. `config.py` reads that file, so new runs, the chat, the **Warm up
models** button and `Restart_Node3_Worker.bat` all use the new model. Runs already going keep the
old one.

| Setting | Default | What it does |
|---|---|---|
| Preset | Fast | **Fast** for daily use. **Long context (32k)** for very large files or chats: about half speed, because speculative decoding is off so the bigger context fits. **Old model** (Qwen2.5-Coder-32B) as a fallback. Saving records which preset the values match, or "Custom" |
| Model | `RedHatAI/Qwen3.8-27B-INT4` | The Hugging Face model; **Check model** suggests settings for a new one. A new name downloads on first start (after asking). The pipeline uses whatever vLLM serves |
| Context length | 16,384 | Most tokens one request may hold (prompt plus answer). About 12,000 words or 1,500 lines of code. The pipeline measures and trims prompts to fit. Above 16k, vLLM's working memory jumps from 0.6 to 2.8 GiB, so fewer requests fit at once |
| GPU memory | 0.92 | Share of the 4090 vLLM claims. It holds the model (~17 GB), working memory, and the **KV cache**: the model's short-term memory of the text it's working on. See the table below |
| Parallel requests | 8 | Most requests served at once. Candidates, the tester, judges, research and chat share them. KV cache is the real limit, not this |
| KV cache | fp8 | 8-bit short-term memory: twice the room of 16-bit, with no noticeable quality loss |
| Attention backend | TRITON_ATTN | FlashInfer can't build here with fp8, so Triton is used. Leave it |
| Speculative decoding (MTP), draft tokens | on, 2 | The model's built-in predictor guesses 2 tokens ahead; the full model checks them in one step. About 94% of guesses are right, which is most of why output runs at ~104 tokens/s instead of ~35. The output is identical to running without it |
| CUDA graphs | on | Records the GPU's work once and replays it. Roughly tripled speed; costs ~1 GB and ~60 s of start-up. Off adds `--enforce-eager` (troubleshooting only) |
| Prefix caching | off | Reuses work when requests start with the same text. Doesn't combine well with this model's design and speculative decoding. The 32k preset turns it on |
| Text only (skip vision) | on | Skips the model's image encoder, which leaves more memory for KV cache |
| Reasoning parser | qwen3 | Keeps the model's private thinking separate from its answer. Required for thinking |
| Extra arguments | empty | Any other vLLM flags. Shell symbols are rejected |

Measured on this 4090. WSL leaves 22.45 of 23.99 GiB free, so 0.95 can't start:

| GPU memory | KV cache | Full-length requests at once | Spare at start-up |
|---|---|---|---|
| 0.91 | 54,886 tokens | 3.35 | 0.62 GiB |
| **0.92** | **58,982 tokens** | **3.6** | 0.38 GiB |
| 0.93 | 62,259 tokens | 3.8 | 0.14 GiB (fragile) |

The **Long context (32k)** preset (GPU memory 0.92, no speculative decoding) holds **118,935
tokens** of KV cache, 3.6 full 32k requests at once: more than Fast, because there's no draft
model taking memory. It generates about 53 tokens/s for one request (Fast: ~104) and about 230
tokens/s in total with five at once (Fast: ~290), so it's half speed for chat but only about 20%
slower when a High run writes four candidates and a test together.

An A/B on 2026-10-31 tried other settings for this preset under the load of a MAX run: one long
thinking request, then eight long requests at once, then five short reviews (`vllm_ab.py` in the
cluster-ops skill's tests):

| Setting | KV cache | One request | Eight at once | All three |
|---|---|---|---|---|
| 0.90 (until 2026-10-31) | 106,799 tokens | 53 tokens/s | 434 s, 4 preemptions | 552 s |
| **0.92 (now)** | **118,935 tokens** | 53 tokens/s | **394 s, 2 preemptions** | **514 s** |
| 0.92 + 4096-token prefill batches | 63,108 tokens | 53 tokens/s | 865 s, 18 preemptions | 984 s |
| 0.92 + speculative decoding | 71,493 tokens | 72 tokens/s | 1,802 s, 678 preemptions | 1,894 s |
| 0.92 + both | didn't start: too little memory left for one 32k request | | | |

A preemption is vLLM pausing a request because the KV cache is full, then computing it again
later. Speculative decoding makes one request a third faster, but its draft model leaves 40% less
cache, so eight requests at once ran four times slower. Bigger prefill batches
(`--max-num-batched-tokens 4096`) need more working memory, which also comes out of the cache.
During two hours of real Ultra and MAX runs the 32k server paused requests only 15 times, so
0.92's extra cache is headroom more than a fix.

Node 1's monitors run on the Intel graphics, not the 4090, which is why vLLM sees almost all 24 GB.
Keep it that way: a monitor on the 4090 would use some of its memory.

- **Check free VRAM** measures what vLLM will actually see (inside WSL, as vLLM does) and sets the
  slider to the highest value that will start. Use it if something else is using the GPU.
- **Buttons:**
  - **Start everything:** connects `Z:` if needed, starts vLLM if it isn't running, and warms up
    Node 3.
  - **Start / Stop / Restart vLLM.** Stop and Restart warn you first if runs are going, because they
    would fail.
  - **Show command:** the exact command line.
  - **Open log file:** the full log in Notepad.
- If vLLM fails to start, the Activity log shows the reason with a hint.

**Reading vLLM's log.** While it works, vLLM prints a line like this every 10 seconds, followed by
the number of requests waiting and how full the KV cache is:

```
Avg prompt throughput: 628.1 tokens/s, Avg generation throughput: 204.0 tokens/s, Running: 5 reqs
```

- **Generation throughput** is the number to watch: how fast the model writes, summed over the
  requests it's serving. On the 32k server that's about 52 tokens/s for one request and 230-250 for
  five.
- **Prompt throughput reads 0.0 most of the time, and that's normal.** vLLM books a request's whole
  prompt in the one reading where its first reply token comes out, counting only what it had to
  compute (text reused from its cache is left out). Reading a prompt takes a second or two and
  writing the reply takes minutes, so in 6 hours of a test battery 96% of readings showed 0.0 and the
  rest jumped between 40 and 4,134 tokens/s. A spike is the tokens booked in those 10 seconds divided
  by 10, not how fast the GPU reads.
- **Waiting** requests are normal for a moment when several arrive together. A KV cache near 100%
  for long stretches means the load needs more cache than the server has (see the A/B above).

### Cluster tab

| Button | What it does |
|---|---|
| Connect Z: drive | Opens a window running `net use`; you type the share password there |
| Reset pipeline | Stops every run, empties the queue, marks their records stopped and removes leftover test containers on Node 2. The window stays open |
| Restart Node 2 services | Restarts Redis, Qdrant, SearXNG, the dashboard and the embedding model (Docker Compose). Warns first if runs are going |
| Restart Ollama on Node 3 | Opens a window that asks for your own `sudo` password on Node 3 |
| Warm up models | Loads the helper model on Node 3 and the embedding model on Node 2, so the first use isn't slow |
| Back up to GitHub | See [Backups](#backups) |

Next to them: links to the web dashboard, the search page, GitHub, the workspace and runs folders,
logs, the allowlist, `config.py` and the window's settings file. Below them, the full status
details for every node.

**Closing the window** asks first if runs are going (and stops them if you agree). vLLM keeps
running; stop it on the Model server tab.

## Accuracy levels

Chosen per task on the Task & Queue tab (or `--accuracy low|medium|high|ultra|max` on the command
line). Older runs stored "normal" (now Low) and "overnight" (now Medium). Every setting is in
`RUN_PROFILES` in `config.py`, with a comment for each.

| | Low | Medium | High | Ultra | MAX |
|---|---|---|---|---|---|
| Server | 16k | 16k | 16k | **32k (switches automatically)** | **32k (switches automatically)** |
| Attempts x candidates | 3 x 2 | 8 x 3 | 10 x 4 | 12 x 4 | 16 x 5 |
| Different approaches | - | - | yes | yes | yes |
| Thinking per call | up to 5,000 | up to 5,000 | up to 10,000 (about 5,000 for the engineer in 16k) | up to 16,000 | up to 16,000 |
| **Spec review** before coding | - | - | - | yes | yes |
| **Examples checked** by running code before coding | - | - | yes | yes | yes |
| **Independent tests** | - | - | acceptance test | + reference and property checks | + an **adversarial tester** |
| **Candidates compared** on probe inputs | - | - | - | yes, with a referee | yes, with a referee |
| Judges | 1 | 1 | 3 | 3 | 5, plus a **head-to-head** pick |
| **Critics** per round x rounds | - | - | 1 x 2 | 1 x 3, **claims proven by tests** | 2 x 4, claims proven by tests |
| **Mutation testing** | - | - | - | - | yes |
| Test runs | 1 | 3 | 3 | 3, varied settings | 5, varied settings |
| Test time limit | 20 s | 20 s | 20 s | 60 s | 60 s |
| Web research | tick to add | tick to add | ticked by default | ticked by default | ticked by default |
| Time cap | 30 min | 12 h | 12 h | 12 h | 24 h |
| GPU | shared (2 runs at once) | shared | to itself | to itself | to itself |
| Measured, small tasks | ~2 min | ~4 min | ~7 min | ~21 min | ~38 min |

**Automatic 32k switching.** In the Agent Cluster window, the queue restarts vLLM with the **Long
context (32k)** preset before an Ultra or MAX run, keeps it for back-to-back Ultra and MAX runs, and
switches back to your saved settings when none are left (about a minute each way; the status strip
shows "vLLM starting"). Your saved settings never change. If the 32k server won't start, the run uses
the normal one. Runs started from the command line don't switch; they print a note if they're on 16k.

**What Ultra and MAX add.**

- **Spec review:** after the planner, a reviewer writes a precise spec (exact rules, error cases,
  tricky inputs, and the standard conventions the goal relies on) and corrects the plan, checks and
  interface while a misunderstanding is still cheap. Anything it's unsure of is marked ASSUMPTION.
  Everyone downstream sees the spec, but judges against the goal if they disagree.
- **Reference and property tests:** the independent tester also writes a slow, obviously correct
  reference inside its test and compares the script with it on many generated inputs, plus checks
  that must always hold. Hand-calculated expected values were the tester's weak spot.
- **Candidates compared:** every candidate that passes answers the same 20-50 probe inputs (written by
  a prober from the interface). Where they disagree, a referee works out the right answer from the goal,
  and candidates that answered wrong go back with that input as a counterexample.
- **Proven critics:** every problem a critic reports must come with a small test that shows it. The
  test is run against the passing version: if it passes, the claim is dropped; if it fails, a referee
  checks the test's expectation against the goal. Confirmed tests are kept as **regression checks**
  that every later version must pass.
- **Varied test runs:** repeat runs use other time zones (UTC+5:30, US Pacific, UTC+12:45), locales,
  hash seeds and working folders, to catch results that depend on the environment.
- **MAX also:** an **adversarial tester** that tries to break the script (boundaries, extreme sizes,
  invalid input); a **head-to-head** judge that compares the top two candidates side by side, asked
  twice with the order swapped (a pick counts only if both agree); two critics per round (correctness
  and robustness); five judges; and **mutation testing**: it plants up to 12 small bugs in the winner
  (`<` to `<=`, `+` to `-`, a constant off by one, a removed `not`) and checks the tests catch them.
  For bugs that slip through, the tester writes new checks; those that hold on the real code join the
  regression checks, and any that fail on it go to the referee as possible real bugs.

Benchmark flags for the command line: `--no-memory` (no past solutions as examples) and
`--no-ingest` (don't store the result).

**Why the higher levels are more accurate.**

- **Independent tests:** in Low and Medium, one model call writes both the code and the test that
  checks it, so a misunderstanding of the task can end up in both and the test still passes. The
  independent tester works only from the goal, which breaks that link. When its test and the code
  disagree, the diagnosis step decides, against the goal, whether the script or the test is wrong.
  A wrong test goes back to the tester.
- **Diverse candidates:** best-of-4 compares real alternatives instead of near-copies.
- **Panel and critic:** the panel makes a lucky pass from a single judge unlikely, and the critic
  reads the winner for problems no test exercised.

**Why Ultra and MAX use the 32k server.** In 16k, the prompt, the thinking and a long file don't
all fit, so long files get cut off and thinking is squeezed. With the **Long context (32k)** preset
they fit. Measured with High on the same task (a cron schedule parser of 300-500 lines, from scratch,
no memory examples), one run each:

| | Fast preset (16k) | Long context preset (32k) |
|---|---|---|
| Result | passed on attempt 2 | passed on attempt 1 |
| Time | 19.9 min | 13.8 min |
| Candidates cut off | 2 of 8 | 0 of 4 |
| First passing version correct | no (the critic caught a bug, fixed in round 2) | yes |
| Tokens generated | 164,000 | 98,000 |

Both final versions matched a brute-force reference on 52 test cases. High stays on 16k so it remains
the faster choice; to run it on 32k anyway, choose **Long context (32k)** on the Model server tab,
press **Apply preset** and **Restart vLLM**, and switch back to **Fast** afterwards.

**Ultra and MAX on the same task** (32k server, from scratch, no memory examples, one run each,
2026-10-31):

| | High (32k) | Ultra | MAX |
|---|---|---|---|
| Result | passed on attempt 1 | passed on attempt 1 | passed on attempt 2 |
| Time | 13.8 min | 32.8 min | 54.3 min |
| Tokens generated | 98,000 | 207,000 | 409,000 |
| Matched the brute-force reference (52 cases) | yes | yes | yes |
| Caught along the way | - | an independent test whose own reference was wrong | an independent test with a wrong expectation (4 of 5 candidates agreed against it); a year-9999 crash in 4 of 5 candidates; mutation testing 10 of 12 |

On a task this size, High already gets it right, so Ultra and MAX buy insurance rather than a
different answer: more independent checks that each catch a different kind of mistake. They pay
off when the goal has rules that are easy to get subtly wrong. A first MAX run on this task exposed
weak spots in the pipeline itself, all fixed before the run above: the spec reviewer's worked
example was wrong (every candidate was right and "failed" against it), fix prompts lost the spec
to the thinking budget, a spec assumption (a 1,461-day search limit) broke leap-day schedules,
candidates whose thinking spilled into their answer were dropped, and a tester printed FAIL lines
but exited 0.

**Beyond the cron task: a five-task battery** (2026-10-31, from scratch, no memory examples, one
run each). Five goals with rules that are easy to get subtly wrong: shell-style wildcard matching,
bowling scores with validation, an integer expression evaluator, a dependency order with cycle
reporting, and free meeting slots. Each ran on Low, Medium and High, plus three on Ultra and MAX:
18 runs, unattended, through the queue. Afterwards each result was checked in the sandbox against
a reference implementation on 600-3,000 generated cases.

| | Low | Medium | High | Ultra | MAX |
|---|---|---|---|---|---|
| Passed | 4 of 5 | 5 of 5 | 5 of 5 | 2 of 2 | 1 of 1 |
| Final file matched the reference on every case | 5 of 5 | 5 of 5 | 5 of 5 | 2 of 2 | 1 of 1 |
| Time per run | 1.5-7 min | 2.5-6.5 min | 9-27 min | 27-32 min | 62 min |

Every file the pipeline produced was correct, including the Low run marked failed: its code was
right, and its own self-test's expected value was wrong (it said `a*b*c` doesn't match `abcc`),
which the quick diagnosis then blamed on the code. The two slowest runs (wildcards on High and the
evaluator on MAX, 4 attempts each) also lost their time to wrong tests, not wrong code: each fix
of an independent test brought a new wrong value. That led to in-place test fixes, a short thinking
diagnosis on Low and Medium, and a check that rejects a plan returned instead of code. More thinking
for the test writers didn't help: the MAX run repeated with `--helper-think 8000` still had two
wrong expected values in its adversarial test (`10-4/2/3` as 9 instead of 10, `1- - -2` as 3
instead of -1) and took the same 4 attempts in about the same hour, with 35% more tokens.

**A second battery** (same day, same setup): semantic version ranges, text justification, Game of
Life with other birth/survival rules, a CSV parser and a cache with expiry, each checked against a
reference on 307-1,537 generated cases (`scripts/tests/battery2_checks.py` of the cluster-ops skill).

| | Low | Medium | High | Ultra | MAX |
|---|---|---|---|---|---|
| Passed | 3 of 5 | 4 of 5 | 4 of 5 | 2 of 2 | 1 of 1 |
| Final file matched the reference on every case | 4 of 5 | 4 of 5 | 5 of 5 | 2 of 2 | 1 of 1 |
| Time per run | 3-6 min | 4-10 min | 11-57 min | 37-62 min | 30 min |

Again every file produced was correct. The misses were two runs that stopped without a file and
two that rejected correct code, and each showed a weak spot in the pipeline, now fixed:

- **Version ranges on Low and Medium stopped without a file.** On Low, fixing a long file didn't fit
  the 16k window; the engineer now sends SEARCH/REPLACE edits to the previous version instead. On
  Medium, the step that finishes a cut-off candidate from its notes asked for more room than was
  left (the file plus half again); it now settles for the file's own size, and if even that can't
  fit, only that candidate is left cut off.
- **Game of Life on Low rejected correct code:** each rewrite brought new wrong grids into its own
  test. When the diagnosis blames only the expected values, one candidate now corrects just those.
- **The CSV parser on High spent all 10 attempts on correct code.** The goal says "a line break at
  the very end doesn't start another record", which can be read two ways: the independent test took
  a lone `\n` as no record, while every candidate returned one empty record, as Python's `csv`
  module (and the reference) does. The diagnosis blamed the script nine times, and the candidates
  never changed. Now, when the same checks still fail after a diagnosis blamed the script, the
  diagnosis is told so and asked for a decision that sticks: blame the test if the goal allows the
  candidates' reading, or put a correction into the interface the engineer must implement exactly.
  Replayed on Node 1, the old diagnosis blamed the script 3 times of 3, as in the run. With the
  note, all 4 tries broke the cycle: once it blamed the test (calling the goal ambiguous and the
  candidates' reading defensible), and three times it wrote the test's reading into the interface.
  Candidates written from that interface dropped the old failures but overcorrected a neighbouring
  case, so a run would go on with new failures instead of repeating the old ones. The battery's goal
  now spells out the `\n` case.
- **The CSV parser on Ultra took 6 attempts** for another reason: its independent test compared
  random inputs with the test writer's own CSV parser, which had a new bug after each fix. The
  diagnosis rightly blamed the test every time. Telling the test writer to use a standard-library
  module as its reference instead (Python's `csv`, which the script was banned from but a test isn't)
  didn't help, so it isn't in the pipeline: in a side-by-side of 9 acceptance tests on the same plan,
  none used `csv`, and only 1 of 3 tests with the old instructions and 1 of 6 with two new wordings
  passed a correct parser. The rest tripped over empty lines (`['']` where the goal says `[]`).
  With the goal's `\n` case spelled out, a repeat run on Ultra passed on attempt 3 in 36 minutes
  and 210,000 tokens (against 6 attempts, 62 minutes and 390,000 before), and matched the reference
  on all 815 cases.

**A third battery: Ultra against MAX** (2026-11-01, same setup). Sets 1 and 2 never told the two
apart, so this one used three tasks with rules that are hard to get exactly right: a strict JSON parser
(NaN and Infinity rejected, surrogate pairs, repeated keys), IPv6 address normalization to a canonical
form, and a matcher for a subset of regular expressions that must consider every way to match and
never loop on patterns like `(a*)*`. Each ran on Ultra and then MAX, and was checked against
standard-library references on 947-1,919 generated cases with a one-second limit per call
(`scripts/tests/battery3_checks.py`).

| | JSON | IPv6 | Regex |
|---|---|---|---|
| Ultra | 1,242/1,242 in 2 attempts, 45 min, 299,000 tokens | 947/947 in 3, 46 min, 279,000 | 1,918/1,919 in 4, 59 min, 354,000 |
| MAX | 1,242/1,242 in 7 attempts, 109 min, 891,000 tokens | 947/947 in 1, 52 min, 372,000 | 1,919/1,919 in 4, 82 min, 606,000 |

- **No real difference in quality.** All six passed. The one case between them came from the regex
  goal's wording: a backslash before "a letter or digit" is an error, and the reference counts `é` as
  a letter (as Python's `str.isalnum()` does) where Ultra's matcher read "letter" as ASCII. The goal
  now says which.
- **MAX cost 1.1-2.4x the time and 1.3-3x the tokens.** Its extra steps all ran: adversarial tests,
  one head-to-head pick, and mutation testing that caught 11 of 12 planted bugs on every MAX run. The
  critics found nothing real on either level.
- **MAX's JSON run lost five attempts to its own adversarial test.** The test ended with
  `sys.exit(1 if fails else 0)`, where `fails` held one `False` per passing check, so it failed every
  candidate while printing only PASS lines. Two diagnoses in a row invented a failure and blamed the
  script, and the engineer broke working emoji output to satisfy them. Such a test now goes back to
  its writer without asking the model (see [How a run works](#how-a-run-works)); on all 32 saved run
  logs, that rule would have fired exactly at this run's three broken-test attempts and nowhere else.
- **Ultra's slower runs lost their time to wrong tests**, as before: IPv6 and regex each needed two
  re-tests, and the regex test's own reference matcher was wrong twice (it matched `b+` against an
  empty string).
- **None of the six runs got a summary**, because of a change to the window's queue made during the
  battery: the battery's window waited two minutes before switching vLLM back, and closed first. The
  window that put vLLM on 32k now switches back at once.

**A fourth battery: bigger files, every level** (2026-11-02, same setup, 15 runs in 20 hours). To
push Ultra and MAX apart, three tasks whose scripts run 800-900 lines, each checked against an exact
reference on 1,037-1,315 cases, every call in its own process with time and memory limits
(`scripts/tests/battery4_checks.py`): an evaluator for Python's integer expressions with Python's
exact rules (precedence, chained comparisons, short-circuiting, 100,000-digit numbers, a size limit
that must not compute `9**9**9`), a TOML 1.0 reader (against `tomllib`) and a `struct` clone (pack,
unpack and calcsize, with half precision rounded by hand). Cases matched by the file each run kept,
with the best of all its candidates in brackets where better (`score_candidates.py`):

| | Low | Medium | High | Ultra | MAX |
|---|---|---|---|---|---|
| Expressions (1,234) | failed: 887 | failed: 180 (944) | failed: 0 | failed: 757 (972) | failed: **1,213** |
| TOML (1,037) | failed: 271 (718) | failed: 697 | failed: 732 | passed: 920 | passed: **975** (1,005) |
| struct (1,315) | failed: 658 | failed: 712 (1,140) | failed: 1,164 (1,197) | passed: **1,314** | passed: 1,298 (1,309) |
| Time per run | 8-12 min | 19-45 min | 62-73 min | 96-194 min | 126-264 min |
| Output tokens | 52,000-85,000 | 186,000-272,000 | 409,000-443,000 | 643,000-1.3 million | 885,000-2.0 million |

- **Only the 32k levels passed anything.** On the 16k server a file this size, its failure report and
  room to think don't fit together. The expression evaluator on High wrote 750 lines on its first
  attempt and left `evaluate` and `_main` as placeholders that raise `NotImplementedError`. Every
  later attempt had to send edits, and with 1,500 tokens kept for the answer, 28 of 36 edit replies
  were cut off before one complete edit: the evaluator never got written (0 cases). struct on High
  came closest: its code matched 1,197 cases, but its self-test held wrong hand-worked bytes (the
  byte order of half-precision floats), and each diagnosis corrected one more until the 10 attempts
  ran out.
- **Ultra and MAX differ for the first time.** Neither passed the expression evaluator, but MAX's
  file matches 1,213 of 1,234 cases, against Ultra's 757 (972 for its best candidate of 44). MAX's
  best came on its last attempt, while Ultra's came on attempt 4 and later fixes made things worse.
  The misses the checker shows point to one rule: MAX accepts `not` right after a comparison
  (`1 == not 2`), which Python rejects. On TOML, MAX's file matches 975 cases against Ultra's 920:
  its adversarial test failed the candidates on three attempts (the diagnosis blamed code and test
  once, then the test twice), and mutation testing caught 11 of 12 planted bugs. On struct
  it's a draw (1,314 against 1,298). MAX cost 1.1-1.8 times the output tokens and 1.1-1.5 times the
  time.
- **A failed run kept worse code than it had.** It saved its last attempt's code: TOML on Low kept a
  version the static check had rejected (271) over its first attempt's (718), and the expression
  evaluator on Medium kept 180 over 944. A failed run now keeps the candidate that got furthest (see
  step 11 of [How a run works](#how-a-run-works)). Replayed on the 11 failed runs' logs, that keeps
  8,913 of the 9,158 points their best candidates reach, against 7,271 before; no run loses more
  than 11.
- **MAX's evaluator ran out of attempts on a broken test.** Its acceptance test's random generator
  had two bugs. On attempt 15 it recursed with no base case and crashed; the diagnosis caught that
  and a real script bug (`0x__1` accepted) together. Fixing the recursion exposed the second bug on
  attempt 16, the last: the generator wrote expressions Python itself rejects (`4 - not 4`) and
  failed four candidates that had passed their own tests.
- **Every run got its summary.** The battery's window switched vLLM back 75 seconds after the last
  run, and Node 1 wrote all 15 summaries while the battery waited.
- **Fixed since, each with a unit test (`bigfile_unit.py`):** a failed run keeps the candidate that
  got furthest; a forgotten standard-library import is added rather than the candidate rejected
  (TOML on Low lost both candidates of an attempt to `re.` calls without `import re`); placeholder
  functions are rejected by name; and edits keep 4,000 tokens for their answer when the model thinks
  first.
- **Fixed since: tests meet two stand-ins, and a wrong test gets a last chance** (`standin_unit.py`,
  `lastchance_unit.py`; see steps 4 and 7 of [How a run works](#how-a-run-works)). On MAX's two saved
  acceptance tests the stand-in check found both generator bugs, and a third that no run had seen:
  printing the failure of its big-number check took `repr()` of a 100,000-digit integer, past
  Python's 4,300-digit limit (no candidate failed that check, so the crash never showed). On the 6
  saved tests that winning candidates passed, it found nothing.
- **Starting fixes from the furthest candidate made no measurable difference.** The three High runs
  were repeated with `--fix-base furthest` and the fixes above. The expression evaluator rose from 0
  to 622 (843 for its best candidate), TOML fell from 732 to 543, and struct from 1,164 to 853 (858).
  The fix went back to an earlier version only three times, all in the struct run, so run-to-run
  variation explains both directions; `latest` stays the default.
- **Most fixes on the 16k server never reached a test.** Of the re-run's 120 candidate slots, 32 were
  fix replies with an edit that matched nowhere and 38 came back without any edit; 33 candidates were
  tested. Replaying one fix request live (`edits_live.py`) showed both kinds. With the 680-line file
  filling most of the window, the model had about 1,300 tokens to think, kept reasoning in the answer
  and ran out of room before its first edit. Or it replaced a whole 100-line function and its copy of
  the function differed from the file in two comment lines. And an attempt where nothing applied
  passed on only "your edits couldn't be applied", so the next one didn't know what it was fixing.
  All three are fixed (`editmatch_unit.py`, with the two saved replies): on the replayed request 3 of
  4 replies now apply, against 0 of 4 before. Failed replies are now kept in `model_reply.txt`; they
  used to be saved empty.

**The fourth battery again** (2026-11-03, same setup, 15 runs in 24 hours), with the stand-in check,
the last chance and the edit fixes above. Each cell is the first battery's kept file, then this one's,
with this one's best candidate in brackets where better:

| | Low | Medium | High | Ultra | MAX |
|---|---|---|---|---|---|
| Expressions (1,234) | 887 → 544 (634) | 180 → 727 | 0 → 250 (937) | 757 → 706 (1,009) | 1,213 → 6 (602) |
| TOML (1,037) | 271 → 765 | 697 → 805 | 732 → 910 (974) | passed: 920 → passed: **990** (992) | passed: 975 → 673 (975) |
| struct (1,315) | 658 → 638 (764) | 712 → 1,040 (1,056) | 1,164 → 1,274 | passed: **1,314** → 1,302 | passed: 1,298 → 1,232 (1,252) |

- **The 16k levels gained most.** Low, Medium and High kept 6,953 points against 5,301, and High's
  best candidates reached 3,185 against 1,929. High tested 80 candidates against 43, and across the
  three levels 38 fix replies that ran out of room while thinking were finished from their notes.
  Nothing passed on 16k.
- **Ultra and MAX did worse: one pass against four.** One run per cell can't tell the changes from
  luck, and the first battery's Ultra and MAX logs had been pruned by then. The logs show three
  things. The expression evaluator on MAX hit a dead end: for its last 10 attempts, the candidates
  (each a fix of the same version) failed their own tests with the same `ValueError` on valid
  expressions, often all five alike. It began right after the diagnosis wrote implementation details
  into the interface for every later step ("the parser must terminate on the explicit end-of-input
  token, use unique AST operator codes..."); a dead end now gets a fresh start (step 7 of
  [How a run works](#how-a-run-works)). TOML on MAX never had a candidate pass its own self-test in
  16 attempts, while the file grew from 1,000 to 1,600 lines. struct on Ultra and MAX had their
  self-tests' hand-worked half-precision bytes blamed 4 and 5 times; their code matched 1,302 and
  1,232 of 1,315 cases.
- **Failed runs kept worse files than they had:** 11,862 points kept of the 14,068 their best
  candidates reach. The furthest-candidate rank trusts a passing self-test, and the evaluator on MAX
  kept a candidate whose own test passed while it rejected `1 + 2 * 3` (6 points; its best had 602).
  Fixed (step 11 of [How a run works](#how-a-run-works), `finalpick_unit.py`): a failed run now
  judges its candidates by its final independent tests, but overrules the furthest one only at a
  large gap. Replayed on the 8 failed High, Ultra and MAX runs (`finalpick_sim.py`), that keeps 7,937
  of the 8,325 points their best candidates reach, against 6,353; any threshold from 60% to 80% gives
  the same, and on the three High runs of the fix-base re-run it changes nothing. Always taking the
  top share would keep only 7,410: struct on Ultra's test held wrong bytes and favoured a candidate
  that shared them (753 against 1,302).
- **The stand-in check found 2 real test bugs and raised 2 false alarms.** On High, the expression
  evaluator's test crashed printing a 100,000-digit number (the 4,300-digit limit again), and
  struct's crashed in its reference call to `struct.calcsize`. Neither repair worked: one came back
  without edits, the other used `struct.error` without `import struct` (a forgotten standard-library
  import is now added to tests as it is to candidates, and a failed repair's reply is saved). On MAX,
  51 and 76 checks that expect an exception were reported because they were worded "expected error,
  got no error" and "got no exception". Neither stand-in raises, so such checks are now left out
  however they're worded (`standin_unit.py` keeps all four tests). The writers rightly changed
  nothing, and those runs rarely got past their own self-tests anyway.
- **The last chance never fired:** no run ended with only an independent test failing.

**The fourth battery's Ultra and MAX runs, a third time** (2026-11-04 and 05, 6 runs in 21 hours),
with the fresh start, the final pick and the stand-in fixes above. Each cell is the first battery's
kept file, then the second's, then this one's, with this one's best candidate in brackets where better:

| | Ultra | MAX |
|---|---|---|
| Expressions (1,234) | 757 → 706 → 152 (946) | **1,213** → 6 → 1,167 (1,173) |
| TOML (1,037) | passed: 920 → passed: **990** → passed: 974 (986) | passed: 975 → 673 → 970 |
| struct (1,315) | passed: **1,314** → 1,302 → passed: 1,208 | passed: 1,298 → 1,232 → 1,311 |
| Time per run | 129-201 min | 207-271 min |
| Output tokens | 0.84-1.35 million | 1.63-2.14 million |

- **Two passes, against one and four; 5,782 points kept of 7,172, against 4,909 and 6,477.** MAX kept
  more on the expression evaluator (1,167 against 152) and struct (1,311 against 1,208) but passed
  nothing. One run per cell still can't separate the changes from luck.
- **The fresh start helped where a line was stuck, and misfired where a weak self-test set the bar.**
  The evaluator on MAX started over twice, and each fresh line jumped: attempt 7 reached 1,151 cases
  (the best before was 781), and attempt 12 reached 1,173, the run's best. In the second battery the
  same run spent its last 10 attempts on one broken parser and kept 6. On Ultra, a candidate whose
  self-test passed while it matched 1 case set the line's best on attempt 3, so attempts 4-6 (853-871
  cases, failing their own tests) counted as getting less far; the fresh line peaked at 842.
- **A re-test set off a restart (fixed).** struct on Ultra re-tested two candidates on attempts 9-11
  against an acceptance test being corrected; the lower ranks set off a restart, and the third re-test
  passed with those same candidates just before it could happen. A re-test now counts as neither
  progress nor a stall (`restart_unit.py`).
- **struct on MAX failed holding a file that passes every final check (fixed).** The candidate it kept
  (attempt 15) matches 1,311 of 1,315 cases and passes every check of both final tests. On attempt 15 the diagnosis rightly
  blamed the adversarial test, but the run had spent its 3 re-tests on the acceptance test (attempts 8,
  10 and 11), so the engineer rewrote the candidates instead, and all five rewrites failed their own
  tests. Re-tests are now counted per independent test (`lastchance_unit.py`, `silent_unit.py`).
- **TOML on MAX never started over, which was probably right.** Every self-test stopped at its first
  failure without a PASS line ("unexpected end of input" in most candidates of 15 of 16 attempts), so
  every attempt ranked the same, and a tie counts as progress. But its code matched 941-970 cases from
  attempt 2 on, and fresh candidates (attempt 1: 766) would likely have lost ground.
- **The final pick overruled once, and a test that stops early misled it.** On the evaluator on Ultra
  it replaced the furthest candidate (its self-test passed; 1 case) with one matching 152, while the
  run's best (attempt 1, 946 cases) came out lower by share: the final acceptance test stopped after 85
  checks for the 152-case candidate, which passed 68 (80%), and ran 395 for the 946-case one, which
  passed 77 (19%). Counting passes against the most checks any candidate reached would have kept a
  candidate matching 813 here, but it fails the other way in the second battery's struct run on Ultra,
  where the test stopped early for the right candidates (49 of 63 passed, against 315 of 341 for one
  matching 753 cases): it would have kept 753 instead of 1,302. Over both batteries' 11 failed runs the
  two come within 1% (10,642 points against the share's 10,530, of the 11,716 their best candidates
  reach; `finalpick_metric.py`), each losing one run badly, so the share and the 70% rule stay. In the
  other three failed runs the furthest candidate stayed, within a point of the best share: 1,167, 970
  and 1,311 cases kept, against bests of 1,173, 970 and 1,311.
- **The stand-in check found 4 real test bugs; its false alarms are fixed.** Real: the 4,300-digit
  limit in both of the evaluator on MAX's tests, and two crashes in struct on MAX's acceptance test
  (its own `raises()` helper, and a reference call that raised `struct.error`). False, all in struct
  on MAX: checks that expect an exception, worded "128 should raise ValueError, got None" or written as
  `isinstance(exc(...), ValueError)` and printed as "expected None, got None", and an
  `isinstance(x, tuple)` check. Findings now leave out "should raise" and a bare None, True or False
  after "got" (`standin_unit.py` keeps both tests: the old rule finds 19 and 1 in them, the new one
  none).
- **The last chance never fired**, as in the second battery.

**A fifth battery: three new tasks for the same changes** (2026-11-05 and 06, 6 runs in 21 hours).
Every fix above was found on the fourth battery's tasks, so this one tries them on tasks they were never
tuned on, Ultra and MAX only, each checked against an exact reference
(`scripts/tests/battery5_checks.py`): Python's `format()` for integers, floats and strings with every
rule of the format-spec language (fill and alignment, signs, `z`, `#`, zero padding with grouping,
half-even rounding of the exact value, the `g` and no-type rules; 1,346 cases), `datetime.strptime`
(directives as a regex table with backtracking, ISO weeks, `%z`; 1,226 cases) and zlib's `decompress`
written without zlib (zlib, gzip and raw streams with every header and Huffman-table rule; 900 cases,
74 of them hand-built streams that each break one rule). The correct solutions that validate the
checker were written from the goals alone, so the goals state every rule the cases rely on. Cases
matched by the file each run kept, with the best candidate in brackets where better:

| | Ultra | MAX |
|---|---|---|
| Format specs (1,346) | 1,014 (1,202) | 1,163 (1,194) |
| strptime (1,226) | passed: **1,226** | passed: 1,222 |
| Decompression (900) | 574 (673) | 768 (892) |
| Time per run | 166-199 min | 157-265 min |
| Output tokens | 1.08-1.31 million | 1.22-2.05 million |

- **Two passes, both strptime; 5,967 points kept of 6,944.** MAX kept more in both failures (1,163
  against 1,014, and 768 against 574). The four failed runs kept 3,519 of the 3,961 points their best
  candidates reach.
- **The format-spec runs never got a candidate past its own self-test, because the fix to the test was
  lost every time (fixed).** On Ultra, every candidate from the first attempt on printed
  `fmt(1e-05, '.88')` right, with all 65 significant digits of the double, while its self-test expected
  `'1e-05'`; on MAX the self-tests expected 42 centred in 10 with three spaces on the left instead of
  four. The diagnosis saw it: it blamed both the code and the self-test and gave the right value, 7
  times on Ultra and 12 on MAX, often the same correction again. But after a "both" verdict every
  candidate rewrote the whole 1,000-line file and copied the wrong values along; only a verdict that
  blamed the expected values alone had them corrected in place. "Both" corrections came 28 times in this
  battery and 15 times in the fourth battery's third run, and the runs with the most of them all
  failed. Now a "both" verdict on the self-test first corrects the values it names, with edits to the
  previous version, and every candidate fixes the code from there (`edits_unit.py`).
- **A self-test with wrong values also misleads every step that ranks candidates.** The decompressor
  on MAX found its best candidate on attempt 3 (892 of 900 cases), but its self-test expected wrong
  hand-built byte strings (an empty gzip stream, an empty stored block), the fixes on attempt 4 fell to
  656, and the run started over after it, giving that line up; the fresh lines peaked at 768. On Ultra
  the fresh start helped: 580 cases before it, 673 after. The format-spec run on Ultra had its best
  candidate on attempt 1 (1,202 cases), but the fixes started from the first-attempt candidate that
  printed the most (84 near-identical failure lines) and stayed near 1,014.
- **The final pick never overruled, once by a hair.** In the format-spec run on Ultra the kept
  candidate passed 62% of the final acceptance test's checks and attempt 1's first candidate 88%: 70.5%
  of the top share, just above the 70% line, and that candidate matches 1,202 cases against the kept
  1,014. Replayed on every candidate (`finalpick_sim.py`), an 80% line would have switched here and in
  the decompressor on Ultra (50% against 65%: 673 cases against 574), keeping 3,806 of the 3,961 points
  the failed runs' best candidates reach, against 3,519; in the fourth battery's second and third runs
  every line from 60% to 80% keeps the same files, while always taking the top share lost 527 points in
  the second. Counting passes against the most checks any candidate reached would also have kept the
  decompressor's 892-case candidate on MAX: that count and the share have now each lost one run badly
  where the other didn't, the share twice, the count once. **The line is now 80%** (`FINAL_PICK_RATIO`,
  2026-11-07): of the 19 failed runs replayed from the fourth and fifth batteries, it changes only those
  two picks (+287 points). It can't go much higher: in the second battery's struct run on Ultra the
  kept file was correct (1,302 cases) and passed 82.5% of the top share, which went to a candidate
  matching 753.
- **Re-tests counted per test worked.** strptime re-tested once on each level, against a wrong
  acceptance test on Ultra and a wrong adversarial test on MAX, and both runs passed afterwards.
- **The stand-in check caught a broken test.** The decompressor's acceptance test on Ultra crashed in
  its own code (an option passed wrongly to zlib); the crash was gone after the third repair. A
  `KeyError` in a helper of the adversarial test on MAX came out the same for both stand-ins and its
  repair changed nothing, but that test never failed a candidate.
- **The last chance fired for the first time** (the decompressor on MAX, after attempt 16): the
  candidates passed their own tests and only the acceptance test failed, so one more diagnosis ran.
  It blamed the script, rightly: the kept file fails 95 of the 300 valid streams.

**On every level.**

- **Static check (pyflakes):** rejects a candidate that uses a name it never defines, a crash
  waiting on a line the test may never reach. A forgotten standard-library import is added instead
  (when the code uses `re.split` and every other `re.` name it uses exists in `re`), since it is
  never a design choice. Functions that only raise `NotImplementedError` are rejected as
  placeholders, named in the message (methods are left alone: an abstract method is normal).
  Independent tests get the same import fix.
- **Repeat runs (Medium and above):** catch tests that only pass sometimes (randomness, timing, or
  leftover files).
- **Failure lines first:** when a test fails, the lines that report failures are always shown, wherever
  they appear in its output.
- **FAIL lines count:** an independent test that prints a line starting with `FAIL` has failed, even
  if it exits with code 0 (testers sometimes forget the exit code).
- **No failure, said plainly:** when a test exits with an error but every check it printed passed,
  the failure report says so, rather than leaving the diagnosis to guess from a page of PASS lines.

## How a run works

1. **Pick the target file** (the Target box, a file named in the goal, or a new name).
2. **Gather, in parallel:**
   - **Memory:** search for similar solved tasks. Anything scoring 0.63 or more is shown to the
     planner as an example, with the pitfalls proven when it was built. A match just below that
     (within 0.05) is shown only if Node 3 judges it relevant to the goal.
   - **Scout:** brief any other workspace file the goal mentions.
   - **Web research**, if ticked.
3. **Planner** (thinks first): writes steps and 2-4 concrete **acceptance checks** (up to 6 on Ultra
   and MAX). On High and above it also writes the **interface**: the functions and command-line
   usage tests will call. On Ultra and MAX the **spec reviewer** then writes a precise spec and
   corrects the plan.
   - **Example check (High and above):** Node 1 writes a short brute-force script, without
     thinking, that recomputes every hand-worked expected value in the spec and checks, and runs it
     in the sandbox (about 15-60 s; a crashed script gets one repair). Node 1 then re-derives any
     value the script disputes, thinking first, and corrects the plan before any candidate copies
     it. If anything goes wrong (a script that still fails), the step is skipped.
     `EXAMPLE_CHECK_BACKEND = "node3"` hands the script to Node 3 instead, which frees Node 1 but
     fails on harder checks (see [Where the time and hardware go](#where-the-time-and-hardware-go)).
4. **Engineer:** writes **several candidate files at once** into `Z:\runs\<run>\a<attempt>c<candidate>\`,
   never straight into the workspace. Each includes its own self-test under `--test`.
   - It thinks first when fixing a failure (always, on Medium and above).
   - Candidates that use undefined names are rejected straight away, and so are replies that aren't
     a script: no `--test` mode, or only bare values (a plan in JSON compiles as Python too).
   - At the same time: the tester writes `acceptance_test.py` (High and above), the adversary writes
     `adversarial_test.py` (MAX), and the prober writes `probe_cases.py` (Ultra and MAX).
   - **Stand-in check:** each new or revised independent test first runs against two stand-ins for
     the script that implement nothing and answer differently: one is truthy and equal to
     everything, the other falsy and equal to nothing. A failure the test reports the same way
     against both (a FAIL line with the same value, or the same crash in its own code) can't come
     from the script's answer, so it goes back to the writer, up to twice, before any candidate is
     blamed. Left out, because they come out the same against both stand-ins whether the test is
     right or wrong: checks that expect an exception, however they word it ("expected ValueError",
     "got no error", "did not raise", "should raise"); checks that end in a bare None, True or False,
     a verdict the test worked out itself (`isinstance(x, tuple)`); and checks that run the script as
     a program.
   - Meanwhile, Node 2 starts one test container per candidate.
5. **Testing:** each candidate runs in its own container on Node 2:
   - its own `python3 <file> --test`, then each independent test and the kept regression checks, then
     repeat runs (Medium and above; in varied settings on Ultra and MAX);
   - on Ultra and MAX, the candidates that passed answer the probe cases, and a referee settles any
     disagreement;
   - no network unless allowed; the workspace is read-only, with a writable scratch folder;
   - 1 GB of memory, 2 CPUs, 20 seconds per run (60 on Ultra and MAX);
   - it runs as the share's user, not root.

   Each container is used for one candidate and then removed.
6. **Verifier** (thinks first): scores every candidate that passed from 0-10 against the checks. The
   best one wins; on a tie, the shorter code (on MAX, a head-to-head judge picks between the top two).
   On High and above the winner needs a majority of the panel (3 votes, or 5 on MAX).
7. **If none pass:** the **diagnosis** step works out what failed (including whether the code, its
   own test, or an independent test is wrong) and the engineer tries again. Lines that report
   failures are always shown to it, wherever they appear in the output. If only an independent
   test was wrong, its writer fixes it and the **same candidates are tested again** without being
   rewritten (up to 3 times for each independent test, so one test's string of fixes can't use up
   another's). That holds after the last attempt too: when the attempts run out with time left and
   the candidates failed only an independent test, the failure still gets one diagnosis, and if it
   blames the test alone, the test is fixed and the same code tested once more.
   - The writer fixes a wrong test **in place**: small search-and-replace edits to just the
     disputed checks, so the checks that already passed can't change. (Rewriting the whole test
     re-rolled every hand-computed value: in the battery below, a MAX run fixed its adversarial test
     three times because each rewrite brought a new wrong value.) If the edits don't apply, the
     test is written again as before.
   - The engineer's self-test gets the same treatment: when the diagnosis blames only its expected
     values, candidate 1 corrects them with edits to the previous version and the other candidates
     rewrite the file, in case the diagnosis is wrong.
   - When a fix's whole file can't fit in the context window (a long file on the 16k server: the
     prompt carries the previous version and the answer would need it all again), every candidate
     sends edits instead. Before, the run stopped there with an error. When it thinks first, the
     thinking gets only what is left after 4,000 tokens for the edits themselves: with 1,500 kept,
     a High run in the fourth battery thought through most of an 8,300-token room, and 28 of 36 edit
     replies were cut off before one complete edit. A reply that still runs out of room while
     thinking is finished from its own notes, without thinking again. A SEARCH part that matches
     nowhere exactly is used where it can only mean one place: the same lines once indentation and
     spacing are ignored (the replacement is re-indented to fit), or, for 3 lines or more, the one
     place between matching first and last lines where at most 1 line in 10 differs. Models retype a
     little when they copy a long passage: a fix that replaced a whole 100-line function failed
     because its copy wrote `i.e.,` for `i.e.` in a comment. When no candidate of an attempt can be
     tested, the next attempt is still told the failure it was fixing.
   - On Low and Medium, when checks fail without a crash, the diagnosis thinks briefly (up to
     3,000 tokens) before deciding whether the code or the self-test's expected value is wrong.
   - On High and above the diagnosis thinks first, sees the spec, and is told when several
     candidates failed in exactly the same way. Candidates written independently rarely share a
     bug, but they all copy an expected value from the plan or spec, so identical failures point at
     the expected value. When independently written candidates agree and the diagnosis finds the
     spec's example wrong, a **correction is added to the spec** for every later step.
   - **A disagreement that won't move gets settled.** If an independent test's checks still fail the
     same way after the diagnosis blamed the script, the candidates evidently read the goal
     differently from the test, and saying it again won't change them. The diagnosis is told this
     and must decide for good: blame the test when the goal allows the candidates' reading, or add
     a **correction to the interface**, which the engineer implements exactly and the test writers
     read too. (In the second battery a CSV run went round this loop nine times.)
   - **A dead end gets a fresh start.** When three attempts in a row get less far than the best of
     their line of fixes (by the same measure as the furthest candidate in step 11), the next attempt
     writes fresh candidates from the goal and spec, thinking first (on High and above each with a
     different approach), told how the set-aside version failed, instead of fixing it again. That
     happens at most twice per run, and the count starts over so the fresh line has time to climb.
     Fixes inherit their version's design: in the fourth battery's second run, the expression
     evaluator on MAX spent its last 10 attempts fixing one parser that rejected every valid
     expression. Replayed on that battery's logs (`restart_sim.py`), the rule fires in 4 stuck runs
     and never in the run that passed; earlier candidates stay on disk for the final pick. A re-test
     doesn't count either way: its code is unchanged, and only the test moved.
   - **A test that fails with nothing failing goes back to its writer.** When an independent test
     exits with an error for every candidate alike while printing only PASS lines (no FAIL line, no
     traceback, no timeout), its own bookkeeping is wrong: it goes back to its writer and the same
     candidates are tested again, without asking the model. Asked who was wrong with no failure in
     view, the diagnosis invented one: in the third battery a MAX run's adversarial test ended with
     `sys.exit(1 if fails else 0)`, where `fails` held one `False` per passing check, and two
     diagnoses in a row blamed the script for a failure that didn't exist.
   - A candidate whose answer was cut off after thinking is finished from its own notes, asking for
     at least the room its file needs. If even that doesn't fit, it stays cut off and the other
     candidates carry on; before, this could stop the run.
8. **Critics (High and above):** review the passing version; real problems send it back with new
   checks. On Ultra and MAX each claim must be proven by a test first, and proven tests become
   regression checks. A pass is never lost: if the fixes don't pass in time, or a later step stops on
   an error (vLLM timing out, Node 2 unreachable), the run finishes with the version that passed and
   its verdict says why.
9. **Mutation testing (MAX):** small planted bugs check that the tests catch them; missed ones get new
   checks, or go back to the engineer if a new check shows a real bug.
10. **On a pass:**
    - the old file goes to `workspace\.history\` (20 kept per file);
    - the winner is copied in;
    - Node 3 summarizes it into long-term memory in the background, with the pitfalls the run
      proved by machine (corrected expected values, and checks added by critics and mutation
      testing).
11. **On a failure:** the workspace file isn't touched. The run keeps the candidate that got
    furthest as `final_<target>` (its own test passed, then the most independent tests passed, then
    the largest share of its own checks), which is what **Talk about result** explains. Before, it
    kept the last attempt's code, which can be far worse: in the fourth battery, the TOML run on Low
    kept a version the static check had rejected (271 of 1,037 reference cases) over its first
    attempt's (718). On High and above, it then runs the final version of each independent test on
    every different candidate (about a minute for 25) and keeps the one that passes the largest share
    of their checks instead, if the furthest passes under 80% of that share. A weak self-test can pass
    on a broken candidate, and shares of a candidate's own checks compare self-tests that change every
    attempt; but independent tests can be wrong too, so a small lead doesn't count.

### What a run leaves behind

- `Z:\runs\<run>\`:
  - `pipeline.log` (everything the run printed);
  - `final_<target>` (the winning code, or in a failed run the candidate that got furthest);
  - every candidate under `a<attempt>c<candidate>\`, with its independent tests, regression checks and
    probe cases;
  - on Ultra and MAX, `proofs-r<round>\` (the critics' proof tests) and, on MAX, `mut-<n>\` (the
    planted bugs).

  The newest 30 run folders are kept.
- **Redis record** `workflow:task:<run>`: status, phase, level (`profile`), goal, plan, checks,
  interface, spec, verdict, output, time per step (`timings`), tokens per role (`tokens`), elapsed
  time, regression checks kept, the mutation score, and the result file's path.
- **While running:** a heartbeat in `workflow:active` every 30 s, and a PID file
  `%TEMP%\agent_pipeline_<run>.pid`. Several runs can go at once without interfering.

Exit codes from the command line: 0 passed, 1 failed, 2 stopped by an error.

```
python run_langgraph_pipeline.py (--goal="..." | --goal-file=FILE) [--target=name.py] [--attach=path ...]
                                 [--allow-network] [--research] [--accuracy=low|medium|high|ultra|max]
                                 [--no-memory] [--no-ingest] [--helper-think=TOKENS]
                                 [--fix-base=latest|furthest]
```

`--goal-file` reads the goal from a UTF-8 text file, which is safer than quoting a long goal on the
command line (the test batteries use it). `--overnight` still works as the old name for
`--accuracy=medium`.

`--helper-think` sets how much the test writers (tester, adversary, prober) may think, for
experiments; normally they use the level's budget. Raising it to 8,000 on MAX didn't reduce the
wrong expected values in tests (see the five-task battery above).

`--fix-base furthest` (experimental; `latest` is the default) starts each fix from the candidate that
got furthest in the whole run, rather than from the best of the attempt that just failed, and tells
the engineer what the worse attempt tried. It returns to the same version at most twice. In the
fourth battery, the expression evaluator on Ultra peaked on attempt 4 (972 of 1,234 reference cases),
and its later fixes, each built on the attempt before, ended at 757. Repeating the battery's three
High runs with it settled nothing: it went back only three times, in a run where most fixes failed to
apply for other reasons (since fixed). Ultra, where the slide happened, is the place to try it next.

## Web research

Used by the Chat tab's "Search the web" and the Task tab's "Research the web first".

1. Node 1 writes 2-3 search queries. IP addresses, local paths and emails are stripped first.
2. SearXNG on Node 2 (port 8888) searches several engines, with no account behind it. Results
   outside `research_allowlist.txt` are dropped.
3. Up to 5 allowlisted pages are fetched (15 s and 2 MB limits each) and reduced to their main
   text. Stack Overflow and the other Stack Exchange sites block scripted page fetches, so their
   questions and top answers are read through the public Stack Exchange API instead.
4. A reader pulls out what's relevant from each page, in parallel: Node 1, or Node 3 while Node 1 is
   busy with runs. Pages with nothing relevant are dropped.
5. Node 1 writes a short brief with `[1]`, `[2]` citations.

**The allowlist** (`workspace/research_allowlist.txt`, 153 sites) starts from OpenAI Codex's
published "Common dependencies" preset. It adds documentation, reference and Q&A sites for
Python, Linux, networking, databases, other languages and AI. Edit it freely: one domain per line,
and subdomains are included.

Web text is treated as untrusted reference material, never as instructions, and generated code
never gets internet access. Every search, fetch and skipped result is logged to
`workspace/logs/research.log`. The same reader condenses large attachments and summarizes long
chats.

## Long-term memory

Each passed run is summarized by Node 3, embedded with `qwen3-embedding:0.6b` on Node 2 and stored
in Qdrant with its goal, checks and code (taken from the run's own `final_<target>`). Similar future
goals get it as an example.

The embedding model runs in Ollama on Node 2's CPU: the `embed` service in
`docker/docker-compose.yml`, container `blackboard-embed`. It moved there from Node 3 on
2026-11-07, which leaves the laptop to its chat model. Node 3's Ollama program and model file
were copied, without the GPU libraries, into `/home/server/ollama_cpu`. That folder is outside the
share, so the backup never commits them. The model files are mounted read-only, so nothing on the
network can pull other models into it. A call takes about 1 s instead of 0.1 s, and a run makes
two. The vectors match the stored ones (cosine 0.9997 or more, `embed_compare.py`), so the store
needed no reindex, and the retrieval test picks the same matches (`embed_eval.py`: right matches
0.705 and up, best wrong match 0.555).

- `reindex_memory.py --list`: what's stored.
- `reindex_memory.py --drop NAME`: remove entries.
- `reindex_memory.py`: rebuild everything with the current embedding model (needed after changing
  `EMBED_MODEL`).
- `reindex_memory.py --import FILE`: restore from a `memory_export/` file.
- Logs go to `workspace/logs/ingest.log`.

## config.py reference

Change behaviour everywhere (pipeline, agent tabs, dashboard, memory tools) by editing
`workspace/config.py`. The window and the pipeline read it when they start.

**Accuracy levels** (`RUN_PROFILES`, one entry per level; see [Accuracy levels](#accuracy-levels))

| Key | Meaning |
|---|---|
| `max_attempts`, `candidates`, `time_limit_s` | Attempts, candidates per attempt and the time cap |
| `think_engineer` | "retries" (think only when fixing), "always" or "never" |
| `think_tokens` | Most hidden thinking per call (always capped so the answer still fits) |
| `diverse` | On the first attempt, each candidate is told to take a different approach |
| `tester` | Write an independent acceptance test (and plan an interface for it) |
| `judges` | Verifier votes the winner needs a majority of |
| `critic_rounds` | Review-and-fix rounds after a pass |
| `repeat_tests` | Runs of a passing test |
| `exclusive` | The run has the GPU to itself in the queue |
| `research_default` | The Task tab ticks web research when this level is chosen |
| `server` | "long": the window switches vLLM to the 32k preset (`LONG_CONTEXT_PRESET`) for the run |
| `spec_review` | A reviewer writes a precise spec and corrects the plan before coding |
| `reference_tests` | The tester also compares with a simple reference and checks properties |
| `differential` | Passing candidates answer the same probe inputs; a referee settles disagreements |
| `critics` | Critics per round (two have different focuses) |
| `critic_proof` | Critic claims must be proven by tests; proven tests become regression checks |
| `adversary` | A second independent tester tries to break the script |
| `head_to_head` | A judge compares the top two candidates side by side |
| `mutation` | Plant small bugs to check the tests catch them, and strengthen the tests |
| `vary_env` | Repeat runs use other time zones, locales, hash seeds and folders |
| `test_timeout`, `max_checks` | Seconds per test run; acceptance checks the planner may write |
| `example_check` | Recompute the plan's hand-worked expected values with a script before coding |
| `helper_think_tokens` | Thinking for the test writers (unset: the level's `think_tokens`) |

Keys a level leaves out come from `LEVEL_DEFAULTS`.
`DEFAULT_ACCURACY` (low) is used when none is given; `MAX_PARALLEL_RUNS` (2) is how many shared
runs the queue starts at once.

**Model behaviour**

| Setting | Value | Meaning |
|---|---|---|
| `LLM_BASE_URL` | http://127.0.0.1:8001 | Where vLLM answers. `127.0.0.1`, not `localhost`: Windows tries IPv6 first, and each new connection to WSL then waits about 2 s |
| `LLM_MODEL` | RedHatAI/Qwen3.8-27B-INT4 | The model the pipeline expects. If vLLM serves another one, it uses that |
| `LLM_FALLBACK_CONTEXT` | 8192 | Context size assumed only if vLLM doesn't report its own |
| `LLM_ENABLE_THINKING` | False | Whether calls think by default. Off is several times faster; the settings below and each level's `think_engineer` turn thinking on where it pays |
| `ENGINEER_MAX_OUTPUT` | 12000 | Longest file the engineer may write, in tokens. A file is also kept to half the context window: 8,192 tokens (about 600-800 lines) with the 16k server, the full 12,000 with the 32k preset |
| `LLM_TEMPERATURE`, `LLM_TOP_P`, `LLM_TOP_K` | 0.7, 0.8, 20 | How adventurous word choice is (the model maker's values). Lower is more predictable. Thinking calls use 0.6 / 0.95. The randomness is what makes candidates differ |
| `THINK_PLANNER`, `THINK_VERIFIER` | True | Let those steps think first |
| `THINK_TOKENS` | 5000 | Default thinking budget (Low and Medium use it; High and above set their own) |
| `LLM_TIMEOUT` | 1200 | Seconds before one request is abandoned (generous because runs share the GPU) |

**Helpers and Node 3**

| Setting | Value | Meaning |
|---|---|---|
| `HELPER_BACKEND` | "node1" | Who writes the scout's brief and failure diagnoses. Node 1 is faster and better; "node3" frees Node 1 at some cost to quality. (Deciding whether a script or an independent test is wrong always uses Node 1) |
| `EXAMPLE_CHECK_BACKEND` | "node1" | Who writes the example-check script. Node 1's scripts worked 6 of 6 times; Node 3's often crashed or were cut off on checks as hard as the task |
| `READER_BACKEND` | "auto" | Who reads research pages, condenses attachments and summarizes chats. "auto" uses Node 1, or Node 3 while Node 1 is busy with runs |
| `WORKER_MODEL`, `WORKER_THINK` | qwen3.5:9b, False | Node 3's model, thinking off for speed (None for models without a thinking mode). Set from the Model server tab, which saves them in `Z:\config\node3_model.json`; these are the defaults without that file |
| `OLLAMA_NUM_CTX`, `OLLAMA_NUM_GPU` | 8192, None | Node 3's context and GPU layers (None: Ollama decides), from the same file. `ollama_options()` sends them with every request, because a different value makes Ollama reload the model (~10 s) |
| `OLLAMA_KEEP_ALIVE` | -1 | Keep Node 3's models loaded permanently |

**Memory**

| Setting | Value | Meaning |
|---|---|---|
| `EMBED_URL` | http://192.168.254.25:11434 | Where text is turned into vectors: Ollama on Node 2's CPU since 2026-11-07. Point it at Node 3 (`http://192.168.254.26:11434`) to go back; the stored vectors work with either |
| `EMBED_MODEL` | qwen3-embedding:0.6b | Turns text into vectors to find similar tasks. Changing it needs `reindex_memory.py`, and the new model in Node 2's `ollama_cpu/models`. The 4B model ranked the same 10 test goals just as well (10 of 10) with a wider gap between right and wrong matches, but it's 4x larger and would be several times slower on Node 2's CPU, so 0.6B stays |
| `MEMORY_MIN_SCORE` | 0.63 | How similar a past solution must be to be shown. In tests right matches scored 0.71+ and the best wrong one 0.57. Raise it if irrelevant examples appear, lower it if good ones are missed (the retriever logs scores) |
| `MEMORY_RELEVANCE_CHECK`, `MEMORY_RELEVANCE_MARGIN` | True, 0.05 | A match up to 0.05 below the minimum is shown only if Node 3 judges it relevant (it recovered a right match at 0.629) |
| `MEMORY_TOP_K` | 3 | Most past examples shown |

**Research**

| Setting | Value | Meaning |
|---|---|---|
| `RESEARCH_MAX_PAGES` | 5 | Pages read per question: more is broader but slower |
| `RESEARCH_FETCH_TIMEOUT`, `RESEARCH_MAX_PAGE_BYTES`, `RESEARCH_MAX_PAGE_CHARS` | 15 s, 2 MB, 60,000 | Download limits |
| `ATTACHMENT_COMPRESS_CHARS` | 24,000 | Attachments larger than this in total are condensed |

**Sandbox**

| Setting | Value | Meaning |
|---|---|---|
| `SANDBOX_IMAGE`, `SANDBOX_PYTHON` | agent-sandbox:latest, 3.11 | The test image (built from `docker/sandbox/Dockerfile`) and its Python version, which the prompts and the result chat name |
| `SANDBOX_TIMEOUT`, `SANDBOX_MEMORY`, `SANDBOX_CPUS`, `SANDBOX_PIDS` | 20 s, 1g, 2, 128 | Limits per test run (the process limit stops runaway spawning) |
| `SANDBOX_PACKAGES` | requests, redis, psutil, yaml | Libraries available in tests. To add one, add it to `docker/sandbox/Dockerfile` **and** this list, then rebuild the image (`docker compose build` on Node 2) |
| `SANDBOX_PREWARM` | True | Start test containers while the engineer writes (see below) |
| `KEEP_RUNS` | 30 | Run folders kept in `Z:\runs` |

**Records and safety**

| Setting | Value | Meaning |
|---|---|---|
| `TASK_TTL_SECONDS` | 30 days | Run records in Redis expire after this |
| `DASHBOARD_MAX_TASKS` | 50 | Runs shown on the web dashboard |
| `KEEP_HISTORY_PER_FILE` | 20 | Old versions kept per file in `.history` |
| `PROTECTED_FILES` | the core files | Files the agent may never overwrite |
| `ACTIVE_STALE_S` | 120 s | A run whose heartbeat is older than this counts as gone (LOST) |

**Pipeline switches** (in `run_langgraph_pipeline.py`, next to the steps they change, for
experiments; each run reads them when it starts)

| Setting | Value | Meaning |
|---|---|---|
| `STANDIN_CHECK` | True | Run each new or revised independent test against two stand-ins before blaming a candidate (step 4 of [How a run works](#how-a-run-works)) |
| `MAX_RETESTS` | 3 | Re-tests of unchanged code after a blamed test, per independent test (step 7) |
| `RESTART_AFTER`, `MAX_RESTARTS` | 3, 2 | Attempts in a row that get less far than their line's best before a fresh start, and fresh starts per run (step 7) |
| `LOW_DIAGNOSIS_THINK` | 3000 | Thinking for Low and Medium's diagnosis of a check that failed without a crash (step 7) |
| `FINAL_PICK`, `FINAL_PICK_RATIO` | True, 0.8 | A failed High+ run judges its candidates by its final independent tests, and overrules the furthest one when that passes under 80% of the best share (step 11). It was 70% until set 5 |
| `FIX_BASE` | "latest" | What a fix starts from; set by `--fix-base` |

Optional Redis and Qdrant passwords go in `Z:\config\agent_secrets.env` (template in `config/`).
That folder is outside the workspace, so tests can't read it, and it's never committed.

## Where the time and hardware go

Measured on 2026-10-30:

- **The 4090 does almost all the work.** A typical run spends nearly all of its time in Node 1
  writing and checking.
  - Speed: ~104 tokens/s output for one request and ~2,870 tokens/s reading prompts. With several
    requests at once (candidates, judges), total output reaches ~250-330 tokens/s.
  - CPU and RAM: Node 1's are mostly idle, which is normal.
  - Node 2's 128 GB and 24 threads are mostly idle too: its services use about 0.6 GB (Qdrant 0.4 GB,
    on 2026-11-05). Its 2013-era CPUs and DDR3 would run a model at only 1-2 tokens/s, so it stores,
    searches and tests instead.
- **Two runs at once.** vLLM serves several requests together. One run fills the GPU only while it
  writes candidates; during planning and checking, most of its capacity sits unused, and a second
  run fills that gap. In the first test, three queued runs (two at once, the third waiting) finished
  in 5.6 minutes from start to finish, while their individual times add up to 8 minutes.
- **High runs alone.** A High run already keeps the GPU busy (4 candidates plus the tester, then
  the panel), so a second run beside it would mostly slow both down.
- **Node 3 (RTX 2070, Qwen3.5 9B at ~49 tokens/s without thinking)** takes the jobs that must not
  slow Node 1 down: memory summaries (embeddings run on Node 2's CPU since 2026-11-07), the
  relevance check on near-miss memory matches, reading web pages during runs, and chat while a
  run is going (Automatic). It was also
  tried for the example check, measured on 2026-10-31: its scripts were reliable when the check is
  simpler than the task (bowling scores: 3 of 3) and often failed when the check is as hard as the
  task (a cron parser: about 1 in 5; an expression parser: 0 of 3). Its thinking mode didn't help
  (8,000 tokens and no script), and qwen2.5-coder 7B found nothing to check. Node 1 wrote working
  scripts 6 of 6 times in 15-30 s, so the example check moved to Node 1. Node 1 also writes the run
  summaries, when it's idle.
  It was also tried for Ultra and MAX's **probe cases** (2026-10-31, `probe_trial.py` in the
  cluster-ops skill's tests): each probe file ran on the correct candidates of three battery runs and
  on 35-40 small deliberate bugs in their final files. Node 1's files caught 114 of 115 bugs with no
  false disputes. Of 9 Node 3 files, 2 didn't compile, 3 caught nothing (each wrapped a wrong call to
  the script in its own `try`, so every version gave the same answer), 3 caught most bugs but made
  correct versions disagree 4-7 times (each a referee call on Node 1), and 1 matched Node 1. The
  prober is one call per run, so it stays on Node 1.
- **Ready-made test containers.** Starting a container on Node 2's HDD array takes ~7 s; running a
  command in an already-started one takes ~0.1 s.
  - The pipeline starts each attempt's containers while the engineer is still writing, so a test
    run takes ~0.45 s plus the script's own run time.
  - Each container is still used for one candidate and removed, and an unused one removes itself
    after an hour.
- **Where each run's time went** is recorded per step. For a High run on a small task (7.2 min):
  planning 82 s, writing 204 s (4 candidates and the independent test at once), testing 5 s,
  checking 22 s, review 118 s. For the cron benchmark on the 32k preset (13.8 min): planning 204 s,
  writing 318 s, testing 14 s, checking 101 s, review 189 s.

## Web dashboard

`http://192.168.254.25:8080`, served from Node 2, so it works from a phone, another PC, or when
Node 1 is off. It shows the newest 50 runs with goal, status, accuracy level, how long they took,
time per step, plan, checks, verdict and output, and refreshes every 10 seconds. The Runs tab
shows the same records with more detail and actions.

## Backups

Use **Back up to GitHub** on the Cluster tab (or `Backup_To_GitHub.bat`). It copies the window's code
and settings and the `.bat` files to Node 2, exports memory, commits on Node 2 and pushes. Node 2
pushes with its own key (`~/.ssh/github_agent_cluster`), registered as a deploy key on this
repository only.

GitHub gets the code, settings, the Docker setup and the memory export. Not the Redis or Qdrant
databases, run folders, logs or secrets.

## Restoring from scratch

1. **Node 2:**
   - clone this repository into `/mnt/blackboard` and share that folder with Samba as `blackboard`;
   - create `config/searxng.env` containing `SEARXNG_SECRET=<random hex>`;
   - put a CPU-only Ollama and `qwen3-embedding:0.6b` in `/home/server/ollama_cpu` for the `embed`
     service: `bin/ollama`, `lib/ollama/` without its `cuda_*` and `vulkan` folders, and `models/`
     (copied from another Ollama install, or fetched with
     `OLLAMA_MODELS=/home/server/ollama_cpu/models ollama pull qwen3-embedding:0.6b`);
   - run `docker compose up -d` in `docker/` (this also builds the sandbox image).
2. **Node 3:** install Ollama, then `ollama pull qwen3.5:9b`.
3. **Node 1:**
   - Install vLLM 0.32 in WSL at `~/vllm_env`. The first launch downloads `RedHatAI/Qwen3.8-27B-INT4`.
   - Create the `C:\AI\venvs\agent_brain` venv with `openai`, `langgraph`, `redis`, `qdrant-client`,
     `requests`, `trafilatura` and `pyflakes`.
   - Map `Z:` to `\\192.168.254.25\blackboard`.
   - Copy `launchers\cluster_launcher\` to `C:\AI\cluster_launcher` and make an "Agent Cluster"
     shortcut with target
     `C:\AI\venvs\agent_brain\Scripts\pythonw.exe C:\AI\cluster_launcher\cluster_launcher.py`.
   - Optionally copy `launchers\*.bat` to the Desktop as fallbacks.
   - Copy `launchers\wslconfig.txt` to `%USERPROFILE%\.wslconfig`.
   - Copy `launchers\cluster-ops\` to `%USERPROFILE%\.claude\skills\cluster-ops\` so Claude Code
     knows the cluster.
4. **Memory:** `python Z:\workspace\reindex_memory.py --import Z:\memory_export\agent_solutions.json`

## Troubleshooting

| Symptom | Fix |
|---|---|
| The Chat, Task & Queue and Runs tabs show "Connect Z:" | `Z:` isn't connected. Press Connect Z: and type the share password; the tabs load by themselves |
| vLLM won't start: "free memory ... less than desired" | Something else is using the GPU. Close it, or press Check free VRAM and start again |
| Chat says vLLM isn't reachable | vLLM is stopped or still loading (see the Model server tab's log). Start it, or pick Node 3 in the chat |
| vLLM is down after the PC slept | Sleep can end vLLM without a trace: no vLLM process in WSL, and its log stops with no shutdown line. Press Start everything, or Start vLLM on the Model server tab. A run that was going can't finish; re-run it. For long unattended runs and test batteries, set Windows not to sleep while plugged in (Settings, System, Power) |
| vLLM's log shows "Avg prompt throughput: 0.0 tokens/s" most of the time | Normal: vLLM counts a prompt only in the 10-second reading where its reply starts. See "Reading vLLM's log" on the [Model server tab](#model-server-tab) |
| A run shows LOST | Its process ended without finishing (killed, PC restarted). Re-run this goal |
| A run seems stuck | Its log on the Task & Queue tab shows what it's waiting for. Stop / remove it, or press Reset pipeline on the Cluster tab |
| A High, Ultra or MAX run waits in the queue | It starts once the runs ahead of it finish, because it needs the GPU to itself (Ultra and MAX then wait about a minute for vLLM to switch to 32k) |
| Chat is slow during an Ultra or MAX run | vLLM is on the 32k server then (about half speed for one request); it switches back when those runs finish |
| A script needs a package to run on this PC | Talk about result names it with the pip command, and Run it installs it for you |
| A run log says "Shortened '...' to fit the ... context window" | The prompt plus room for thinking and the answer didn't fit. Extras (attachments, web notes, past examples) are cut first; then the thinking shrinks, down to half its budget, before the spec or the failure report is cut. Common on High (16k) with big files; Ultra and MAX use the 32k server for this reason |
| A run log says "cut off at N tokens: about X of thinking, Y of answer" | A reply reached its token limit; the line shows where the room went. When thinking runs past its budget, the model tends to keep reasoning in its answer, which then gets cut off. Every thinking step then answers again from its own notes without thinking ("answering again from its notes"; for candidates, "finishing them from their own notes"). A candidate that still came back cut off or broken keeps the model's reply as `model_reply.txt` in its folder under `Z:\runs\<run>\`; a reply with no `--test` mode (a plan or notes instead of the script) is rejected straight away |
| Research finds nothing useful | The allowlist may not cover the topic. Add the relevant documentation site to `research_allowlist.txt` |
| Node 3 is slow on its first answer | Its models were unloaded. Cluster tab, Warm up models |
| A run log says "Memory search skipped" with port 11434 | The embedding service on Node 2 is down (the Embeddings light is red). Cluster tab, Restart Node 2 services, or `docker compose up -d embed` in `docker/` on Node 2 |
| The window itself won't respond | Run `Reset_Cluster.bat` (one of the fallback `.bat` files; copies are in `launchers/`): it stops the window and every run, then reopens the window |
