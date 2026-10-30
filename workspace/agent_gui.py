"""Agent Control GUI: chat with the models, then dispatch pipeline runs and watch them live.

Two tabs:
  Chat       - talk a task through with the Node 1 model (vLLM) or Node 3's helper (Ollama).
               "Make task from chat" turns the conversation into a goal, target file and
               network setting on the Task tab, for you to review before dispatching.
  Task & Log - the goal form, attachments and the live pipeline log.

Tk isn't thread-safe, so background threads (pipeline output reader, chat streaming, Redis
poller) only put messages on a queue, and the Tk main loop drains it every 50 ms. Writes its
PID to %TEMP%\\agent_gui.pid so Reset_Cluster.bat can stop exactly this process.
"""
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, scrolledtext, ttk

import requests

import config

PIPELINE = os.path.join(config.WORKSPACE, "run_langgraph_pipeline.py")
GUI_PID_FILE = os.path.join(tempfile.gettempdir(), "agent_gui.pid")
GOAL_FILE = os.path.join(tempfile.gettempdir(), "agent_gui_goal.txt")

BG, PANEL, FIELD, TEXT, MUTED = "#1e1e1e", "#2d2d2d", "#252526", "#d4d4d4", "#8a8a8a"

NODE1_LABEL = f"Node 1 - {config.LLM_MODEL.split('/')[-1]} (RTX 4090)"
NODE3_LABEL = f"Node 3 - {config.WORKER_MODEL} (RTX 2070)"

CHAT_SYSTEM = (
    "You are the planning assistant for a home-lab AI cluster. Talk with the user, answer questions, "
    "and help them shape tasks for the autonomous coding pipeline.\n"
    "About the pipeline: it writes or edits ONE Python file in the workspace, runs it as "
    f"`python3 <file> --test` in a throwaway Docker container (Python {config.SANDBOX_PYTHON} standard "
    f"library plus {', '.join(config.SANDBOX_PACKAGES)}; no network unless the user allows LAN access; "
    f"{config.SANDBOX_TIMEOUT} second limit), checks the output against acceptance checks, and only "
    "then saves the file. Inside the sandbox the script runs in /work (a writable scratch folder) and "
    "can read the workspace at /workspace, which lives on Node 2's 5 TB blackboard volume.\n"
    f"About the cluster: Node 1 ({config.NODE1_IP}) runs vLLM on an RTX 4090. Node 2 ({config.NODE2_IP}) "
    f"runs Redis on {config.REDIS_PORT}, Qdrant on {config.QDRANT_PORT}, the dashboard on "
    f"{config.DASHBOARD_PORT} and the Docker sandbox. Node 3 ({config.NODE3_IP}) runs Ollama on 11434 "
    "with an RTX 2070.\n"
    "When helping with a task, ask about anything ambiguous, and suggest a file name, concrete "
    "requirements, and what --test mode should print to prove it works. Keep answers concise."
)

DRAFT_PROMPT = (
    "Turn this conversation into a task for the coding pipeline. Reply in exactly this format and "
    "nothing else:\n"
    "TARGET: <file_name.py>\n"
    "NETWORK: <yes if the script must reach other hosts, otherwise no>\n"
    "GOAL:\n"
    "<what the script must do: inputs, outputs, edge cases, and what --test mode must print or check "
    "to prove it works>"
)


