import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

# 1. Connect to Node 2 Qdrant
QDRANT_HOST = "192.168.254.25"
client = QdrantClient(host=QDRANT_HOST, port=6333)
COLLECTION_NAME = "agent_solutions"

# 2. Local fast embedding model (384 dimensions, runs lightweight on CPU/RAM)
print("[*] Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")

# 3. Create collection if it doesn't exist
collections = [c.name for c in client.get_collections().collections]
if COLLECTION_NAME not in collections:
    print(f"[*] Creating Qdrant collection: {COLLECTION_NAME}")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )
else:
    print(f"[*] Found existing collection: {COLLECTION_NAME}")

# 4. Ingest verified artifacts from Z:\workspace
WORKSPACE = r"Z:\workspace"
artifacts = [
    {
        "id": 1,
        "filename": "file_hasher.py",
        "description": "Calculate MD5 and SHA256 checksum hashes for files in a folder and print a table.",
        "tags": ["hashing", "md5", "sha256", "table", "standard_library"]
    },
    {
        "id": 2,
        "filename": "sys_audit.py",
        "description": "Audit system CPU cores, hostname, disk space using shutil.disk_usage unpacking (total, used, free), and memory without pip packages.",
        "tags": ["hardware", "audit", "disk_usage", "shutil", "proc_meminfo"]
    },
    {
        "id": 3,
        "filename": "combined_tool.py",
        "description": "Scans folder for Python files, computes total disk usage, and prints MD5 and SHA256 checksums in a formatted table using only the standard library.",
        "tags": ["hashing", "disk_usage", "os_walk", "hashlib", "table_formatting"]
    }
]

points = []
for item in artifacts:
    file_path = os.path.join(WORKSPACE, item["filename"])
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            code_content = f.read()
        
        # Combine description and tags for rich semantic retrieval
        text_to_embed = f"{item['description']} Tags: {', '.join(item['tags'])}"
        vector = model.encode(text_to_embed).tolist()
        
        points.append(
            PointStruct(
                id=item["id"],
                vector=vector,
                payload={
                    "filename": item["filename"],
                    "description": item["description"],
                    "code": code_content,
                    "tags": item["tags"]
                }
            )
        )
        print(f"[+] Prepared vector point for: {item['filename']}")

if points:
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"\n[✓] Successfully stored {len(points)} verified solutions in Qdrant long-term memory!")
else:
    print("[!] No artifact files found to ingest.")