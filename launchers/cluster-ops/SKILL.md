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
  context (MTP, ~104 tok/s single) and **Long context** 32k (GPU memory 0.92, no MTP; ~53 tok/s
  single, ~270 tok/s with 6 requests). The window's queue switches to 32k for Ultra/MAX runs and
  back afterwards (~40 s each). Runs from other processes (heartbeats in `workflow:active`: another
  window, a battery, the CLI) hold Node 1 too: the queue starts nothing beside them, doesn't switch
  vLLM under them, and switches back from 32k only after Node 1 has had no run for
  `SWITCH_BACK_QUIET_S` (120 s), rechecking every 30 s (`queueguard_unit.py`). So the user's window
  can stay open during a battery. To compare server settings: `scripts/tests/vllm_ab.py [config ...]`
  (restarts vLLM per config, restores the saved settings, merges into `vllm_ab_results.json`; nothing
  else may use Node 1 meanwhile). On 32k, MTP or `--max-num-batched-tokens 4096` shrink the KV cache
  by 40-47% and run 2-4x slower with eight requests at once (2026-10-31).
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
- Line endings: the repo stores LF, and edits to files on `Z:` can come back CRLF (a whole-file
  `git diff --stat` on Node 2). Fix on Node 2 with `sed -i 's/\r$//' FILE`. Check with Python
  (`open(f, 'rb').read().count(b'\r')`) or `grep -c $'\r'` on Node 2: in Git Bash on Node 1,
  `grep -c $'\r'` counts every line, so it can't tell. Run pyflakes on `Z:` files by full path
  (`Z:/workspace/x.py`); a relative path once gave "Invalid argument".

## The pipeline in one paragraph

Levels (config `RUN_PROFILES`): Low 2 candidates/30 min, Medium 3/12 h, High 4 diverse + independent
tests + 3 judges + critic (16k server), Ultra 4 + spec review + reference tests + candidate comparison
+ proven critics (32k), MAX 5 + adversarial tester + head-to-head + 2 critics x 4 rounds + mutation
testing (32k, 24 h). Graph nodes: retriever, scout, web, planner (+spec review), engineer (+tester,
adversary, prober in parallel), executor, verifier, condenser, retest, critic, mutation, finalize.
CLI: `run_langgraph_pipeline.py --goal-file F --target T --accuracy LEVEL [--no-memory --no-ingest]`.
A running pipeline has its code loaded already; edits only affect runs started afterwards.

