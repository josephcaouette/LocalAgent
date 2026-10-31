import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import battery2_checks as R  # noqa
satisfies = R.ref_satisfies
