"""The control panel page (HTML/CSS/JS), served by server.py.

Palette: the surfaces follow Docker Desktop's dark theme (page #11151a, panels
#1e262c, rail #090b0d, navy header gradient). The accent is #4684f7 on dark and
#1a6fd4 on light - both re-validated at >=3:1 against *these* surfaces, which
matters: the previous accent fell to 2.91:1 once the light surface turned cooler.

Colour carries meaning rather than decoration: blue = infrastructure/neutral
actions, amber = destructive "break it" actions, and the reserved status palette
(good/warning/critical) is used ONLY for pod and incident state. Every status is a
dot plus a word, so colour never carries meaning alone.

The brand mark is an original cluster glyph, not the Kubernetes logo (a trademark).
Swap in the official CNCF SVG if you prefer.
"""

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Incident Responder</title>
<style>
:root{color-scheme:light;
  --plane:#eef1f5; --surface:#ffffff; --sunken:#e2e7ee;
  --ink:#0d1117; --ink-2:#4a5560; --muted:#78838f;
  --rule:#dfe4ea; --border:rgba(13,17,23,.12);
  --accent:#1a6fd4; --accent-soft:rgba(26,111,212,.10);
  --caution:#b26a00; --caution-soft:rgba(178,106,0,.10);
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
  --nav-a:#071845; --nav-b:#1a2b5e;
  --term-bg:#0b0e13; --term-ink:#cfd8e3;
}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
  --plane:#0c0f13; --surface:#171d23; --sunken:#05070a;
  --ink:#e8edf2; --ink-2:#9aa7b4; --muted:#6b7885;
  --rule:#242d38; --border:rgba(255,255,255,.08);
  --accent:#4684f7; --accent-soft:rgba(70,132,247,.14);
  --caution:#e2a33c; --caution-soft:rgba(226,163,60,.13);
  --term-bg:#05070a; --term-ink:#cfd8e3;
}}
:root[data-theme="dark"]{color-scheme:dark;
  --plane:#0c0f13; --surface:#171d23; --sunken:#05070a;
  --ink:#e8edf2; --ink-2:#9aa7b4; --muted:#6b7885;
  --rule:#242d38; --border:rgba(255,255,255,.08);
  --accent:#4684f7; --accent-soft:rgba(70,132,247,.14);
  --caution:#e2a33c; --caution-soft:rgba(226,163,60,.13);
  --term-bg:#05070a;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}

/* navy header band, the way Docker Desktop anchors its window */
.topbar{background:linear-gradient(90deg,var(--nav-a),var(--nav-b));color:#fff;
  padding:14px 0;border-bottom:1px solid rgba(0,0,0,.35)}
.topbar .inner{max-width:1060px;margin:0 auto;padding:0 16px;
  display:flex;align-items:center;gap:12px;justify-content:space-between}
.brand{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:650;letter-spacing:.01em}
.brand svg{width:26px;height:26px;color:#8fb8ff;flex:none}
.brand small{display:block;font-size:11px;font-weight:500;color:#b9c8e8;letter-spacing:.04em;
  text-transform:uppercase;margin-top:1px}

.wrap{max-width:1060px;margin:0 auto;padding:22px 16px 72px}
.sub{color:var(--ink-2);font-size:13px;margin:0 0 22px}
h2{font-size:12px;font-weight:700;margin:26px 0 10px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:7px}
h2 .spacer{flex:1}
.ghost{display:inline-flex;align-items:center;gap:5px;cursor:pointer;
  background:none;border:1px solid var(--border);border-radius:6px;padding:3px 8px;
  color:var(--ink-2);font:inherit;font-size:11px;font-weight:600;letter-spacing:.04em;
  text-transform:uppercase;transition:border-color .12s,color .12s}
.ghost:hover{border-color:var(--accent);color:var(--accent)}
.ghost svg{width:13px;height:13px}
h2 svg{width:15px;height:15px;color:var(--accent)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px}
svg{fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}

/* status: a dot AND a word, always */
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
  border:1px solid var(--border);border-radius:999px;padding:4px 10px;background:var(--surface)}
.topbar .pill{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.22);color:#fff}
.dot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--muted)}
.ok .dot{background:var(--good)} .bad .dot{background:var(--critical)}
.warn .dot{background:var(--warning)} .skip .dot{background:var(--muted)}

