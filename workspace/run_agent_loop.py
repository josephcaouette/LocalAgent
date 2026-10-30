import os
import json
import time
import uuid
import redis
import subprocess
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer

# 1. Connect to Brain, Blackboard State, and Long-Term Vector Memory
client = OpenAI(base_url="http://localhost:8000/v1", api_key="none")
r = redis.Redis(host="192.168.254.25", port=6379, db=0)
qdrant = QdrantClient(host="192.168.254.25", port=6333)
embedder = SentenceTransformer("all-MiniLM-L6-v2")

WORKSPACE = r"Z:\workspace"
COLLECTION_NAME = "agent_solutions"

# 2. Define a fresh programming task
TASK_KEY = "workflow:task:006"
GOAL = (
    "Create a standalone Python utility that monitors directory storage health: "
    "it counts total files, calculates cumulative file sizes grouped by extension "
    "(e.g., .py, .txt, .log), and prints a sorted breakdown table using only standard libraries."
    "The script must default to analyzing the current working directory (os.getcwd()) without requiring CLI arguments or interactive input() calls."
)
TARGET_FILENAME = "storage_analyzer.py"
TARGET_PATH = os.path.join(WORKSPACE, TARGET_FILENAME)

print("=== Starting Autonomous Memory-Augmented Agent Pipeline ===")
print(f"Goal: {GOAL}\n")

def extract_code(raw_text: str) -> str:
    if "```python" in raw_text:
        return raw_text.split("```python")[1].split("```")[0].strip()
    elif "```" in raw_text:
        return raw_text.split("```")[1].split("```")[0].strip()
    return raw_text.strip()

# --- Step 0: Long-Term Memory Retrieval (RAG) ---
print("[Memory Agent] Searching Qdrant vector storage for relevant past code patterns...")
query_vec = embedder.encode(GOAL).tolist()
search_results = qdrant.query_points(
    collection_name=COLLECTION_NAME,
    query=query_vec,
    limit=2
).points

memory_context = ""
for hit in search_results:
    if hit.score > 0.30:
        print(f"--> Found past solution '{hit.payload.get('filename')}' (Similarity: {hit.score:.2f})")
        memory_context += f"\n--- Reference Pattern: {hit.payload.get('filename')} ---\n{hit.payload.get('code')}\n"

if not memory_context:
    print("--> No prior solutions met similarity threshold. Starting fresh.\n")
else:
    print("--> Retrieved relevant code patterns to guide development.\n")

# --- Step 1: Architect / Planner ---
print("[Agent 1: Planner] Designing implementation plan...")
planner_prompt = (
    "You are the System Architect.\n"
    f"Goal: {GOAL}\n\n"
    f"Past Working Patterns from Memory:\n{memory_context}\n"
    "Break down this programming objective into 3 practical implementation steps. "
    "Respond strictly in JSON format with a key 'steps' containing a list of 3 strings."
)

plan_res = client.chat.completions.create(
    model="Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
    messages=[{"role": "user", "content": planner_prompt}],
    max_tokens=400,
    temperature=0.2
)
plan_raw = plan_res.choices[0].message.content.strip()
r.hset(TASK_KEY, mapping={"goal": GOAL, "plan": plan_raw, "status": "PLANNED"})
print(f"--> Plan logged to Redis:\n{plan_raw}\n")

# --- Step 2: Engineer / Coder ---
print("[Agent 2: Engineer] Generating code using plan & memory references...")
coder_prompt = (
    "You are an expert Python Engineer.\n"
    f"Architectural Plan:\n{plan_raw}\n\n"
    f"Verified Reference Patterns from Memory:\n{memory_context}\n"
    f"Write the complete Python script to achieve: {GOAL}\n"
    "Return ONLY pure executable Python code inside standard markdown fences (```python ... ```)."
)

code_res = client.chat.completions.create(
    model="Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
    messages=[{"role": "user", "content": coder_prompt}],
    max_tokens=1400,
    temperature=0.2
)
current_code = extract_code(code_res.choices[0].message.content)

with open(TARGET_PATH, "w", encoding="utf-8") as f:
    f.write(current_code)
print(f"--> Artifact saved to {TARGET_PATH}\n")

# --- Step 3: Sandbox Execution, Self-Healing, and Auto-Ingestion ---
MAX_RETRIES = 3
attempt = 1

while attempt <= MAX_RETRIES:
    print(f"--- [Execution Attempt {attempt}/{MAX_RETRIES}] Running in Node 2 Sandbox ---")
    
    cmd = f'ssh server@192.168.254.25 "docker exec -w /workspace blackboard-sandbox python3 {TARGET_FILENAME}"'
    exec_result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    
    out_str = exec_result.stdout or ""
    err_str = exec_result.stderr or ""
    
    if exec_result.returncode == 0:
        print("[+] Execution Succeeded!")
        print(f"Sandbox Output:\n{out_str}")
        
        # --- Auto-Ingestion into Qdrant Long-Term Memory ---
        print("\n[Memory Agent] Auto-ingesting verified solution into Qdrant...")
        text_to_embed = f"{GOAL} Filename: {TARGET_FILENAME}\nPlan: {plan_raw}"
        solution_vector = embedder.encode(text_to_embed).tolist()
        point_id = str(uuid.uuid4())
        
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector=solution_vector,
                    payload={
                        "filename": TARGET_FILENAME,
                        "goal": GOAL,
                        "plan": plan_raw,
                        "code": current_code,
                        "timestamp": int(time.time()),
                        "task_key": TASK_KEY
                    }
                )
            ]
        )
        print(f"[✓] Solution indexed permanently in Qdrant (Point ID: {point_id})")
        
        # Update Redis Blackboard status
        r.hset(TASK_KEY, mapping={
            "status": "PASSED",
            "execution_output": out_str,
            "attempts": attempt,
            "memory_point_id": point_id
        })
        break
    else:
        print(f"[!] Execution Failed (Exit Code: {exec_result.returncode})")
        print(f"Traceback / Error:\n{err_str}")
        
        if attempt == MAX_RETRIES:
            print("[x] Maximum retry attempts reached. Workflow halted.")
            r.hset(TASK_KEY, mapping={"status": "FAILED", "error": err_str})
            break
            
        print("\n[Agent 2: Engineer] Analyzing sandbox failure and rewriting code...")
        debug_prompt = (
            "The following Python script was executed inside an isolated Linux Docker sandbox and failed:\n\n"
            f"```python\n{current_code}\n```\n\n"
            f"The execution produced this exact error traceback:\n{err_str}\n\n"
            "Fix the bug or missing dependency issue. Return ONLY the corrected, full Python code inside standard markdown fences (```python ... ```)."
        )

        fix_res = client.chat.completions.create(
            model="Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
            messages=[{"role": "user", "content": debug_prompt}],
            max_tokens=1400,
            temperature=0.2
        )
        current_code = extract_code(fix_res.choices[0].message.content)
        
        with open(TARGET_PATH, "w", encoding="utf-8") as f:
            f.write(current_code)
        print("--> Updated code deployed to Z:\\workspace. Retrying...\n")
        
        attempt += 1

print("=== Autonomous Workflow Complete ===")