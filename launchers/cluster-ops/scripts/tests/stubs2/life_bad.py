import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import battery2_checks as R  # noqa
def step(g, rule="B3/S23", wrap=False):
    return R.ref_step(g, rule, False)  # wrong: ignores wrap
