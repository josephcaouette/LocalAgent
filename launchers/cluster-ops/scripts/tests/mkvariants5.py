"""Write battery 5's deliberately wrong stubs from the correct ones: stubs5/<task>_bad_<bug>.py is
<task>_ok.py with BUG set. Each must lose at least one case to the checker; the ok stubs must score
in full. Run: python mkvariants5.py (then validate in the sandbox as the cluster-ops skill says)."""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stubs5")
BUGS = {"fmtspec": ["half_up", "no_zero_group", "z_ignored", "str_zero_right", "g_strip", "c_wrap",
                    "int_precision_ok", "pct_exact", "repr_exp17", "sep_start"],
        "strptime": ["pivot_50", "no_ci", "j_ignored", "I_no_am", "ws_exact", "f_left", "z_colon_strict",
                     "leap_default", "first_wins", "uw_simple"],
        "inflate": ["no_adler", "trailing_error", "no_hcrc", "nlen_unchecked", "no_far_check",
                    "lenient_incomplete", "empty_ok", "gzip_multi", "cl_split"]}

for task, bugs in BUGS.items():
    with open(os.path.join(HERE, f"{task}_ok.py"), encoding="utf-8") as f:
        src = f.read()
    assert src.count('\nBUG = ""\n') == 1, task
    for bug in bugs:
        with open(os.path.join(HERE, f"{task}_bad_{bug}.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(src.replace('\nBUG = ""\n', f'\nBUG = "{bug}"\n'))
print(sum(len(b) for b in BUGS.values()), "variants written")
