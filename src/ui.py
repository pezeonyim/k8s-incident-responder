"""The control panel page (HTML/CSS/JS), served by server.py.

Palette note: the accent is Docker blue (#2496ED light / #3d9ae8 dark), both
validated at >=3:1 against their surfaces. Status colours (good/warning/critical)
are the reserved set and are used ONLY for pod/incident state, never as button
decoration - and every status is a dot plus a word, so colour never carries
meaning on its own.
"""

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Incident Responder</title>
<style>
:root{color-scheme:light;
  --plane:#f9f9f7; --surface:#fcfcfb; --sunken:#f2f2ef;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --rule:#e1e0d9; --border:rgba(11,11,11,.10);
  --accent:#2496ED; --accent-soft:rgba(36,150,237,.10);
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
  --term-bg:#13161b; --term-ink:#d7dde6;
}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --sunken:#121211;
  --ink:#f0efec; --ink-2:#c3c2b7; --muted:#898781;
  --rule:#2c2c2a; --border:rgba(255,255,255,.10);
  --accent:#3d9ae8; --accent-soft:rgba(61,154,232,.14);
  --term-bg:#0b0d10; --term-ink:#d7dde6;
}}
:root[data-theme="dark"]{color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --sunken:#121211;
  --ink:#f0efec; --ink-2:#c3c2b7; --rule:#2c2c2a; --border:rgba(255,255,255,.10);
  --accent:#3d9ae8; --accent-soft:rgba(61,154,232,.14);
  --term-bg:#0b0d10;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1060px;margin:0 auto;padding:28px 16px 72px}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;margin-bottom:6px}
h1{font-size:20px;font-weight:650;margin:0;display:flex;align-items:center;gap:9px}
.whale{width:22px;height:22px;flex:none;color:var(--accent)}
.sub{color:var(--ink-2);font-size:13px;margin:0 0 22px}
h2{font-size:13px;font-weight:650;margin:28px 0 10px;letter-spacing:.02em;
  text-transform:uppercase;color:var(--ink-2)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px}

/* status: always a dot AND a word - colour never alone */
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
  border:1px solid var(--border);border-radius:999px;padding:4px 10px;background:var(--surface)}
.dot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--muted)}
.ok .dot{background:var(--good)} .bad .dot{background:var(--critical)}
.warn .dot{background:var(--warning)} .skip .dot{background:var(--muted)}

/* control panel */
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.grp h3{font-size:12px;margin:0 0 8px;color:var(--muted);font-weight:650;
  text-transform:uppercase;letter-spacing:.03em}
.btn{display:block;width:100%;text-align:left;margin-bottom:8px;cursor:pointer;
  background:var(--surface);border:1px solid var(--border);border-radius:9px;
  padding:10px 12px;color:var(--ink);font:inherit;transition:border-color .12s,background .12s}
