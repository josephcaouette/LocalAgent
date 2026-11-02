"""Bug: accepts raw control characters inside strings."""
import json


def _no_constant(name):
    raise ValueError(name)


def parse_json(text):
    return json.loads(text, strict=False, parse_constant=_no_constant)
