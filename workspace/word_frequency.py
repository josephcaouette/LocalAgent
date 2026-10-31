import sys
from collections import Counter

SAMPLE_TEXT = (
    "Apple, 123 apple apple apple apple banana banana banana banana "
    "cherry cherry cherry cherry date date date date elderberry elderberry elderberry "
    "fig fig fig grape grape grape honeydew honeydew honeydew "
    "icebox icebox icebox jackfruit jackfruit jackfruit kiwi kiwi kiwi lemon lemon"
)


def count_words(text):
    normalized = "".join(ch if ch.isalpha() else " " for ch in text.lower())
    words = normalized.split()
    counts = Counter(words)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]


def print_results(results):
    for word, count in results:
        print(f"{word} {count}")


def self_test():
    expected = [
        ("apple", 5),
        ("banana", 4),
        ("cherry", 4),
        ("date", 4),
        ("elderberry", 3),
        ("fig", 3),
        ("grape", 3),
        ("honeydew", 3),
        ("icebox", 3),
        ("jackfruit", 3),
    ]

    results = count_words(SAMPLE_TEXT)
    print_results(results)

    if results == expected:
        print("PASS")
        return 0

    print("FAIL")
    return 1


def main():
    args = sys.argv[1:]

    if "--test" in args:
        return self_test()

    if len(args) != 1:
        print("usage: python3 word_frequency.py <file> or --test", file=sys.stderr)
        return 2

    path = args[0]
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print_results(count_words(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
