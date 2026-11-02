"""Write battery 4's deliberately wrong stubs from the correct ones: stubs4/<task>_bad_<bug>.py is
<task>_ok.py with BUG set. Each must lose at least one case to the checker; the ok stubs must score
in full. Run: python mkvariants4.py (then validate in the sandbox as the cluster-ops skill says)."""
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stubs4")
BUGS = {"pyexpr": ["trunc_div", "not_tight", "no_chain", "pow_left", "unary_tight", "recursive", "int_limit",
                   "eager", "bool_as_int", "no_size_check", "quadratic"],
        "toml": ["crlf_strict", "inline_comma", "leading_zero", "empty_key", "dates_ok", "ints_as_floats"],
        "struct": ["noprefix_ok", "ws_count", "c_bytearray", "e_trunc", "overflow_as_value", "unpack_lenient"]}

for task, bugs in BUGS.items():
    with open(os.path.join(HERE, f"{task}_ok.py"), encoding="utf-8") as f:
        src = f.read()
    assert src.count('\nBUG = ""\n') == 1, task
    for bug in bugs:
        with open(os.path.join(HERE, f"{task}_bad_{bug}.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(src.replace('\nBUG = ""\n', f'\nBUG = "{bug}"\n'))
print(sum(len(b) for b in BUGS.values()), "variants written")
