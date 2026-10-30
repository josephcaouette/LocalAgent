import os
import json
import redis
from openai import OpenAI

# 1. Connect to Brain & Blackboard
client = OpenAI(base_url="http://localhost:8000/v1", api_key="none")
r = redis.Redis(host="192.168.254.25", port=6379, db=0)
WORKSPACE = r"Z:\workspace"

# Define the task
TASK_KEY = "workflow:task:001"
GOAL = "Create a self-contained Python utility that calculates system file hash signatures (MD5 and SHA256) for any file in the current folder, and prints a formatted summary table."

print(f"=== Starting Multi-Agent Task Loop ===")
print(f"Goal: {GOAL}\n")

# --- Agent 1: The Architect / Planner ---
print("[Agent 1: Planner] Formulating step-by-step architecture...")
planner_prompt = f"""
You are the System Architect.
Break down this programming objective into 3 distinct, practical implementation steps:
{GOAL}
Respond strictly in JSON format with a key 'steps' containing a list of 3 strings.
"""

planner_res = client.chat.completions.create(
    model="Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
    messages=[{"role": "user", "content": planner_prompt}],
    max_tokens=400,
    temperature=0.2
)
plan_raw = planner_res.choices[0].message.content.strip()

# Record plan to Redis Blackboard
r.hset(TASK_KEY, mapping={
    "goal": GOAL,
    "plan": plan_raw,
    "status": "PLANNED"
})
print(f"--> Architecture Plan logged to Redis:\n{plan_raw}\n")

# --- Agent 2: The Engineer / Coder ---
print("[Agent 2: Engineer] Writing executable code based on the plan...")
coder_prompt = f"""
You are an expert Python Engineer.
Follow this architectural plan:
{plan_raw}

Write the complete, production-grade Python script to fulfill the goal: {GOAL}
Return ONLY pure executable Python code inside standard markdown code fences (```python ... ```).
"""

coder_res = client.chat.completions.create(
    model="Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
    messages=[{"role": "user", "content": coder_prompt}],
    max_tokens=1200,
    temperature=0.2
)
coder_output = coder_res.choices[0].message.content.strip()

# Extract code block cleanly
if "```python" in coder_output:
    code = coder_output.split("```python")[1].split("```")[0].strip()
elif "```" in coder_output:
    code = coder_output.split("```")[1].split("```")[0].strip()
else:
    code = coder_output

# Write artifact across LAN to shared workspace
target_script = os.path.join(WORKSPACE, "file_hasher.py")
with open(target_script, "w", encoding="utf-8") as f:
    f.write(code)

r.hset(TASK_KEY, mapping={
    "status": "CODE_WRITTEN",
    "artifact_path": target_script
})
print(f"--> Script saved to Blackboard storage: {target_script}\n")

# --- Agent 3: QA Reviewer ---
print("[Agent 3: QA Auditor] Reviewing generated script for syntax, logic, and safety...")
auditor_prompt = f"""
You are a senior Code Reviewer.
Inspect this script for correctness and security:
{code}

Provide:
1. Verdict (APPROVED / REJECTED)
2. A 2-sentence rationale.
"""

auditor_res = client.chat.completions.create(
    model="Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
    messages=[{"role": "user", "content": auditor_prompt}],
    max_tokens=250,
    temperature=0.1
)
audit_review = auditor_res.choices[0].message.content.strip()

r.hset(TASK_KEY, mapping={
    "status": "COMPLETED",
    "qa_review": audit_review
})
print(f"--> QA Decision:\n{audit_review}\n")

print("=== Multi-Agent Loop Successfully Finished ===")