Node 3's jobs: embeddings and memory summaries, memory relevance checks, web reading during runs,
and chat while a run is going (the chat's Automatic model). On High+ the **example check**
(`check_examples`, config `EXAMPLE_CHECK_BACKEND`, Node 1 by default; "node3" moves it back) writes
a brute-force script for the plan's hand-worked values, runs it in the sandbox, and re-derives any
disputed value with thinking. Failures skip harmlessly. Node 3 is a poor fit for writing code that
other steps run unchecked: `scripts/tests/probe_trial.py` (probe files scored on the correct
candidates and on AST mutants of three saved runs; Node 3 and the sandbox only) gave Node 1 114/115
mutants caught with no false disputes, and Node 3 1 good file in 9 (2026-10-31).
Node 1 writes **run digests** (`run_digest.py`, Redis field `digest`, shown as the Runs tab's
Summary) whenever the window's queue is idle; a launch or a vLLM switch kills the worker.

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
new pipeline behaviour (copy the pattern in `scripts/tests/*_unit.py`). Give fakes a `**kw` (or every
keyword `llm_chat`/`llm_complete` takes): a new keyword on the real function otherwise breaks every
fake that lists them, as `think_tokens` once did. `chatroute_unit.py` skips its idle check while a
real run is going, and `examples_unit.py` part 2 makes one live Node 1 call, so don't run the suite
in the middle of a timing measurement. The suite's exit code catches a test that crashes, exits
non-zero or prints `N FAILED`; most older tests only print True/False per case, so read the output
too, and make new tests print `PASS`/`FAIL` per check, then `ALL PASS` or `N FAILED`, and
`sys.exit(1)` on a failure (as `bigfile_unit.py` does). (Before 2026-11-02 each test's status came
from the end of a pipe, so no unit test could fail the suite.) For GUI or queue changes,
an end-to-end run through the window is the real test: `scripts/tests/ultra_max_e2e.py smoke`
(Ultra, MAX and Low on small tasks; about an hour) drives a hidden ClusterWindow.

### Test battery (non-cron, several levels)
`scripts/tests/battery.py full set1` (18 runs, about 3.5 hours) or `quick set1` (Low only) queues
five tasks (glob matcher, bowling, calculator, dependency order, free slots) through a hidden window
and checks each result in the sandbox with `battery_checks.py` (references: fnmatch, minute brute
force, own parsers; validated against good and deliberately wrong stubs in `tests/stubs/`). `set2`
uses `battery2_checks.py` (semver ranges, text justify, Game of Life, CSV, TTL cache; stubs in
`tests/stubs2/`). One run: `battery.py one set1 TASK LEVEL`; `BATTERY_TAG=_x` suffixes the target
name and `BATTERY_EXTRA="--helper-think 8000"` adds pipeline flags. Results go to
`battery_results_<set>.json` for a full battery (set 1's first run wrote `battery_results.json`);
quick, one-off and tagged runs add a suffix (`battery_results_set2_x_one.json`); the produced
`<task>_<level>.py` files in `Z:\workspace` must be deleted afterwards. Use it after pipeline changes
so fixes aren't tuned to one task. `set3` (`battery3_checks.py`: a strict JSON parser, IPv6
normalization, a regex-subset matcher; references are `json`, `ipaddress` and `re` behind thin layers
for the goals' own rules, each call under a 1 s alarm; `python3 battery3_checks.py selfcheck`, and
stubs in `tests/stubs3/`, where every `<task>_ok` must score in full and every `<task>_bad_*` must not)
goes with `umax` mode: Ultra then MAX on each task, 6 runs, about 8 hours. `BATTERY_HOURS` (default 10)
caps the wait for the queue. `scripts/tests/umax_report.py battery_results_set3_umax.json` (or run ids)
tabulates score, attempts, minutes, tokens and which Ultra/MAX steps fired (independent and
adversarial failures, blames, head-to-head, critic rounds, proven findings, mutation score, stuck
notes). The battery drives a hidden window with its own queue (the user's window shows nothing),
and puts the user's `agent_gui.pid` back at the end only if no window wrote its own meanwhile.

`set4` (`battery4_checks.py`) goes with `full` mode, all five levels on each task (15 runs, roughly
15-20 hours; use `BATTERY_HOURS=30`). Three big tasks with exact references, built to push Ultra and
MAX apart: pyexpr (a Python-subset integer evaluator; traps: 100,000-deep nesting, million-character
inputs, 100,000-digit literals past Python 3.11's 4,300-digit `int()` limit, and a size rule that must
not compute 9**9**9), toml (TOML 1.0 against `tomllib`, ~460 invalid documents) and struct
(pack/unpack/calcsize against `struct`, half and single precision rounded by hand). Every candidate
call runs in a forked child with a time and memory limit, because an alarm can't interrupt a
computation inside C (a huge power, a backtracking regex); the battery gives set 4's check 900 s and
1 GB. The deep and long pyexpr cases use closed forms (`ast.parse` stops at 200 nested parentheses),
which the selfcheck verifies at small scale. Validate changes with `python3 battery4_checks.py
selfcheck` and `tests/stubs4/`: `python mkvariants4.py` writes the 23 `*_bad_*` variants from the
`*_ok` stubs through their `BUG` switch, and each must lose cases (2026-11-02: all do; the ok stubs
score 1234/1234, 1037/1037 and 1315/1315 in 12-28 s). `tests/probe4.py` records the reference
behaviours the goals rely on: tomllib has no 64-bit limit, rejects `0x_1`, and recurses past ~900
nested arrays (so no deep TOML cases); struct raises struct.error, not OverflowError, for a huge int
packed as `f`, so no case depends on that.

`battery.py level set4 high` runs one level on every task (results in
`battery_results_<set><TAG>_<level>.json`), for checking a change on the runs that showed a problem.
A battery scores only the file each run kept. `scripts/tests/score_candidates.py <set> [-P 8]
[--failed-only] [--results set4_fb_high]` scores every candidate of every run in `battery_results_<set>.json` (and each
`final_` file) with the same checker on Node 2, P containers at once (set 4's 337 files took about
15 minutes), into `candidate_scores_<set>.json`; Node 1 isn't used. `furthest_sim.py <set>` then
replays each run's log through the pipeline's `progress()` ranking and prints, per run, the kept
file's score, the furthest candidate's (what a failed run now saves) and the best candidate's.

Reading results: a FAILED run whose final file still scores full marks means the pipeline rejected
correct code, almost always a wrong hand-computed expected value in a test. Look in
`Z:\runs\<run>\pipeline.log` for the diagnosis and BLAME lines, and run a candidate's own test with
`ssh server@<NODE2_IP> "docker run --rm --network none -v /mnt/blackboard:/bb:ro agent-sandbox:latest
python3 /bb/runs/<run>/a3c1/<file> --test"`. Set 1 (2026-10-31): 17/18 passed, all 18 files correct;
the slow runs were re-test loops (now fixed in place, `inplace_unit.py`). Repeating its MAX run with
`--helper-think 8000` changed nothing but tokens (+35%): the test writers still wrote wrong expected
values, so it isn't a level default. Set 2 (2026-10-31): 14/18 passed, every file produced was
correct (two runs stopped without one). Its four non-passes are fixed, each with a unit test:
semver/low stopped on a fix too long for the window (`edits_unit.py`: SEARCH/REPLACE edits instead),
semver/medium in the step that finishes a cut-off candidate from its notes (`finishroom_unit.py`),
life/low re-rolled its self-test grids (`edits_unit.py`: in-place correction when only the
expectation is blamed), and csv/high spent all 10 attempts on an ambiguous goal ("\n" as no record
or one empty record), with the diagnosis blaming the script nine times while every candidate kept the
reading the reference shares (`stuck_unit.py`: a repeat after a script blame now gets a decision
that sticks). csv/ultra took 6 attempts because its test checked random inputs against the test
writer's own parser, which had a new bug at each fix (the diagnosis rightly blamed the test).
Set 3 umax (2026-11-01): all 6 passed; json and ipv6 full marks on both levels; regex Ultra 1918/1919,
lost on goal wording alone (`\é`: "letter" read as ASCII; the goal now says Unicode counts). MAX cost
1.1-2.4x the time and 1.3-3x the tokens; json/max lost 5 attempts to an adversarial test that exited 1
with only PASS lines (`silent_unit.py`: such a test is now blamed without a model call; replayable
outputs in `tests/data/silent_test_case/`). No run got a summary: the battery's window waited the
quiet period before switching back and closed first (fixed: the window that switched to 32k switches
back at once, `queueguard_unit.py`; battery.py also waits for the switch back). A window keeps the
code it loaded: compare a window's start time with your edits (`Get-Process -Id N | Select StartTime`)
before relying on a fix in it.
Set 4 full (2026-11-02, 20 h): every Low/Medium/High run failed and Ultra/MAX passed toml and struct;
pyexpr failed everywhere. Kept-file scores pyexpr 887/180/0/757/1213 of 1234, toml 271/697/732/920/975
of 1037, struct 658/712/1164/1314/1298 of 1315 (Low..MAX). First battery where Ultra and MAX differ:
MAX's pyexpr 1213 vs Ultra's best candidate 972 (Ultra peaked on attempt 4 and regressed), toml 975 vs
920 (MAX's adversarial test and mutation testing); struct a draw. MAX 1.1-1.8x output tokens. The 16k
levels fail on 800-900-line files: pyexpr/high's first file had placeholder functions and edits with
1,500 answer tokens came back empty 28 of 36 times; struct/high's self-test had wrong hand-worked
bytes, corrected one per attempt. Fixed in `bigfile_unit.py`: a failed run keeps the furthest
candidate (`progress()`; replayed on the 11 failures: 8,913 of the best 9,158 points vs 7,271 kept);
missing stdlib imports added; placeholder functions rejected; edits keep 4,000 answer tokens when
thinking. MAX pyexpr's acceptance-test generator had two bugs found one per attempt (a recursion with
no base case on attempt 15, caught with a real `0x__1` script bug; then invalid Python such as
`4 - not 4` on attempt 16, the last), so the run ended with four candidates that had passed their own
tests failing only that test. Fixed (2026-11-03): the **stand-in check** (`standin_review`, switch
`STANDIN_CHECK`; `standin_unit.py`) runs each new or revised independent test against two stand-ins
that implement nothing (A truthy/equal to all, B falsy/equal to none) and sends back to the writer
(up to 2 rounds) any FAIL line with a value, or crash in the test's own code, that is identical for
both; it found both MAX bugs plus a third (a 100,000-digit `repr()` past the 4,300-digit limit), and
`standin_replay.py [copy.py]` gave 0 findings on the 6 saved tests winners passed. The **last chance**
(`last_chance()`, `lastchance_unit.py`): attempts used up, time left, only an independent test failing
-> one diagnosis, and one re-test if it blames the test. `--fix-base furthest` (default `latest`,
`fixbase_unit.py`) starts each fix from the furthest candidate (Ultra pyexpr's regression), at most
twice per version. Its High re-run (`BATTERY_TAG=_fb`, 2026-11-03, `battery_results_set4_fb_high.json`)
was inconclusive: pyexpr 0 -> 622 (best 843), toml 732 -> 543, struct 1164 -> 853 (858), with only 3
go-backs, all in struct; latest stays the default; try it on Ultra next.
That re-run showed why the 16k levels fail on big files: of 120 candidate slots, 32 fix replies had an
edit matching nowhere and 38 had no edit; 33 candidates were tested. `scripts/tests/edits_live.py [RUN
CAND N]` replays a fix request through `engineer_edits` (Node 1, ~3 min) and diagnoses each failed
SEARCH part: thinking overran its ~1,300-token budget into the answer, or a 100-line SEARCH copy
differed in two comment lines. Fixed (`editmatch_unit.py`, saved replies in `tests/data/edits_case/`):
`loose_place()` matching (spacing/indent-insensitive, else first and last lines anchored with at most
1 line in 10 different, unique only), finishing cut-off edit replies from their notes, carrying
`PROBLEM_MARK` ("The problem you were fixing") through an attempt where nothing applied, and keeping
failed replies in `model_reply.txt`. Live: 0 of 4 replies applied before, 3 of 4 after.
To test a pipeline change while a battery runs (the live file must not change mid-battery), edit a
copy and run unit tests against it with `python scripts/tests/devtest.py COPY.py TEST_unit.py`.
Set 4 v2 (2026-11-03, 23.6 h, `BATTERY_TAG=_v2`, `battery_results_set4_v2.json`): kept pyexpr
544/727/250/706/6, toml 765/805/910/990 (passed)/673, struct 638/1040/1274/1302/1232 (Low..MAX). The 16k
levels gained (Low+Medium+High kept 6,953 vs 5,301; 38 edit replies finished from notes); Ultra/MAX
lost (1 pass vs 4; v1's logs were pruned, so no side-by-side): pyexpr/max hit a dead end (10 attempts of
fixes of one broken parser, after the diagnosis put implementation details into the interface),
toml/max never passed its own self-test, struct U/M self-test bytes blamed 4-5 times. Stand-in check:
2 real findings, both unrepaired, and 2 false alarms (51/76 exception checks worded "got no error" /
"got no exception"); fixed: `_EXPECTS_ERROR` covers those wordings, `test_problem` adds missing stdlib
imports to tests, failed repair replies saved as `Z:\runs\<run>\standin-<role>-a<N>-reply.txt`, and
`standin_unit.py` reads `tests/data/standin_case/` (run folders get pruned; v1's MAX tests were lost
that way). Failed runs kept 11,862 of the 14,068 points their best candidates reach: `final_pick()`
(`FINAL_PICK`, `FINAL_PICK_RATIO` 0.7, `finalpick_unit.py`) now runs a failed High+ run's final
independent tests on every distinct candidate (~1 min per 25) and overrules the furthest one when it
passes under 70% of the top share. `finalpick_sim.py <name> [-P 8]` (BATTERY_TAG for target names;
Node 2 only, ~20 min for 576 test runs) replays that: 7,937 of 8,325 vs 6,353 kept; ratios 0.6-0.8 all
give it; always taking the top share gives 7,410 (struct/ultra's test held wrong bytes). Dead ends
(2026-11-04, `dead_end()`, `restart_unit.py`): after `RESTART_AFTER` (3) attempts in a row whose best
progress() rank is below the best of the current line of fixes (`line_best`; equal counts as progress),
the executor sets `restart_note` and the engineer writes fresh (diverse on High+) candidates with that
note instead of fixing; at most `MAX_RESTARTS` (2) per run, and the count starts over after one; an
attempt with nothing testable keeps the note. `restart_sim.py <name> [AFTER]` replays the rule on a
battery's logs (first firing per run): on set4_v2 it fires in toml/medium (7), pyexpr/max (10),
toml/max (6), struct/max (10), never in the run that passed. Open: interface corrections that
prescribe implementation instead of behaviour (pyexpr/max v2's dead end began right after two).
Set 4 v3 umax (2026-11-04/05, 21 h, `BATTERY_TAG=_v3 battery.py umax set4`, `battery_results_set4_v3_umax.json`,
`candidate_scores_set4_v3_umax.json`): kept pyexpr 152 (best 946)/1167, toml 974 (passed)/970, struct 1208
(passed)/1311 (Ultra/MAX); 5,782 of 7,172 points vs v2 4,909 and v1 6,477. Restarts: pyexpr/max twice, each
fresh line jumped (781 -> 1151, then 1173); pyexpr/ultra once, but a3c3 (weak self-test passed, 1 case) had
set `line_best`, so attempts 4-6 (853-871) counted as worse; struct/ultra's fired during re-tests (fixed: the
re-test node passes `retesting=True` and the executor skips `dead_end`). toml/max never restarted (every
self-test stopped at its first failure, so all attempts tied at the floor) but its code sat at 941-970 from
attempt 2, so the tie rule stays. struct/max failed holding a correct candidate (a15c5, 1311, 100% of both
final tests): its 3 re-tests all went to the acceptance test, so the adversarial test's rightful blame on
attempt 15 forced rewrites that all failed; fixed: `retests_by_test` and `retests_left()` (MAX_RETESTS per
test; `lastchance_unit.py`, `silent_unit.py`). Stand-in false alarms fixed: `_EXPECTS_ERROR` takes "should
raise", `_BARE_GOT` drops FAIL lines ending in a bare None/True/False (`isinstance` verdicts); standin_unit
keeps struct/max's two tests (old rule 19 and 1 findings, new 0). Final pick: overruled once (pyexpr/ultra
a3c3 1 -> a2c3 152) and missed a1c3 (946): the test stopped early for a2c3 (68/85) but ran 395 checks for
a1c3 (77). `finalpick_metric.py <names>` compares share with reach (passes / most checks printed): v2
reach 6,381 vs share 6,930 (struct/ultra's test stopped early for the right candidates), v3 pyexpr/ultra
reach 813 vs 152; both batteries (finalpick_set4_v2/v3_umax.json) 10,642 vs 10,530 of 11,716 at any ratio
0.6-0.8, one bad loss each, so share stays (no change on two opposite cases).
`restart_sim.py` now skips re-tests and pruned logs; its shares come from log tails, so it's approximate.
If vLLM is down (the PC slept: no process in WSL, log ends without a shutdown line), start it with the
window's saved settings: `cl.vllm_script(cl.load_settings()["vllm"])` run detached through `wsl bash
-c`, as `scripts/tests/vllm_ab.py`'s `start()` does (about 45 s on the Fast preset).

Live checks on two saved failures (`tests/data/`): `scripts/tests/inplace_live.py [1|2]`, about a
minute with Node 1 free. Part 1 replays the in-place fix of a wrong adversarial value (must be one
call without thinking that changes only that check); part 2 runs Low's thinking diagnosis on a
correct glob matcher with a wrong self-test (must blame the expectation in 2 of 3 tries). Both
passed on 2026-10-31 (part 1 twice, part 2 three of three). `scripts/tests/stuck_live.py [N]` replays
set 2's stuck csv/high diagnosis with and without the stuck note (2N calls, ~2.5 min each);
`stuck_live.py follow` writes two engineer candidates from an interface correction and runs the real
acceptance test on them. On 2026-10-31: without the note, script 3/3 (the loop); with it, 4/4 broke
the cycle (test once, script plus a correction three times), and the corrected candidates dropped
the old failures but overcorrected a neighbouring case. The battery's csv goal now spells out "\n";
the original wording is kept in `tests/data/csv_high_case/goal.txt` for the replay.

`scripts/tests/testwriter_ab.py [N] [ARMS]` A/Bs the acceptance test writer on set 2's csv/ultra plan:
each test runs on the run's correct implementations (a failure = a false failure, which costs a
re-test in a real run) and on 40 mutants. On 2026-10-31, guidance to use a standard-library reference
and to write an own reference only when much simpler didn't help (usable tests: old 1/3, new 1/3 and
0/3; no test used `csv`), so it was removed. The base rate is the finding: 2 of 3 Ultra acceptance
tests for CSV fail correct code out of the gate (empty lines), and the pipeline recovers by re-testing.

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
| `[Node: Example Checker] -> N expected value(s) confirmed, M disputed` | Node 3's brute-force check of the plan's examples; disputes go to Node 1, which may print `Corrected ... before coding` |
| `Node 3's script still failed ...; skipped` / `Nothing in the plan can be recomputed exactly` | The example check didn't apply or Node 3 couldn't write a working checker; the run continues unchanged |

Lessons from the benchmarks (2026-10-31): the shared spec is a single point of failure (one wrong
worked example or invented limit reaches every candidate); hand-computed expected values are the
most common source of false failures; High is usually enough for mid-size tasks, Ultra/MAX add
insurance (Ultra ~2x and MAX ~4x High's tokens).
