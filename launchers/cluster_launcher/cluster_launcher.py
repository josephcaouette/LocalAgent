"""Cluster Launcher: one window to start, stop, tune and check the whole cluster.

Replaces Launch_GUI.bat, Reset_Cluster.bat, Restart_Node2_Blackboard.bat,
Restart_Node3_Worker.bat and Backup_To_GitHub.bat (they still work as fallbacks).

  Status (top)  live health of every node and service, refreshed every 5 seconds
  Model server  vLLM settings with presets, a free-VRAM check, start / stop / restart
  Cluster       agent GUI, Z: drive, pipeline reset, Node 2 / Node 3 restarts, backup
  Links         dashboard, search page, GitHub, folders, logs and settings files

It lives on Node 1 (C:\\AI\\cluster_launcher), so it works even when Z: isn't connected.
Settings are saved next to it in launcher_settings.json.
"""
import copy
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
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "launcher_settings.json")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
GUI_PID_FILE = os.path.join(tempfile.gettempdir(), "agent_gui.pid")
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

BG, PANEL, FIELD, TEXT, MUTED = "#1e1e1e", "#2d2d2d", "#252526", "#d4d4d4", "#8a8a8a"
GREEN, RED, ORANGE, GREY = "#4CAF50", "#e05252", "#f0ad4e", "#777777"


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

