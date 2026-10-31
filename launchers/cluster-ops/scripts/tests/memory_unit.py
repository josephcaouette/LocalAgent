"""Verified lessons and the Node 3 relevance check on memory (live Qdrant + Node 3; lessons faked)."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

state = {"spec": "Rules...\n\nCORRECTION (checked by running code before coding started; overrides any example "
                 "above): ex1: fifth run is 2024-02-01 00:00",
         "regression": [{"name": "review 1.1: next_runs crashes for start years near 9999", "code": "..."},
                        {"name": "mutation 3: line 40: `<` -> `<=`", "code": "..."},
                        {"name": "review 2.1: next_runs crashes for start years near 9999", "code": "..."}]}
for x in p.verified_lessons(state):
    print("LESSON:", x[:150])
print()
p.NO_MEMORY = False
for goal in ["Update primes_report.py so it also prints the sum of the primes",
             "Write a bowling score calculator for ten-pin games",
             "Check that the cluster's services answer: Redis, Qdrant and Ollama"]:
    out = p.memory_retriever_node({"goal": goal})
    print("GOAL:", goal[:60], "| examples kept:", out["memory_summary"].count("\n- ") + bool(out["memory_summary"]))
