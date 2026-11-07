"""A failed run judges its candidates by its final independent tests (final_pick). In set 4's second
battery the failed High/Ultra/MAX runs kept 6,353 of the 8,325 points their best candidates reach:
the expression evaluator on MAX kept a candidate whose weak self-test passed while it rejected
`1 + 2 * 3` (6/1234; its best scored 602). The final tests overrule the furthest candidate only when
it passes under 80% of the share the best passes: struct on Ultra's test held wrong bytes, and its
correct file passed 82.5% of the top share (a switch would have swapped a 1,302 file for a 753 one),
while set 5's decompressor on Ultra kept 77% (574 cases against 673; the line was 70% until
2026-11-07). Part 1 runs three tiny candidates in the sandbox (Node 2); part 2 uses made-up test
outputs; part 3 is finalize_node."""
import os
import shutil
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

p.report = lambda *a, **k: None
RUN, TARGET = "unit-finalpick", "add_fp.py"
GOOD = "def add(a, b):\n    return a + b\n"
HALF = "def add(a, b):\n    return a + b if a >= 0 else 0\n"
BAD = "def add(a, b):\n    return 0\n"
BODY = ("cases = [(1, 2), (2, 3), (0, 0), (5, 5), (-1, 1), (-2, -3), (-5, 2), (7, -7)]\n"
        "for a, b in cases:\n"
        "    got = target.add(a, b)\n"
        "    print(f'PASS add {a} {b}' if got == a + b else f'FAIL add {a} {b} expected {a + b}, got {got}')\n")
TEST = p.test_header(TARGET) + BODY
folder = os.path.join(config.RUNS_DIR, RUN)


def make(cands):
    shutil.rmtree(folder, ignore_errors=True)
    for name, code in cands.items():
        os.makedirs(os.path.join(folder, name))
        with open(os.path.join(folder, name, TARGET), "w", encoding="utf-8", newline="\n") as f:
            f.write(code)


state = {"run_id": RUN, "target_file": TARGET, "tests": {"acceptance": TEST}, "lvl": config.level_settings("high"),
         "allow_network": False, "code": BAD, "status": "FAILED", "attempt": 4}
checks = []

# --- 1. In the sandbox ------------------------------------------------------------------------------
make({"a1c1": GOOD, "a2c1": HALF, "a3c1": BAD, "a3c2": GOOD})
picked = p.final_pick(state)
checks += [
    ("sandbox: the best candidate overrules a far worse kept one", picked is not None and picked["code"] == GOOD.strip()),
    ("  named after its latest copy (identical code is run once)", picked and picked["name"] == "a3c2"),
    ("  with both shares (always 0 still passes 0+0, -1+1 and 7-7)",
     picked and picked["share"] == 1.0 and picked["kept_share"] == 3 / 8),
    ("  and its boxes' folders are cleaned up", sorted(os.listdir(folder)) == ["a1c1", "a2c1", "a3c1", "a3c2"]),
]

# --- 2. Made-up outputs -------------------------------------------------------------------------------
outputs, ran = {}, []


class Res:
    def __init__(self, out, rc=0, err=""):
        self.stdout, self.returncode, self.stderr = out, rc, err


def fake_box(st, box, args, **kw):
    ran.append(box)
    return outputs[box]


real_box, real_remove = p.run_in_box, p.remove_boxes
p.run_in_box, p.remove_boxes = fake_box, lambda *a, **k: None


def lines(passed, failed):
    return "".join(f"PASS c{i}\n" for i in range(passed)) + "".join(f"FAIL d{i}\n" for i in range(failed))


make({"a1c1": GOOD, "a2c1": HALF, "a3c1": BAD})
outputs.update({"final-a1c1": Res(lines(92, 8), 1), "final-a2c1": Res(lines(50, 50), 1), "final-a3c1": Res(lines(76, 24), 1)})
checks.append(("a small gap keeps the candidate (76% against 92%, as struct on Ultra)", p.final_pick(state) is None))
outputs.update({"final-a1c1": Res(lines(65, 35), 1), "final-a2c1": Res(lines(10, 90), 1),
                "final-a3c1": Res(lines(50, 50), 1)})
picked = p.final_pick(state)
checks.append(("a gap between 70% and 80% overrules it (50% against 65%, as the decompressor on Ultra)",
               picked is not None and picked["name"] == "a1c1" and picked["kept_share"] == 0.5))
outputs.update({"final-a1c1": Res(lines(46, 54), 1), "final-a2c1": Res(lines(10, 90), 1),
                "final-a3c1": Res(lines(21, 79), 1)})
picked = p.final_pick(state)
checks.append(("a large gap overrules it (21% against 46%, as the evaluator on MAX)",
               picked is not None and picked["name"] == "a1c1"))
outputs.update({"final-a1c1": Res("PASS a\n", 1, "Traceback (most recent call last):\nValueError: x\n"),
                "final-a3c1": Res(lines(1, 0), 0)})
picked = p.final_pick(state)
checks.append(("a crash after its PASS lines counts as one more failure (50% against 100%: no switch)",
               picked is None))
ran.clear()
checks.append(("no independent tests: nothing runs", p.final_pick(dict(state, tests={})) is None and ran == []))
make({"a1c1": BAD})
checks.append(("only the kept code was written: nothing to compare", p.final_pick(state) is None and ran == []))

# --- 3. finalize_node -------------------------------------------------------------------------------
make({"a1c1": GOOD, "a3c1": BAD})
outputs.update({"final-a1c1": Res(lines(8, 0), 0), "final-a3c1": Res(lines(2, 6), 1)})
base = dict(state, task_key="t", max_attempts=3, started=0, time_limit_s=10 ** 10, best_passed={}, furthest={},
            error="FAIL x", verdict="v", execution_stderr="", winner=0, regression=[])
p.finalize_node(base)
final = open(os.path.join(folder, "final_" + TARGET), encoding="utf-8").read()
checks.append(("finalize: a failed run saves the candidate the final tests pick", final.strip() == GOOD.strip()))
real_pick = p.final_pick
p.final_pick = lambda st: (_ for _ in ()).throw(RuntimeError("Node 2 unreachable"))
p.finalize_node(base)
final = open(os.path.join(folder, "final_" + TARGET), encoding="utf-8").read()
checks.append(("finalize: an error there keeps the candidate it had", final.strip() == BAD.strip()))
called = []
p.final_pick = lambda st: called.append(1)
p.FINAL_PICK = False
p.finalize_node(base)
p.FINAL_PICK = True
p.finalize_node(dict(base, status="STOPPED"))
checks.append(("finalize: switched off, or a stopped run: not judged", called == []))
p.final_pick, p.run_in_box, p.remove_boxes = real_pick, real_box, real_remove
shutil.rmtree(folder, ignore_errors=True)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
