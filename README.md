# Agent Cluster

A three-node home lab where a local LLM plans, writes, tests and verifies small Python
utilities, can research the web for them, remembers what worked, and explains its results.

| Node | Hardware | Role |
|---|---|---|
| Node 1, 192.168.254.24 | i7-14700K, RTX 4090, 32 GB, Windows 11 + WSL2 | vLLM serving Qwen3.8-27B (4-bit, CUDA graphs, speculative decoding); the Agent Cluster window and the pipeline |
| Node 2, 192.168.254.25 | Dual Xeon E5-2620 v2, 64 GB ECC, 5 TB RAID volume, Ubuntu 24.04 | The file share (`/mnt/blackboard`, mapped as `Z:\` on Node 1), Redis, Qdrant, SearXNG, the web dashboard, the test sandbox |
| Node 3, 192.168.254.26 | MSI laptop, RTX 2070 8 GB, Ubuntu 24.04 | Ollama: `qwen3-embedding:0.6b` embeddings, background memory summaries, chat fallback, and page reading while Node 1 is busy (`qwen3.5:9b`) |

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
  - Every other `.py` file is a utility the agent built.
- `docker/`: `docker-compose.yml` (Redis, Qdrant, SearXNG, dashboard), the sandbox image's
  Dockerfile and SearXNG's settings.
- `launchers/`: the Agent Cluster window (`cluster_launcher/`), the fallback `.bat` files, Node 1's
  WSL settings (`wslconfig.txt`) and `backup_node2.sh`.
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

- **Model:** Node 1 (the 27B model, best, ~104 tokens/s) or Node 3 (the 9B model, for when Node 1 is
  off; it makes more mistakes).
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
- **Details:** settings, the current phase, **time per step**, **tokens generated** per role, the
  goal, plan, checks, interface (High), verdict and output.
- **Buttons:** **Talk about this run**, **Open file** (in an editor), **Run it** (runs the file on
  this PC in a console window, after asking; it installs missing packages with pip first),
  **Re-run this goal** (loads the goal, level and settings into the Task tab), **Show full log**
  (the run's `pipeline.log`) and **Open run folder** (every candidate of every attempt).

### Model server tab

Every vLLM setting as a form. Changes apply the next time you press **Start** or **Restart vLLM**;
**Save settings** remembers them. vLLM runs without a window of its own: its log shows at the bottom
of this tab (the status-check lines are hidden), and it keeps running when you close the window.

| Setting | Default | What it does |
|---|---|---|
| Preset | Fast | **Fast** for daily use. **Long context (32k)** for very large files or chats: about half speed, because speculative decoding is off so the bigger context fits. **Old model** (Qwen2.5-Coder-32B) as a fallback. Saving records which preset the values match, or "Custom" |
| Model | `RedHatAI/Qwen3.8-27B-INT4` | The Hugging Face model. A new name downloads on first start. The pipeline uses whatever vLLM serves |
| Context | 16,384 | Most tokens one request may hold (prompt plus answer). About 12,000 words or 1,500 lines of code. The pipeline measures and trims prompts to fit. Above 16k, vLLM's working memory jumps from 0.6 to 2.8 GiB, so fewer requests fit at once |
| GPU memory | 0.92 | Share of the 4090 vLLM claims. It holds the model (~17 GB), working memory, and the **KV cache**: the model's short-term memory of the text it's working on. See the table below |
| Parallel requests | 8 | Most requests served at once. Candidates, the tester, judges, research and chat share them. KV cache is the real limit, not this |
| KV cache type | fp8 | 8-bit short-term memory: twice the room of 16-bit, with no noticeable quality loss |
| Attention backend | TRITON_ATTN | FlashInfer can't build here with fp8, so Triton is used. Leave it |
| Speculative decoding (MTP), draft tokens | on, 2 | The model's built-in predictor guesses 2 tokens ahead; the full model checks them in one step. About 94% of guesses are right, which is most of why output runs at ~104 tokens/s instead of ~35. The output is identical to running without it |
| CUDA graphs | on | Records the GPU's work once and replays it. Roughly tripled speed; costs ~1 GB and ~60 s of start-up. Off adds `--enforce-eager` (troubleshooting only) |
| Prefix caching | off | Reuses work when requests start with the same text. Doesn't combine well with this model's design and speculative decoding. The 32k preset turns it on |
| Text-only | on | Skips the model's image encoder, which leaves more memory for KV cache |
| Reasoning parser | qwen3 | Keeps the model's private thinking separate from its answer. Required for thinking |
| Extra arguments | empty | Any other vLLM flags. Shell symbols are rejected |

Measured on this 4090. WSL leaves 22.45 of 23.99 GiB free, so 0.95 can't start:

| GPU memory | KV cache | Full-length requests at once | Spare at start-up |
|---|---|---|---|
| 0.91 | 54,886 tokens | 3.35 | 0.62 GiB |
| **0.92** | **58,982 tokens** | **3.6** | 0.38 GiB |
| 0.93 | 62,259 tokens | 3.8 | 0.14 GiB (fragile) |

The **Long context (32k)** preset (GPU memory 0.90, no speculative decoding) holds **106,799
tokens** of KV cache, 3.26 full 32k requests at once: more than Fast, because there's no draft
model taking memory. It generates about 54 tokens/s for one request (Fast: ~104) and about 230
tokens/s in total with five at once (Fast: ~290), so it's half speed for chat but only about 20%
slower when a High run writes four candidates and a test together.

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

### Cluster tab

| Button | What it does |
|---|---|
| Connect Z: drive | Opens a window running `net use`; you type the share password there |
| Reset pipeline | Stops every run, empties the queue, marks their records stopped and removes leftover test containers on Node 2. The window stays open |
| Restart Node 2 services | Restarts Redis, Qdrant, SearXNG and the dashboard (Docker Compose). Warns first if runs are going |
| Restart Ollama on Node 3 | Opens a window that asks for your own `sudo` password on Node 3 |
| Warm up Node 3 models | Loads both Node 3 models so the first use isn't slow |
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

**On every level.**

- **Static check (pyflakes):** rejects a candidate that uses a name it never defines, a crash
  waiting on a line the test may never reach.
- **Repeat runs (Medium and above):** catch tests that only pass sometimes (randomness, timing, or
  leftover files).
- **Failure lines first:** when a test fails, the lines that report failures are always shown, wherever
  they appear in its output.
- **FAIL lines count:** an independent test that prints a line starting with `FAIL` has failed, even
  if it exits with code 0 (testers sometimes forget the exit code).

## How a run works

1. **Pick the target file** (the Target box, a file named in the goal, or a new name).
2. **Gather, in parallel:**
   - **Memory:** search for similar solved tasks. Anything scoring 0.63 or more is shown to the
     planner as an example.
   - **Scout:** brief any other workspace file the goal mentions.
   - **Web research**, if ticked.
3. **Planner** (thinks first): writes steps and 2-4 concrete **acceptance checks** (up to 6 on Ultra
   and MAX). On High and above it also writes the **interface**: the functions and command-line
   usage tests will call. On Ultra and MAX the **spec reviewer** then writes a precise spec and
   corrects the plan.
4. **Engineer:** writes **several candidate files at once** into `Z:\runs\<run>\a<attempt>c<candidate>\`,
   never straight into the workspace. Each includes its own self-test under `--test`.
   - It thinks first when fixing a failure (always, on Medium and above).
   - Candidates that use undefined names are rejected straight away.
   - At the same time: the tester writes `acceptance_test.py` (High and above), the adversary writes
     `adversarial_test.py` (MAX), and the prober writes `probe_cases.py` (Ultra and MAX).
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
   rewritten (up to 3 times per run).
   - On High and above the diagnosis thinks first, sees the spec, and is told when several
     candidates failed in exactly the same way. Candidates written independently rarely share a
     bug, but they all copy an expected value from the plan or spec, so identical failures point at
     the expected value. When independently written candidates agree and the diagnosis finds the
     spec's example wrong, a **correction is added to the spec** for every later step.
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
    - Node 3 summarizes it into long-term memory in the background.

### What a run leaves behind

- `Z:\runs\<run>\`:
  - `pipeline.log` (everything the run printed);
  - `final_<target>` (the winning code, or the best failed attempt);
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
python run_langgraph_pipeline.py --goal="..." [--target=name.py] [--attach=path ...]
                                 [--allow-network] [--research] [--accuracy=low|medium|high|ultra|max]
                                 [--no-memory] [--no-ingest]
```

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

Each passed run is summarized by Node 3, embedded with `qwen3-embedding:0.6b` and stored in Qdrant
with its goal, checks and code (taken from the run's own `final_<target>`). Similar future goals get
it as an example.

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

Low, Medium and High leave the last twelve unset; `LEVEL_DEFAULTS` fills them in.
`DEFAULT_ACCURACY` (low) is used when none is given; `MAX_PARALLEL_RUNS` (2) is how many shared
runs the queue starts at once.

**Model behaviour**

| Setting | Value | Meaning |
|---|---|---|
| `ENGINEER_MAX_OUTPUT` | 12000 | Longest file the engineer may write, in tokens. A file is also kept to half the context window: 8,192 tokens (about 600-800 lines) with the 16k server, the full 12,000 with the 32k preset |
| `LLM_TEMPERATURE`, `LLM_TOP_P`, `LLM_TOP_K` | 0.7, 0.8, 20 | How adventurous word choice is (the model maker's values). Lower is more predictable. Thinking calls use 0.6 / 0.95. The randomness is what makes candidates differ |
| `THINK_PLANNER`, `THINK_VERIFIER` | True | Let those steps think first |
| `THINK_TOKENS` | 5000 | Default thinking budget (Low and Medium use it; High sets its own) |
| `LLM_TIMEOUT` | 1200 | Seconds before one request is abandoned (generous because runs share the GPU) |

**Helpers and Node 3**

| Setting | Value | Meaning |
|---|---|---|
| `HELPER_BACKEND` | "node1" | Who writes the scout's brief and failure diagnoses. Node 1 is faster and better; "node3" frees Node 1 at some cost to quality. (Deciding whether a script or an independent test is wrong always uses Node 1) |
| `READER_BACKEND` | "auto" | Who reads research pages, condenses attachments and summarizes chats. "auto" uses Node 1, or Node 3 while Node 1 is busy with runs |
| `WORKER_MODEL`, `WORKER_THINK` | qwen3.5:9b, False | Node 3's model, thinking off for speed |
| `OLLAMA_NUM_CTX` | 8192 | Node 3's context. Must match everywhere, or Ollama reloads the model (~10 s) |
| `OLLAMA_KEEP_ALIVE` | -1 | Keep Node 3's models loaded permanently |

**Memory**

| Setting | Value | Meaning |
|---|---|---|
| `EMBED_MODEL` | qwen3-embedding:0.6b | Turns text into vectors to find similar tasks. Changing it needs `reindex_memory.py` |
| `MEMORY_MIN_SCORE` | 0.63 | How similar a past solution must be to be shown. In tests right matches scored 0.71+ and the best wrong one 0.57. Raise it if irrelevant examples appear, lower it if good ones are missed (the retriever logs scores) |
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

Optional Redis and Qdrant passwords go in `Z:\config\agent_secrets.env` (template in `config/`).
That folder is outside the workspace, so tests can't read it, and it's never committed.

## Where the time and hardware go

Measured on 2026-10-30:

- **The 4090 does almost all the work.** A typical run spends nearly all of its time in Node 1
  writing and checking.
  - Speed: ~104 tokens/s output for one request and ~2,870 tokens/s reading prompts. With several
    requests at once (candidates, judges), total output reaches ~250-330 tokens/s.
  - CPU and RAM: Node 1's are mostly idle, which is normal.
  - Node 2's 64 GB and 24 threads are mostly idle too: its services use about 0.3 GB. Its 2013-era
    CPUs and DDR3 would run a model at only 1-2 tokens/s, so it stores, searches and tests instead.
- **Two runs at once.** vLLM serves several requests together. One run fills the GPU only while it
  writes candidates; during planning and checking, most of its capacity sits unused, and a second
  run fills that gap. In the first test, three queued runs (two at once, the third waiting) finished
  in 5.6 minutes from start to finish, while their individual times add up to 8 minutes.
- **High runs alone.** A High run already keeps the GPU busy (4 candidates plus the tester, then
  the panel), so a second run beside it would mostly slow both down.
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
   - run `docker compose up -d` in `docker/` (this also builds the sandbox image).
2. **Node 3:** install Ollama, then `ollama pull qwen3.5:9b` and `ollama pull qwen3-embedding:0.6b`.
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
4. **Memory:** `python Z:\workspace\reindex_memory.py --import Z:\memory_export\agent_solutions.json`

## Troubleshooting

| Symptom | Fix |
|---|---|
| The Chat, Task & Queue and Runs tabs show "Connect Z:" | `Z:` isn't connected. Press Connect Z: and type the share password; the tabs load by themselves |
| vLLM won't start: "free memory ... less than desired" | Something else is using the GPU. Close it, or press Check free VRAM and start again |
| Chat says vLLM isn't reachable | vLLM is stopped or still loading (see the Model server tab's log). Start it, or pick Node 3 in the chat |
| A run shows LOST | Its process ended without finishing (killed, PC restarted). Re-run this goal |
| A run seems stuck | Its log on the Task & Queue tab shows what it's waiting for. Stop / remove it, or press Reset pipeline on the Cluster tab |
| A High, Ultra or MAX run waits in the queue | It starts once the runs ahead of it finish, because it needs the GPU to itself (Ultra and MAX then wait about a minute for vLLM to switch to 32k) |
| Chat is slow during an Ultra or MAX run | vLLM is on the 32k server then (about half speed for one request); it switches back when those runs finish |
| A script needs a package to run on this PC | Talk about result names it with the pip command, and Run it installs it for you |
| A run log says "Shortened '...' to fit the ... context window" | The prompt plus room for thinking and the answer didn't fit. Extras (attachments, web notes, past examples) are cut first; then the thinking shrinks, down to half its budget, before the spec or the failure report is cut. Common on High (16k) with big files; Ultra and MAX use the 32k server for this reason |
| A run log says "cut off at N tokens: about X of thinking, Y of answer" | A reply reached its token limit; the line shows where the room went. When thinking runs past its budget, the model tends to keep reasoning in its answer, which then gets cut off; such a candidate is finished from its own notes without thinking again ("finishing them from their own notes"). A candidate that still came back cut off or broken keeps the model's reply as `model_reply.txt` in its folder under `Z:\runs\<run>\` |
| Research finds nothing useful | The allowlist may not cover the topic. Add the relevant documentation site to `research_allowlist.txt` |
| Node 3 is slow on its first answer | Its models were unloaded. Cluster tab, Warm up Node 3 models |
| The window itself won't respond | Run `Reset_Cluster.bat` (one of the fallback `.bat` files; copies are in `launchers/`): it stops the window and every run, then reopens the window |
