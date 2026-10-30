import os
import socket
import fcntl
import struct

def get_network_stats_from_proc():
    stats = {}
    try:
        with open('/proc/net/dev', 'r') as file:
            lines = file.readlines()
            for line in lines[2:]:  # Skip the header lines
                parts = line.split()
                interface_name = parts[0].strip(':')
                rx_bytes = int(parts[1])
                tx_bytes = int(parts[9])
                stats[interface_name] = {'rx': rx_bytes, 'tx': tx_bytes}
    except FileNotFoundError:
        pass
    return stats

def get_network_stats_from_socket():
    stats = {}
    max_possible = 128  # arbitrary. adjust as needed
    bytes = max_possible * 32
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    names = array.array('B', b'\0' * bytes)
    outbytes = struct.unpack('iL', fcntl.ioctl(
        s.fileno(),
        0x8912,  # SIOCGIFCONF
        struct.pack('iL', bytes, names.buffer_info()[0])
    ))[0]
    namestr = names.tostring()
    for i in range(0, outbytes, 40):
        name = namestr[i:i+16].split(b'\0', 1)[0]
        stats[name.decode('utf-8')] = {'rx': 0, 'tx': 0}  # Placeholder values
        # To get actual RX/TX bytes, additional ioctls like SIOCGIFFLAGS and SIOCGIFSTATS would be needed
        # which are more complex and platform-specific.
    return stats

def format_and_print_stats(stats):
    print(f"{'Interface':<15} {'RX Bytes':>15} {'TX Bytes':>15}")
    print("-" * 45)
    for interface, data in stats.items():
        print(f"{interface:<15} {data['rx']:>15} {data['tx']:>15}")

def main():
    stats = get_network_stats_from_proc()
    if not stats:
        stats = get_network_stats_from_socket()
    format_and_print_stats(stats)

if __name__ == "__main__":
    main()