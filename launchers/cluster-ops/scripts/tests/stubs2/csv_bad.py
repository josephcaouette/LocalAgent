def parse_csv(text):
    return [ln.split(",") for ln in text.splitlines()]  # naive