class Launcher:
    def __init__(self, root):
        self.root = root
        self.s = load_settings()
        self.q = queue.Queue()
        self.vllm_window = None
        self.vllm_started_at = None      # set while vLLM is starting
        self.open_gui_when_ready = False
        root.title("Cluster Launcher")
        root.geometry("1040x900")
        root.configure(bg=BG)
        self._style()
        self._build()
        self._load_form(self.s["vllm"])
        threading.Thread(target=self._status_loop, daemon=True).start()
        root.after(100, self._drain)

    # ------------------------------------------------------------------ layout

    def _style(self):
        st = ttk.Style()
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

    def _label(self, parent, text, muted=False, bold=False, size=10):
        return tk.Label(parent, text=text, bg=BG, fg=MUTED if muted else "#cccccc", justify=tk.LEFT,
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
        # ---- status grid
        status = tk.Frame(self.root, bg=PANEL, padx=12, pady=8)
        status.pack(fill=tk.X)
        self.dots = {}
        columns = [("Node 1 (this PC)", ["vLLM", "GPU", "Z: drive", "Agent GUI"]),
                   ("Node 2 (Blackboard)", ["Redis", "Qdrant", "SearXNG", "Dashboard", "File share"]),
                   ("Node 3 (Worker)", ["Ollama", "Models", "Last run"])]
        for col, (title, names) in enumerate(columns):
            frame = tk.Frame(status, bg=PANEL)
            frame.grid(row=0, column=col, sticky="nw", padx=(0, 30))
            tk.Label(frame, text=title, bg=PANEL, fg="#5bc0de", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
            for name in names:
                row = tk.Frame(frame, bg=PANEL)
                row.pack(anchor=tk.W, fill=tk.X)
                dot = tk.Label(row, text="\u25cf", bg=PANEL, fg=GREY, font=("Segoe UI", 10))
                dot.pack(side=tk.LEFT)
                txt = tk.Label(row, text=f"{name}: checking...", bg=PANEL, fg=TEXT, font=("Segoe UI", 9))
                txt.pack(side=tk.LEFT)
                self.dots[name] = (dot, txt)

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill=tk.BOTH, expand=False, padx=8, pady=(8, 4))
        model_tab, cluster_tab, links_tab = (tk.Frame(self.tabs, bg=BG) for _ in range(3))
        self.tabs.add(model_tab, text="Model server")
        self.tabs.add(cluster_tab, text="Cluster")
        self.tabs.add(links_tab, text="Links & files")
        self._build_model(model_tab)
        self._build_cluster(cluster_tab)
        self._build_links(links_tab)

        logf = tk.Frame(self.root, bg=BG, padx=10)
        logf.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self._label(logf, "Activity").pack(anchor=tk.W)
        self.log_box = scrolledtext.ScrolledText(logf, bg="#0c0c0c", fg="#00ff66", height=10,
                                                 font=("Consolas", 9), relief=tk.FLAT)
        self.log_box.pack(fill=tk.BOTH, expand=True)
        self.log_box.tag_config("err", foreground="#ff6b6b")
        self.log_box.tag_config("ok", foreground="#9dff7a")

    def _build_model(self, p):
        self.v_preset = tk.StringVar(value=self.s.get("preset", "Fast (default)"))
        self.v_model, self.v_ctx, self.v_reason, self.v_extra = (tk.StringVar() for _ in range(4))
        self.v_kv, self.v_attn = tk.StringVar(), tk.StringVar()
        self.v_util = tk.DoubleVar()
        self.v_seqs, self.v_mtp_n = tk.IntVar(), tk.IntVar()
        self.v_mtp, self.v_graphs, self.v_prefix, self.v_textonly = (tk.BooleanVar() for _ in range(4))

        form = tk.Frame(p, bg=BG, padx=12, pady=10)
        form.pack(fill=tk.X)
        r = 0

        def row(label, widget, note=""):
            nonlocal r
            self._label(form, label).grid(row=r, column=0, sticky="w", pady=3)
            widget.grid(row=r, column=1, sticky="w", pady=3)
            if note:
                self._label(form, note, muted=True).grid(row=r, column=2, sticky="w", padx=10)
            r += 1

        preset_box = tk.Frame(form, bg=BG)
        cb = ttk.Combobox(preset_box, textvariable=self.v_preset, values=list(PRESETS), state="readonly", width=38)
        cb.pack(side=tk.LEFT)
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
            "Most requests vLLM runs at once (best-of-3 candidates + chat need about 4).")
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

        bar = tk.Frame(p, bg=BG, padx=12, pady=6)
        bar.pack(fill=tk.X)
        self._button(bar, "Start everything", self.start_everything, "#0275d8").pack(side=tk.LEFT, padx=(0, 6))
        self._button(bar, "Start vLLM", self.start_vllm, "#3d8b3d").pack(side=tk.LEFT, padx=3)
        self._button(bar, "Stop vLLM", self.stop_vllm, "#8a6d3b").pack(side=tk.LEFT, padx=3)
        self._button(bar, "Restart vLLM", self.restart_vllm, "#d9534f").pack(side=tk.LEFT, padx=3)
        self._button(bar, "Save settings", self.save_form).pack(side=tk.LEFT, padx=(18, 3))
        self._button(bar, "Show command", self.show_command).pack(side=tk.LEFT, padx=3)
        self._button(bar, "Open vLLM log", self.open_vllm_log).pack(side=tk.LEFT, padx=3)

    def _build_cluster(self, p):
        grid = tk.Frame(p, bg=BG, padx=12, pady=10)
        grid.pack(fill=tk.X)
        actions = [
            ("Open agent GUI", self.open_agent_gui, "#0275d8", "Opens the chat and task window (connects Z: first if needed)."),
            ("Connect Z: drive", self.connect_drive, None, "Opens a window that asks for the share password once."),
            ("Reset pipeline", self.reset_pipeline, "#d9534f", "Stops the GUI and any run, clears the last-run record, reopens the GUI."),
            ("Restart Node 2 services", self.restart_node2, None, "Restarts Redis, Qdrant, SearXNG and the dashboard (about 15 s)."),
            ("Restart Ollama on Node 3", self.restart_node3, None, "Opens a window for your sudo password, then warms up the models."),
            ("Warm up Node 3 models", self.warm_node3, None, "Loads the helper and embedding models and keeps them loaded."),
            ("Back up to GitHub", self.backup, "#3d8b3d", "Copies launchers and settings to Node 2, commits and pushes."),
        ]
        for i, (text, cmd, color, note) in enumerate(actions):
            self._button(grid, text, cmd, color or "#3e3e42", width=24).grid(row=i, column=0, sticky="w", pady=3)
            self._label(grid, note, muted=True).grid(row=i, column=1, sticky="w", padx=12)

    def _build_links(self, p):
        grid = tk.Frame(p, bg=BG, padx=12, pady=10)
        grid.pack(fill=tk.X)
        ws = os.path.join(self.s["drive"] + "\\", "workspace")
        links = [
            ("Dashboard", lambda: webbrowser.open(f"http://{self.s['node2_ip']}:8080")),
            ("Search page (SearXNG)", lambda: webbrowser.open(f"http://{self.s['node2_ip']}:8888")),
            ("GitHub repository", lambda: webbrowser.open(self.s["github"])),
            ("Workspace folder", lambda: self.open_path(ws)),
            ("Runs folder", lambda: self.open_path(os.path.join(self.s["drive"] + "\\", "runs"))),
            ("Research allowlist", lambda: self.edit(os.path.join(ws, "research_allowlist.txt"))),
            ("config.py", lambda: self.edit(os.path.join(ws, "config.py"))),
            ("research.log", lambda: self.edit(os.path.join(ws, "logs", "research.log"))),
            ("ingest.log", lambda: self.edit(os.path.join(ws, "logs", "ingest.log"))),
            ("Launcher settings", lambda: self.edit(SETTINGS_FILE)),
        ]
        for i, (text, cmd) in enumerate(links):
            self._button(grid, text, cmd, width=22).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 10), pady=3)

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
            messagebox.showerror("Cluster Launcher", "Context length and the number fields must be whole numbers.")
            return None
        problem = validate_vllm(v)
        if problem:
            messagebox.showerror("Cluster Launcher", problem)
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
        st["gui"] = self._pid_alive(GUI_PID_FILE)
        st["last_run"] = None
        if st["Redis"]:
            try:
                import redis
                r = redis.Redis(host=n2, socket_timeout=1, socket_connect_timeout=1, decode_responses=True)
                st["last_run"] = r.hmget("workflow:langgraph:001", "status", "phase", "target_file")
                st["active_runs"] = r.zcount("workflow:active", time.time() - 120, "+inf")
            except Exception:
                pass
        st["vllm_error"] = None
        if self.vllm_started_at and not st["card"]:
            code, out = run_quiet(["wsl", "bash", "-c", "tail -c 6000 ~/vllm_last.log"], timeout=10)
            m = re.findall(r"(ValueError: .*|RuntimeError: .*|torch\.OutOfMemoryError.*|CUDA out of memory.*)", out)
            st["vllm_error"] = m[-1][:300] if m else None
        return st

    @staticmethod
    def _pid_alive(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
        except (OSError, ValueError):
            return False
        code, out = run_quiet(["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=5)
        return "python" in out.lower()

    def _set(self, name, color, text):
        dot, label = self.dots[name]
        dot.config(fg=color)
        label.config(text=f"{name}: {text}")

    def _show_status(self, st):
        card = st["card"]
        if card:
            if self.vllm_started_at:
                self.log(f"vLLM is ready after {time.time() - self.vllm_started_at:.0f} s.", "ok")
                self.vllm_started_at = None
            self._set("vLLM", GREEN, f"ready, {card['id'].split('/')[-1]}, {card.get('max_model_len')} context")
            if self.open_gui_when_ready:
                self.open_gui_when_ready = False
                self.open_agent_gui()
        elif st["vllm_error"]:
            self._set("vLLM", RED, "failed to start (see Activity)")
            self.log("vLLM failed to start: " + st["vllm_error"], "err")
            self.log("Tip: lower Context length or GPU memory, or try 'Check free VRAM'.", "err")
            self.vllm_started_at = None
            self.open_gui_when_ready = False
        elif self.vllm_started_at:
            self._set("vLLM", ORANGE, f"starting ({time.time() - self.vllm_started_at:.0f} s, usually 1-3 min)")
        else:
            self._set("vLLM", RED, "stopped")
        if st["gpu"]:
            used, total, util, temp = st["gpu"]
            self._set("GPU", GREEN, f"{float(used) / 1024:.1f} of {float(total) / 1024:.1f} GB used, "
                                    f"{util}% busy, {float(temp):.0f} C")
        else:
            self._set("GPU", GREY, "nvidia-smi unavailable")
        self._set("Z: drive", GREEN if st["drive"] else RED, "connected" if st["drive"] else "not connected")
        self._set("Agent GUI", GREEN if st["gui"] else GREY, "running" if st["gui"] else "not running")
        for name in ("Redis", "Qdrant", "SearXNG", "Dashboard", "File share", "Ollama"):
            self._set(name, GREEN if st[name] else RED, "up" if st[name] else "down")
        models = st["models"]
        self._set("Models", GREEN if models else ORANGE,
                  ", ".join(models) if models else ("none loaded (Warm up)" if models == [] else "unknown"))
        lr, active = st["last_run"], st.get("active_runs", 0)
        if active:
            text = f"{active} running" + (f" - newest: {lr[1]} ({lr[2]})" if lr and lr[1] else "")
            self._set("Last run", ORANGE, text)
        elif lr and lr[0]:
            status = "LOST" if lr[0] == "RUNNING" else lr[0]   # no heartbeat: its process is gone
            color = {"PASSED": GREEN, "STOPPED": ORANGE, "LOST": GREY}.get(status, RED)
            self._set("Last run", color, status + (f" ({lr[2]})" if lr[2] else ""))
        else:
            self._set("Last run", GREY, "none")

    # ------------------------------------------------------------------ vLLM

    def start_vllm(self, then_gui=False):
        v = self.save_form(quiet=True)
        if v is None:
            return
        if vllm_card():
            self.log("vLLM is already running. Use Restart vLLM to apply new settings.")
            if then_gui:
                self.open_agent_gui()
            return
        self.log("Starting vLLM: " + " ".join(vllm_args(v)[2:]))
        run_quiet(["wsl", "-u", "root", "bash", "-c",
                   "fuser -k -9 8001/tcp >/dev/null 2>&1; pkill -9 -f '[v]llm serve' >/dev/null 2>&1"])
        run_quiet(["wsl", "bash", "-c", "rm -f ~/vllm_last.log"])
        title = "vLLM Engine - " + v["model"].split("/")[-1]
        ps = f"$host.UI.RawUI.WindowTitle = '{title}'; wsl bash -c '{vllm_script(v)}'"
        self.vllm_window = subprocess.Popen(["powershell", "-NoExit", "-Command", ps], creationflags=NEW_CONSOLE)
        self.vllm_started_at = time.time()
        self.open_gui_when_ready = then_gui
        self._set("vLLM", ORANGE, "starting...")

    def start_everything(self):
        if not os.path.exists(self.s["drive"] + "\\workspace"):
            self.log("Z: isn't connected. Connect it in the window that opens, then press Start everything again.", "err")
            self.connect_drive()
            return
        self.start_vllm(then_gui=True)

    def _stop_vllm_blocking(self):
        run_quiet(["wsl", "-u", "root", "bash", "-c",
                   "fuser -k -9 8001/tcp >/dev/null 2>&1; pkill -9 -f '[v]llm serve' >/dev/null 2>&1"])
        if self.vllm_window and self.vllm_window.poll() is None:
            run_quiet(["taskkill", "/F", "/T", "/PID", str(self.vllm_window.pid)])
        # Also close a vLLM window started by Launch_GUI.bat (match its command line, not ours).
        run_quiet(["powershell", "-NoProfile", "-Command",
                   "$p = '*vllm' + ' serve*'; Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
                   "Where-Object { $_.CommandLine -like $p } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
        self.vllm_window = None
        for _ in range(20):
            if not port_open("127.0.0.1", 8001, 0.5):
                return True
            time.sleep(0.5)
        return False

    def stop_vllm(self):
        self.vllm_started_at = None
        self.open_gui_when_ready = False

        def work():
            self.post("log", "Stopping vLLM...")
            ok = self._stop_vllm_blocking()
            self.post("log", "vLLM stopped." if ok else "vLLM's port is still busy; try again.", "ok" if ok else "err")
        self.in_thread(work)

    def restart_vllm(self):
        v = self.save_form(quiet=True)
        if v is None:
            return

        def work():
            self.post("log", "Restarting vLLM with the settings above...")
            self._stop_vllm_blocking()
            self.post("call", lambda: self.start_vllm())
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

    def open_vllm_log(self):
        code, home = run_quiet(["wsl", "bash", "-c", "wslpath -w ~/vllm_last.log"])
        path = home.strip().splitlines()[-1] if code == 0 and home.strip() else ""
        if path:
            subprocess.Popen(["notepad", path])
        else:
            self.log("Couldn't find the vLLM log in WSL.", "err")

    # ------------------------------------------------------------------ cluster actions

    def connect_drive(self):
        cmd = (f"echo Connecting {self.s['drive']} to {self.s['share']}. Enter the share password for "
               f"'{self.s['ssh_user']}' when asked. && net use {self.s['drive']} {self.s['share']} "
               f"/user:{self.s['ssh_user']} /persistent:yes && echo Done. You can close this window.")
        subprocess.Popen(["cmd", "/k", cmd], creationflags=NEW_CONSOLE)
        self.log("Opened a window to connect the Z: drive.")

    def open_agent_gui(self):
        ws = os.path.join(self.s["drive"] + "\\", "workspace")
        if not os.path.exists(os.path.join(ws, "agent_gui.py")):
            self.log("Z: isn't connected, so the agent GUI can't start. Connect it first.", "err")
            self.connect_drive()
            return
        if self._pid_alive(GUI_PID_FILE):
            self.log("The agent GUI is already running.")
            return
        python = os.path.join(self.s["venv"], "Scripts", "python.exe")
        # A hidden console, so the GUI's own child processes (ssh, the pipeline) don't flash windows.
        subprocess.Popen([python, os.path.join(ws, "agent_gui.py")], cwd=ws, creationflags=NO_WINDOW)
        self.log("Opened the agent GUI.", "ok")

    def reset_pipeline(self):
        if not messagebox.askyesno("Reset pipeline", "Stop the agent GUI and every running task, clear "
                                                     "their records and test containers, and reopen the GUI?"):
            return

        def work():
            import glob
            for pid_file in [GUI_PID_FILE] + glob.glob(PIPELINE_PID_GLOB):
                try:
                    with open(pid_file) as f:
                        pid = int(f.read().strip())
                except (OSError, ValueError):
                    continue
                if self._pid_alive(pid_file):
                    run_quiet(["taskkill", "/F", "/T", "/PID", str(pid)])
                    self.post("log", f"Stopped process {pid}.")
                try:
                    os.remove(pid_file)
                except OSError:
                    pass
            try:
                import redis
                r = redis.Redis(host=self.s["node2_ip"], socket_timeout=3, decode_responses=True)
                # Mark every run still listed as running as stopped, so nothing shows as running.
                stopped = 0
                for key in r.zrevrange("workflow:tasks", 0, 50):
                    if r.hget(key, "status") == "RUNNING":
                        r.hset(key, mapping={"status": "STOPPED", "phase": "stopped by Reset pipeline"})
                        stopped += 1
                r.delete("workflow:langgraph:001", "workflow:active")
                self.post("log", f"Cleared the run records in Redis ({stopped} marked stopped).")
            except Exception as e:
                self.post("log", f"Couldn't clear Redis ({e}).", "err")
            code, out = run_quiet(self.ssh(self.s["node2_ip"], "docker ps -aq --filter name=agent- | "
                                           "xargs -r docker rm -f | wc -l"), timeout=60)
            if code == 0:
                self.post("log", f"Removed {out.strip() or 0} leftover test container(s) on Node 2.")
            time.sleep(1)
            self.post("call", self.open_agent_gui)
        self.in_thread(work)

    def restart_node2(self):
        self.stream(self.ssh(self.s["node2_ip"],
                             "pkill -f '^python3 /mnt/blackboard/workspace/agent_dashboard.py'; "
                             "cd /mnt/blackboard/docker && docker compose down --remove-orphans && "
                             "docker compose up -d && docker ps --format '{{.Names}}: {{.Status}}'"),
                    "Restarting Node 2 services")

    def restart_node3(self):
        cmd = (f"echo Restarting Ollama on Node 3. Enter the sudo password for '{self.s['ssh_user']}' when asked. && "
               f"ssh -t {self.s['ssh_user']}@{self.s['node3_ip']} \"sudo systemctl restart ollama\" && "
               "echo Done. Back in the launcher, press Warm up Node 3 models. You can close this window.")
        subprocess.Popen(["cmd", "/k", cmd], creationflags=NEW_CONSOLE)
        self.log("Opened a window to restart Ollama on Node 3. Afterwards, press Warm up Node 3 models.")

    def warm_node3(self):
        def work():
            url = f"http://{self.s['node3_ip']}:11434"
            worker, embedder, ctx = self.s["worker_model"], self.s["embed_model"], self.s["ollama_num_ctx"]
            try:
                self.post("log", f"Loading {worker}...")
                requests.post(f"{url}/api/generate", timeout=300, json={
                    "model": worker, "prompt": "warmup", "stream": False, "think": False,
                    "keep_alive": -1, "options": {"num_ctx": ctx}}).raise_for_status()
                self.post("log", f"Loading {embedder}...")
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

    # ------------------------------------------------------------------ files

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


def selftest():
    root = tk.Tk()
    root.withdraw()
    app = Launcher(root)
    st = app._collect_status()
    app._show_status(st)
    print("command:", vllm_script(app.read_form()))
    print("status:", {k: (v if k not in ("card",) else (v or {}).get("id")) for k, v in st.items()})
    print("labels:", " | ".join(lbl.cget("text") for _, lbl in app.dots.values()))
    print("LAUNCHER_SELF_TEST_PASSED")
    root.destroy()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        root = tk.Tk()
        Launcher(root)
        root.mainloop()
