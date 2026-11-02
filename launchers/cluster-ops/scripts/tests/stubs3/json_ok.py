"""Correct reference wrapper for battery 3's json goal (validates the checker; not pipeline code)."""
import json


def _no_constant(name):
    raise ValueError(name)


def parse_json(text):
    return json.loads(text, parse_constant=_no_constant)