class AgentControlGUI:
    def __init__(self, root, write_pid=True):
        self.root = root
        self.root.title("Cluster Orchestrator GUI - Compton / Blackboard / Worker")
        self.root.geometry("1000x860")
        self.root.configure(bg=BG)
        self.msgs = queue.Queue()
        self.proc = None
        self.run_gen = 0        # increases per run; output from older runs is ignored
        self.stopped_gen = -1
        self.attachments = []
        self.allow_network = tk.BooleanVar(value=False)
        self.chat_think = tk.BooleanVar(value=False)
        self.chat_attach = tk.BooleanVar(value=False)
        self.chat_history = []  # [{"role": "user"|"assistant", "content": ...}]
        self.chat_gen = 0
        self.chat_busy = False
        self.chat_stop = threading.Event()
        self._vllm_cache = None
        self.write_pid = write_pid
        self._build_ui()
        if write_pid:
            self._write_pid_file()
        threading.Thread(target=self._redis_poller, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._drain)

    # ------------------------------------------------------------------ layout

    def _label(self, parent, text, bold=False, muted=False):
        return tk.Label(parent, text=text, bg=BG, fg=MUTED if muted else "#cccccc",
                        font=("Segoe UI", 9 if muted else 10, "bold" if bold else "normal"))

    def _button(self, parent, text, command, color, **kw):
        return tk.Button(parent, text=text, command=command, bg=color, fg="white",
                         activebackground=color, activeforeground="white",
                         font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=10, **kw)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground="#cccccc", padding=(16, 6),
                        font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#0275d8")],
                  foreground=[("selected", "white")])
        style.configure("TCombobox", fieldbackground=FIELD, background=PANEL, foreground=TEXT,
                        arrowcolor=TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)],
                  selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#0275d8")

        top = tk.Frame(self.root, bg=PANEL, pady=8, padx=10)
        top.pack(fill=tk.X)
        self.status_lbl = tk.Label(top, text="Cluster Status: IDLE", fg="#4CAF50", bg=PANEL,
                                   font=("Segoe UI", 11, "bold"))
        self.status_lbl.pack(side=tk.LEFT)
        self.redis_lbl = tk.Label(top, text="Redis: connecting...", fg="#5bc0de", bg=PANEL,
                                  font=("Segoe UI", 9))
        self.redis_lbl.pack(side=tk.LEFT, padx=(16, 0))
        for text, command, color in (("Restart Pipeline", self.restart_pipeline, "#d9534f"),
                                     ("Stop", self.stop_pipeline, "#8a6d3b"),
                                     ("View Dashboard", lambda: webbrowser.open(config.DASHBOARD_URL), "#17a2b8"),
                                     ("Dispatch Run", self.start_pipeline, "#0275d8")):
            self._button(top, text, command, color).pack(side=tk.RIGHT, padx=4)

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 8))
        self.chat_tab = tk.Frame(self.tabs, bg=BG)
        self.task_tab = tk.Frame(self.tabs, bg=BG)
        self.tabs.add(self.chat_tab, text="Chat")
        self.tabs.add(self.task_tab, text="Task & Log")
        self._build_chat(self.chat_tab)
        self._build_task(self.task_tab)

    def _build_chat(self, parent):
        opts = tk.Frame(parent, bg=BG, padx=10, pady=6)
        opts.pack(fill=tk.X)
        self._label(opts, "Model:").pack(side=tk.LEFT)
        self.chat_backend = ttk.Combobox(opts, state="readonly", width=40,
                                         values=[NODE1_LABEL, NODE3_LABEL])
        self.chat_backend.current(0)
        self.chat_backend.pack(side=tk.LEFT, padx=6)
        for text, var in (("Think step by step (slower)", self.chat_think),
                          ("Include attachments", self.chat_attach)):
            tk.Checkbutton(opts, text=text, variable=var, bg=BG, fg=TEXT, selectcolor=FIELD,
                           activebackground=BG, activeforeground=TEXT,
                           font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(8, 0))
        self._button(opts, "New chat", self.new_chat, "#3e3e42").pack(side=tk.RIGHT)
        self._button(opts, "Make task from chat", self.draft_task, "#3d8b3d").pack(side=tk.RIGHT, padx=6)

        self.chat_view = scrolledtext.ScrolledText(parent, bg="#0c0c0c", fg=TEXT, font=("Segoe UI", 10),
                                                   wrap=tk.WORD, relief=tk.FLAT, padx=10, pady=8,
                                                   state=tk.DISABLED)
        self.chat_view.pack(fill=tk.BOTH, expand=True, padx=10)
        self.chat_view.tag_config("you", foreground="#5bc0de", font=("Segoe UI", 10, "bold"))
        self.chat_view.tag_config("model", foreground="#9dff7a", font=("Segoe UI", 10, "bold"))
        self.chat_view.tag_config("think", foreground="#7a7a7a", font=("Segoe UI", 9, "italic"))
        self.chat_view.tag_config("info", foreground="#8a8a8a", font=("Segoe UI", 9, "italic"))
        self.chat_view.tag_config("error", foreground="#ff6b6b")

        row = tk.Frame(parent, bg=BG, padx=10, pady=6)
        row.pack(fill=tk.X)
        self.chat_input = tk.Text(row, height=4, bg=FIELD, fg=TEXT, insertbackground="white",
                                  font=("Segoe UI", 10), wrap=tk.WORD, relief=tk.FLAT)
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chat_input.bind("<Control-Return>", self._on_ctrl_enter)
        buttons = tk.Frame(row, bg=BG)
        buttons.pack(side=tk.LEFT, padx=(6, 0))
        self._button(buttons, "Send", self.send_chat, "#0275d8", width=9).pack()
        self._button(buttons, "Stop", self.stop_chat, "#8a6d3b", width=9).pack(pady=(4, 0))
        self.chat_status = tk.Label(parent, bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor=tk.W,
                                    text="Ctrl+Enter sends. Chatting never changes files; press "
                                         "'Make task from chat' when the task is clear.")
        self.chat_status.pack(fill=tk.X, padx=10, pady=(0, 6))

    def _build_task(self, parent):
        form = tk.Frame(parent, bg=BG, padx=10, pady=8)
        form.pack(fill=tk.X)
        self._label(form, "Agent Goal / Task Prompt:", bold=True).pack(anchor=tk.W)
        self.goal_entry = tk.Text(form, height=7, bg=FIELD, fg=TEXT, insertbackground="white",
                                  font=("Consolas", 10), wrap=tk.WORD, relief=tk.FLAT)
        self.goal_entry.pack(fill=tk.X, pady=(4, 6))

        row = tk.Frame(form, bg=BG)
        row.pack(fill=tk.X)
        self._label(row, "Target file:").pack(side=tk.LEFT)
        self.target_entry = tk.Entry(row, width=30, bg=FIELD, fg=TEXT, insertbackground="white",
                                     font=("Consolas", 10), relief=tk.FLAT)
        self.target_entry.pack(side=tk.LEFT, padx=6, ipady=2)
        self._label(row, "blank = the file named in the goal, or a new file", muted=True).pack(side=tk.LEFT)
        tk.Checkbutton(row, text="Allow LAN network in sandbox", variable=self.allow_network,
                       bg=BG, fg=TEXT, selectcolor=FIELD, activebackground=BG,
                       activeforeground=TEXT, font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        self._label(form, "Attachments (sent as separate context, not pasted into the goal):").pack(
            anchor=tk.W, pady=(8, 2))
        att = tk.Frame(form, bg=BG)
        att.pack(fill=tk.X)
        self.att_list = tk.Listbox(att, height=3, bg=FIELD, fg=TEXT, selectmode=tk.EXTENDED,
                                   relief=tk.FLAT, font=("Consolas", 9), activestyle="none")
        self.att_list.pack(side=tk.LEFT, fill=tk.X, expand=True)
        att_buttons = tk.Frame(att, bg=BG)
        att_buttons.pack(side=tk.LEFT, padx=(6, 0))
        for text, command in (("Add files...", self.add_attachments),
                              ("Remove", self.remove_attachments),
                              ("Clear", self.clear_attachments)):
            tk.Button(att_buttons, text=text, command=command, bg="#3e3e42", fg="white",
                      font=("Segoe UI", 8, "bold"), relief=tk.FLAT, width=11).pack(pady=1)

        console_frame = tk.Frame(parent, bg=BG, padx=10, pady=5)
        console_frame.pack(fill=tk.BOTH, expand=True)
        self._label(console_frame, "Real-Time Pipeline Execution Log:").pack(anchor=tk.W)
        self.console = scrolledtext.ScrolledText(console_frame, bg="#0c0c0c", fg="#00ff66",
                                                 font=("Consolas", 9), insertbackground="white",
                                                 relief=tk.FLAT)
        self.console.pack(fill=tk.BOTH, expand=True, pady=4)
        self.console.tag_config("err", foreground="#ff6b6b")
        self.console.tag_config("ok", foreground="#9dff7a")
        self.console.tag_config("node", foreground="#5bc0de")

    # ------------------------------------------------------------------ helpers (main thread)

    def log(self, text):
        s = text.lstrip()
        if s.startswith(("[!]", "[x]")) or "Traceback (most recent call last)" in s:
            tag = "err"
        elif s.startswith("[+]"):
            tag = "ok"
        elif s.startswith(("[Node:", "===")):
            tag = "node"
        else:
            tag = None
        if tag:
            self.console.insert(tk.END, text + "\n", tag)
        else:
            self.console.insert(tk.END, text + "\n")
        self.console.see(tk.END)

    def _set_status(self, text, color):
        self.status_lbl.config(text=text, fg=color)

    def _running(self):
        return self.proc is not None and self.proc.poll() is None

    # ------------------------------------------------------------------ chat (main thread)

    def _chat_write(self, text, tag=None):
        self.chat_view.config(state=tk.NORMAL)
        if tag:
            self.chat_view.insert(tk.END, text, tag)
        else:
            self.chat_view.insert(tk.END, text)
        self.chat_view.see(tk.END)
        self.chat_view.config(state=tk.DISABLED)

    def _on_ctrl_enter(self, _event):
        self.send_chat()
        return "break"

    def _backend(self):
        return "node3" if self.chat_backend.current() == 1 else "node1"

    def send_chat(self):
        if self.chat_busy:
            return
        text = self.chat_input.get("1.0", tk.END).strip()
        if not text:
            return
        self.chat_input.delete("1.0", tk.END)
        self.chat_history.append({"role": "user", "content": text})
        self._chat_write("\nYou\n", "you")
        self._chat_write(text + "\n")
        self._start_chat_request(list(self.chat_history), "chat")

    def draft_task(self):
        if self.chat_busy:
            return
        if not self.chat_history:
            self._chat_write("\nStart a conversation first, then press 'Make task from chat'.\n", "info")
            return
        self._chat_write("\nDrafting the task from this conversation...\n", "info")
        history = self.chat_history + [{"role": "user", "content": DRAFT_PROMPT}]
        self._start_chat_request(history, "draft")

    def stop_chat(self):
        if self.chat_busy:
            self.chat_stop.set()

    def new_chat(self):
        if self.chat_busy:
            self.chat_stop.set()
        self.chat_gen += 1          # ignore anything still streaming from the old chat
        self.chat_busy = False
        self.chat_history = []
        self.chat_view.config(state=tk.NORMAL)
        self.chat_view.delete("1.0", tk.END)
        self.chat_view.config(state=tk.DISABLED)
        self.chat_status.config(text="New chat. Ctrl+Enter sends.")

    def _start_chat_request(self, history, mode):
        backend = self._backend()
        think = bool(self.chat_think.get()) and mode == "chat"
        label = NODE3_LABEL if backend == "node3" else NODE1_LABEL
        self.chat_busy = True
        self.chat_stop.clear()
        self.chat_gen += 1
        self._shown_think = False
        self._shown_answer = False
        if mode == "chat":
            self._chat_write(f"\n{label.split(' (')[0]}\n", "model")
        self.chat_status.config(text=f"{label} is {'thinking' if think else 'replying'}... (Stop to interrupt)")
        threading.Thread(target=self._chat_worker,
                         args=(self.chat_gen, backend, self._chat_system_prompt(), history, think, mode),
                         daemon=True).start()

    def _chat_system_prompt(self):
        system = CHAT_SYSTEM
        if self.chat_attach.get() and self.attachments:
            parts = []
            for p in self.attachments:
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        content = f.read(30000)
                except OSError as e:
                    content = f"(couldn't read this file: {e})"
                parts.append(f"--- {os.path.basename(p)} ---\n{content}")
            system += "\n\nFiles the user attached:\n" + "\n\n".join(parts)
        return system

    def _handle_chat_msg(self, kind, payload):
        mode, data = payload
        if kind == "chat_delta" and mode == "chat":
            part, text = data
            if part == "think":
                if not self._shown_think:
                    self._chat_write("Thinking: ", "think")
                    self._shown_think = True
                self._chat_write(text, "think")
            else:
                if self._shown_think and not self._shown_answer:
                    self._chat_write("\n\n")
                self._shown_answer = True
                self._chat_write(text)
        elif kind == "chat_done":
            text, stopped = data
            self.chat_busy = False
            if mode == "chat":
                if text.strip():
                    self.chat_history.append({"role": "assistant", "content": text.strip()})
                self._chat_write("\n")
                if stopped:
                    self._chat_write("[stopped]\n", "info")
                self.chat_status.config(text="Ctrl+Enter sends. 'Make task from chat' fills in the Task tab.")
            elif stopped:
                self._chat_write("Drafting stopped.\n", "info")
            else:
                self._apply_draft(text)
        elif kind == "chat_error":
            self.chat_busy = False
            self._chat_write(f"\n{data}\n", "error")
            self.chat_status.config(text="The request failed; your message is back in the input box.")
            if mode == "chat" and self.chat_history and self.chat_history[-1]["role"] == "user":
                self.chat_input.insert("1.0", self.chat_history.pop()["content"])

    def _apply_draft(self, text):
        target = re.search(r"^\s*TARGET:\s*`?([A-Za-z0-9_\-]+\.py)`?", text, re.M | re.I)
        network = re.search(r"^\s*NETWORK:\s*(yes|no)", text, re.M | re.I)
        goal = re.search(r"^\s*GOAL:\s*(.*)\Z", text, re.S | re.M | re.I)
        goal_text = (goal.group(1) if goal else text).strip()
        self.goal_entry.delete("1.0", tk.END)
        self.goal_entry.insert("1.0", goal_text)
        if target:
            self.target_entry.delete(0, tk.END)
            self.target_entry.insert(0, target.group(1))
        if network:
            self.allow_network.set(network.group(1).lower() == "yes")
        self._chat_write("Task drafted. It's on the Task & Log tab for you to review.\n", "info")
        self.chat_status.config(text="Task drafted. Review it on the Task & Log tab, then press Dispatch Run.")
        self.tabs.select(self.task_tab)
        self.log("[+] Task drafted from the chat. Review the goal, target file and network setting, "
                 "then press Dispatch Run.")

    # ------------------------------------------------------------------ chat (background thread)

    def _vllm_info(self):
        if self._vllm_cache is None:
            try:
                card = requests.get(config.LLM_BASE_URL + "/v1/models", timeout=5).json()["data"][0]
            except Exception as e:
                raise RuntimeError(f"vLLM isn't reachable at {config.LLM_BASE_URL} ({e}). Start it with "
                                   "Launch_GUI.bat, or pick Node 3 in the Model list.")
            self._vllm_cache = (card["id"], int(card.get("max_model_len") or config.LLM_FALLBACK_CONTEXT))
        return self._vllm_cache

    @staticmethod
    def _fit(system, history, budget_chars):
        """Drop the oldest messages (and cut oversized attachments) to fit the context window."""
        if len(system) > budget_chars * 0.6:
            system = system[:int(budget_chars * 0.6)] + "\n[attachments cut to fit the context window]"
        msgs = list(history)
        while len(msgs) > 1 and len(system) + sum(len(m["content"]) for m in msgs) > budget_chars:
            msgs.pop(0)
        return [{"role": "system", "content": system}] + msgs

    def _stream_chat(self, backend, system, history, think):
        """Yield ("think" | "content", text) pieces from the chosen model."""
        if backend == "node1":
            from openai import OpenAI
            model, ctx = self._vllm_info()
            max_tokens = min(8000 if think else 3000, ctx // 2)
            messages = self._fit(system, history, (ctx - max_tokens - 300) * 3)
            client = OpenAI(base_url=config.LLM_BASE_URL + "/v1", api_key="none", timeout=900, max_retries=0)
            stream = client.chat.completions.create(
                model=model, messages=messages, stream=True, max_tokens=max_tokens,
                temperature=config.LLM_TEMPERATURE, top_p=config.LLM_TOP_P,
                extra_body={"top_k": config.LLM_TOP_K, "chat_template_kwargs": {"enable_thinking": think}})
            try:
                for chunk in stream:
                    if self.chat_stop.is_set():
                        break
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                    if reasoning:
                        yield "think", reasoning
                    if delta.content:
                        yield "content", delta.content
            finally:
                stream.close()
        else:
            max_tokens = 3000 if think else 1500
            messages = self._fit(system, history, (config.OLLAMA_NUM_CTX - max_tokens - 300) * 3)
            payload = {"model": config.WORKER_MODEL, "messages": messages, "stream": True,
                       "keep_alive": config.OLLAMA_KEEP_ALIVE,
                       "options": {"num_ctx": config.OLLAMA_NUM_CTX, "temperature": 0.7,
                                   "num_predict": max_tokens}}
            if config.WORKER_THINK is not None:
                payload["think"] = think
            res = requests.post(f"{config.OLLAMA_URL}/api/chat", json=payload, stream=True, timeout=900)
            try:
                res.raise_for_status()
                for line in res.iter_lines():
                    if self.chat_stop.is_set():
                        break
                    if not line:
                        continue
                    data = json.loads(line)
                    msg = data.get("message") or {}
                    if msg.get("thinking"):
                        yield "think", msg["thinking"]
                    if msg.get("content"):
                        yield "content", msg["content"]
                    if data.get("done"):
                        break
            finally:
                res.close()

    def _chat_worker(self, gen, backend, system, history, think, mode):
        text = ""
        try:
            for part, piece in self._stream_chat(backend, system, history, think):
                if part == "content":
                    text += piece
                self.msgs.put(("chat_delta", gen, (mode, (part, piece))))
            self.msgs.put(("chat_done", gen, (mode, (text, self.chat_stop.is_set()))))
        except Exception as e:
            self._vllm_cache = None   # re-check the server next time
            self.msgs.put(("chat_error", gen, (mode, f"Chat request failed: {e}")))

    # ------------------------------------------------------------------ attachments

    def add_attachments(self):
        paths = filedialog.askopenfilenames(
            initialdir=config.WORKSPACE, title="Select files to send as context",
            filetypes=[("Text & Code Files",
                        "*.py;*.json;*.txt;*.md;*.log;*.sh;*.yml;*.yaml;*.ini;*.cfg;*.toml;*.csv"),
                       ("All Files", "*.*")])
        added = 0
        for p in paths:
            p = os.path.normpath(p)
            if p not in self.attachments:
                self.attachments.append(p)
                self.att_list.insert(tk.END, p)
                added += 1
        if added:
            self.log(f"[+] Added {added} attachment(s).")

    def remove_attachments(self):
        for i in reversed(self.att_list.curselection()):
            self.att_list.delete(i)
            del self.attachments[i]

    def clear_attachments(self):
        self.att_list.delete(0, tk.END)
        self.attachments.clear()

    # ------------------------------------------------------------------ pipeline control

    def start_pipeline(self):
        self.tabs.select(self.task_tab)
        if self._running():
            self.log("[!] A pipeline run is already in progress.")
            return
        goal = self.goal_entry.get("1.0", tk.END).strip()
        if not goal:
            self.log("[!] Enter a goal before dispatching (or use 'Make task from chat').")
            return
        try:
            # Passing the goal in a file avoids Windows' command-line length limit.
            with open(GOAL_FILE, "w", encoding="utf-8") as f:
                f.write(goal)
        except OSError as e:
            self.log(f"[!] Couldn't write the goal file: {e}")
            return
        cmd = [sys.executable, "-u", PIPELINE, f"--goal-file={GOAL_FILE}"]
        target = self.target_entry.get().strip()
        if target:
            cmd.append(f"--target={target}")
        cmd += [f"--attach={p}" for p in self.attachments]
        if self.allow_network.get():
            cmd.append("--allow-network")
        try:
            # Started here on the main thread, so two quick clicks can't launch two runs.
            self.proc = subprocess.Popen(
                cmd, cwd=config.WORKSPACE, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                bufsize=1, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        except OSError as e:
            self.log(f"[!] Couldn't start the pipeline: {e}")
            return
        self.run_gen += 1
        self.console.delete("1.0", tk.END)
        self.log(f"[*] Dispatched pipeline run (PID {self.proc.pid}).")
        self._set_status("Cluster Status: RUNNING", "#f0ad4e")
        threading.Thread(target=self._read_output, args=(self.proc, self.run_gen), daemon=True).start()

    def stop_pipeline(self, quiet=False):
        proc = self.proc
        if proc is None or proc.poll() is not None:
            if not quiet:
                self.log("[i] No pipeline run is active.")
            return
        self.stopped_gen = self.run_gen
        self.log("[!] Stopping the pipeline run...")
        if os.name == "nt":
            # /T also ends child processes such as an in-flight ssh to the sandbox.
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    def restart_pipeline(self):
        self.log("[!] Restart requested.")
        self.stop_pipeline(quiet=True)
        self.start_pipeline()

    def _run_finished(self, gen, rc):
        if gen == self.stopped_gen:
            self._set_status("Cluster Status: STOPPED", "#f0ad4e")
        elif rc == 0:
            self._set_status("Cluster Status: PASSED", "#4CAF50")
        elif rc == 1:
            self._set_status("Cluster Status: FAILED (checks not met)", "#d9534f")
        else:
            self._set_status(f"Cluster Status: ERROR (exit {rc})", "#d9534f")

    # ------------------------------------------------------------------ background threads

    def _read_output(self, proc, gen):
        try:
            for line in iter(proc.stdout.readline, ""):
                self.msgs.put(("log", gen, line.rstrip("\r\n")))
        except Exception as e:
            self.msgs.put(("log", gen, f"[!] Output reader stopped: {e}"))
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            self.msgs.put(("done", gen, proc.wait()))

    def _redis_poller(self):
        client = config.get_redis(decode_responses=True, timeout=2)
        sent_goal = False
        while True:
            try:
                data = client.hgetall(config.LATEST_KEY)
                self.msgs.put(("redis", 0, data))
                if not sent_goal:
                    self.msgs.put(("last_goal", 0, data.get("goal", "")))
                    sent_goal = True
            except Exception as e:
                self.msgs.put(("redis_err", 0, str(e)))
            time.sleep(2)

    def _drain(self):
        try:
            for _ in range(500):
                kind, gen, payload = self.msgs.get_nowait()
                if kind == "log":
                    if gen == self.run_gen:
                        self.log(payload)
                elif kind == "done":
                    if gen == self.run_gen:
                        self._run_finished(gen, payload)
                elif kind.startswith("chat_"):
                    if gen == self.chat_gen:
                        self._handle_chat_msg(kind, payload)
                elif kind == "redis":
                    self._show_redis(payload)
                elif kind == "redis_err":
                    self.redis_lbl.config(text=f"Redis: unreachable ({payload[:60]})", fg="#f0ad4e")
                elif kind == "last_goal":
                    if payload and not self.goal_entry.get("1.0", tk.END).strip():
                        self.goal_entry.insert(tk.END, payload)
        except queue.Empty:
            pass
        self.root.after(50, self._drain)

    def _show_redis(self, data):
        if not data:
            self.redis_lbl.config(text="Redis: connected, no runs yet", fg="#5bc0de")
            return
        status = data.get("status", "?")
        text = f"Last run: {status}"
        if status == "RUNNING" and data.get("phase"):
            text += f" - {data['phase']}"
        if data.get("target_file"):
            text += f" ({data['target_file']})"
        if status == "PASSED" and data.get("memory_sync"):
            text += " - stored in memory"
        self.redis_lbl.config(text=text, fg="#5bc0de")

    # ------------------------------------------------------------------ lifecycle

    def _write_pid_file(self):
        try:
            with open(GUI_PID_FILE, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass

    def _remove_pid_file(self):
        if not self.write_pid:
            return
        try:
            with open(GUI_PID_FILE) as f:
                mine = f.read().strip() == str(os.getpid())
            if mine:
                os.remove(GUI_PID_FILE)
        except OSError:
            pass

    def _on_close(self):
        if self._running():
            if not messagebox.askyesno("Run in progress",
                                       "A pipeline run is still going. Stop it and close the GUI?"):
                return
            self.stop_pipeline(quiet=True)
        self.chat_stop.set()
        self._remove_pid_file()
        self.root.destroy()


def main():
    selftest = "--selftest" in sys.argv
    root = tk.Tk()
    app = AgentControlGUI(root, write_pid=not selftest)
    if selftest:
        def finish():
            ok = app.console.winfo_exists() and app.chat_view.winfo_exists()
            print("GUI_SELF_TEST_PASSED" if ok else "GUI self-test failed")
            root.destroy()
        root.after(2500, finish)
    root.mainloop()


if __name__ == "__main__":
    main()
