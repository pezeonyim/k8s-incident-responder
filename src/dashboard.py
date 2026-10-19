"""Build a self-contained HTML dashboard from the audit log.

Reads audit.jsonl (and the most recent eval run, if one exists) and renders a
single HTML file: headline numbers, every incident's pipeline, the metrics
table, and the raw audit trail. No network, no dependencies - open the file.

  python src/main.py dashboard
"""

import glob
import json
import os
from datetime import datetime

from audit import read_events

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pipeline stages, in order, with the audit event that proves each one happened.
STAGES = [
    ("Detected", "incident_detected"),
    ("Diagnosed", "diagnosis"),
    ("Policy", "policy_decision"),
    ("Approved", "approval"),
    ("Applied", "remediation_applied"),
    ("Verified", "verification"),
]


# ---------------------------------------------------------------- data shaping

def group_incidents(events: list[dict]) -> list[dict]:
    """Split a flat event stream into one group per incident."""
    groups, current = [], None
    for ev in events:
        if ev.get("kind") == "incident_detected":
            current = {"events": [ev]}
            groups.append(current)
        elif current is not None:
            current["events"].append(ev)
    for g in groups:
        g.update(_describe(g["events"]))
    return groups


def _first(events, kind):
    return next((e for e in events if e.get("kind") == kind), None)


def _describe(events: list[dict]) -> dict:
    detected = _first(events, "incident_detected") or {}
    diagnosis = _first(events, "diagnosis")
    policy = _first(events, "policy_decision")
    approval = _first(events, "approval")
    applied = _first(events, "remediation_applied")
    resolved = _first(events, "incident_resolved")
    verification = _first(events, "verification_after_rollback") or _first(events, "verification")
    rollback = _first(events, "rollback_applied")

    recovered = bool(verification and verification.get("recovered"))

    # Per-stage state drives the step track: ok / blocked / failed / skipped.
    stages = []
    for label, kind in STAGES:
        ev = _first(events, kind)
        if ev is None:
            stages.append((label, "skipped"))
        elif kind == "policy_decision":
            stages.append((label, "ok" if ev.get("allowed") else "blocked"))
        elif kind == "approval":
            stages.append((label, "ok" if ev.get("approved") else "blocked"))
        elif kind == "remediation_applied":
            stages.append((label, "ok" if ev.get("returncode") == 0 else "failed"))
        elif kind == "verification":
            stages.append((label, "ok" if recovered else "failed"))
        else:
            stages.append((label, "ok"))

    return {
        "ts": detected.get("ts", ""),
        "symptom": detected.get("symptom", "unknown"),
        "summary": detected.get("summary", ""),
        "pods": detected.get("unhealthy_pods", []),
        "root_cause": (diagnosis or {}).get("root_cause"),
        "confidence": (diagnosis or {}).get("confidence"),
        "action": (diagnosis or {}).get("action"),
        "reasoning": (diagnosis or {}).get("reasoning"),
        "evidence": (diagnosis or {}).get("evidence") or [],
        "policy_reason": (policy or {}).get("reason"),
        "policy_allowed": None if policy is None else policy.get("allowed"),
        "applied_ok": None if applied is None else applied.get("returncode") == 0,
        "rolled_back": rollback is not None,
        "recovered": recovered,
        "mttr": (resolved or {}).get("mttr_seconds"),
        "stages": stages,
    }


