import socket
import subprocess
import time

# Define the nodes with their respective IP addresses and ports
nodes = {
    'Node 1 (Brain)': ('192.168.254.24', 8000),
    'Node 2 (Blackboard)': ('192.168.254.25', 6379),
    'Node 3 (Worker)': ('192.168.254.26', 11434),
}

def tcp_connectivity(ip, port):
    try:
        start_time = time.time()
        with socket.create_connection((ip, port), timeout=2):
            end_time = time.time()
            return True, int((end_time - start_time) * 1000)
    except Exception:
        return False, None

def icmp_connectivity(ip):
    try:
        # Run the ping command
        response = subprocess.run(
            ['ping', '-c', '1', '-W', '2', ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if response.returncode == 0:
            return True
        else:
            return False
    except Exception:
        return False

def main():
    results = []
    
    for node_name, (ip, port) in nodes.items():
        tcp_status, tcp_latency = tcp_connectivity(ip, port)
        icmp_status = icmp_connectivity(ip)
        
        tcp_status_str = 'UP' if tcp_status else 'DOWN'
        icmp_status_str = 'UP' if icmp_status else 'DOWN'
        
        results.append((node_name, ip, port, tcp_status_str, tcp_latency, icmp_status_str))
    
    # Print the results in a formatted ASCII table
    print(f"{'Node Name':<25} {'IP':<15} {'Port':<5} {'TCP Status':<10} {'TCP Latency (ms)':<15} {'ICMP Status':<10}")
    print("-" * 80)
    for result in results:
        print(f"{result[0]:<25} {result[1]:<15} {result[2]:<5} {result[3]:<10} {str(result[4]):<15} {result[5]:<10}")

if __name__ == "__main__":
    main()