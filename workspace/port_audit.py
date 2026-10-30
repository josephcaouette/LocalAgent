#!/usr/bin/env python3
"""
port_audit.py - Reads host:port:service lines from a file and audits them.

Usage:
    python3 port_audit.py --test
    python3 port_audit.py <file_path>
"""

import re
import sys


def parse_line(line: str):
    """
    Parse a single 'host:port:service' line.
    Returns (is_valid, reason) where reason is None if valid.
    """
    line = line.strip()
    if not line:
        return False, "Empty line"

    parts = line.split(":")
    if len(parts) != 3:
        return False, "Missing service field" if len(parts) == 2 else "Invalid field count"

    host, port_str, service = parts[0].strip(), parts[1].strip(), parts[2].strip()

    if not host:
        return False, "Missing host field"

    # Validate host: allow IPv4 or hostname
    ipv4_pattern = re.compile(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$')
    hostname_pattern = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$')

    if ipv4_pattern.match(host):
        octets = host.split(".")
        for octet in octets:
            if int(octet) > 255:
                return False, "Invalid host"
    elif not hostname_pattern.match(host):
        return False, "Invalid host"

    if not port_str.isdigit():
        return False, "Invalid port"

    port = int(port_str)
    if port < 1 or port > 65535:
        return False, "Invalid port"

    if not service:
        return False, "Missing service field"

    return True, None


def run_test_mode() -> int:
    """
    Run built-in test with known valid and invalid samples.
    Returns 0 on success, 1 on failure.
    """
    sample_lines = [
        # Valid entries
        "192.168.1.1:80:web",
        "10.0.0.1:22:ssh",
        "myhost.local:6379:redis",
        "255.255.255.255:65535:svc",
        # Invalid entries
        "192.168.1.1:80",                # Missing service field
        "192.168.1.1:99999:db",          # Invalid port
        ":80:web",                        # Missing host field
        "192.168.1.1:abc:web",           # Invalid port
        "192.168.1.1:80:",               # Missing service field
        "999.999.999.999:80:web",        # Invalid host
        "192.168.1.1:80:web:extra",      # Invalid field count
    ]

    expected_valid = {
        "192.168.1.1:80:web",
        "10.0.0.1:22:ssh",
        "myhost.local:6379:redis",
        "255.255.255.255:65535:svc",
    }

    expected_invalid = {
        "192.168.1.1:80": "Missing service field",
        "192.168.1.1:99999:db": "Invalid port",
        ":80:web": "Missing host field",
        "192.168.1.1:abc:web": "Invalid port",
        "192.168.1.1:80:": "Missing service field",
        "999.999.999.999:80:web": "Invalid host",
        "192.168.1.1:80:web:extra": "Invalid field count",
    }

    print("=" * 60)
    print("TEST MODE: port_audit.py")
    print("=" * 60)

    valid_entries = []
    invalid_entries = []

    for line in sample_lines:
        is_valid, reason = parse_line(line)
        if is_valid:
            valid_entries.append(line)
            print(f"  {line} -> Well-formed")
        else:
            invalid_entries.append((line, reason))
            print(f"  {line} -> Bad: {reason}")

    # Verify valid entries
    if set(valid_entries) != expected_valid:
        print("\nFAIL: Valid entries do not match expected.")
        print(f"  Expected: {sorted(expected_valid)}")
        print(f"  Got:      {sorted(valid_entries)}")
        return 1

    # Verify invalid entries
    actual_invalid = {line: reason for line, reason in invalid_entries}
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
        sys.exit(run_test_mode())
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

        print("Port Audit Report")
        print("-" * 40)
        for line in lines:
            is_valid, reason = parse_line(line)
            if is_valid:
                print(f"  {line.strip()} -> Well-formed")
            else:
                print(f"  {line.strip()} -> Bad: {reason}")
    else:
        print("Usage: python3 port_audit.py --test")
        print("       python3 port_audit.py <file_path>")
        sys.exit(1)


if __name__ == "__main__":
    main()
