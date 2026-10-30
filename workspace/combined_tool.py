import os
import hashlib

def find_py_files(directory):
    """Find all .py files in the specified directory."""
    py_files = []
    for filename in os.listdir(directory):
        if filename.endswith('.py'):
            py_files.append(os.path.join(directory, filename))
    return py_files

def calculate_disk_usage(py_files):
    """Calculate disk usage statistics for the list of .py files."""
    total_size = 0
    for file_path in py_files:
        total_size += os.path.getsize(file_path)
    return total_size

def calculate_hashes(file_path):
    """Calculate MD5 and SHA256 hashes of a given file."""
    md5_hash = hashlib.md5()
    sha256_hash = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        # Read the file in chunks to avoid memory issues with large files
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
            sha256_hash.update(byte_block)
    
    return md5_hash.hexdigest(), sha256_hash.hexdigest()

def main():
    # Step 1: Find all .py files in the current directory
    py_files = find_py_files('.')
    
    # Step 2: Calculate disk usage statistics for the .py files
    total_size = calculate_disk_usage(py_files)
    print(f"Total disk usage for .py files: {total_size} bytes")
    
    # Step 3: Calculate and display MD5 and SHA256 hash signatures for each .py file
    print(f"{'Filename':<30} {'MD5':<32} {'SHA256':<64}")
    print("-" * 126)
    for file_path in py_files:
        md5, sha256 = calculate_hashes(file_path)
        print(f"{os.path.basename(file_path):<30} {md5:<32} {sha256:<64}")

if __name__ == "__main__":
    main()