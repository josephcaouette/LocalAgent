"""Bug: accepts NaN, Infinity and -Infinity."""
import json


def parse_json(text):
    return json.loads(text)
