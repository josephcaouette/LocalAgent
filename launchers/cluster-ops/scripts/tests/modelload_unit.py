"""Loading any model from the Agent Cluster window (2026-11-12): the settings it suggests for a typed
Node 1 model, Node 3's thinking switch, and config.py reading Node 3's choice from
Z:\\config\\node3_model.json. No network, no window, and the real config folder isn't touched (a
copy of config.py is loaded from a temporary folder)."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r"C:\AI\cluster_launcher")
import cluster_launcher as cl  # noqa: E402

checks = []
fast = dict(cl.PRESETS["Fast (default)"])

new, changes = cl.suggest_vllm(fast, "RedHatAI/Qwen3.8-27B-INT4")
checks.append(("the Qwen3.8 preset model keeps every setting", new == fast and changes == []))
new, changes = cl.suggest_vllm(fast, "Qwen/Qwen3-14B-AWQ", max_ctx=40960)
checks.append(("Qwen3 (no MTP heads, no vision): MTP and text-only off, qwen3 parser kept",
               not new["mtp"] and not new["text_only"] and new["reasoning_parser"] == "qwen3"
               and new["ctx"] == fast["ctx"] and len(changes) == 2))
new, changes = cl.suggest_vllm(fast, "meta-llama/Llama-3.1-8B-Instruct", max_ctx=8192)
checks.append(("another family: no parser, and the context capped at the model's limit",
               new["reasoning_parser"] == "" and new["ctx"] == 8192 and new["model"].startswith("meta-llama")
               and any("context length" in c for c in changes)))
checks.append(("R1 distills and QwQ get the deepseek_r1 parser",
               cl.reasoning_parser_for("deepseek-ai/DeepSeek-R1-Distill-Qwen-14B") == "deepseek_r1"
               and cl.reasoning_parser_for("Qwen/QwQ-32B-AWQ") == "deepseek_r1"))
checks.append(("suggestions start from the form, not the preset (GPU memory, parallel requests kept)",
               cl.suggest_vllm(dict(fast, gpu_util=0.88, max_seqs=4), "x/y")[0]["gpu_util"] == 0.88))
checks.append(("Node 3: thinking is sent only to models that can think",
               cl.node3_think(["completion", "thinking"], False) is False
               and cl.node3_think(["completion", "thinking"], True) is True
               and cl.node3_think(["completion", "tools"], True) is None))
checks.append(("Ollama names: tags and hf.co paths pass, shell symbols don't",
               cl.valid_ollama_name("qwen3.5:9b") and cl.valid_ollama_name("hf.co/bartowski/x-GGUF:Q4_K_M")
               and not cl.valid_ollama_name("qwen; rm -rf ~") and not cl.valid_ollama_name("")))
checks.append(("the recent list puts the newest first, without repeats",
               cl.add_recent(["a", "b", "c"], "b") == ["b", "a", "c"]
               and len(cl.add_recent([str(i) for i in range(20)], "x")) == cl.RECENT_MAX))
checks.append(("ollama.com manifests: dotted names, default tag and user models; none for hf.co",
               cl.ollama_manifest_path("llama3.1:8b") == "library/llama3.1/manifests/8b"
               and cl.ollama_manifest_path("qwen3.5") == "library/qwen3.5/manifests/latest"
               and cl.ollama_manifest_path("someone/model:q4") == "someone/model/manifests/q4"
               and cl.ollama_manifest_path("hf.co/owner/repo:Q4_K_M") is None
               and cl.ollama_registry_gb("hf.co/owner/repo:Q4_K_M") is None))


def load_config(choice):
    """config.py from a temporary copy, with node3_model.json beside it (or none)."""
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "workspace"))
    os.makedirs(os.path.join(tmp, "config"))
    shutil.copy(r"Z:\workspace\config.py", os.path.join(tmp, "workspace", "config.py"))
    if choice is not None:
        with open(os.path.join(tmp, "config", "node3_model.json"), "w", encoding="utf-8") as f:
            f.write(choice if isinstance(choice, str) else json.dumps(choice))
    spec = importlib.util.spec_from_file_location("config_copy", os.path.join(tmp, "workspace", "config.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    shutil.rmtree(tmp, ignore_errors=True)
    return mod


c = load_config(None)
checks.append(("no saved choice: qwen3.5:9b, thinking off, 8192 context, Ollama picks the GPU layers",
               (c.WORKER_MODEL, c.WORKER_THINK, c.OLLAMA_NUM_CTX, c.OLLAMA_NUM_GPU) == ("qwen3.5:9b", False, 8192, None)
               and c.ollama_options(temperature=0.1) == {"num_ctx": 8192, "temperature": 0.1}))
c = load_config({"model": "qwen2.5-coder:7b", "think": None, "num_ctx": 16384, "num_gpu": 20})
checks.append(("a saved choice is read, and every request sends its context and GPU layers",
               (c.WORKER_MODEL, c.WORKER_THINK, c.OLLAMA_NUM_CTX) == ("qwen2.5-coder:7b", None, 16384)
               and c.ollama_options(num_predict=5) == {"num_ctx": 16384, "num_gpu": 20, "num_predict": 5}))
c = load_config("{not json")
checks.append(("a broken file falls back to the defaults", c.WORKER_MODEL == "qwen3.5:9b" and c.OLLAMA_NUM_CTX == 8192))
c = load_config({"model": "m", "think": "yes"})
checks.append(("a think value that isn't true, false or null counts as false", c.WORKER_THINK is False))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
