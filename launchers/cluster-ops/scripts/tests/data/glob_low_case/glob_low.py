"""
glob_low.py

Shell-style wildcard matching without fnmatch, glob, or re.

Usage:
    python3 glob_low.py --test
    python3 glob_low.py PATTERN TEXT
"""

import sys


def _parse_pattern(pattern: str):
    """
    Parse a wildcard pattern into tokens.

    Token forms:
        ("star",)
        ("question",)
        ("literal", ch)
        ("class", negated, members)

    For a class, members is a list of (lo, hi) inclusive code-point ranges.
    A single character is represented as (ch, ch).
    """
    tokens = []
    i = 0
    n = len(pattern)

    while i < n:
        ch = pattern[i]

        if ch == "*":
            tokens.append(("star",))
            i += 1
        elif ch == "?":
            tokens.append(("question",))
            i += 1
        elif ch == "[":
            # Try to parse a bracket expression.
            j = i + 1
            negated = False

            if j < n and pattern[j] == "!":
                negated = True
                j += 1

            members = []

            # A ']' immediately after '[' or '[!' is a literal member.
            if j < n and pattern[j] == "]":
                members.append(("]", "]"))
                j += 1

            closed = False
            while j < n:
                cj = pattern[j]

                if cj == "]":
                    closed = True
                    j += 1
                    break

                # Range: x-y, but not if the range would end at the closing ']'
                # or if there is not enough room.
                if (
                    j + 2 < n
                    and pattern[j + 1] == "-"
                    and pattern[j + 2] != "]"
                ):
                    lo = cj
                    hi = pattern[j + 2]
                    if lo <= hi:
                        members.append((lo, hi))
                        j += 3
                    else:
                        # Degenerate/invalid range: treat the first character
                        # as literal and continue parsing normally.
                        members.append((lo, lo))
                        j += 1
                else:
                    members.append((cj, cj))
                    j += 1

            if closed:
                tokens.append(("class", negated, members))
                i = j
            else:
                # No closing ']': the '[' is literal, and the rest is parsed
                # as ordinary pattern characters.
                tokens.append(("literal", "["))
                i += 1
        else:
            tokens.append(("literal", ch))
            i += 1

    return tokens


def _char_in_class(ch: str, negated: bool, members) -> bool:
    """Return True if ch is accepted by the bracket class."""
    in_class = False
    for lo, hi in members:
        if lo <= ch <= hi:
            in_class = True
            break
    return (not in_class) if negated else in_class


def match(pattern: str, text: str) -> bool:
    """
    Return True if the entire text matches the shell-style wildcard pattern.

    Semantics:
        *       matches any sequence of characters, including none
        ?       matches exactly one character
        [abc]   matches one of a, b, c
        [a-c]   matches one character in the range a through c
        [!abc]  matches one character not in the set
        [*]      matches literal '*'
        []]      matches literal ']'
        [        matches literal '[' if the bracket is not closed
    """
    tokens = _parse_pattern(pattern)
    n = len(text)

    # dp[j] means: the remaining tokens (starting at the current token index)
    # match text[j:].
    dp = [False] * (n + 1)
    dp[n] = True

    for token in reversed(tokens):
        cur = [False] * (n + 1)

        if token[0] == "star":
            # Compute from right to left so cur[j + 1] is already known.
            for j in range(n, -1, -1):
                if dp[j]:
                    cur[j] = True
                elif j < n and cur[j + 1]:
                    cur[j] = True
        elif token[0] == "question":
            for j in range(n - 1, -1, -1):
                cur[j] = dp[j + 1]
        elif token[0] == "literal":
            ch = token[1]
            for j in range(n - 1, -1, -1):
                if text[j] == ch and dp[j + 1]:
                    cur[j] = True
        elif token[0] == "class":
            _, negated, members = token
            for j in range(n - 1, -1, -1):
                if _char_in_class(text[j], negated, members) and dp[j + 1]:
                    cur[j] = True
        else:
            raise ValueError(f"Unknown token: {token!r}")

        dp = cur

    return dp[0]


