"""Local control panel for the incident responder.

Runs a small HTTP server on 127.0.0.1 that serves an interactive page: start the
cluster, break the app on demand, watch the responder detect/diagnose/fix it, and
approve or reject the proposed change yourself.

  python src/server.py          then open http://127.0.0.1:8club  (see PORT below)

Security note, and it mirrors the system's own design: the browser never sends a
command. It sends an action *id*, and the server looks that id up in a fixed
ALLOWLIST. There is no code path that executes arbitrary input, and the socket is
bound to loopback only. The control panel is bounded the same way the remediator is.
"""

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import audit
import dashboard
from watcher import get_pod_signals, evaluate
from controller import propose, execute
from diagnostician import current_model, set_model, LLM_PROVIDER
from ui import PAGE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.getenv("PANEL_PORT", "8420"))

# The only things this panel can run. Keys are what the browser may ask for;
# values are argv lists (never shell strings - nothing to interpolate or escape).
ALLOWLIST = {
    "cluster-up":   (["bash", "scripts/dev.sh", "cluster-up"],  "Create the local kind cluster"),
    "cluster-down": (["bash", "scripts/dev.sh", "cluster-down"], "Delete the local kind cluster"),
    "deploy":       (["kubectl", "apply", "-f", "manifests/sample-app.yaml"], "Deploy the sample app"),
    "status":       (["kubectl", "get", "pods", "-l", "app=sample-app"], "List the app's pods"),
    "crashloop":    (["bash", "scenarios/crashloop.sh"], "Break it: bad nginx config"),
    "oom":          (["bash", "scenarios/oom.sh"],       "Break it: exceed the memory limit"),
    "rollout":      (["bash", "scenarios/rollout.sh"],   "Break it: roll out a bad image"),
    "reset":        (["bash", "scenarios/reset.sh"],     "Restore the app to healthy"),
    "report":       (["python", "src/main.py", "dashboard"], "Write the static HTML report"),
    "rbac":         (["kubectl", "apply", "-f", "manifests/rbac.yaml"], "Apply the two least-privilege identities"),
    "rbac-check":   (["bash", "scripts/rbac-check.sh"], "Prove the read-only identity cannot write"),
}

_jobs = {}
_jobs_lock = threading.Lock()
_pending = {"proposal": None, "detected_at": None}


def start_job(action_id: str) -> int:
    """Run an allowlisted command in the background, streaming output into memory."""
    argv, _ = ALLOWLIST[action_id]
    with _jobs_lock:
        job_id = len(_jobs) + 1
        _jobs[job_id] = {"lines": [f"$ {' '.join(argv)}"], "done": False, "code": None}

    def run():
        try:
            proc = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in proc.stdout:
                with _jobs_lock:
                    _jobs[job_id]["lines"].append(line.rstrip("\n"))
            proc.wait()
            code = proc.returncode
        except Exception as e:                      # noqa: BLE001 - surfaced to the UI
            with _jobs_lock:
                _jobs[job_id]["lines"].append(f"error: {e}")
            code = 1
        with _jobs_lock:
            _jobs[job_id]["done"] = True
            _jobs[job_id]["code"] = code

    threading.Thread(target=run, daemon=True).start()
    return job_id


def available_models() -> list[str]:
    """Models this machine can actually run, from `ollama list`.

    Returned to the browser so the picker offers real choices; switching is
    validated against this same list server-side, so the client cannot name an
    arbitrary model any more than it can name an arbitrary command.
    """
    if LLM_PROVIDER != "ollama":
        # Hosted providers have no local inventory to enumerate; offer what is
        # configured rather than guessing at a catalogue that changes over time.
        return [current_model()] if current_model() else []
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    names = []
    for line in out.stdout.splitlines()[1:]:          # skip the header row
        name = line.split()[0] if line.split() else ""
        if name:
            names.append(name)
    return names


def cluster_state() -> dict:
    """Current pods and incident, or a flag that the cluster is unreachable."""
    try:
        signals = get_pod_signals()
    except RuntimeError as e:
        return {"reachable": False, "error": str(e)[:200], "pods": [], "incident": None}
    incident = evaluate(signals)
    return {
        "reachable": True,
        "pods": [s.model_dump() for s in signals],
        "incident": None if incident is None else {
            "symptom": incident.symptom, "summary": incident.summary},
    }


