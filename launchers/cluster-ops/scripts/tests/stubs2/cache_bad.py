import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import battery2_checks as R  # noqa
class TTLCache(R.RefCache):
    def get(self, key, now):  # wrong: a get does not refresh recency
        if not self._alive(key, now):
            self.items.pop(key, None)
            return None
        return self.items[key][0]