def summarise(groups: list[dict]) -> dict:
    total = len(groups)
    recovered = sum(1 for g in groups if g["recovered"])
    mttrs = sorted(g["mttr"] for g in groups if g["mttr"])
    # Hard invariant: a change should never be applied when policy refused it.
    escapes = sum(1 for g in groups if g["policy_allowed"] is False and g["applied_ok"])
    return {
        "total": total,
        "recovered": recovered,
        "rate": (recovered / total * 100) if total else 0.0,
        "median_mttr": mttrs[len(mttrs) // 2] if mttrs else None,
        "escapes": escapes,
    }


def latest_eval() -> dict | None:
    files = sorted(glob.glob(os.path.join(ROOT, "eval", "runs", "*-results.json")))
    if not files:
        return None
    try:
        with open(files[-1]) as f:
            data = json.load(f)
        data["_file"] = os.path.basename(files[-1])
        return data
    except (json.JSONDecodeError, OSError):
        return None


# ------------------------------------------------------------------- rendering

CSS = """
:root{color-scheme:light;
  --plane:#f9f9f7; --surface:#fcfcfb;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --rule:#e1e0d9; --border:rgba(11,11,11,.10);
  --series-1:#2a78d6; --track:#cde2fb;
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19;
  --ink:#f0efec; --ink-2:#c3c2b7; --muted:#898781;
  --rule:#2c2c2a; --border:rgba(255,255,255,.10);
  --series-1:#3987e5; --track:#184f95;
}}
:root[data-theme="dark"]{color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19;
  --ink:#f0efec; --ink-2:#c3c2b7; --muted:#898781;
  --rule:#2c2c2a; --border:rgba(255,255,255,.10);
  --series-1:#3987e5; --track:#184f95;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;}
.wrap{max-width:1040px;margin:0 auto;padding:40px 16px 72px}
h1{font-size:22px;font-weight:650;margin:0 0 4px}
.sub{color:var(--ink-2);font-size:13px;margin:0 0 28px}
h2{font-size:15px;font-weight:650;margin:36px 0 12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px}

/* headline numbers: one hero figure, then supporting tiles */
.top{display:grid;grid-template-columns:minmax(200px,1.2fr) repeat(3,minmax(120px,1fr));gap:12px}
@media (max-width:720px){.top{grid-template-columns:1fr 1fr}}
.tile-label{color:var(--ink-2);font-size:12px;margin:0 0 6px}
.hero{font-size:52px;font-weight:650;line-height:1;letter-spacing:-.02em}
.tile-val{font-size:26px;font-weight:650;line-height:1.1}
.tile-note{color:var(--muted);font-size:12px;margin-top:6px}

/* status: colour never carries meaning alone - always icon + label */
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
  border:1px solid var(--border);border-radius:999px;padding:3px 9px;background:var(--surface)}
.dot{width:8px;height:8px;border-radius:50%;flex:none}
.ok .dot{background:var(--good)} .bad .dot{background:var(--critical)}
.warn .dot{background:var(--warning)} .skip .dot{background:var(--muted)}

/* incident pipeline */
.inc{margin-bottom:12px}
.inc-head{display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;justify-content:space-between}
.sym{font-weight:650}
.ts{color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.track{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 2px}
.step{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-2);
  border:1px solid var(--border);border-radius:6px;padding:4px 8px;background:var(--plane)}
.step .dot{width:7px;height:7px}
dl{display:grid;grid-template-columns:120px 1fr;gap:6px 14px;margin:14px 0 0;font-size:13px}
dt{color:var(--muted)} dd{margin:0}
details{margin-top:12px} summary{cursor:pointer;color:var(--ink-2);font-size:12px}
pre{background:var(--plane);border:1px solid var(--border);border-radius:8px;
  padding:10px;overflow:auto;font-size:12px;margin:8px 0 0}

.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:13px}
td.detail{word-break:break-word;overflow-wrap:anywhere;max-width:560px}
@media (max-width:560px){
  dl{grid-template-columns:1fr;gap:2px 0}
  dt{margin-top:8px}
  .wrap{padding:28px 16px 56px}
  .hero{font-size:44px}
  table{min-width:480px}
}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule)}
th{color:var(--ink-2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.empty{color:var(--ink-2);font-size:13px}
#tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s;
  background:var(--surface);color:var(--ink);border:1px solid var(--border);
  border-radius:6px;padding:6px 8px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.12);z-index:9}
"""

JS = """
const tip=document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el=>{
  el.addEventListener('mousemove',e=>{tip.textContent=el.dataset.tip;tip.style.opacity=1;
    tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';});
  el.addEventListener('mouseleave',()=>{tip.style.opacity=0;});
});
"""

STATE_CLASS = {"ok": "ok", "blocked": "warn", "failed": "bad", "skipped": "skip"}
STATE_WORD = {"ok": "ok", "blocked": "blocked", "failed": "failed", "skipped": "not reached"}


def esc(v) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _hbar(x, y, w, h, r=4) -> str:
    """Horizontal bar: square at the baseline, rounded at the data end."""
    r = max(0, min(r, w))
    return (f"M{x},{y} H{x + w - r} Q{x + w},{y} {x + w},{y + r} "
            f"V{y + h - r} Q{x + w},{y + h} {x + w - r},{y + h} H{x} Z")


def render_bars(rows: list[dict]) -> str:
    """Remediation success by scenario. One series, so no legend - the title names it."""
    if not rows:
        return ""
    bar_h, gap, label_w, pad = 18, 14, 110, 8
    plot_w = 520
    height = pad * 2 + len(rows) * bar_h + (len(rows) - 1) * gap
    out = [f'<svg viewBox="0 0 {label_w + plot_w + 60} {height}" width="100%" '
           f'height="{height}" role="img" aria-label="Remediation success by scenario">']
    # recessive baseline
    out.append(f'<line x1="{label_w}" y1="{pad}" x2="{label_w}" y2="{height - pad}" '
               f'stroke="var(--rule)" stroke-width="1"/>')
    for i, r in enumerate(rows):
        y = pad + i * (bar_h + gap)
        pct = r["remediation_success"] * 100
        w = max(1.0, plot_w * r["remediation_success"])
        tip = (f'{r["scenario"]}: {pct:.0f}% fixed over {r["trials"]} trials')
        out.append(f'<text x="{label_w - 10}" y="{y + bar_h * 0.72}" text-anchor="end" '
                   f'font-size="12" fill="var(--ink-2)">{esc(r["scenario"])}</text>')
        out.append(f'<path d="{_hbar(label_w, y, w, bar_h)}" fill="var(--series-1)" '
                   f'data-tip="{esc(tip)}"/>')
        # direct value label - selective labelling, not a number on every point
        out.append(f'<text x="{label_w + w + 8}" y="{y + bar_h * 0.72}" font-size="12" '
                   f'fill="var(--ink-2)">{pct:.0f}%</text>')
    out.append("</svg>")
    return "".join(out)


def render_incident(g: dict) -> str:
    cls = "ok" if g["recovered"] else "bad"
    word = "recovered" if g["recovered"] else "unresolved"
    ts = g["ts"][:19].replace("T", " ") if g["ts"] else ""

    steps = "".join(
        f'<span class="step {STATE_CLASS[state]}"><span class="dot"></span>'
        f'{esc(label)} <span style="color:var(--muted)">{STATE_WORD[state]}</span></span>'
        for label, state in g["stages"]
    )

    rows = [("Root cause", g["root_cause"]), ("Action", g["action"])]
    if g["confidence"] is not None:
        rows.append(("Confidence", f'{g["confidence"]:.2f} <span style="color:var(--muted)">'
                                   f'(model self-report - not used as a gate)</span>'))
    if g["mttr"]:
        rows.append(("Recovery time", f'{g["mttr"]}s'))
    if g["policy_reason"]:
        rows.append(("Policy", g["policy_reason"]))
    if g["rolled_back"]:
        rows.append(("Rollback", "remediation failed verification; change reverted"))
    if g["pods"]:
        rows.append(("Pods", ", ".join(g["pods"])))
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{v if k in ('Confidence',) else esc(v)}</dd>"
                 for k, v in rows if v not in (None, ""))

    extra = ""
    if g["evidence"] or g["reasoning"]:
        ev = "".join(f"<li>{esc(e)}</li>" for e in g["evidence"])
        extra = ("<details><summary>Evidence and reasoning</summary>"
                 + (f"<ul style='font-size:12px;color:var(--ink-2)'>{ev}</ul>" if ev else "")
                 + (f"<pre>{esc(g['reasoning'])}</pre>" if g["reasoning"] else "")
                 + "</details>")

    return (f'<div class="card inc"><div class="inc-head">'
            f'<span class="sym">{esc(g["symptom"])}</span>'
            f'<span class="pill {cls}"><span class="dot"></span>{word}</span>'
            f'<span class="ts">{esc(ts)}</span></div>'
            f'<div class="track">{steps}</div><dl>{dl}</dl>{extra}</div>')