def history() -> dict:
    events = audit.read_events()
    groups = dashboard.group_incidents(events)
    ev = dashboard.latest_eval()
    return {
        "summary": dashboard.summarise(groups),
        "incidents": [{k: g[k] for k in
                       ("ts", "symptom", "root_cause", "action", "confidence",
                        "mttr", "recovered", "policy_reason", "stages",
                        "model", "diagnosis_seconds")}
                      for g in reversed(groups[-12:])],
        "metrics": (ev or {}).get("summary") or [],
    }


def pending_view() -> dict | None:
    p = _pending["proposal"]
    if not p:
        return None
    d = p.get("diagnosis")
    return {
        "symptom": p["incident"].symptom,
        "allowed": p["allowed"],
        "reason": p["reason"],
        "error": p.get("error"),
        "command": " ".join(p["command"]) if p.get("command") else None,
        "preview": p.get("preview", ""),
        "root_cause": getattr(d, "root_cause", None),
        "action": getattr(getattr(d, "proposed_action", None), "type", None),
        "confidence": getattr(d, "confidence", None),
        "reasoning": getattr(d, "reasoning", None),
        "evidence": getattr(d, "evidence", None) or [],
        "model": (p.get("meta") or {}).get("model"),
        "diagnosis_seconds": (p.get("meta") or {}).get("seconds"),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):          # keep the terminal clean
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/state":
            models = available_models()
            self._send({"cluster": cluster_state(), **history(),
                        "pending": pending_view(),
                        "models": models, "model": current_model(),
                        "provider": LLM_PROVIDER,
                        "actions": {k: v[1] for k, v in ALLOWLIST.items()},
                        "commands": {k: " ".join(v[0]) for k, v in ALLOWLIST.items()}})
        elif u.path == "/api/job":
            q = parse_qs(u.query)
            jid = int(q.get("id", ["0"])[0]); frm = int(q.get("from", ["0"])[0])
            with _jobs_lock:
                job = _jobs.get(jid)
                if not job:
                    return self._send({"error": "no such job"}, 404)
                self._send({"lines": job["lines"][frm:], "next": len(job["lines"]),
                            "done": job["done"], "code": job["code"]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or "{}")

        if u.path == "/api/action":
            action = payload.get("id")
            # The allowlist is the whole security model: an unknown id is refused,
            # and no command text ever crosses the wire.
            if action not in ALLOWLIST:
                return self._send({"error": f"action '{action}' is not allowed"}, 400)
            return self._send({"job": start_job(action)})

        if u.path == "/api/model":
            name = payload.get("name", "")
            if name not in available_models():
                return self._send({"error": f"model '{name}' is not installed"}, 400)
            set_model(name)
            audit.log_event("model_selected", {"model": name})
            return self._send({"model": current_model()})

        if u.path == "/api/propose":
            try:
                signals = get_pod_signals()
            except RuntimeError as e:
                return self._send({"error": str(e)[:200]}, 503)
            # Wait a little: the watcher ignores pods that are merely starting, so a
            # failure injected seconds ago has not shown evidence yet.
            deadline = time.time() + 30
            incident = evaluate(signals)
            while incident is None and time.time() < deadline:
                time.sleep(3)
                try:
                    incident = evaluate(get_pod_signals())
                except RuntimeError:
                    break
            if incident is None:
                _pending["proposal"] = None
                return self._send({"error": "nothing is broken - inject a failure first"}, 400)
            _pending["detected_at"] = time.time()
            _pending["proposal"] = propose(incident)
            return self._send({"pending": pending_view()})

        if u.path == "/api/decide":
            p = _pending["proposal"]
            if not p or not p.get("command"):
                return self._send({"error": "no approvable proposal"}, 400)
            if not payload.get("approve"):
                audit.log_event("approval", {"approved": False, "reason": "declined by operator"})
                _pending["proposal"] = None
                return self._send({"result": {"declined": True}})
            result = execute(p, detected_at=_pending["detected_at"],
                             approval_reason="approved by operator (control panel)")
            _pending["proposal"] = None
            return self._send({"result": result})

        self._send({"error": "not found"}, 404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"control panel: http://127.0.0.1:{PORT}   (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