def _self_test() -> int:
    cases = [
        # Basic literals and empty strings.
        ("abc", "abc", True),
        ("abc", "abd", False),
        ("", "", True),
        ("", "a", False),
        ("a", "", False),

        # Star basics.
        ("*", "", True),
        ("*", "anything", True),
        ("a*", "a", True),
        ("a*", "abc", True),
        ("a*", "b", False),
        ("*a", "a", True),
        ("*a", "ba", True),
        ("*a", "ab", False),
        ("a*b", "ab", True),
        ("a*b", "acb", True),
        ("a*b", "acdb", True),
        ("a*b", "ac", False),
        ("a**b", "ab", True),
        ("a**b", "acb", True),
        ("**", "", True),
        ("**", "xyz", True),

        # Star backtracking.
        ("a*b*c", "abc", True),
        ("a*b*c", "abbc", True),
        ("a*b*c", "abcc", False),
        ("a*b*c*d", "abXcYdZ", False),
        ("a*b*c*d", "abXcYd", True),
        ("a*b*c*d", "aXbYcZd", True),
        ("a*b*c*d", "abcd", True),
        ("a*b*c*d", "aXbYcZdW", False),
        ("*a*b*c*", "abc", True),
        ("*a*b*c*", "aXbYc", True),
        ("*a*b*c*", "XaYbZcW", True),
        ("*a*b*c*", "XaYbZ", False),
        ("a*?b", "ab", False),
        ("a*?b", "acb", True),
        ("a*?b", "acdb", True),
        ("a*?b", "ac", False),

        # Question mark.
        ("?", "a", True),
        ("?", "", False),
        ("?", "ab", False),
        ("a?c", "abc", True),
        ("a?c", "ac", False),
        ("a?c", "abbc", False),
        ("??", "ab", True),
        ("??", "a", False),
        ("??", "abc", False),
        ("*?*", "a", True),
        ("*?*", "", False),
        ("*?*", "ab", True),

        # Simple classes.
        ("[abc]", "a", True),
        ("[abc]", "b", True),
        ("[abc]", "c", True),
        ("[abc]", "d", False),
        ("[abc]", "", False),
        ("[abc]", "ab", False),
        ("x[abc]y", "xay", True),
        ("x[abc]y", "xdy", False),

        # Ranges.
        ("[a-c]", "a", True),
        ("[a-c]", "b", True),
        ("[a-c]", "c", True),
        ("[a-c]", "d", False),
        ("[0-9]", "5", True),
        ("[0-9]", "a", False),
        ("[a-zA-Z]", "Q", True),
        ("[a-zA-Z]", "1", False),
        ("[a-c][a-c]", "ab", True),
        ("[a-c][a-c]", "aa", True),
        ("[a-c][a-c]", "ad", False),
        ("[a-c][a-c]", "a", False),
        ("[a-c][a-c]", "abc", False),

        # Negated classes.
        ("[!abc]", "d", True),
        ("[!abc]", "a", False),
        ("[!abc]", "b", False),
        ("[!abc]", "c", False),
        ("[!abc]", "", False),
        ("[!a-c]", "d", True),
        ("[!a-c]", "b", False),
        ("[!0-9]", "a", True),
        ("[!0-9]", "5", False),
        ("a[!b]*c", "adc", True),
        ("a[!b]*c", "abc", False),
        ("a[!b]*c", "abdc", False),

        # Literal special characters inside brackets.
        ("[*]", "*", True),
        ("[*]", "a", False),
        ("[*]", "", False),
        ("[?]", "?", True),
        ("[?]", "a", False),
        ("[[]", "[", True),
        ("[[]", "a", False),

        # ']' as first member.
        ("[]]", "]", True),
        ("[]]", "a", False),
        ("[!]]", "]", False),
        ("[!]]", "a", True),
        ("[!]]", "b", True),

        # Unterminated bracket: literal '[' followed by the rest literally.
        ("[", "[", True),
        ("[", "a", False),
        ("[abc", "[abc", True),
        ("[abc", "a", False),
        ("x[", "x[", True),
        ("x[", "xa", False),
        ("[]", "[]", True),
        ("[]", "]", False),
        ("[]", "a", False),
        ("[]", "", False),

        # Mixed and tricky combinations.
        ("[a-z]*[0-9]", "abc1", True),
        ("[a-z]*[0-9]", "abc", False),
        ("[a-z]*[0-9]", "1abc", False),
        ("[a-z]*[0-9]", "1", False),
        ("[a-z]*[0-9]", "a1", True),

        # Case sensitivity.
        ("[a-c]", "A", False),
        ("[A-C]", "a", False),
        ("[A-C]", "B", True),
        ("a", "A", False),
        ("A", "a", False),
    ]

    failures = 0
    for pattern, text, expected in cases:
        got = match(pattern, text)
        ok = got == expected
        if not ok:
            failures += 1
        print(
            "PASS" if ok else "FAIL",
            f"pattern={pattern!r} text={text!r} expected={expected} got={got}",
        )

    if failures:
        print(f"FAIL {failures} case(s) failed")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        sys.exit(_self_test())
    elif len(sys.argv) == 3:
        print(match(sys.argv[1], sys.argv[2]))
    else:
        print("usage: python3 glob_low.py --test | PATTERN TEXT", file=sys.stderr)
        sys.exit(2)
