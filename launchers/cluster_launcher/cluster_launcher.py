"""Agent Cluster: one window for the whole cluster.

  Status strip  live health of every node and service (every 5 s), the run queue and Dispatch Run
  Chat          talk with the models; "Talk about result" explains finished runs   } from
  Task & Queue  the task form, accuracy level, attachments, queue and per-run logs   } Z:\\workspace\\
  Runs          every recorded run with details and actions                          } agent_gui.py
  Model server  vLLM settings, presets, free-VRAM check, start / stop / restart, live log
  Cluster       Z: drive, pipeline reset, Node 2 / Node 3 restarts, backup, links, status details
  Activity      what the window did (bottom)

It lives on Node 1 (C:\\AI\\cluster_launcher), so it opens even when Z: isn't connected: the three
agent tabs then show a Connect Z: button and load as soon as Z: is there. vLLM runs without a
window of its own (its log is on the Model server tab) and keeps running when this window
closes. Settings are saved next to this file in launcher_settings.json. The old .bat files and
agent_gui.py on its own still work as fallbacks.
"""
import copy
import glob
import importlib
import json
import os
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "launcher_settings.json")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
GUI_PID_FILE = os.path.join(tempfile.gettempdir(), "agent_gui.pid")      # this window (Reset_Cluster.bat)
PIPELINE_PID_GLOB = os.path.join(tempfile.gettempdir(), "agent_pipeline*.pid")   # one per run
LLM_URL = "http://127.0.0.1:8001"     # not "localhost": Windows tries IPv6 first (2 s delay)

PRESETS = {
    # Measured on this 4090 (WSL leaves 22.45 of 23.99 GiB free): at 16k, 0.91 holds 3.35 full
    # requests at once and 0.93 holds 3.8 but leaves only 0.14 GiB spare at startup. 20k needs
    # ~2.2 GiB more working memory, so it fits only ~1.5 requests: not worth it with best-of-N.
    "Fast (default)": {
        "model": "RedHatAI/Qwen3.8-27B-INT4", "ctx": 16384, "gpu_util": 0.92, "max_seqs": 8,
        "kv_dtype": "fp8", "attention": "TRITON_ATTN", "mtp": True, "mtp_tokens": 2,
        "cuda_graphs": True, "prefix_caching": False, "text_only": True,
        "reasoning_parser": "qwen3", "extra": ""},
    "Long context (32k, about half speed)": {
        "model": "RedHatAI/Qwen3.8-27B-INT4", "ctx": 32768, "gpu_util": 0.90, "max_seqs": 8,
        "kv_dtype": "fp8", "attention": "TRITON_ATTN", "mtp": False, "mtp_tokens": 2,
        "cuda_graphs": True, "prefix_caching": True, "text_only": True,
        "reasoning_parser": "qwen3", "extra": ""},
    "Old model (Qwen2.5-Coder-32B)": {
        "model": "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ", "ctx": 12288, "gpu_util": 0.90,
        "max_seqs": 8, "kv_dtype": "fp8", "attention": "TRITON_ATTN", "mtp": False,
        "mtp_tokens": 2, "cuda_graphs": True, "prefix_caching": True, "text_only": False,
        "reasoning_parser": "", "extra": ""},
}
DEFAULTS = {
    "node2_ip": "192.168.254.25", "node3_ip": "192.168.254.26", "ssh_user": "server",
    "drive": "Z:", "share": r"\\192.168.254.25\blackboard", "venv": r"C:\AI\venvs\agent_brain",
    "github": "https://github.com/josephcaouette/LocalAgent",
    "worker_model": "qwen3.5:9b", "embed_model": "qwen3-embedding:0.6b", "ollama_num_ctx": 8192,
    "preset": "Fast (default)", "vllm": copy.deepcopy(PRESETS["Fast (default)"]),
}
KNOWN_MODELS = ["RedHatAI/Qwen3.8-27B-INT4", "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"]
LONG_PRESET = "Long context (32k, about half speed)"   # what Ultra and MAX runs switch to

BG, PANEL, FIELD, TEXT, MUTED = "#1e1e1e", "#2d2d2d", "#252526", "#d4d4d4", "#8a8a8a"
GREEN, RED, ORANGE, GREY = "#4CAF50", "#e05252", "#f0ad4e", "#777777"

# vLLM log lines not worth showing (the status checks hit /v1/models every few seconds).
LOG_NOISE = re.compile(r'"(GET /v1/models|POST /tokenize|GET /health|GET /metrics)')


# --------------------------------------------------------------------------- settings and commands

