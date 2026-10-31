import sys


def wrap(text, width):
    """
    Wrap text to lines of at most `width` characters.
    Breaks at spaces when possible; splits words longer than `width`.
    """
    if width <= 0:
        raise ValueError("width must be positive")

    # Normalize whitespace: split on any whitespace, rejoin with single spaces
    words = text.split()
    if not words:
        return []

    lines = []
    current_line = []
    current_len = 0

    for word in words:
        # If the word is longer than width, we need to split it
        if len(word) > width:
            # First, flush the current line if it has content
            if current_line:
                lines.append(' '.join(current_line))
                current_line = []
                current_len = 0

            # Split the long word into chunks of `width`
            for i in range(0, len(word), width):
                chunk = word[i:i + width]
                lines.append(chunk)
            continue

        # Word fits within width
        if current_len == 0:
            current_line.append(word)
            current_len = len(word)
        else:
            # Check if adding this word (with a space) fits
            if current_len + 1 + len(word) <= width:
                current_line.append(word)
                current_len += 1 + len(word)
            else:
                # Flush current line
                lines.append(' '.join(current_line))
                current_line = [word]
                current_len = len(word)

    # Don't forget the last line
    if current_line:
        lines.append(' '.join(current_line))

    return lines


def run_tests():
    """
    Run built-in tests. Returns True if all pass, False otherwise.
    """
    all_passed = True

    # Test 1: Normal space wrapping
    text1 = "The quick brown fox jumps over the lazy dog"
    width1 = 15
    result1 = wrap(text1, width1)
    expected_lines1 = [
        "The quick",
        "brown fox",
        "jumps over",
        "the lazy dog"
    ]
    # Verify all lines are within width
    for line in result1:
        if len(line) > width1:
            print(f"FAIL: normal wrapping - line '{line}' exceeds width {width1}")
            all_passed = False
            break
    else:
        # Verify content is preserved (no lost characters)
        reconstructed = ' '.join(result1)
        if reconstructed != text1:
            print(f"FAIL: normal wrapping - content mismatch")
            print(f"  Expected: {text1}")
            print(f"  Got:      {reconstructed}")
            all_passed = False
        else:
            print(f"PASS: normal wrapping - lines within width, content preserved")

    # Test 2: Long word splitting
    text2 = "hello world"
    width2 = 5
    result2 = wrap(text2, width2)
    # "hello" is 5 chars, fits. "world" is 5 chars, fits.
    # But let's use a truly long word
    text2b = "a" * 10 + " " + "b" * 3
    width2b = 4
    result2b = wrap(text2b, width2b)
    # "aaaaaaaaaa" should be split into "aaaa", "aaaa", "aa"
    # "bbb" should be on its own line
    expected2b = ["aaaa", "aaaa", "aa", "bbb"]
    for line in result2b:
        if len(line) > width2b:
            print(f"FAIL: long word - line '{line}' exceeds width {width2b}")
            all_passed = False
            break
    else:
        # Verify no characters lost
        reconstructed2b = ''.join(result2b)
        original_no_spaces = text2b.replace(' ', '')
        if reconstructed2b != original_no_spaces:
            print(f"FAIL: long word - content mismatch")
            print(f"  Expected: {original_no_spaces}")
            print(f"  Got:      {reconstructed2b}")
            all_passed = False
        else:
            print(f"PASS: long word - split correctly, no characters lost")

    # Test 3: Width 1
    text3 = "ab cd"
    width3 = 1
    result3 = wrap(text3, width3)
    for line in result3:
        if len(line) > width3:
            print(f"FAIL: width 1 - line '{line}' exceeds width {width3}")
            all_passed = False
            break
    else:
        reconstructed3 = ''.join(result3)
        original3_no_spaces = text3.replace(' ', '')
        if reconstructed3 != original3_no_spaces:
            print(f"FAIL: width 1 - content mismatch")
            print(f"  Expected: {original3_no_spaces}")
            print(f"  Got:      {reconstructed3}")
            all_passed = False
        else:
            print(f"PASS: width 1 - each char on its own line, content preserved")

    # Test 4: Empty input
    text4 = ""
    width4 = 10
    result4 = wrap(text4, width4)
    if result4 == []:
        print(f"PASS: empty input - returns empty list")
    else:
        print(f"FAIL: empty input - expected [], got {result4}")
        all_passed = False

    # Test 5: Short input (fits in one line)
    text5 = "hi"
    width5 = 10
    result5 = wrap(text5, width5)
    if result5 == ["hi"]:
        print(f"PASS: short input - single line as expected")
    else:
        print(f"FAIL: short input - expected ['hi'], got {result5}")
        all_passed = False

    return all_passed


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        success = run_tests()
        if success:
            print("ALL TESTS PASSED")
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        if len(sys.argv) < 2:
            print("Usage: python word_wrap.py WIDTH", file=sys.stderr)
            sys.exit(1)
        try:
            width = int(sys.argv[1])
        except ValueError:
            print(f"Error: WIDTH must be an integer, got '{sys.argv[1]}'", file=sys.stderr)
            sys.exit(1)
        if width <= 0:
            print("Error: WIDTH must be positive", file=sys.stderr)
            sys.exit(1)
        text = sys.stdin.read()
        lines = wrap(text, width)
        for line in lines:
            print(line)


if __name__ == "__main__":
    main()
