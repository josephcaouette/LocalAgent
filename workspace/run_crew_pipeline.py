import os
import subprocess
import redis
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

# 1. Hardware Backends
LOCAL_LLM_URL = "http://localhost:8000/v1"
REDIS_HOST = "192.168.254.25"
QDRANT_HOST = "192.168.254.25"
WORKSPACE = r"Z:\workspace"

# Connect to Blackboard & Memory
r = redis.Redis(host=REDIS_HOST, port=6379, db=0)
qdrant = QdrantClient(host=QDRANT_HOST, port=6333)
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Configure Local Brain LLM
brain_llm = LLM(
    model="openai/Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
    base_url=LOCAL_LLM_URL,
    api_key="none",
    temperature=0.2
)

# 2. Define Custom Tools for Agents
@tool("Query Qdrant Memory")
def query_qdrant_memory(search_phrase: str) -> str:
    """Searches long-term Qdrant vector memory for past working code patterns and solutions."""
    query_vector = embedder.encode(search_phrase).tolist()
    results = qdrant.query_points(
        collection_name="agent_solutions",
        query=query_vector,
        limit=2
    ).points
    
    if not results:
        return "No similar solutions found in long-term memory."
    
    context = ""
    for hit in results:
        payload = hit.payload or {}
        context += f"\nFile: {payload.get('filename')}\nCode:\n{payload.get('code')}\n"
    return context

@tool("Remote Sandbox Runner")
def run_in_sandbox(filename: str) -> str:
    """Executes a Python script located in the shared workspace inside the isolated Node 2 Docker sandbox."""
    cmd = f'ssh server@{REDIS_HOST} "docker exec -w /workspace blackboard-sandbox python3 {filename}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    if result.returncode == 0:
        return f"SUCCESS:\n{result.stdout}"
    else:
        return f"EXECUTION_FAILED (Exit Code {result.returncode}):\n{result.stderr}"

@tool("Write Code to Blackboard")
def write_code_artifact(filename: str, code_content: str) -> str:
    """Writes or overwrites a source code file to the shared Blackboard drive Z:\workspace."""
    target_path = os.path.join(WORKSPACE, filename)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(code_content.strip())
    return f"Artifact written to {target_path}"

# 3. Create Specialized Agents
researcher = Agent(
    role="Systems Architect & Memory Specialist",
    goal="Investigate past verified patterns in Qdrant and outline a clean architecture for the given task.",
    backstory="You specialize in technical discovery, consulting long-term memory to prevent repeating past errors.",
    tools=[query_qdrant_memory],
    llm=brain_llm,
    verbose=True
)

engineer = Agent(
    role="Software Engineer & Debugger",
    goal="Write complete, zero-dependency Python utilities, save them to the Blackboard, and iterate until sandbox validation passes.",
    backstory="You write clean Python code using standard libraries. You write files to the Blackboard and run them in the sandbox to verify them.",
    tools=[write_code_artifact, run_in_sandbox],
    llm=brain_llm,
    verbose=True
)

# 4. Define Coordinated Tasks
task_objective = (
    "Create a self-contained Python utility named 'network_monitor.py' that inspects local network interfaces "
    "using '/proc/net/dev' or socket standard library modules, reports total TX and RX bytes, "
    "and prints a formatted summary table. The script must execute without requiring any external pip dependencies."
)

task_plan = Task(
    description=f"Check memory for past code patterns relating to: '{task_objective}'. Provide a concise implementation specification.",
    expected_output="An architectural plan and relevant code patterns found in memory.",
    agent=researcher
)

task_implement = Task(
    description=f"Using the architect's plan, write 'network_monitor.py' using the write_code_artifact tool, "
                f"execute it in the sandbox using run_in_sandbox, and verify the output. "
                f"If it fails, fix the code and test again until execution succeeds.",
    expected_output="A passing sandbox execution output report and confirmed deployment of network_monitor.py.",
    agent=engineer
)

# 5. Execute Crew
crew = Crew(
    agents=[researcher, engineer],
    tasks=[task_plan, task_implement],
    process=Process.sequential,
    verbose=True
)

print("\n=== Initializing Multi-Agent Crew Workflow ===")
result = crew.kickoff()
print("\n=== Crew Workflow Complete ===")
print("Final Output:\n", result)

# Log completed job to Redis
r.hset("workflow:crew:001", mapping={"status": "PASSED", "summary": str(result)})