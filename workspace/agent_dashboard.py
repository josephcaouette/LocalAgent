"""Telemetry dashboard for pipeline runs, served on Node 2 port 8080.

Runs as the 'dashboard' service in /mnt/blackboard/docker/docker-compose.yml,
so it restarts with Docker after a reboot. Reads the task index (a sorted set)
instead of KEYS, shows the newest runs, and refreshes every 10 seconds.

    python3 agent_dashboard.py          serve on port 8080
    python3 agent_dashboard.py --test   self-test on a spare port
"""
import argparse
import html
import http.server
import json
import socketserver
import threading
import time
import urllib.request

import config

STATUS_COLORS = {"PASSED": "#4CAF50", "FAILED": "#f44336", "ERROR": "#e05cff",
                 "RUNNING": "#ff9800", "PLANNED": "#ff9800", "STOPPED": "#b0a060", "LOST": "#8a8a8a"}


def fmt_secs(seconds):
    try:
        f = float(seconds)
    except (TypeError, ValueError):
        return ""
    s = int(f)
    if f < 10:
        return f"{f:.1f}s"
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {s % 3600 // 60:02d}m"

_redis = None
_backfilled = False


def redis_conn():
    global _redis
    if _redis is None:
        _redis = config.get_redis(decode_responses=True, timeout=3)
    return _redis


def _score_from_key(key):
    suffix = key.rsplit(":", 1)[-1]
    if suffix.isdigit():
        return int(suffix)                        # older keys use epoch seconds
    try:
        return int(time.mktime(time.strptime(suffix, "%Y%m%d-%H%M%S")))
    except ValueError:
        return 0


def backfill_index(r):
    """Index task records written before the index existed (SCAN, not KEYS)."""
    for key in r.scan_iter(match=config.TASK_KEY_PREFIX + "*", count=200):
        r.zadd(config.TASK_INDEX_KEY, {key: _score_from_key(key)}, nx=True)


def fetch_tasks(limit):
    global _backfilled
    r = redis_conn()
    if not _backfilled:
        if r.zcard(config.TASK_INDEX_KEY) == 0:
            backfill_index(r)
        _backfilled = True
    entries = r.zrevrange(config.TASK_INDEX_KEY, 0, limit - 1, withscores=True)
    if not entries:
        return []
    pipe = r.pipeline()
    for key, _ in entries:
        pipe.hgetall(key)
    records = pipe.execute()
    active = set(config.active_runs(r))
    now = time.time()
    tasks, expired = [], []
    for (key, score), data in zip(entries, records):
        if not data:
            expired.append(key)               # the record expired; drop it from the index
            continue
        data["_id"] = key.rsplit(":", 1)[-1]
        data["_started"] = int(float(data.get("started_at") or score or 0))
        running = data["_id"] in active
        if data.get("status") == "RUNNING" and not running and \
                now - float(data.get("updated_at") or 0) > config.ACTIVE_STALE_S:
            data["status"] = "LOST"           # its process ended without finishing
        if data.get("elapsed_s"):
            data["_took"] = fmt_secs(data["elapsed_s"])
        elif data["_started"]:
            end = now if running else float(data.get("updated_at") or data["_started"])
            data["_took"] = fmt_secs(end - data["_started"])
        tasks.append(data)
    if expired:
        r.zrem(config.TASK_INDEX_KEY, *expired)
    return tasks


def esc(value):
    return html.escape(str(value or ""))


def render_row(t):
    status = t.get("status", "")
    color = STATUS_COLORS.get(status, "#d4d4d4")
    status_html = f"<div style='color:{color};font-weight:bold'>{esc(status)}</div>"
    if t.get("phase") and status not in ("PASSED",):
        status_html += f"<div class='sub'>{esc(t['phase'])}</div>"
    if t.get("attempt"):
        status_html += f"<div class='sub'>attempt {esc(t['attempt'])}</div>"
    if t.get("profile"):
        status_html += f"<div class='sub'>accuracy {esc(config.accuracy_level(t['profile']))}</div>"
    if t.get("_took"):
        status_html += f"<div class='sub'>took {esc(t['_took'])}</div>"
    if t.get("memory_sync"):
        status_html += "<div class='sub'>memory updated</div>"
    try:
        timings = json.loads(t.get("timings") or "{}")
    except ValueError:
        timings = {}
    steps = [f"{k} {fmt_secs(v)}" for k, v in timings.items() if float(v) >= 0.5]
    if steps:
        status_html += f"<div class='sub'>{esc(' · '.join(steps))}</div>"

    goal_html = ""
    if t.get("target_file"):
        net = " &middot; network on" if t.get("allow_network") == "1" else ""
        goal_html += f"<div class='sub'>Target: <b>{esc(t['target_file'])}</b>{net}</div>"
    goal_html += f"<div class='goal-box'>{esc(t.get('goal'))}</div>"

    plan = t.get("plan", "")
    try:
        checks = json.loads(t.get("checks") or "[]")
    except ValueError:
        checks = []
    if checks:
        plan += "\n\nAcceptance checks:\n" + "\n".join(f"- {c}" for c in checks)

    output = t.get("execution_output") or t.get("output") or ""
    verdict = t.get("verdict", "")
    output_html = f"<pre>{esc(output)}</pre>"
    if verdict:
        output_html = f"<div class='verdict'>{esc(verdict)}</div>" + output_html

    return (f"<tr><td><span class='ts' data-ts='{t['_started']}'></span>"
            f"<div class='sub'>{esc(t['_id'])}</div></td>"
            f"<td>{goal_html}</td><td>{status_html}</td>"
            f"<td><pre>{esc(plan)}</pre></td><td>{output_html}</td></tr>")


def render_page():
    try:
        tasks = fetch_tasks(config.DASHBOARD_MAX_TASKS)
        redis_status = f"Redis connected, newest {len(tasks)} runs"
    except Exception as e:
        tasks, redis_status = [], f"Redis error: {e}"
    rows = "".join(render_row(t) for t in tasks) or (
        "<tr><td colspan='5' style='text-align:center;'>No tasks recorded in Redis yet.</td></tr>")
    return f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>Workflow Tasks - Telemetry</title>
<meta http-equiv='refresh' content='10'>
<style>
  body {{ font-family: Segoe UI, sans-serif; background: #1e1e1e; color: #d4d4d4; padding: 20px; }}
  h1 {{ color: #5bc0de; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 15px; table-layout: fixed; }}
  th, td {{ border: 1px solid #333; padding: 10px; text-align: left; vertical-align: top; word-break: break-word; }}
  th {{ background: #2d2d2d; color: #fff; }}
  th:nth-child(1) {{ width: 11%; }} th:nth-child(2) {{ width: 27%; }} th:nth-child(3) {{ width: 10%; }}
  th:nth-child(4) {{ width: 24%; }} th:nth-child(5) {{ width: 28%; }}
  tr:nth-child(even) {{ background: #252526; }}
  pre {{ background: #0c0c0c; color: #00ff66; padding: 8px; border-radius: 4px; overflow: auto; max-height: 250px; font-family: Consolas, monospace; white-space: pre-wrap; margin: 0; }}
  .goal-box {{ background: #161616; color: #e0e0e0; padding: 8px; border-radius: 4px; overflow: auto; max-height: 250px; font-family: Consolas, monospace; white-space: pre-wrap; font-size: 12px; margin-top: 4px; }}
  .sub {{ color: #9a9a9a; font-size: 12px; margin-top: 2px; }}
  .verdict {{ color: #e0e0e0; font-size: 12px; margin-bottom: 6px; white-space: pre-wrap; }}
</style></head><body>
<h1>Workflow Tasks Telemetry <span style='font-size:14px;color:#aaa;'>({esc(redis_status)})</span></h1>
<table><tr><th>Started</th><th>Goal</th><th>Status</th><th>Plan &amp; checks</th><th>Output &amp; verdict</th></tr>
{rows}
</table>
<script>
document.querySelectorAll('.ts').forEach(function (el) {{
  var t = parseInt(el.dataset.ts, 10);
  if (t > 0) {{ el.textContent = new Date(t * 1000).toLocaleString(); }}
}});
</script>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, ctype, body, head_only=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _handle(self, head_only):
        path = self.path.split("?", 1)[0]
        if path.startswith("/favicon"):
            self._send(204, "text/plain", b"", head_only)
            return
        if path not in ("/", "/index.html"):
            self._send(404, "text/plain; charset=utf-8", b"Not found", head_only)
            return
        try:
            body = render_page().encode("utf-8", errors="replace")
            self._send(200, "text/html; charset=utf-8", body, head_only)
        except Exception as e:
            self._send(500, "text/plain; charset=utf-8", f"Internal error: {e}".encode(), head_only)

    def do_GET(self):
        self._handle(head_only=False)

    def do_HEAD(self):
        self._handle(head_only=True)

    def log_message(self, fmt, *args):
        pass   # don't write a log line for every 10-second refresh


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_server(port):
    with Server(("", port), Handler) as httpd:
        print(f"Serving telemetry dashboard on port {port}...", flush=True)
        httpd.serve_forever()


def self_test():
    httpd = Server(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ok = resp.status == 200 and "Workflow Tasks" in body
    except Exception as e:
        print(f"Test failed with exception: {e}")
        return 1
    finally:
        httpd.shutdown()
    print("DASHBOARD_SELF_TEST_PASSED" if ok else "Test failed: unexpected page content")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the telemetry HTTP dashboard.")
    parser.add_argument("--test", action="store_true", help="run a self-test on a spare port")
    parser.add_argument("--port", type=int, default=config.DASHBOARD_PORT)
    args = parser.parse_args()
    raise SystemExit(self_test() if args.test else run_server(args.port))
