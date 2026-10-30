import os
import shutil

def get_system_metrics():
    # Step 1: Retrieve hostname and count of CPU cores
    hostname = os.uname().nodename
    cpu_cores = os.cpu_count()

    # Step 2: Get total and free disk space, converting bytes to gigabytes
    total_disk_space, used_disk_space, free_disk_space = shutil.disk_usage("/")
    total_disk_gb = total_disk_space / (1024 ** 3)
    free_disk_gb = free_disk_space / (1024 ** 3)

    # Step 3: Fetch memory usage using os and sys as psutil is not in standard library
    import sys
    import resource

    # Get memory usage in bytes
    memory_usage_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # ru_maxrss is in kilobytes on Unix
    memory_usage_mb = memory_usage_bytes / (1024 ** 2)

    # Format and print the summary
    summary = (
        f"Hostname: {hostname}\n"
        f"CPU Cores: {cpu_cores}\n"
        f"Total Disk Space: {total_disk_gb:.2f} GB\n"
        f"Free Disk Space: {free_disk_gb:.2f} GB\n"
        f"Memory Usage: {memory_usage_mb:.2f} MB"
    )
    print(summary)

if __name__ == "__main__":
    get_system_metrics()