def load_settings():
    s = copy.deepcopy(DEFAULTS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        s.update({k: v for k, v in saved.items() if k != "vllm"})
        s["vllm"].update(saved.get("vllm", {}))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


def fmt_util(x):
    return ("%.3f" % x).rstrip("0").rstrip(".")


def validate_vllm(v):
    if not re.fullmatch(r"[\w.\-/]+", v["model"]):
        return "The model name can only contain letters, digits, '.', '-', '_' and '/'."
    if not 1024 <= v["ctx"] <= 262144:
        return "Context length must be between 1024 and 262144."
    if not 0.5 <= v["gpu_util"] <= 0.95:
        return "GPU memory must be between 0.50 and 0.95."
    if not 1 <= v["max_seqs"] <= 64:
        return "Parallel requests must be between 1 and 64."
    if re.search(r"[\"'`$;&|<>\\]", v["extra"] + v["reasoning_parser"]):
        return "Extra arguments can't contain quotes or shell symbols ( \" ' ` $ ; & | < > \\ )."
    return ""


def vllm_args(v):
    args = ["vllm", "serve", v["model"], "--host", "0.0.0.0", "--port", "8001",
            "--max-model-len", str(v["ctx"]), "--gpu-memory-utilization", fmt_util(v["gpu_util"]),
            "--max-num-seqs", str(v["max_seqs"])]
    if v["kv_dtype"] != "auto":
        args += ["--kv-cache-dtype", v["kv_dtype"]]
    if v["attention"] != "auto":
        args += ["--attention-backend", v["attention"]]
    if v["text_only"]:
        args.append("--language-model-only")
    if v["reasoning_parser"]:
        args += ["--reasoning-parser", v["reasoning_parser"]]
    if not v["prefix_caching"]:
        args.append("--no-enable-prefix-caching")
    if v["mtp"]:
        args += ["--speculative-config.method", "mtp",
                 "--speculative-config.num_speculative_tokens", str(v["mtp_tokens"])]
    if not v["cuda_graphs"]:
        args.append("--enforce-eager")
    return args + v["extra"].split()


def vllm_script(v):
    """The bash line run inside WSL. Output also goes to ~/vllm_last.log."""
    return ("source ~/vllm_env/bin/activate && env VLLM_USE_FLASHINFER_SAMPLER=0 "
            "PYTHONUNBUFFERED=1 " + " ".join(vllm_args(v)) + " 2>&1 | tee ~/vllm_last.log")


def run_quiet(cmd, timeout=30):
    """Run a command without flashing a console window. Returns (code, output)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def port_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def vllm_card():
    try:
        return requests.get(LLM_URL + "/v1/models", timeout=2).json()["data"][0]
    except Exception:
        return None


# --------------------------------------------------------------------------- the window

class ClusterWindow:
    def __init__(self, root, load_agent=True):
        self.root = root
        self.s = load_settings()
        self.q = queue.Queue()
        self.vllm_proc = None            # the hidden wsl process running vLLM (if started here)
        self.vllm_started_at = None      # set while vLLM is starting
        self.agent = None                # the Chat / Task & Queue / Runs tabs, once loaded
        self.agent_failed = False        # loading raised an error: wait for "Try again"
        self.redis_active = 0            # runs with a heartbeat (from any window or the CLI)
        self._vlog_path = None
        self._vlog_busy = False
        self._vlog_text = ""
        root.title("Agent Cluster")
        root.geometry("1280x960")
        root.minsize(1060, 760)
        root.configure(bg=BG)
        self._style()
        self._build()
        self._load_form(self.s["vllm"])
        self._write_pid_file()
        if load_agent:
            self.load_agent()
        threading.Thread(target=self._status_loop, daemon=True).start()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._drain)
        root.after(1500, self._vlog_tick)

    # ------------------------------------------------------------------ layout

    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=PANEL, foreground="#cccccc", padding=(16, 6),
                     font=("Segoe UI", 10, "bold"))
        st.map("TNotebook.Tab", background=[("selected", "#0275d8")], foreground=[("selected", "white")])
        st.configure("TCombobox", fieldbackground=FIELD, background=PANEL, foreground=TEXT, arrowcolor=TEXT)
        st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#0275d8")

    def _label(self, parent, text, muted=False, bold=False, size=10, bg=BG):
        return tk.Label(parent, text=text, bg=bg, fg=MUTED if muted else "#cccccc", justify=tk.LEFT,
                        font=("Segoe UI", size - 1 if muted else size, "bold" if bold else "normal"))

    def _button(self, parent, text, cmd, color="#3e3e42", width=None):
        b = tk.Button(parent, text=text, command=cmd, bg=color, fg="white", activebackground=color,
                      activeforeground="white", relief=tk.FLAT, font=("Segoe UI", 9, "bold"), padx=10, pady=3)
        if width:
            b.config(width=width)
        return b

    def _check(self, parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var, bg=BG, fg=TEXT, selectcolor=FIELD,
                              activebackground=BG, activeforeground=TEXT, font=("Segoe UI", 9))

    def _build(self):
        # ---- status strip: one compact row of service dots, then the run queue's own header
        strip = tk.Frame(self.root, bg=PANEL, padx=10, pady=5)
        strip.pack(fill=tk.X)
        row = tk.Frame(strip, bg=PANEL)
        row.pack(fill=tk.X)
        self.dots = {}        # name -> (dot, short label, detail label)
        groups = [("Node 1", ["vLLM", "GPU", "Z: drive"]),
                  ("Node 2", ["Redis", "Qdrant", "SearXNG", "Dashboard", "File share"]),
                  ("Node 3", ["Ollama"])]
        for title, names in groups:
            tk.Label(row, text=title, bg=PANEL, fg="#5bc0de", font=("Segoe UI", 9, "bold")).pack(
                side=tk.LEFT, padx=(0, 4))
            for name in names:
                dot = tk.Label(row, text="\u25cf", bg=PANEL, fg=GREY, font=("Segoe UI", 10))
                dot.pack(side=tk.LEFT)
                short = tk.Label(row, text=name, bg=PANEL, fg=TEXT, font=("Segoe UI", 9))
                short.pack(side=tk.LEFT, padx=(0, 8))
                self.dots[name] = [dot, short, None]
            tk.Frame(row, bg="#444444", width=1, height=16).pack(side=tk.LEFT, padx=(2, 10))
        self.agent_header = tk.Frame(strip, bg=PANEL)
        self.agent_header.pack(fill=tk.X, pady=(4, 0))

        # ---- activity log (packed before the tabs so it always keeps its space at the bottom)
        logf = tk.Frame(self.root, bg=BG, padx=10)
        logf.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        head = tk.Frame(logf, bg=BG)
        head.pack(fill=tk.X)
        self._label(head, "Activity").pack(side=tk.LEFT)
        self.log_toggle = self._button(head, "Show more", self._toggle_log)
        self.log_toggle.pack(side=tk.RIGHT)
        self.log_box = scrolledtext.ScrolledText(logf, bg="#0c0c0c", fg="#00ff66", height=4,
                                                 font=("Consolas", 9), relief=tk.FLAT)
        self.log_box.pack(fill=tk.X)
        self.log_box.tag_config("err", foreground="#ff6b6b")
        self.log_box.tag_config("ok", foreground="#9dff7a")

        # ---- tabs
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))
        self.agent_frames = tuple(tk.Frame(self.tabs, bg=BG) for _ in range(3))
        self.model_tab, self.cluster_tab = tk.Frame(self.tabs, bg=BG), tk.Frame(self.tabs, bg=BG)
        for frame, text in zip(self.agent_frames + (self.model_tab, self.cluster_tab),
                               ("Chat", "Task & Queue", "Runs", "Model server", "Cluster")):
            self.tabs.add(frame, text=text)
        self._build_model(self.model_tab)
        self._build_cluster(self.cluster_tab)

    def _toggle_log(self):
        big = int(self.log_box.cget("height")) <= 4
        self.log_box.config(height=16 if big else 4)
        self.log_toggle.config(text="Show less" if big else "Show more")
        self.log_box.see(tk.END)

    def _build_model(self, p):
        self.v_preset = tk.StringVar(value=self.s.get("preset", "Fast (default)"))
        self.v_model, self.v_ctx, self.v_reason, self.v_extra = (tk.StringVar() for _ in range(4))
        self.v_kv, self.v_attn = tk.StringVar(), tk.StringVar()
        self.v_util = tk.DoubleVar()
        self.v_seqs, self.v_mtp_n = tk.IntVar(), tk.IntVar()
        self.v_mtp, self.v_graphs, self.v_prefix, self.v_textonly = (tk.BooleanVar() for _ in range(4))

        form = tk.Frame(p, bg=BG, padx=12, pady=8)
        form.pack(fill=tk.X)
        r = 0

        def row(label, widget, note=""):
            nonlocal r
            self._label(form, label).grid(row=r, column=0, sticky="w", pady=2)
            widget.grid(row=r, column=1, sticky="w", pady=2)
            if note:
                self._label(form, note, muted=True).grid(row=r, column=2, sticky="w", padx=10)
            r += 1

        preset_box = tk.Frame(form, bg=BG)
        ttk.Combobox(preset_box, textvariable=self.v_preset, values=list(PRESETS), state="readonly",
                     width=38).pack(side=tk.LEFT)
        self._button(preset_box, "Apply preset", self.apply_preset).pack(side=tk.LEFT, padx=6)
        row("Preset", preset_box, "Fills in the settings below; nothing changes until you start vLLM.")
        row("Model", ttk.Combobox(form, textvariable=self.v_model, values=KNOWN_MODELS, width=44),
            "Hugging Face name; new models download on first start.")
        row("Context length", ttk.Combobox(form, textvariable=self.v_ctx, width=12,
                                           values=["8192", "12288", "16384", "20480", "24576", "32768"]),
            "Tokens per request. Larger leaves less room for parallel requests.")

        util_box = tk.Frame(form, bg=BG)
        tk.Scale(util_box, variable=self.v_util, from_=0.80, to=0.95, resolution=0.005, digits=3,
                 orient=tk.HORIZONTAL, length=260, bg=BG, fg=TEXT, troughcolor=FIELD,
                 highlightthickness=0, activebackground="#0275d8").pack(side=tk.LEFT)
        self._button(util_box, "Check free VRAM", self.check_vram).pack(side=tk.LEFT, padx=8)
        row("GPU memory", util_box, "Share of the 4090 for vLLM. 0.92 is the tested default; 0.95 can't start here.")

        row("Parallel requests", tk.Spinbox(form, from_=1, to=32, textvariable=self.v_seqs, width=6,
                                            bg=FIELD, fg=TEXT, buttonbackground=PANEL, relief=tk.FLAT),
            "Most requests vLLM runs at once (candidates, judges and chat share them).")
        kv_box = tk.Frame(form, bg=BG)
        ttk.Combobox(kv_box, textvariable=self.v_kv, values=["fp8", "auto"], state="readonly", width=8).pack(side=tk.LEFT)
        self._label(kv_box, "   Attention backend ").pack(side=tk.LEFT)
        ttk.Combobox(kv_box, textvariable=self.v_attn, state="readonly", width=14,
                     values=["TRITON_ATTN", "auto", "FLASH_ATTN", "FLASHINFER"]).pack(side=tk.LEFT)
        row("KV cache", kv_box, "fp8 doubles context per GB. FlashInfer can't build on this WSL.")

        opts = tk.Frame(form, bg=BG)
        self._check(opts, "Speculative decoding (MTP), draft tokens:", self.v_mtp).pack(side=tk.LEFT)
        tk.Spinbox(opts, from_=1, to=4, textvariable=self.v_mtp_n, width=3, bg=FIELD, fg=TEXT,
                   buttonbackground=PANEL, relief=tk.FLAT).pack(side=tk.LEFT, padx=(0, 12))
        self._check(opts, "CUDA graphs", self.v_graphs).pack(side=tk.LEFT, padx=(0, 12))
        self._check(opts, "Prefix caching", self.v_prefix).pack(side=tk.LEFT, padx=(0, 12))
        self._check(opts, "Text only (skip vision)", self.v_textonly).pack(side=tk.LEFT)
        row("Options", opts)
        row("Reasoning parser", tk.Entry(form, textvariable=self.v_reason, width=14, bg=FIELD, fg=TEXT,
                                         insertbackground="white", relief=tk.FLAT),
            "qwen3 for Qwen3.x models (keeps thinking out of answers); blank for others.")
        row("Extra arguments", tk.Entry(form, textvariable=self.v_extra, width=60, bg=FIELD, fg=TEXT,
                                        insertbackground="white", relief=tk.FLAT),
            "Added to the vllm serve command as-is.")

        bar = tk.Frame(p, bg=BG, padx=12, pady=4)
        bar.pack(fill=tk.X)
        self._button(bar, "Start everything", self.start_everything, "#0275d8").pack(side=tk.LEFT, padx=(0, 6))
        self._button(bar, "Start vLLM", self.start_vllm, "#3d8b3d").pack(side=tk.LEFT, padx=3)
        self._button(bar, "Stop vLLM", self.stop_vllm, "#8a6d3b").pack(side=tk.LEFT, padx=3)
        self._button(bar, "Restart vLLM", self.restart_vllm, "#d9534f").pack(side=tk.LEFT, padx=3)
        self._button(bar, "Save settings", self.save_form).pack(side=tk.LEFT, padx=(18, 3))
        self._button(bar, "Show command", self.show_command).pack(side=tk.LEFT, padx=3)
        self._button(bar, "Open log file", self.open_vllm_log).pack(side=tk.LEFT, padx=3)

        logf = tk.Frame(p, bg=BG, padx=12)
        logf.pack(fill=tk.BOTH, expand=True, pady=(4, 6))
        self._label(logf, "vLLM log (its status-check lines are hidden):", muted=True).pack(anchor=tk.W)
        self.vlog = scrolledtext.ScrolledText(logf, bg="#0c0c0c", fg="#bbbbbb", font=("Consolas", 8),
                                              relief=tk.FLAT, wrap=tk.WORD, height=10, state=tk.DISABLED)
        self.vlog.pack(fill=tk.BOTH, expand=True)

    def _build_cluster(self, p):
        top = tk.Frame(p, bg=BG, padx=12, pady=10)
        top.pack(fill=tk.X)
        actions = tk.Frame(top, bg=BG)
        actions.pack(side=tk.LEFT, anchor="n")
        self._label(actions, "Actions", bold=True).grid(row=0, column=0, sticky="w", pady=(0, 4))
        items = [
            ("Connect Z: drive", self.connect_drive, None, "Opens a window that asks for the share password."),
            ("Reset pipeline", self.reset_pipeline, "#d9534f", "Stops every run, clears their records and test containers."),
            ("Restart Node 2 services", self.restart_node2, None, "Redis, Qdrant, SearXNG and the dashboard (~15 s)."),
            ("Restart Ollama on Node 3", self.restart_node3, None, "Opens a window for your sudo password."),
            ("Warm up Node 3 models", self.warm_node3, None, "Loads the helper and embedding models."),
            ("Back up to GitHub", self.backup, "#3d8b3d", "Copies launchers and settings to Node 2, commits, pushes."),
        ]
        for i, (text, cmd, color, note) in enumerate(items, 1):
            self._button(actions, text, cmd, color or "#3e3e42", width=22).grid(row=i, column=0, sticky="w", pady=2)
            self._label(actions, note, muted=True).grid(row=i, column=1, sticky="w", padx=10)

        links = tk.Frame(top, bg=BG)
        links.pack(side=tk.LEFT, anchor="n", padx=(30, 0))
        self._label(links, "Links & files", bold=True).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ws = os.path.join(self.s["drive"] + "\\", "workspace")
        entries = [
            ("Web dashboard", lambda: webbrowser.open(f"http://{self.s['node2_ip']}:8080")),
            ("Search page (SearXNG)", lambda: webbrowser.open(f"http://{self.s['node2_ip']}:8888")),
            ("GitHub repository", lambda: webbrowser.open(self.s["github"])),
            ("Workspace folder", lambda: self.open_path(ws)),
            ("Runs folder", lambda: self.open_path(os.path.join(self.s["drive"] + "\\", "runs"))),
            ("Research allowlist", lambda: self.edit(os.path.join(ws, "research_allowlist.txt"))),
            ("config.py", lambda: self.edit(os.path.join(ws, "config.py"))),
            ("research.log", lambda: self.edit(os.path.join(ws, "logs", "research.log"))),
            ("ingest.log", lambda: self.edit(os.path.join(ws, "logs", "ingest.log"))),
            ("Window settings", lambda: self.edit(SETTINGS_FILE)),
        ]
        for i, (text, cmd) in enumerate(entries):
            self._button(links, text, cmd, width=20).grid(row=1 + i // 2, column=i % 2, sticky="w", padx=(0, 8), pady=2)

        details = tk.Frame(p, bg=BG, padx=12, pady=6)
        details.pack(fill=tk.X)
        self._label(details, "Status details", bold=True).pack(anchor=tk.W, pady=(0, 4))
        grid = tk.Frame(details, bg=PANEL, padx=12, pady=8)
        grid.pack(fill=tk.X)
        columns = [("Node 1 (this PC)", ["vLLM", "GPU", "Z: drive"]),
                   ("Node 2 (Blackboard)", ["Redis", "Qdrant", "SearXNG", "Dashboard", "File share"]),
                   ("Node 3 (Worker)", ["Ollama", "Models"])]
        for col, (title, names) in enumerate(columns):
            frame = tk.Frame(grid, bg=PANEL)
            frame.grid(row=0, column=col, sticky="nw", padx=(0, 40))
            tk.Label(frame, text=title, bg=PANEL, fg="#5bc0de", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
            for name in names:
                lbl = tk.Label(frame, text=f"{name}: checking...", bg=PANEL, fg=TEXT, font=("Segoe UI", 9))
                lbl.pack(anchor=tk.W)
                if name in self.dots:
                    self.dots[name][2] = lbl
                else:
                    self.dots[name] = [None, None, lbl]

    # ------------------------------------------------------------------ the agent tabs

    def _clear(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def _show_agent_placeholder(self, message):
        for frame in self.agent_frames:
            self._clear(frame)
            box = tk.Frame(frame, bg=BG)
            box.place(relx=0.5, rely=0.4, anchor="center")
            self._label(box, message, size=11).pack(pady=(0, 10))
            buttons = tk.Frame(box, bg=BG)
            buttons.pack()
            self._button(buttons, "Connect Z:", self.connect_drive, "#0275d8").pack(side=tk.LEFT, padx=4)
            self._button(buttons, "Try again", lambda: self.load_agent(retry=True)).pack(side=tk.LEFT, padx=4)
        self._clear(self.agent_header)
        self._label(self.agent_header, "Chat, tasks and runs load once Z: is connected.", muted=True,
                    bg=PANEL).pack(side=tk.LEFT)

    def load_agent(self, retry=False):
        """Build the Chat, Task & Queue and Runs tabs from Z:\\workspace\\agent_gui.py."""
        if self.agent is not None:
            return True
        if retry:
            self.agent_failed = False
        ws = os.path.join(self.s["drive"] + "\\", "workspace")
        if not os.path.exists(os.path.join(ws, "agent_gui.py")):
            self._show_agent_placeholder("Z: isn't connected, so chat, tasks and runs aren't available yet.\n"
                                         "They load by themselves as soon as Z: is connected.")
            return False
        try:
            if ws not in sys.path:
                sys.path.insert(0, ws)
            if "agent_gui" in sys.modules:
                importlib.reload(sys.modules["agent_gui"])
            import agent_gui
            for frame in self.agent_frames:
                self._clear(frame)
            self._clear(self.agent_header)
            self.agent = agent_gui.AgentControlGUI(self.root, write_pid=False, notebook=self.tabs,
                                                   frames=self.agent_frames, header=self.agent_header)
            # Let the queue switch vLLM for Ultra and MAX runs, starting from what's running now.
            self.agent.server_hook = self.ensure_server
            card = vllm_card()
            if card and card.get("max_model_len") == PRESETS[LONG_PRESET]["ctx"] != self.s["vllm"]["ctx"]:
                self.agent._server_mode = "long"
        except Exception as e:
            self.agent = None
            self.agent_failed = True     # don't retry every 5 s; the Try again button retries
            self.log("Couldn't load the agent tabs:\n" + traceback.format_exc(limit=3), "err")
            self._show_agent_placeholder(f"Couldn't load chat, tasks and runs: {e}")
            return False
        self.log("Loaded Chat, Task & Queue and Runs from Z:\\workspace.", "ok")
        return True

    def _runs_going(self):
        mine = self.agent.active_count() if self.agent else 0
        return max(mine, self.redis_active)

    def _confirm_runs(self, what):
        n = self._runs_going()
        if not n:
            return True
        return messagebox.askyesno("Runs in progress", f"{n} run(s) are going. {what} will make them fail.\n\n"
                                                       "Continue anyway?")

    # ------------------------------------------------------------------ form helpers

    def _load_form(self, v):
        self.v_model.set(v["model"])
        self.v_ctx.set(str(v["ctx"]))
        self.v_util.set(v["gpu_util"])
        self.v_seqs.set(v["max_seqs"])
        self.v_kv.set(v["kv_dtype"])
        self.v_attn.set(v["attention"])
        self.v_mtp.set(v["mtp"])
        self.v_mtp_n.set(v["mtp_tokens"])
        self.v_graphs.set(v["cuda_graphs"])
        self.v_prefix.set(v["prefix_caching"])
        self.v_textonly.set(v["text_only"])
        self.v_reason.set(v["reasoning_parser"])
        self.v_extra.set(v["extra"])

    def read_form(self):
        try:
            v = {"model": self.v_model.get().strip(), "ctx": int(self.v_ctx.get()),
                 "gpu_util": round(float(self.v_util.get()), 3), "max_seqs": int(self.v_seqs.get()),
                 "kv_dtype": self.v_kv.get(), "attention": self.v_attn.get(), "mtp": bool(self.v_mtp.get()),
                 "mtp_tokens": int(self.v_mtp_n.get()), "cuda_graphs": bool(self.v_graphs.get()),
                 "prefix_caching": bool(self.v_prefix.get()), "text_only": bool(self.v_textonly.get()),
                 "reasoning_parser": self.v_reason.get().strip(), "extra": self.v_extra.get().strip()}
        except (ValueError, tk.TclError):
            messagebox.showerror("Agent Cluster", "Context length and the number fields must be whole numbers.")
            return None
        problem = validate_vllm(v)
        if problem:
            messagebox.showerror("Agent Cluster", problem)
            return None
        return v

    def apply_preset(self):
        if self.v_preset.get() not in PRESETS:
            return
        self._load_form(PRESETS[self.v_preset.get()])
        self.log(f"Loaded preset '{self.v_preset.get()}'. Start or restart vLLM to use it.")

    @staticmethod
    def preset_name(v):
        """The preset these settings match exactly, or 'Custom'."""
        return next((name for name, p in PRESETS.items()
                     if all(v.get(k) == p[k] for k in p)), "Custom")

    def save_form(self, quiet=False):
        v = self.read_form()
        if v is None:
            return None
        self.v_preset.set(self.preset_name(v))
        self.s["vllm"], self.s["preset"] = v, self.v_preset.get()
        save_settings(self.s)
        if not quiet:
            self.log("Settings saved.", "ok")
        return v

    def show_command(self):
        v = self.read_form()
        if v:
            cmd = vllm_script(v)
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
            self.log("vLLM command (copied to the clipboard):\n" + cmd)

    # ------------------------------------------------------------------ logging and the queue

    def log(self, text, tag=None):
        line = f"{time.strftime('%H:%M:%S')}  {text}\n"
        if tag:
            self.log_box.insert(tk.END, line, tag)
        else:
            self.log_box.insert(tk.END, line)
        self.log_box.see(tk.END)

    def post(self, kind, *payload):
        self.q.put((kind, payload))

    def _drain(self):
        try:
            for _ in range(200):
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log(*payload)
                elif kind == "status":
                    self._show_status(payload[0])
                elif kind == "vlog":
                    self._show_vlog(payload[0])
                elif kind == "call":
                    payload[0]()
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def in_thread(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def stream(self, cmd, label):
        """Run a command in the background, copying its output into the activity log."""
        def work():
            self.post("log", f"{label}...")
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                                        creationflags=NO_WINDOW)
                for line in proc.stdout:
                    if line.strip():
                        self.post("log", "    " + line.rstrip())
                code = proc.wait()
            except OSError as e:
                self.post("log", f"{label} failed: {e}", "err")
                return
            self.post("log", f"{label}: {'done' if code == 0 else f'finished with exit code {code}'}",
                      "ok" if code == 0 else "err")
        self.in_thread(work)

    def ssh(self, host, remote_cmd):
        return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", f"{self.s['ssh_user']}@{host}", remote_cmd]

    def _redis(self):
        """A Redis client: config.get_redis() (with any password) once the agent tabs loaded it."""
        cfg = sys.modules.get("config")
        if cfg is not None and hasattr(cfg, "get_redis"):
            return cfg.get_redis(decode_responses=True, timeout=2)
        import redis
        return redis.Redis(host=self.s["node2_ip"], socket_timeout=2, socket_connect_timeout=2,
                           decode_responses=True)

    # ------------------------------------------------------------------ status

    def _status_loop(self):
        while True:
            try:
                self.post("status", self._collect_status())
            except Exception as e:
                self.post("log", f"Status check failed: {e}", "err")
            time.sleep(5)

    def _collect_status(self):
        n2, n3 = self.s["node2_ip"], self.s["node3_ip"]
        st = {"card": vllm_card(), "drive": os.path.exists(self.s["drive"] + "\\workspace")}
        code, out = run_quiet(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu",
                               "--format=csv,noheader,nounits"], timeout=5)
        st["gpu"] = [x.strip() for x in out.split(",")] if code == 0 and out.count(",") == 3 else None
        for name, host, port in (("Redis", n2, 6379), ("Qdrant", n2, 6333), ("SearXNG", n2, 8888),
                                 ("Dashboard", n2, 8080), ("File share", n2, 445), ("Ollama", n3, 11434)):
            st[name] = port_open(host, port)
        st["models"] = None
        if st["Ollama"]:
            try:
                st["models"] = [m["name"] for m in requests.get(f"http://{n3}:11434/api/ps", timeout=2).json()["models"]]
            except Exception:
                pass
        st["active_runs"] = 0
        if st["Redis"]:
            try:
                st["active_runs"] = self._redis().zcount("workflow:active", time.time() - 120, "+inf")
            except Exception:
                pass
        st["vllm_error"] = None
        if self.vllm_started_at and not st["card"]:
            code, out = run_quiet(["wsl", "bash", "-c", "tail -c 6000 ~/vllm_last.log"], timeout=10)
            m = re.findall(r"(ValueError: .*|RuntimeError: .*|torch\.OutOfMemoryError.*|CUDA out of memory.*)", out)
            st["vllm_error"] = m[-1][:300] if m else None
        return st

    def _set(self, name, color, short, detail=None):
        dot, short_lbl, detail_lbl = self.dots[name]
        if dot is not None:
            dot.config(fg=color)
            short_lbl.config(text=short)
        if detail_lbl is not None:
            detail_lbl.config(text=f"{name}: {detail or short}", fg=TEXT if color != RED else "#ff8a8a")

    def _show_status(self, st):
        self.redis_active = st.get("active_runs", 0)
        card = st["card"]
        if card:
            if self.vllm_started_at:
                self.log(f"vLLM is ready after {time.time() - self.vllm_started_at:.0f} s.", "ok")
                self.vllm_started_at = None
            ctx = card.get("max_model_len")
            self._set("vLLM", GREEN, f"vLLM ready ({ctx // 1024 if ctx else '?'}k)",
                      f"ready, {card['id'].split('/')[-1]}, {ctx} context")
        elif st["vllm_error"]:
            self._set("vLLM", RED, "vLLM failed", "failed to start (see Activity and the Model server log)")
            self.log("vLLM failed to start: " + st["vllm_error"], "err")
            self.log("Tip: lower Context length or GPU memory, or try 'Check free VRAM'.", "err")
            self.vllm_started_at = None
        elif self.vllm_started_at:
            secs = time.time() - self.vllm_started_at
            self._set("vLLM", ORANGE, f"vLLM starting {secs:.0f}s", f"starting ({secs:.0f} s, usually about a minute)")
        else:
            self._set("vLLM", RED, "vLLM stopped", "stopped (Model server tab, Start vLLM)")
        if st["gpu"]:
            used, total, util, temp = st["gpu"]
            self._set("GPU", GREEN, f"GPU {float(used) / 1024:.1f}/{float(total) / 1024:.0f} GB {float(temp):.0f}°C",
                      f"{float(used) / 1024:.1f} of {float(total) / 1024:.1f} GB used, {util}% busy, "
                      f"{float(temp):.0f} C")
        else:
            self._set("GPU", GREY, "GPU ?", "nvidia-smi unavailable")
        self._set("Z: drive", GREEN if st["drive"] else RED, "Z:", "connected" if st["drive"] else "not connected")
        for name, short in (("Redis", "Redis"), ("Qdrant", "Qdrant"), ("SearXNG", "SearXNG"),
                            ("Dashboard", "Dashboard"), ("File share", "Share")):
            self._set(name, GREEN if st[name] else RED, short, "up" if st[name] else "down")
        models = st["models"]
        if not st["Ollama"]:
            self._set("Ollama", RED, "Ollama down", "down")
        else:
            color = GREEN if models else ORANGE
            self._set("Ollama", color, f"Ollama · {len(models)} models" if models else "Ollama · none loaded", "up")
        self._set("Models", GREEN if models else ORANGE, "",
                  ", ".join(models) if models else ("none loaded (Warm up Node 3 models)" if models == [] else "unknown"))
        if self.agent is None and st["drive"] and not self.agent_failed:
            self.load_agent()            # Z: has just been connected

    # ------------------------------------------------------------------ vLLM

    def start_vllm(self):
        v = self.save_form(quiet=True)
        if v is None:
            return
        if vllm_card():
            self.log("vLLM is already running. Use Restart vLLM to apply new settings.")
            return
        self.log("Starting vLLM: " + " ".join(vllm_args(v)[2:]))
        self._launch_vllm(v)
        self._set("vLLM", ORANGE, "vLLM starting", "starting...")

    def _launch_vllm(self, v):
        """Start vLLM with settings v (no window of its own: the log shows on the Model server tab,
        and vLLM keeps running if this window closes; Stop vLLM stops it). Safe from any thread."""
        run_quiet(["wsl", "-u", "root", "bash", "-c",
                   "fuser -k -9 8001/tcp >/dev/null 2>&1; pkill -9 -f '[v]llm serve' >/dev/null 2>&1"])
        run_quiet(["wsl", "bash", "-c", "rm -f ~/vllm_last.log"])
        self.vllm_proc = subprocess.Popen(["wsl", "bash", "-c", vllm_script(v)], stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          creationflags=NO_WINDOW | NEW_GROUP)
        self.vllm_started_at = time.time()
        self._vlog_text = ""

    def ensure_server(self, want, done):
        """For the run queue: make vLLM serve the 32k preset ("long") or your saved settings
        ("normal"), then call done(ok, message) on the main thread. Never changes the saved
        settings. If the 32k preset won't start, it goes back to the saved settings (ok=False)."""
        v = copy.deepcopy(PRESETS[LONG_PRESET]) if want == "long" else copy.deepcopy(self.s["vllm"])
        label = "the 32k server" if want == "long" else "your saved settings"

        def matches():
            card = vllm_card()
            return bool(card) and card.get("max_model_len") == v["ctx"] and card.get("id") == v["model"]

        def wait_ready(limit=480):
            end = time.time() + limit
            while time.time() < end:
                if matches():
                    return True
                if self.vllm_proc is not None and self.vllm_proc.poll() is not None:
                    return False
                time.sleep(3)
            return False

        def work():
            if matches():
                self.post("call", lambda: done(True, f"vLLM already runs {label}."))
                return
            self.post("log", f"Switching vLLM to {label} for the run queue (about a minute)...")
            self._stop_vllm_blocking()
            self._launch_vllm(v)
            if wait_ready():
                self.vllm_started_at = None
                self.post("log", f"vLLM now runs {label} ({v['ctx'] // 1024}k context).", "ok")
                self.post("call", lambda: done(True, f"vLLM switched to {label}."))
                return
            self.post("log", f"vLLM didn't start with {label}.", "err")
            if want == "long":
                self._stop_vllm_blocking()
                self._launch_vllm(copy.deepcopy(self.s["vllm"]))
                ok = wait_ready()
                self.vllm_started_at = None
                self.post("call", lambda: done(False, "The 32k server didn't start, so the run uses the normal "
                                                      "one" + ("" if ok else " (which isn't up yet either)") + "."))
            else:
                self.vllm_started_at = None
                self.post("call", lambda: done(False, "vLLM didn't start with your saved settings; check the "
                                                      "Model server tab."))
        self.in_thread(work)

    def start_everything(self):
        """Connect Z: if needed, start vLLM if it isn't running, and load Node 3's models."""
        if not os.path.exists(self.s["drive"] + "\\workspace"):
            self.log("Z: isn't connected; connect it in the window that opens (the tabs load by themselves).")
            self.connect_drive()
        self.start_vllm()
        self.warm_node3()

    def _stop_vllm_blocking(self):
        run_quiet(["wsl", "-u", "root", "bash", "-c",
                   "fuser -k -9 8001/tcp >/dev/null 2>&1; pkill -9 -f '[v]llm serve' >/dev/null 2>&1"])
        if self.vllm_proc and self.vllm_proc.poll() is None:
            run_quiet(["taskkill", "/F", "/T", "/PID", str(self.vllm_proc.pid)])
        # Also close a vLLM window started by Launch_GUI.bat (match its command line, not ours).
        run_quiet(["powershell", "-NoProfile", "-Command",
                   "$p = '*vllm' + ' serve*'; Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
                   "Where-Object { $_.CommandLine -like $p } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
        self.vllm_proc = None
        for _ in range(20):
            if not port_open("127.0.0.1", 8001, 0.5):
                return True
            time.sleep(0.5)
        return False

    def stop_vllm(self):
        if not self._confirm_runs("Stopping vLLM"):
            return
        self.vllm_started_at = None

        def work():
            self.post("log", "Stopping vLLM...")
            ok = self._stop_vllm_blocking()
            self.post("log", "vLLM stopped." if ok else "vLLM's port is still busy; try again.", "ok" if ok else "err")
        self.in_thread(work)

    def restart_vllm(self):
        if not self._confirm_runs("Restarting vLLM"):
            return
        v = self.save_form(quiet=True)
        if v is None:
            return

        def work():
            self.post("log", "Restarting vLLM with the settings above...")
            self._stop_vllm_blocking()
            self.post("call", self.start_vllm)
        self.in_thread(work)

    def check_vram(self):
        def work():
            if vllm_card():
                self.post("log", "vLLM is running, so its memory is in use. Stop vLLM first to measure "
                                 "how much is free at startup.", "err")
                return
            self.post("log", "Measuring free GPU memory as vLLM sees it (takes a few seconds)...")
            code, out = run_quiet(["wsl", "bash", "-c", "~/vllm_env/bin/python -c 'import torch; "
                                   "f, t = torch.cuda.mem_get_info(); print(f, t)'"], timeout=90)
            m = re.search(r"(\d+)\s+(\d+)\s*$", out.strip())
            if not m:
                self.post("log", f"Couldn't measure: {out.strip()[-300:]}", "err")
                return
            free, total = int(m.group(1)) / 2**30, int(m.group(2)) / 2**30
            best = int((free - 0.15) / total * 200) / 200          # round down to 0.005
            self.post("log", f"Free at startup: {free:.2f} of {total:.2f} GiB. Highest GPU memory setting that "
                             f"will start: {fmt_util(best)} (keeps 0.15 GiB spare).", "ok")
            self.post("call", lambda: self.v_util.set(min(best, 0.95)))
        self.in_thread(work)

    def _vlog_file(self):
        if self._vlog_path is None:
            code, out = run_quiet(["wsl", "bash", "-c", "wslpath -w ~/vllm_last.log"])
            self._vlog_path = out.strip().splitlines()[-1] if code == 0 and out.strip() else ""
        return self._vlog_path

    def open_vllm_log(self):
        path = self._vlog_file()
        if path and os.path.exists(path):
            subprocess.Popen(["notepad", path])
        else:
            self.log("No vLLM log yet (it's written while vLLM runs).", "err")

    def _vlog_tick(self):
        """Refresh the vLLM log pane every 2 s while the Model server tab is open (or vLLM starts)."""
        visible = self.tabs.select() == str(self.model_tab)
        if (visible or self.vllm_started_at) and not self._vlog_busy:
            self._vlog_busy = True
            self.in_thread(self._read_vlog)
        self.root.after(2000, self._vlog_tick)

    def _read_vlog(self):
        text = ""
        try:
            path = self._vlog_file()
            if path:
                with open(path, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - 60000))
                    text = f.read().decode("utf-8", errors="replace")
        except OSError:
            text = ""
        # Drop the status-check lines, blank lines and progress-bar redraws (\r).
        lines = [ln.split("\r")[-1] for ln in text.splitlines()[1:]]
        lines = [ln for ln in lines if ln.strip() and not LOG_NOISE.search(ln)]
        self.post("vlog", "\n".join(lines[-300:]))

    def _show_vlog(self, text):
        self._vlog_busy = False
        if text == self._vlog_text:
            return
        self._vlog_text = text
        at_end = self.vlog.yview()[1] >= 0.999
        top = self.vlog.yview()[0]
        self.vlog.config(state=tk.NORMAL)
        self.vlog.delete("1.0", tk.END)
        self.vlog.insert(tk.END, text or "(no log yet: vLLM writes it while it runs)")
        self.vlog.config(state=tk.DISABLED)
        if at_end:
            self.vlog.see(tk.END)
        else:
            self.vlog.yview_moveto(top)

    # ------------------------------------------------------------------ cluster actions

    def connect_drive(self):
        cmd = (f"echo Connecting {self.s['drive']} to {self.s['share']}. Enter the share password for "
               f"'{self.s['ssh_user']}' when asked. && net use {self.s['drive']} {self.s['share']} "
               f"/user:{self.s['ssh_user']} /persistent:yes && echo Done. You can close this window.")
        subprocess.Popen(["cmd", "/k", cmd], creationflags=NEW_CONSOLE)
        self.log("Opened a window to connect the Z: drive.")

    def reset_pipeline(self):
        if not messagebox.askyesno("Reset pipeline", "Stop every running task, empty the queue, and clear "
                                                     "their records and test containers?"):
            return
        threads = self.agent.stop_all("stopped by Reset pipeline") if self.agent else []

        def work():
            for t in threads:
                t.join(timeout=20)
            # Runs started outside this window (for example from the command line).
            for pid_file in glob.glob(PIPELINE_PID_GLOB):
                try:
                    with open(pid_file) as f:
                        pid = int(f.read().strip())
                except (OSError, ValueError):
                    pid = None
                if pid and pid != os.getpid() and self._pid_alive(pid):
                    run_quiet(["taskkill", "/F", "/T", "/PID", str(pid)])
                    self.post("log", f"Stopped pipeline process {pid}.")
                try:
                    os.remove(pid_file)
                except OSError:
                    pass
            try:
                r = self._redis()
                stopped = 0
                for key in r.zrevrange("workflow:tasks", 0, 50):
                    if r.hget(key, "status") == "RUNNING":
                        r.hset(key, mapping={"status": "STOPPED", "phase": "stopped by Reset pipeline"})
                        stopped += 1
                r.delete("workflow:langgraph:001", "workflow:active")
                self.post("log", f"Cleared the run records in Redis ({stopped} more marked stopped).")
            except Exception as e:
                self.post("log", f"Couldn't clear Redis ({e}).", "err")
            code, out = run_quiet(self.ssh(self.s["node2_ip"], "docker ps -aq --filter name=agent- | "
                                           "xargs -r docker rm -f | wc -l"), timeout=60)
            if code == 0:
                self.post("log", f"Removed {out.strip() or 0} leftover test container(s) on Node 2.")
            self.post("log", "Reset done.", "ok")
            if self.agent:
                self.post("call", self.agent.refresh_runs)
        self.in_thread(work)

    @staticmethod
    def _pid_alive(pid):
        code, out = run_quiet(["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=5)
        return "python" in out.lower()

    def restart_node2(self):
        if not self._confirm_runs("Restarting Node 2's services (Redis and the test sandbox)"):
            return
        self.stream(self.ssh(self.s["node2_ip"],
                             "pkill -f '^python3 /mnt/blackboard/workspace/agent_dashboard.py'; "
                             "cd /mnt/blackboard/docker && docker compose down --remove-orphans && "
                             "docker compose up -d && docker ps --format '{{.Names}}: {{.Status}}'"),
                    "Restarting Node 2 services")

    def restart_node3(self):
        cmd = (f"echo Restarting Ollama on Node 3. Enter the sudo password for '{self.s['ssh_user']}' when asked. && "
               f"ssh -t {self.s['ssh_user']}@{self.s['node3_ip']} \"sudo systemctl restart ollama\" && "
               "echo Done. Back in Agent Cluster, press Warm up Node 3 models. You can close this window.")
        subprocess.Popen(["cmd", "/k", cmd], creationflags=NEW_CONSOLE)
        self.log("Opened a window to restart Ollama on Node 3. Afterwards, press Warm up Node 3 models.")

    def warm_node3(self):
        def work():
            url = f"http://{self.s['node3_ip']}:11434"
            worker, embedder, ctx = self.s["worker_model"], self.s["embed_model"], self.s["ollama_num_ctx"]
            try:
                self.post("log", f"Loading {worker} on Node 3...")
                requests.post(f"{url}/api/generate", timeout=300, json={
                    "model": worker, "prompt": "warmup", "stream": False, "think": False,
                    "keep_alive": -1, "options": {"num_ctx": ctx}}).raise_for_status()
                self.post("log", f"Loading {embedder} on Node 3...")
                requests.post(f"{url}/api/embed", timeout=120, json={
                    "model": embedder, "input": "warmup", "keep_alive": -1}).raise_for_status()
                models = [m["name"] for m in requests.get(f"{url}/api/ps", timeout=5).json()["models"]]
                self.post("log", "Node 3 models loaded: " + ", ".join(models), "ok")
            except Exception as e:
                self.post("log", f"Warm-up failed: {e}", "err")
        self.in_thread(work)

    def backup(self):
        n2, user = self.s["node2_ip"], self.s["ssh_user"]
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        bats = [os.path.join(desktop, b) for b in ("Launch_GUI.bat", "Reset_Cluster.bat",
                                                    "Restart_Node2_Blackboard.bat", "Restart_Node3_Worker.bat",
                                                    "Backup_To_GitHub.bat") if os.path.exists(os.path.join(desktop, b))]

        def work():
            self.post("log", "Copying launchers and settings to Node 2...")
            run_quiet(self.ssh(n2, "mkdir -p /mnt/blackboard/launchers/cluster_launcher"))
            for files, dest in ((bats, "/mnt/blackboard/launchers/"),
                                ([os.path.abspath(__file__), SETTINGS_FILE], "/mnt/blackboard/launchers/cluster_launcher/")):
                files = [f for f in files if os.path.exists(f)]
                if files:
                    code, out = run_quiet(["scp", "-q", "-o", "BatchMode=yes", *files, f"{user}@{n2}:{dest}"], timeout=60)
                    if code != 0:
                        self.post("log", f"Copy failed: {out.strip()[-300:]}", "err")
            wsl_cfg = os.path.join(os.path.expanduser("~"), ".wslconfig")
            if os.path.exists(wsl_cfg):
                run_quiet(["scp", "-q", "-o", "BatchMode=yes", wsl_cfg, f"{user}@{n2}:/mnt/blackboard/launchers/wslconfig.txt"])
            self.post("call", lambda: self.stream(self.ssh(n2, "bash /mnt/blackboard/launchers/backup_node2.sh"),
                                                  "Backing up to GitHub"))
        self.in_thread(work)

    # ------------------------------------------------------------------ files and lifecycle

    def open_path(self, path):
        if os.path.exists(path):
            os.startfile(path)
        else:
            self.log(f"Not found: {path} (is Z: connected?)", "err")

    def edit(self, path):
        if os.path.exists(path):
            subprocess.Popen(["notepad", path])
        else:
            self.log(f"Not found: {path} (is Z: connected?)", "err")

    def _write_pid_file(self):
        try:
            with open(GUI_PID_FILE, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass

    def _remove_pid_file(self):
        try:
            with open(GUI_PID_FILE) as f:
                mine = f.read().strip() == str(os.getpid())
            if mine:
                os.remove(GUI_PID_FILE)
        except OSError:
            pass

    def on_close(self):
        if self.agent is not None:
            if not self.agent.confirm_close():
                return
            self.agent.shutdown()
        self._remove_pid_file()
        self.root.destroy()          # vLLM keeps running; Stop vLLM (or Reset_Cluster) stops it


Launcher = ClusterWindow    # the old name, still used by the test scripts


def selftest():
    root = tk.Tk()
    root.withdraw()
    app = ClusterWindow(root)
    st = app._collect_status()
    app._show_status(st)
    root.update()
    tabs = [app.tabs.tab(i, "text") for i in app.tabs.tabs()]
    print("command:", vllm_script(app.read_form()))
    print("tabs:", tabs, "| agent loaded:", app.agent is not None)
    print("status:", {k: (v if k != "card" else (v or {}).get("id")) for k, v in st.items()})
    print("strip:", " | ".join(short.cget("text") for dot, short, _ in app.dots.values() if short is not None))
    ok = tabs == ["Chat", "Task & Queue", "Runs", "Model server", "Cluster"]
    app._remove_pid_file()
    root.destroy()
    print("LAUNCHER_SELF_TEST_PASSED" if ok else "LAUNCHER SELF-TEST FAILED")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        root = tk.Tk()
        ClusterWindow(root)
        root.mainloop()
