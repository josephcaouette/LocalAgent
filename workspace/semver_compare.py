#!/usr/bin/env python3
"""semver_compare.py - Parse and compare Semantic Versioning 2.0.0 version strings."""

import argparse
import re
import sys
from functools import cmp_to_key


def parse_version(s: str):
    """
    Parse a semantic version string.
    Returns (major, minor, patch, pre_release_identifiers)
    pre_release_identifiers is a list of strings (empty list if no pre-release).
    Raises ValueError for malformed versions.
    """
    if not isinstance(s, str):
        raise ValueError(f"Version must be a string, got {type(s)}")

    s = s.strip()
    if not s:
        raise ValueError("Empty version string")

    # Strip build metadata (everything after the first '+')
    if '+' in s:
        s = s.split('+', 1)[0]

    # Split pre-release (everything after the first '-')
    pre_release = []
    if '-' in s:
        core_part, pre_part = s.split('-', 1)
        if pre_part == '':
            raise ValueError("Empty pre-release identifier")
        pre_ids = pre_part.split('.')
        for pid in pre_ids:
            if pid == '':
                raise ValueError("Empty pre-release identifier")
            # Check for leading zeros in numeric identifiers
            if pid.isdigit():
                if len(pid) > 1 and pid[0] == '0':
                    raise ValueError(f"Leading zeros in numeric pre-release identifier: {pid}")
            pre_release.append(pid)
    else:
        core_part = s

    # Validate core version: major.minor.patch
    parts = core_part.split('.')
    if len(parts) != 3:
        raise ValueError(f"Core version must have exactly 3 parts (major.minor.patch), got: {core_part}")

    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
    except ValueError:
        raise ValueError(f"Invalid numeric component in core version: {core_part}")

    # Check for leading zeros in core version components
    for i, part in enumerate(parts):
        if len(part) > 1 and part[0] == '0':
            raise ValueError(f"Leading zeros in core version component: {part}")

    return (major, minor, patch, pre_release)


def _compare_identifier(a: str, b: str) -> int:
    """
    Compare two pre-release identifiers.
    Returns -1, 0, or 1.
    """
    a_is_num = a.isdigit()
    b_is_num = b.isdigit()

    if a_is_num and b_is_num:
        # Both numeric: compare numerically
        a_val = int(a)
        b_val = int(b)
        if a_val < b_val:
            return -1
        elif a_val > b_val:
            return 1
        else:
            return 0
    elif a_is_num and not b_is_num:
        # Numeric is always lower than alphanumeric
        return -1
    elif not a_is_num and b_is_num:
        # Alphanumeric is always higher than numeric
        return 1
    else:
        # Both alphanumeric: compare in ASCII order
        if a < b:
            return -1
        elif a > b:
            return 1
        else:
            return 0


def compare(a: str, b: str) -> int:
    """
    Compare two semantic version strings.
    Returns -1 if a < b, 0 if a == b, 1 if a > b.
    """
    va = parse_version(a)
    vb = parse_version(b)

    major_a, minor_a, patch_a, pre_a = va
    major_b, minor_b, patch_b, pre_b = vb

    # Compare core version numerically
    if major_a != major_b:
        return -1 if major_a < major_b else 1
    if minor_a != minor_b:
        return -1 if minor_a < minor_b else 1
    if patch_a != patch_b:
        return -1 if patch_a < patch_b else 1

    # Core versions are equal, compare pre-release
    # A version without pre-release has higher precedence than one with pre-release
    if not pre_a and not pre_b:
        return 0
    if not pre_a and pre_b:
        return 1  # a has no pre-release, b does, so a > b
    if pre_a and not pre_b:
        return -1  # a has pre-release, b does not, so a < b

    # Both have pre-release identifiers
    # Compare left to right
    min_len = min(len(pre_a), len(pre_b))
    for i in range(min_len):
        result = _compare_identifier(pre_a[i], pre_b[i])
        if result != 0:
            return result

    # All compared identifiers are equal
    # The longer list has higher precedence
    if len(pre_a) < len(pre_b):
        return -1
    elif len(pre_a) > len(pre_b):
        return 1
    else:
        return 0


def run_tests() -> int:
    """Run acceptance tests. Returns 0 on success, 1 on failure."""
    failures = []

    # Test 1: Precedence chain from the spec
    chain = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
    ]

    chain_ok = True
    for i in range(len(chain) - 1):
        result = compare(chain[i], chain[i + 1])
        if result != -1:
            failures.append(f"Precedence chain: compare({chain[i]!r}, {chain[i+1]!r}) = {result}, expected -1")
            chain_ok = False
            break

    if chain_ok:
        print("PASS: precedence chain")
    else:
        print(f"FAIL: precedence chain")

    # Test 2: Build metadata is ignored
    build_ok = True
    result = compare("1.0.0+build", "1.0.0")
    if result != 0:
        failures.append(f"Build metadata: compare('1.0.0+build', '1.0.0') = {result}, expected 0")
        build_ok = False

    # Also check the reverse
    result2 = compare("1.0.0", "1.0.0+build")
    if result2 != 0:
        failures.append(f"Build metadata: compare('1.0.0', '1.0.0+build') = {result2}, expected 0")
        build_ok = False

    # Check with different build metadata
    result3 = compare("1.0.0+build.1", "1.0.0+build.2")
    if result3 != 0:
        failures.append(f"Build metadata: compare('1.0.0+build.1', '1.0.0+build.2') = {result3}, expected 0")
        build_ok = False

    if build_ok:
        print("PASS: build metadata ignored")
    else:
        print(f"FAIL: build metadata ignored")

    # Print all failures
    for f in failures:
        print(f"FAIL: {f}")

    if failures:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Compare and sort semantic version strings.")
    parser.add_argument("versions", nargs="*", help="Version strings to sort")
    parser.add_argument("--test", action="store_true", help="Run acceptance tests")

    args = parser.parse_args()

    if args.test:
        exit_code = run_tests()
        sys.exit(exit_code)

    if not args.versions:
        print("No versions provided. Use --test to run tests.", file=sys.stderr)
        sys.exit(1)

    try:
        sorted_versions = sorted(args.versions, key=cmp_to_key(compare))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    for v in sorted_versions:
        print(v)


if __name__ == "__main__":
    main()
