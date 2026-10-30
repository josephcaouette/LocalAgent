import sys
import socket
import time
import datetime


def check_tcp(ip: str, port: int, timeout: float = 2.0) -> tuple[bool, float]:
    """
    Attempt a TCP connection to ip:port with the given timeout.
    Returns (is_up, latency_ms).
    """
    start = time.perf_counter()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((ip, port))
        end = time.perf_counter()
        latency_ms = (end - start) * 1000.0
        return True, latency_ms
    except (socket.timeout, ConnectionRefusedError, OSError):
        end = time.perf_counter()
        latency_ms = (end - start) * 1000.0
        return False, latency_ms


def main():
    targets = [
        # (node, address, port, service, informational)
        ("Node 1", "192.168.254.24", 445, "SMB", True),
        ("Node 1", "192.168.254.24", 3389, "RDP", True),
        ("Node 2", "192.168.254.25", 22, "SSH", False),
        ("Node 2", "192.168.254.25", 6379, "Redis", False),
        ("Node 2", "192.168.254.25", 6333, "Qdrant", False),
        ("Node 2", "192.168.254.25", 8080, "Dashboard", False),
        ("Node 3", "192.168.254.26", 22, "SSH", False),
        ("Node 3", "192.168.254.26", 11434, "Ollama", False),
    ]

    results = []
    for node, addr, port, service, informational in targets:
        is_up, latency_ms = check_tcp(addr, port, timeout=2.0)
        status = "UP" if is_up else "DOWN"
        results.append({
            "node": node,
            "address": addr,
            "port": port,
            "service": service,
            "status": status,
            "latency_ms": latency_ms,
            "informational": informational,
        })

    # Print header
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Cluster Connectivity Table as of {timestamp}")
    print("-" * 70)

    # Print table header
    header = f"{'Node':<10} {'Address':<18} {'Port':<6} {'Service':<12} {'Status':<8} {'Latency'}"
    print(header)
    print("-" * 70)

    # Print rows
    for r in results:
        latency_str = f"{r['latency_ms']:.1f} ms"
        print(
            f"{r['node']:<10} {r['address']:<18} {r['port']:<6} "
            f"{r['service']:<12} {r['status']:<8} {latency_str}"
        )

    # Determine overall status for non-informational nodes
    critical_down = [r for r in results if not r["informational"] and r["status"] == "DOWN"]
    if critical_down:
        summary = f"Cluster status: DEGRADED - {len(critical_down)} critical service(s) DOWN"
        exit_code = 1
    else:
        summary = "Cluster status: HEALTHY - all critical services UP"
        exit_code = 0

    print("-" * 70)
    print(summary)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
