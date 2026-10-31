import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from battery_checks import ref_calc as evaluate  # noqa
