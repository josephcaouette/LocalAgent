import os

def traverse_directory(directory):
    """Traverse the directory and collect file information."""
    file_info = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            file_extension = os.path.splitext(file)[1]
            file_size = os.path.getsize(file_path)
            file_info.append((file_extension, file_size))
    return file_info

def aggregate_file_data(file_info):
    """Aggregate the collected data by file extension."""
    extension_data = {}
    for file_extension, file_size in file_info:
        if file_extension not in extension_data:
            extension_data[file_extension] = {'total_files': 0, 'total_size': 0}
        extension_data[file_extension]['total_files'] += 1
        extension_data[file_extension]['total_size'] += file_size
    return extension_data

def print_aggregated_data(extension_data):
    """Format and print the aggregated data in a sorted table."""
    print(f"{'Extension':<10} {'Total Files':>12} {'Total Size (bytes)':>20}")
    print("-" * 42)
    for file_extension in sorted(extension_data.keys()):
        total_files = extension_data[file_extension]['total_files']
        total_size = extension_data[file_extension]['total_size']
        print(f"{file_extension:<10} {total_files:>12} {total_size:>20}")

def main():
    # Default to the current working directory
    directory = os.getcwd()
    
    # Step 1: Traverse the directory and collect file information
    file_info = traverse_directory(directory)
    
    # Step 2: Aggregate the collected data by file extension
    extension_data = aggregate_file_data(file_info)
    
    # Step 3: Print the aggregated data in a sorted table
    print_aggregated_data(extension_data)

if __name__ == "__main__":
    main()