/* control panel */
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(262px,1fr));gap:14px}
.grp h3{font-size:11px;margin:0 0 9px;color:var(--muted);font-weight:700;
  text-transform:uppercase;letter-spacing:.06em;display:flex;align-items:center;gap:6px}
.grp h3 svg{width:14px;height:14px}
.grp.infra h3 svg{color:var(--accent)}
.grp.danger h3 svg{color:var(--caution)}
.btn{display:flex;gap:10px;align-items:flex-start;width:100%;text-align:left;margin-bottom:8px;
  cursor:pointer;background:var(--surface);border:1px solid var(--border);border-radius:9px;
  padding:10px 12px;color:var(--ink);font:inherit;transition:border-color .12s,background .12s}
.btn:hover:not(:disabled){border-color:var(--accent);background:var(--accent-soft)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.btn svg{width:17px;height:17px;flex:none;margin-top:1px;color:var(--accent)}
.danger .btn svg{color:var(--caution)}
.danger .btn:hover:not(:disabled){border-color:var(--caution);background:var(--caution-soft)}
.btn b{display:block;font-size:13px;font-weight:600;margin-bottom:3px}
.btn code{display:block;font-size:11px;color:var(--accent);opacity:.85;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}
.danger .btn code{color:var(--caution)}
.btn.primary{border-color:var(--accent);background:var(--accent);color:#fff}
.btn.primary svg,.btn.primary b{color:#fff}
.btn.primary code{color:rgba(255,255,255,.9);opacity:1}
.btn.primary:hover:not(:disabled){filter:brightness(1.07);background:var(--accent)}

/* terminal - colour here is syntax, not decoration */
.term{background:var(--term-bg);color:var(--term-ink);border:1px solid var(--border);
  border-radius:10px;padding:14px 16px;
  font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
  height:250px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
.term .cmd{color:#6fb3ff;font-weight:600}
.term .dim{color:#6b7885}
.term .err{color:#ff8080}
.term .good{color:#5fd35f}

table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule)}
th{color:var(--ink-2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td code{color:var(--accent);font-size:12px}
.tw{overflow-x:auto}
.empty{color:var(--muted);font-size:13px}
dl{display:grid;grid-template-columns:116px 1fr;gap:5px 14px;margin:12px 0 0;font-size:13px}
dt{color:var(--muted)} dd{margin:0;overflow-wrap:anywhere}
.track{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 2px}
.step{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-2);
  border:1px solid var(--border);border-radius:6px;padding:3px 8px;background:var(--plane)}
.step .dot{width:7px;height:7px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.row .btn{width:auto;margin:0}
.bar{height:16px;background:var(--accent);border-radius:0 4px 4px 0}
.bartrack{display:flex;align-items:center;gap:10px;margin:7px 0}
.barlabel{width:96px;font-size:12px;color:var(--ink-2);text-align:right;flex:none}
@media (max-width:560px){dl{grid-template-columns:1fr}table{min-width:460px}}
</style></head>
<body>

<svg style="display:none" aria-hidden="true">
 <!-- original cluster glyph: a hexagonal node ring around a control point -->
 <symbol id="i-brand" viewBox="0 0 24 24"><path d="M12 2.6 20 7v10l-8 4.4L4 17V7z"/>
   <circle cx="12" cy="12" r="2.4"/><path d="M12 9.6V5.2M14.1 13.3l3.5 2M9.9 13.3l-3.5 2"/></symbol>
 <symbol id="i-power" viewBox="0 0 24 24"><path d="M12 3v9"/><path d="M6.6 6.6a8 8 0 1 0 10.8 0"/></symbol>
 <symbol id="i-upload" viewBox="0 0 24 24"><path d="M12 15V4"/><path d="M8 8l4-4 4 4"/>
   <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></symbol>
 <symbol id="i-list" viewBox="0 0 24 24"><path d="M8 6h12M8 12h12M8 18h12"/>
   <circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></symbol>
 <symbol id="i-loop" viewBox="0 0 24 24"><path d="M3 11a9 9 0 0 1 15-6.7L21 7"/>
   <path d="M21 4v3h-3"/><path d="M21 13a9 9 0 0 1-15 6.7L3 17"/><path d="M3 20v-3h3"/></symbol>
 <symbol id="i-chip" viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1.5"/>
   <path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/></symbol>
 <symbol id="i-layers" viewBox="0 0 24 24"><path d="M12 3 3 7.5 12 12l9-4.5z"/>
   <path d="M3 12.5 12 17l9-4.5"/><path d="M3 17 12 21.5 21 17"/></symbol>
 <symbol id="i-undo" viewBox="0 0 24 24"><path d="M3 9h10a5 5 0 1 1 0 10H7"/><path d="M3 9l4-4M3 9l4 4"/></symbol>
 <symbol id="i-scan" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.4-4.4"/>
   <path d="M8.5 11h1.6l1 2 1.4-4 1 2h1.5"/></symbol>
 <symbol id="i-doc" viewBox="0 0 24 24"><path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z"/>
   <path d="M14 3v4h4"/><path d="M9 13h6M9 17h4"/></symbol>
 <symbol id="i-server" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="7" rx="1.5"/>
   <rect x="3" y="13" width="18" height="7" rx="1.5"/><path d="M7 7.5h.01M7 16.5h.01"/></symbol>
 <symbol id="i-alert" viewBox="0 0 24 24"><path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17h.01"/></symbol>
 <symbol id="i-shield" viewBox="0 0 24 24"><path d="M12 2.8 20 6v6c0 4.6-3.3 8-8 9.2C8 20 4.7 16.6 4.7 12V6z"/>
   <path d="M9 12.2l2.2 2.2L15.3 10"/></symbol>
 <symbol id="i-pulse" viewBox="0 0 24 24"><path d="M2 12h4l3-7 4 14 3-7h6"/></symbol>
 <symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></symbol>
 <symbol id="i-clear" viewBox="0 0 24 24"><path d="M4 7h16"/>
   <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
   <path d="M6.5 7l.8 12a1 1 0 0 0 1 .9h7.4a1 1 0 0 0 1-.9l.8-12"/><path d="M10 11v5M14 11v5"/></symbol>
 <symbol id="i-term" viewBox="0 0 24 24"><rect x="2.5" y="4" width="19" height="16" rx="2"/>
   <path d="M7 9l3 3-3 3M13 15h4"/></symbol>
</svg>

<div class="topbar"><div class="inner">
  <span class="brand"><svg><use href="#i-brand"/></svg>
    <span>Incident Responder<small>policy-constrained remediation &middot; for use with Kubernetes</small></span></span>
  <span id="chip" class="pill skip"><span class="dot"></span>checking…</span>
</div></div>

<div class="wrap">
<p class="sub">Break the app on purpose, then watch it detect, diagnose and fix itself — or approve the fix yourself.</p>

<h2><svg><use href="#i-server"/></svg>Control panel</h2>
<div class="card"><div class="groups">
  <div class="grp infra"><h3><svg><use href="#i-server"/></svg>Environment</h3><div id="g-env"></div></div>
  <div class="grp danger"><h3><svg><use href="#i-alert"/></svg>Break it</h3><div id="g-break"></div></div>
  <div class="grp infra"><h3><svg><use href="#i-shield"/></svg>Respond</h3>
    <button class="btn primary" id="btn-propose"><svg><use href="#i-scan"/></svg>
      <span><b>Diagnose &amp; propose a fix</b>
      <code>detect → diagnose (LLM) → policy check → preview</code></span></button>
    <div id="g-resp"></div>
  </div>
</div></div>

<h2><svg><use href="#i-term"/></svg>Output<span class="spacer"></span>
  <button class="ghost" id="btn-clear" title="Clear the output panel">
    <svg><use href="#i-clear"/></svg>Clear</button></h2>
<div class="term" id="term"><span class="dim">Select an action above — the exact command runs here.</span></div>

<div id="approve"></div>

<h2><svg><use href="#i-pulse"/></svg>Live cluster</h2>
<div class="card tw" id="pods"><p class="empty">loading…</p></div>

<h2><svg><use href="#i-alert"/></svg>Incidents</h2>
<div id="incidents"></div>

<h2><svg><use href="#i-chart"/></svg>Evaluation</h2>
<div id="metrics"></div>

<p class="sub" style="margin:28px 0 0;font-size:11px">
Kubernetes&reg; is a registered trademark of The Linux Foundation. This project is an
independent personal project and is not affiliated with, sponsored or endorsed by
The Linux Foundation, CNCF, or the Kubernetes project.</p>
</div>

<script>
const $ = s => document.querySelector(s);
const term = $('#term');
let busy = false;
const ICONS = {'cluster-up':'i-power','deploy':'i-upload','status':'i-list','cluster-down':'i-power',
  'crashloop':'i-loop','oom':'i-chip','rollout':'i-layers','reset':'i-undo','report':'i-doc',
  'rbac':'i-shield','rbac-check':'i-shield'};

function esc(s){return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function write(line, cls){
  const span=document.createElement('span');
  if(cls) span.className=cls;
  span.textContent=line+'\n'; term.appendChild(span); term.scrollTop=term.scrollHeight;
}
function classify(l){
  if(l.startsWith('$ ')) return 'cmd';
  if(/error|refused|failed|not allowed/i.test(l)) return 'err';
  if(/RECOVERED|exit 0|patched|rolled back|configured|created/i.test(l)) return 'good';
  return null;
}
function setBusy(v){busy=v;document.querySelectorAll('.btn').forEach(b=>b.disabled=v);}
function clearTerm(){
  // back to the first-run placeholder rather than an empty black box
  term.innerHTML='<span class="dim">Select an action above \u2014 the exact command runs here.</span>\n';
}

async function runAction(id){
  if(busy) return; setBusy(true);
  try{
    const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
    const j=await r.json();
    if(j.error){write('error: '+j.error,'err');setBusy(false);return;}
    let from=0;
    while(true){
      const s=await (await fetch('/api/job?id='+j.job+'&from='+from)).json();
      s.lines.forEach(l=>write(l,classify(l)));
      from=s.next;
      if(s.done){write('— exit '+s.code+' —', s.code===0?'good':'err');break;}
      await new Promise(r=>setTimeout(r,400));
    }
  } finally {setBusy(false); refresh();}
}

async function propose(){
  if(busy) return; setBusy(true);
  write('$ detect → diagnose → policy check','cmd');
  write('asking the local model…','dim');
  try{
    const j=await (await fetch('/api/propose',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
    if(j.error) write('error: '+j.error,'err'); else write('proposal ready — review it below','good');
  } finally {setBusy(false); refresh();}
}

async function decide(approve){
  setBusy(true);
  write(approve?'$ applying approved remediation':'$ proposal rejected','cmd');
  try{
    const j=await (await fetch('/api/decide',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({approve})})).json();
    if(j.error) write('error: '+j.error,'err');
    else if(j.result&&j.result.declined) write('no change was made.','dim');
    else if(j.result) write((j.result.recovered?'RECOVERED':'UNRESOLVED')+
      (j.result.mttr_seconds?' in '+j.result.mttr_seconds+'s':'')+' — '+j.result.detail,
      j.result.recovered?'good':'err');
  } finally {setBusy(false); refresh();}
}

function actionBtn(id,label,cmd){
  return `<button class="btn" data-run="${id}"><svg><use href="#${ICONS[id]||'i-term'}"/></svg>
    <span><b>${esc(label)}</b><code>${esc(cmd)}</code></span></button>`;
}

function renderPending(p){
  const box=$('#approve');
  if(!p){box.innerHTML='';return;}
  if(p.error){box.innerHTML=`<h2><svg><use href="#i-scan"/></svg>Proposal</h2><div class="card"><p class="empty">${esc(p.error)}</p></div>`;return;}
  const blocked=!p.allowed;
  box.innerHTML=`<h2><svg><use href="#i-shield"/></svg>Proposal — awaiting your decision</h2>
   <div class="card">
    <span class="pill ${blocked?'bad':'warn'}"><span class="dot"></span>${blocked?'blocked by policy':'needs approval'}</span>
    <dl>
      <dt>Symptom</dt><dd>${esc(p.symptom)}</dd>
      <dt>Root cause</dt><dd>${esc(p.root_cause)}</dd>
      <dt>Action</dt><dd><code>${esc(p.action)}</code></dd>
      <dt>Confidence</dt><dd>${p.confidence==null?'—':p.confidence.toFixed(2)}
        <span style="color:var(--muted)">(model self-report — not a gate)</span></dd>
      <dt>Policy</dt><dd>${esc(p.reason)}</dd>
      ${p.command?`<dt>Command</dt><dd><code>${esc(p.command)}</code></dd>`:''}
    </dl>
    ${p.preview?`<div class="term" style="height:110px;margin-top:12px">${esc(p.preview)}</div>`:''}
    ${blocked?'<p class="empty" style="margin-top:12px">Nothing will be applied — the policy layer refused this action.</p>'
      :`<div class="row">
          <button class="btn primary" onclick="decide(true)"><svg><use href="#i-shield"/></svg><span><b>Approve &amp; apply</b></span></button>
          <button class="btn" onclick="decide(false)"><svg><use href="#i-undo"/></svg><span><b>Reject</b></span></button>
        </div>`}
   </div>`;
}

function renderPods(c){
  const el=$('#pods');
  if(!c.reachable){el.innerHTML=`<p class="empty">Cluster unreachable — start it from the control panel.</p>`;return;}
  if(!c.pods.length){el.innerHTML=`<p class="empty">No pods yet — deploy the sample app.</p>`;return;}
  el.innerHTML=`<table><thead><tr><th>Pod</th><th>Ready</th><th>Waiting</th>
    <th>Last termination</th><th class="num">Restarts</th></tr></thead><tbody>${
    c.pods.map(p=>`<tr><td>${esc(p.name)}</td>
      <td><span class="pill ${p.ready?'ok':'bad'}"><span class="dot"></span>${p.ready?'ready':'not ready'}</span></td>
      <td>${p.waiting_reason?`<code>${esc(p.waiting_reason)}</code>`:'—'}</td>
      <td>${p.last_terminated_reason?`<code>${esc(p.last_terminated_reason)}</code>`:'—'}${p.last_exit_code!=null?' ('+p.last_exit_code+')':''}</td>
      <td class="num">${p.restart_count}</td></tr>`).join('')}</tbody></table>`;
}

function renderIncidents(list){
  const el=$('#incidents');
  if(!list.length){el.innerHTML=`<div class="card"><p class="empty">No incidents yet.</p></div>`;return;}
  el.innerHTML=list.map(g=>`<div class="card" style="margin-bottom:10px">
    <div style="display:flex;gap:10px;align-items:baseline;justify-content:space-between;flex-wrap:wrap">
      <b>${esc(g.symptom)}</b>
      <span class="pill ${g.recovered?'ok':'bad'}"><span class="dot"></span>${g.recovered?'recovered':'unresolved'}</span>
      <span style="color:var(--muted);font-size:12px">${esc((g.ts||'').slice(0,19).replace('T',' '))}</span>
    </div>
    <div class="track">${(g.stages||[]).map(([l,st])=>`<span class="step ${
      st==='ok'?'ok':st==='blocked'?'warn':st==='failed'?'bad':'skip'}"><span class="dot"></span>${esc(l)}
      <span style="color:var(--muted)">${st==='skipped'?'not reached':esc(st)}</span></span>`).join('')}</div>
    <dl><dt>Root cause</dt><dd>${esc(g.root_cause||'—')}</dd>
      <dt>Action</dt><dd>${g.action?`<code>${esc(g.action)}</code>`:'—'}</dd>
      ${g.mttr?`<dt>Recovery</dt><dd>${g.mttr}s</dd>`:''}
      ${g.policy_reason?`<dt>Policy</dt><dd>${esc(g.policy_reason)}</dd>`:''}</dl>
  </div>`).join('');
}

function renderMetrics(rows){
  const el=$('#metrics');
  if(!rows.length){el.innerHTML=`<div class="card"><p class="empty">No evaluation run yet — <code>python eval/harness.py --trials 10</code></p></div>`;return;}
  const bars=rows.map(r=>`<div class="bartrack"><span class="barlabel">${esc(r.scenario)}</span>
      <div class="bar" style="width:${Math.max(2,r.remediation_success*440)}px"
           title="${esc(r.scenario)}: ${(r.remediation_success*100).toFixed(0)}% over ${r.trials} trials"></div>
      <span style="font-size:12px;color:var(--ink-2)">${(r.remediation_success*100).toFixed(0)}%</span></div>`).join('');
  el.innerHTML=`<div class="card"><div style="font-size:12px;color:var(--ink-2);margin-bottom:6px">Remediation success by scenario</div>${bars}</div>
   <div class="card tw" style="margin-top:10px"><table><thead><tr><th>Scenario</th><th class="num">Trials</th>
    <th class="num">Symptom</th><th class="num">Action</th><th class="num">Fixed</th>
    <th class="num">MTTR</th><th class="num">Escapes</th></tr></thead><tbody>${
    rows.map(r=>`<tr><td>${esc(r.scenario)}</td><td class="num">${r.trials}</td>
      <td class="num">${(r.symptom_accuracy*100).toFixed(0)}%</td>
      <td class="num">${(r.action_accuracy*100).toFixed(0)}%</td>
      <td class="num">${(r.remediation_success*100).toFixed(0)}%</td>
      <td class="num">${r.median_mttr?Math.round(r.median_mttr)+'s':'—'}</td>
      <td class="num">${r.mutations_outside_allowlist}</td></tr>`).join('')}</tbody></table></div>`;
}

let built=false;
async function refresh(){
  let s; try{s=await (await fetch('/api/state')).json();}catch(e){return;}
  if(!built){
    const env=['cluster-up','deploy','rbac','status','rbac-check','cluster-down'];
    const brk=['crashloop','oom','rollout','reset'];
    // only render ids the server actually offers, so a stale list can never
    // produce a blank, unlabelled button
    const known=id=>s.actions&&s.actions[id];
    $('#g-env').innerHTML=env.filter(known).map(id=>actionBtn(id,s.actions[id],s.commands[id])).join('');
    $('#g-break').innerHTML=brk.filter(known).map(id=>actionBtn(id,s.actions[id],s.commands[id])).join('');
    $('#g-resp').innerHTML=actionBtn('report',s.actions['report'],s.commands['report']);
    document.querySelectorAll('[data-run]').forEach(b=>b.onclick=()=>runAction(b.dataset.run));
    $('#btn-propose').onclick=propose;
    $('#btn-clear').onclick=clearTerm;     // stays enabled while a job runs
    built=true;
  }
  const c=s.cluster, chip=$('#chip');
  if(!c.reachable){chip.className='pill skip';chip.innerHTML='<span class="dot"></span>cluster unreachable';}
  else if(c.incident){chip.className='pill bad';chip.innerHTML='<span class="dot"></span>'+esc(c.incident.symptom);}
  else {chip.className='pill ok';chip.innerHTML='<span class="dot"></span>healthy';}
  renderPods(c); renderPending(s.pending);
  renderIncidents(s.incidents||[]); renderMetrics(s.metrics||[]);
  if(busy) document.querySelectorAll('.btn').forEach(b=>b.disabled=true);
}
refresh(); setInterval(refresh,3000);
</script></body></html>
"""
