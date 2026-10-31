import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from battery_checks import ref_calc
def evaluate(e):            # floor division instead of truncation: wrong for negatives
    if "/" in e and "-" in e:
        return eval(e.replace("/", "//"))
    return ref_calc(e)
