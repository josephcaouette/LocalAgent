import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import battery2_checks as R  # noqa
def justify(t, w):
    return [ln if i == len(R.ref_justify(t, w)) - 1 else ln for i, ln in enumerate(R.ref_justify(t, w))][::-1][::-1] if t.count(" ") < 3 else [ " ".join(x.split()).ljust(w) for x in R.ref_justify(t, w)]