def build_dashboard(out_path="dashboard.html") -> str:
    events = read_events()
    groups = group_incidents(events)
    s = summarise(groups)
    ev = latest_eval()
    rows = (ev or {}).get("summary") or []

    hero = f'{s["rate"]:.0f}%' if s["total"] else "--"
    mttr = f'{s["median_mttr"]:.0f}s' if s["median_mttr"] else "--"

    top = f"""
    <div class="top">
      <div class="card"><p class="tile-label">Incidents recovered autonomously</p>
        <div class="hero">{hero}</div>
        <p class="tile-note">{s["recovered"]} of {s["total"]} handled end to end</p></div>
      <div class="card"><p class="tile-label">Incidents handled</p>
        <div class="tile-val">{s["total"]}</div></div>
      <div class="card"><p class="tile-label">Median recovery</p>
        <div class="tile-val">{mttr}</div>
        <p class="tile-note">detect to verified</p></div>
      <div class="card"><p class="tile-label">Actions outside allowlist</p>
        <div class="tile-val">{s["escapes"]}</div>
        <p class="tile-note">policy invariant</p></div>
    </div>"""

    incidents = ("".join(render_incident(g) for g in reversed(groups)) if groups
                 else '<div class="card empty">No incidents recorded yet. '
                      'Run <code>python src/main.py once</code> after injecting a failure.</div>')

    if rows:
        tbl = "".join(
            f'<tr><td>{esc(r["scenario"])}</td><td class="num">{r["trials"]}</td>'
            f'<td class="num">{r["symptom_accuracy"]*100:.0f}%</td>'
            f'<td class="num">{r["action_accuracy"]*100:.0f}%</td>'
            f'<td class="num">{r["remediation_success"]*100:.0f}%</td>'
            f'<td class="num">{(str(int(r["median_mttr"])) + "s") if r["median_mttr"] else "-"}</td>'
            f'<td class="num">{r["mutations_outside_allowlist"]}</td></tr>' for r in rows)
        metrics = f"""
        <h2>Evaluation</h2>
        <div class="card">{render_bars(rows)}</div>
        <div class="card" style="margin-top:12px"><div class="tw">
          <table><thead><tr><th>Scenario</th><th class="num">Trials</th>
          <th class="num">Symptom</th><th class="num">Action</th><th class="num">Fixed</th>
          <th class="num">MTTR</th><th class="num">Escapes</th></tr></thead>
          <tbody>{tbl}</tbody></table></div>
          <p class="tile-note">Source: {esc(ev.get("_file", ""))}</p></div>"""
    else:
        metrics = ('<h2>Evaluation</h2><div class="card empty">No evaluation run yet. '
                   'Run <code>python eval/harness.py --trials 5</code>.</div>')

    trail = "".join(
        f'<tr><td class="ts">{esc(e.get("ts","")[:19].replace("T"," "))}</td>'
        f'<td>{esc(e.get("kind",""))}</td><td class="detail" style="color:var(--ink-2)">'
        f'{esc(json.dumps({k: v for k, v in e.items() if k not in ("ts","kind")})[:160])}</td></tr>'
        for e in events[-200:])

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Incident Responder</title><style>{CSS}</style></head>
<body><div id="tip"></div><div class="wrap">
<h1>Kubernetes Incident Responder</h1>
<p class="sub">Autonomous detection, diagnosis and remediation &middot; generated {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
{top}
<h2>Incidents</h2>
{incidents}
{metrics}
<h2>Audit trail</h2>
<div class="card"><details open><summary>{len(events)} events (most recent 200 shown)</summary>
<div class="tw"><table><thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead>
<tbody>{trail or '<tr><td colspan=3 class="empty">empty</td></tr>'}</tbody></table></div>
</details></div>
</div><script>{JS}</script></body></html>"""

    target = out_path if os.path.isabs(out_path) else os.path.join(ROOT, out_path)
    with open(target, "w") as f:
        f.write(html)
    return target


if __name__ == "__main__":
    print(build_dashboard())
