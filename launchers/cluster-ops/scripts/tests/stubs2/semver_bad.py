import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import battery2_checks as R  # noqa
def satisfies(v, r):
    return R.ref_satisfies(v, r.replace("^0.", "^1."))  # wrong: ^0.x treated like ^1