.btn:hover:not(:disabled){border-color:var(--accent);background:var(--accent-soft)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.btn b{display:block;font-size:13px;font-weight:600;margin-bottom:3px}
.btn code{display:block;font-size:11px;color:var(--muted);
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}
.btn.primary{border-color:var(--accent);background:var(--accent);color:#fff}
.btn.primary b{color:#fff} .btn.primary code{color:rgba(255,255,255,.85)}
.btn.primary:hover:not(:disabled){filter:brightness(1.06);background:var(--accent)}

/* terminal */
.term{background:var(--term-bg);color:var(--term-ink);border-radius:10px;padding:14px 16px;
  font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
  height:260px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
.term .cmd{color:#7fd1ff}
.term .dim{color:#8a93a0}

table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule)}
th{color:var(--ink-2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
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
<body><div class="wrap">

<header>
  <h1><svg class="whale" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M21 10h-2V8h-3V6h-3v4H9V8H6v2H3a1 1 0 0 0-1 1c0 3.9 2.6 7 7 7h5c4.4 0 8-3.1 8-7a1 1 0 0 0-1-1Z"/></svg>
    Incident Responder</h1>
  <span id="chip" class="pill skip"><span class="dot"></span>checking…</span>
</header>
<p class="sub">Break the app on purpose, then watch it detect, diagnose and fix itself — or approve the fix yourself.</p>

<h2>Control panel</h2>
<div class="card"><div class="groups">
  <div class="grp"><h3>Environment</h3><div id="g-env"></div></div>
  <div class="grp"><h3>Break it</h3><div id="g-break"></div></div>
  <div class="grp"><h3>Respond</h3>
    <button class="btn primary" id="btn-propose"><b>Diagnose &amp; propose a fix</b>
      <code>detect → diagnose (LLM) → policy check → preview</code></button>
    <div id="g-resp"></div>
  </div>
</div></div>

<h2>Output</h2>
<div class="term" id="term"><span class="dim">Select an action above — the exact command runs here.</span></div>

<div id="approve"></div>

<h2>Live cluster</h2>
<div class="card tw" id="pods"><p class="empty">loading…</p></div>

<h2>Incidents</h2>
<div id="incidents"></div>

<h2>Evaluation</h2>
<div id="metrics"></div>

</div>
<script>
const $ = s => document.querySelector(s);
const term = $('#term');
let busy = false;

function esc(s){return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function write(line, cls){
  const span = document.createElement('span');
  if(cls) span.className = cls;
  span.textContent = line + '\n';
  term.appendChild(span); term.scrollTop = term.scrollHeight;
}
function setBusy(v){
  busy = v;
  document.querySelectorAll('.btn').forEach(b => b.disabled = v);
}

async function runAction(id){
  if(busy) return;
  setBusy(true);
  try{
    const r = await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id})});
    const j = await r.json();
    if(j.error){ write('error: '+j.error); setBusy(false); return; }
    let from = 0;
    while(true){
      const s = await (await fetch('/api/job?id='+j.job+'&from='+from)).json();
      s.lines.forEach(l => write(l, l.startsWith('$ ') ? 'cmd' : null));
      from = s.next;
      if(s.done){ write('— exit '+s.code+' —','dim'); break; }
      await new Promise(r => setTimeout(r, 400));
    }
  } finally { setBusy(false); refresh(); }
}

async function propose(){
  if(busy) return;
  setBusy(true);
  write('$ detect → diagnose → policy check','cmd');
  write('asking the local model…','dim');
  try{
    const j = await (await fetch('/api/propose',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
    if(j.error) write('error: '+j.error);
    else write('proposal ready — review it below','dim');
  } finally { setBusy(false); refresh(); }
}

async function decide(approve){
  setBusy(true);
  write(approve ? '$ applying approved remediation' : '$ proposal rejected','cmd');
  try{
    const j = await (await fetch('/api/decide',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({approve})})).json();
    if(j.error) write('error: '+j.error);
    else if(j.result && j.result.declined) write('no change was made.','dim');
    else if(j.result) write((j.result.recovered?'RECOVERED':'UNRESOLVED')+
      (j.result.mttr_seconds?' in '+j.result.mttr_seconds+'s':'')+' — '+j.result.detail,'dim');
  } finally { setBusy(false); refresh(); }
}

function actionBtn(id, label, cmd){
  return `<button class="btn" data-run="${id}"><b>${esc(label)}</b><code>${esc(cmd)}</code></button>`;
}

function renderPending(p){
  const box = $('#approve');
  if(!p){ box.innerHTML=''; return; }
  if(p.error){ box.innerHTML = `<h2>Proposal</h2><div class="card"><p class="empty">${esc(p.error)}</p></div>`; return; }
  const blocked = !p.allowed;
  box.innerHTML = `<h2>Proposal — awaiting your decision</h2>
   <div class="card">
    <span class="pill ${blocked?'bad':'warn'}"><span class="dot"></span>${blocked?'blocked by policy':'needs approval'}</span>
    <dl>
      <dt>Symptom</dt><dd>${esc(p.symptom)}</dd>
      <dt>Root cause</dt><dd>${esc(p.root_cause)}</dd>
      <dt>Action</dt><dd>${esc(p.action)}</dd>
      <dt>Confidence</dt><dd>${p.confidence==null?'-':p.confidence.toFixed(2)}
        <span style="color:var(--muted)">(model self-report — not a gate)</span></dd>
      <dt>Policy</dt><dd>${esc(p.reason)}</dd>
      ${p.command?`<dt>Command</dt><dd><code>${esc(p.command)}</code></dd>`:''}
    </dl>
    ${p.preview?`<div class="term" style="height:120px;margin-top:12px">${esc(p.preview)}</div>`:''}
    ${blocked?'<p class="empty" style="margin-top:12px">Nothing will be applied — the policy layer refused this action.</p>'
      :`<div class="row">
          <button class="btn primary" onclick="decide(true)"><b>Approve &amp; apply</b></button>
          <button class="btn" onclick="decide(false)"><b>Reject</b></button>
        </div>`}
   </div>`;
}

function renderPods(c){
  const el = $('#pods');
  if(!c.reachable){ el.innerHTML = `<p class="empty">Cluster unreachable — start it from the control panel.</p>`; return; }
  if(!c.pods.length){ el.innerHTML = `<p class="empty">No pods yet — deploy the sample app.</p>`; return; }
  el.innerHTML = `<table><thead><tr><th>Pod</th><th>Ready</th><th>Waiting</th>
    <th>Last termination</th><th class="num">Restarts</th></tr></thead><tbody>${
    c.pods.map(p=>`<tr><td>${esc(p.name)}</td>
      <td><span class="pill ${p.ready?'ok':'bad'}"><span class="dot"></span>${p.ready?'ready':'not ready'}</span></td>
      <td>${esc(p.waiting_reason||'—')}</td>
      <td>${esc(p.last_terminated_reason||'—')}${p.last_exit_code!=null?' ('+p.last_exit_code+')':''}</td>
      <td class="num">${p.restart_count}</td></tr>`).join('')}</tbody></table>`;
}

function renderIncidents(list){
  const el = $('#incidents');
  if(!list.length){ el.innerHTML = `<div class="card"><p class="empty">No incidents yet.</p></div>`; return; }
  el.innerHTML = list.map(g=>`<div class="card" style="margin-bottom:10px">
    <div style="display:flex;gap:10px;align-items:baseline;justify-content:space-between;flex-wrap:wrap">
      <b>${esc(g.symptom)}</b>
      <span class="pill ${g.recovered?'ok':'bad'}"><span class="dot"></span>${g.recovered?'recovered':'unresolved'}</span>
      <span style="color:var(--muted);font-size:12px">${esc((g.ts||'').slice(0,19).replace('T',' '))}</span>
    </div>
    <div class="track">${(g.stages||[]).map(([l,st])=>`<span class="step ${
      st==='ok'?'ok':st==='blocked'?'warn':st==='failed'?'bad':'skip'}"><span class="dot"></span>${esc(l)}
      <span style="color:var(--muted)">${st==='skipped'?'not reached':esc(st)}</span></span>`).join('')}</div>
    <dl><dt>Root cause</dt><dd>${esc(g.root_cause||'—')}</dd>
      <dt>Action</dt><dd>${esc(g.action||'—')}</dd>
      ${g.mttr?`<dt>Recovery</dt><dd>${g.mttr}s</dd>`:''}
      ${g.policy_reason?`<dt>Policy</dt><dd>${esc(g.policy_reason)}</dd>`:''}</dl>
  </div>`).join('');
}

function renderMetrics(rows){
  const el = $('#metrics');
  if(!rows.length){ el.innerHTML = `<div class="card"><p class="empty">No evaluation run yet — <code>python eval/harness.py --trials 10</code></p></div>`; return; }
  const bars = rows.map(r=>`<div class="bartrack"><span class="barlabel">${esc(r.scenario)}</span>
      <div class="bar" style="width:${Math.max(2,r.remediation_success*460)}px"
           title="${esc(r.scenario)}: ${(r.remediation_success*100).toFixed(0)}% over ${r.trials} trials"></div>
      <span style="font-size:12px;color:var(--ink-2)">${(r.remediation_success*100).toFixed(0)}%</span></div>`).join('');
  el.innerHTML = `<div class="card"><div style="font-size:12px;color:var(--ink-2);margin-bottom:6px">Remediation success by scenario</div>${bars}</div>
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

let built = false;
async function refresh(){
  let s;
  try { s = await (await fetch('/api/state')).json(); } catch(e){ return; }

  if(!built){
    const env = ['cluster-up','deploy','status','cluster-down'];
    const brk = ['crashloop','oom','rollout','reset'];
    $('#g-env').innerHTML   = env.map(id=>actionBtn(id,s.actions[id],s.commands[id])).join('');
    $('#g-break').innerHTML = brk.map(id=>actionBtn(id,s.actions[id],s.commands[id])).join('');
    $('#g-resp').innerHTML  = actionBtn('report',s.actions['report'],s.commands['report']);
    document.querySelectorAll('[data-run]').forEach(b=>b.onclick=()=>runAction(b.dataset.run));
    $('#btn-propose').onclick = propose;
    built = true;
  }

  const c = s.cluster, chip = $('#chip');
  if(!c.reachable){ chip.className='pill skip'; chip.innerHTML='<span class="dot"></span>cluster unreachable'; }
  else if(c.incident){ chip.className='pill bad'; chip.innerHTML='<span class="dot"></span>'+esc(c.incident.symptom); }
  else { chip.className='pill ok'; chip.innerHTML='<span class="dot"></span>healthy'; }

  renderPods(c); renderPending(s.pending);
  renderIncidents(s.incidents||[]); renderMetrics(s.metrics||[]);
  if(busy) document.querySelectorAll('.btn').forEach(b=>b.disabled=true);
}
refresh(); setInterval(refresh, 3000);
</script></body></html>
"""
