import os
import hashlib

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
    # Dictionary to store file names and their hashes
    file_hashes = {}
    
    # Iterate over all files in the current directory
    for filename in os.listdir('.'):
        if os.path.isfile(filename):
            md5, sha256 = calculate_hashes(filename)
            file_hashes[filename] = {'MD5': md5, 'SHA256': sha256}
    
    # Print a formatted summary table
    print(f"{'Filename':<30} {'MD5':<32} {'SHA256':<64}")
    print("-" * 126)
    for filename, hashes in file_hashes.items():
        print(f"{filename:<30} {hashes['MD5']:<32} {hashes['SHA256']:<64}")

if __name__ == "__main__":
    main()