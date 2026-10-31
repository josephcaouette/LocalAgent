import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import battery2_checks as R  # noqa
parse_csv = R.ref_csv
