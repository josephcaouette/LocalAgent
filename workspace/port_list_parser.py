#!/usr/bin/env python3
"""
port_list_parser.py - Parses host:port lines, validates IPv4 and port range.

Usage:
    python3 port_list_parser.py --test
    python3 port_list_parser.py <file_path>
"""

import sys


def validate_ipv4(ip_str: str) -> bool:
    """
    Validate an IPv4 address string.
    Must have exactly 4 octets, each an integer between 0 and 255.
    No leading zeros allowed (e.g., '01' is invalid, but '0' is valid).
    """
    parts = ip_str.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit():
            return False
        # Reject leading zeros for multi-digit numbers (e.g., "01" is invalid)
        if len(part) > 1 and part[0] == "0":
            return False
        value = int(part)
        if value < 0 or value > 255:
            return False
    return True


def validate_port(port_str: str) -> bool:
    """
    Validate a port string. Must be an integer between 1 and 65535.
    """
    if not port_str.isdigit():
        return False
    value = int(port_str)
    return 1 <= value <= 65535


def parse_line(line: str):
    """
    Parse a single 'host:port' line.
    Returns (entry, None) if valid, or (None, reason) if invalid.
    """
    line = line.strip()
    if not line:
        return None, "Empty line"

    # Split on the last colon to handle potential edge cases,
    # but standard host:port should have exactly one colon.
    if line.count(":") != 1:
        return None, "Malformed line (expected host:port)"

    host, port_str = line.rsplit(":", 1)
    host = host.strip()
    port_str = port_str.strip()

    # If either host or port is empty, treat as malformed
    if not host or not port_str:
        return None, "Malformed line (expected host:port)"

    if not validate_ipv4(host):
        return None, "Invalid IPv4"

    if not validate_port(port_str):
        return None, "Port out of range"

    return f"{host}:{port_str}", None


def parse_lines(lines: list) -> tuple:
    """
    Parse a list of lines.
    Returns (valid_entries, invalid_entries) where:
      valid_entries: list of strings like "192.168.1.1:80"
      invalid_entries: list of tuples (original_line, reason)
    """
    valid = []
    invalid = []
    for line in lines:
        entry, reason = parse_line(line)
        if entry is not None:
            valid.append(entry)
        else:
            invalid.append((line, reason))
    return valid, invalid


def run_test() -> int:
    """
    Run built-in test with known valid and invalid samples.
    Returns 0 on success, 1 on failure.
    """
    sample_lines = [
        # Valid entries
        "192.168.1.1:80",
        "10.0.0.1:22",
        "172.16.254.24:6379",
        "0.0.0.0:1",
        "255.255.255.255:65535",
        # Invalid entries
        "999.999.999.999:80",       # Invalid IPv4 (octets > 255)
        "192.168.1.1:99999",        # Port out of range
        "192.168.1.1:0",            # Port out of range (0 is not valid)
        "192.168.1.1:65536",        # Port out of range
        "192.168.1.1",              # Malformed (missing colon)
        "192.168.1.1:",             # Malformed (empty port)
        ":80",                      # Malformed (empty host)
        "192.168.1.1:abc",          # Port not an integer
        "192.168.1:80",             # Invalid IPv4 (only 3 octets)
        "192.168.1.1.1:80",         # Invalid IPv4 (5 octets)
        "192.168.01.1:80",          # Invalid IPv4 (leading zero)
        "abc:80",                   # Invalid IPv4 (non-numeric)
        "192.168.1.1:80:22",        # Malformed (multiple colons)
    ]

    valid, invalid = parse_lines(sample_lines)

    # Expected valid entries
    expected_valid = {
        "192.168.1.1:80",
        "10.0.0.1:22",
        "172.16.254.24:6379",
        "0.0.0.0:1",
        "255.255.255.255:65535",
    }

    # Expected invalid entries: map original line -> expected reason
    expected_invalid = {
        "999.999.999.999:80": "Invalid IPv4",
        "192.168.1.1:99999": "Port out of range",
        "192.168.1.1:0": "Port out of range",
        "192.168.1.1:65536": "Port out of range",
        "192.168.1.1": "Malformed line (expected host:port)",
        "192.168.1.1:": "Malformed line (expected host:port)",
        ":80": "Malformed line (expected host:port)",
        "192.168.1.1:abc": "Port out of range",
        "192.168.1:80": "Invalid IPv4",
        "192.168.1.1.1:80": "Invalid IPv4",
        "192.168.01.1:80": "Invalid IPv4",
        "abc:80": "Invalid IPv4",
        "192.168.1.1:80:22": "Malformed line (expected host:port)",
    }

    print("=" * 60)
    print("TEST MODE: port_list_parser.py")
    print("=" * 60)

    # Check valid entries
    print("\nValid Entries:")
    print("-" * 40)
    for entry in sorted(valid):
        print(f"  {entry}")

    if set(valid) != expected_valid:
        print("\nFAIL: Valid entries do not match expected.")
        print(f"  Expected: {sorted(expected_valid)}")
        print(f"  Got:      {sorted(valid)}")
        return 1

    # Check invalid entries
    print("\nInvalid Entries:")
    print("-" * 40)
    for line, reason in invalid:
        print(f"  {line} -> {reason}")

    # Build actual invalid dict
    actual_invalid = {}
    for line, reason in invalid:
        actual_invalid[line] = reason

    if actual_invalid != expected_invalid:
        print("\nFAIL: Invalid entries do not match expected.")
        for k in sorted(set(list(actual_invalid.keys()) + list(expected_invalid.keys()))):
            exp = expected_invalid.get(k)
            act = actual_invalid.get(k)
            if exp != act:
                print(f"  Line: {k!r}")
                print(f"    Expected reason: {exp}")
                print(f"    Actual reason:   {act}")
        return 1

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(run_test())
    elif len(sys.argv) > 1:
        file_path = sys.argv[1]
        try:
            with open(file_path, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)

        valid, invalid = parse_lines(lines)

        print("Valid Entries:")
        print("-" * 40)
        for entry in valid:
            print(f"  {entry}")

        print("\nInvalid Entries:")
        print("-" * 40)
        for line, reason in invalid:
            print(f"  {line} -> {reason}")
    else:
        print("Usage: python3 port_list_parser.py --test")
        print("       python3 port_list_parser.py <file_path>")
        sys.exit(1)


if __name__ == "__main__":
    main()
