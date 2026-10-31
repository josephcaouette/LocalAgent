import sys


def to_roman(n):
    """Convert an integer (1-3999) to a Roman numeral string using standard subtractive notation."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError(f"Expected an integer, got {type(n).__name__}")
    if n < 1 or n > 3999:
        raise ValueError(f"Value {n} out of range (1-3999)")

    table = [
        (1000, 'M'),
        (900, 'CM'),
        (500, 'D'),
        (400, 'CD'),
        (100, 'C'),
        (90, 'XC'),
        (50, 'L'),
        (40, 'XL'),
        (10, 'X'),
        (9, 'IX'),
        (5, 'V'),
        (4, 'IV'),
        (1, 'I'),
    ]

    result = []
    for value, numeral in table:
        while n >= value:
            result.append(numeral)
            n -= value
    return ''.join(result)


def from_roman(s):
    """Convert a Roman numeral string to an integer (1-3999). Raises ValueError for invalid input."""
    if not isinstance(s, str):
        raise ValueError(f"Expected a string, got {type(s).__name__}")
    if len(s) == 0:
        raise ValueError("Empty string is not a valid Roman numeral")

    s_upper = s.upper()

    valid_chars = set('IVXLCDM')
    for ch in s_upper:
        if ch not in valid_chars:
            raise ValueError(f"Invalid character '{ch}' in Roman numeral")

    # Map each character to its value
    values = {
        'I': 1,
        'V': 5,
        'X': 10,
        'L': 50,
        'C': 100,
        'D': 500,
        'M': 1000,
    }

    # Compute numeric value using right-to-left scan with subtractive logic
    total = 0
    prev = 0
    for ch in reversed(s_upper):
        val = values[ch]
        if val < prev:
            total -= val
        else:
            total += val
        prev = val

    if total < 1 or total > 3999:
        raise ValueError(f"Value {total} out of range (1-3999)")

    # Reject non-canonical forms
    if to_roman(total) != s_upper:
        raise ValueError(f"Non-canonical Roman numeral: '{s}'")

    return total


def run_tests():
    """Run all acceptance checks and print results."""
    failures = []

    # Check 1: Known pairs (at least 10, including 4, 9, 14, 40, 90, 400, 1994, 2024, 3999)
    known_pairs = [
        (1, 'I'),
        (4, 'IV'),
        (9, 'IX'),
        (14, 'XIV'),
        (40, 'XL'),
        (90, 'XC'),
        (400, 'CD'),
        (1994, 'MCMXCIV'),
        (2024, 'MMXXIV'),
        (3999, 'MMMCMXCIX'),
    ]

    pair_passed = 0
    for n, expected in known_pairs:
        actual = to_roman(n)
        if actual == expected:
            pair_passed += 1
        else:
            failures.append(f"Known pair failed: to_roman({n}) = '{actual}', expected '{expected}'")

    print(f"known pairs: {pair_passed}/{len(known_pairs)} passed")

    # Check 2: Round-trip for every n from 1 to 3999
    roundtrip_passed = 0
    for n in range(1, 4000):
        roman = to_roman(n)
        back = from_roman(roman)
        if back == n:
            roundtrip_passed += 1
        else:
            failures.append(f"Round-trip failed: from_roman(to_roman({n})) = {back}, expected {n}")

    print(f"round-trip: {roundtrip_passed}/3999 passed")

    # Check 3: Invalid inputs raise ValueError
    invalid_inputs = [
        ("to_roman(0)", lambda: to_roman(0)),
        ("to_roman(4000)", lambda: to_roman(4000)),
        ("from_roman('IIII')", lambda: from_roman('IIII')),
        ("from_roman('VX')", lambda: from_roman('VX')),
        ("from_roman('')", lambda: from_roman('')),
    ]

    invalid_passed = 0
    for desc, func in invalid_inputs:
        try:
            func()
            failures.append(f"Invalid input did not raise ValueError: {desc}")
        except ValueError:
            invalid_passed += 1
        except Exception as e:
            failures.append(f"Invalid input raised wrong exception type: {desc} -> {type(e).__name__}: {e}")

    print(f"invalid inputs: {invalid_passed}/{len(invalid_inputs)} raised ValueError")

    # Summary
    total_checks = len(known_pairs) + 3999 + len(invalid_inputs)
    total_passed = pair_passed + roundtrip_passed + invalid_passed

    if not failures:
        print("RESULT: PASS")
        return 0
    else:
        print("RESULT: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1


def main():
    if '--test' in sys.argv:
        exit_code = run_tests()
        sys.exit(exit_code)
    else:
        print("Usage: python3 roman_numerals.py --test")
        sys.exit(1)


if __name__ == '__main__':
    main()
