# Kubernetes Incident Responder

Detects failures in a running Kubernetes app, works out *why* from logs and events,
and applies a pre-approved fix — then verifies the app actually recovered and
reverts itself if it didn't. A language model does the diagnosis; everything that
touches the cluster is ordinary deterministic code behind a policy gate.

Runs entirely on a laptop against a local `kind` cluster. The model runs locally via
Ollama, so there are no API costs and nothing leaves the machine.

## Results

30 trials — 10 per failure type — each one a full cycle: reset to healthy, inject a
real failure, wait for detection, diagnose, gate, remediate, verify.

| Scenario | Trials | Symptom accuracy | Action accuracy | Recovered | Median MTTR | Actions outside allowlist |
|---|---:|---:|---:|---:|---:|---:|
| Crash loop (bad config) | 10 | 100% | 100% | 100% | 21s | 0 |
| Out of memory | 10 | 100% | 100% | 100% | 22s | 0 |
| Failed rollout (bad image) | 10 | 100% | 100% | 100% | 35s | 0 |

*Single machine, single cluster, `llama3.1:8b`, against the three failure types the
system was designed for. MTTR includes the verifier's polling interval, so read it
as an upper bound rather than precise instrumentation. Raw data in `eval/runs/`.*

## Why this isn't something Kubernetes already does

Kubernetes self-heals by **retrying**: it restarts crashed containers, reschedules
pods, and halts a rolling update whose new pods never become ready. What it never
does is change *what is wrong*. Its job is to make reality match the declared spec —
so if the spec itself is broken, it will faithfully enforce broken forever.

That is exactly what each of these failures looks like. `CrashLoopBackOff` **is**
Kubernetes failing: restarting the same pod with the same bad config, indefinitely.
An `OOMKilled` container is restarted under the same memory ceiling, forever. A
failed rollout correctly stalls — and then waits for a human. This system is the
piece that edits the spec, and choosing *which* edit requires reading evidence and
inferring cause.

## How it works

```
   ┌──────────┐   ┌───────────────┐   ┌────────┐   ┌──────────┐   ┌────────────┐   ┌──────────┐
   │ Watcher  │──▶│ Diagnostician │──▶│ Policy │──▶│ Approval │──▶│ Remediator │──▶│ Verifier │
   └──────────┘   └───────────────┘   └────────┘   └──────────┘   └────────────┘   └──────────┘
   deterministic      LLM             deterministic  deterministic   deterministic    deterministic
                                            │                                              │
                                            └──────── every step → append-only audit log ───┘
```

**Watcher** polls pod state and raises an incident only when there is real evidence
of failure — a bad waiting reason, a prior termination, or a restart. A pod that is
merely starting is not an incident. It classifies from *failing pods only*, so
healthy bystanders and leftovers from an earlier incident can't contribute signals.

**Diagnostician** is the single place a language model is used. It gathers raw
evidence (current and previous container logs, plus `kubectl describe` output —
because each failure hides its cause somewhere different) and returns a *validated,
structured* diagnosis: root cause, the evidence it relied on, and one proposed
action. Logs are never pre-filtered for known error strings; separating the real
error from benign startup noise is precisely the model's job.

**Policy** independently re-checks the proposal: on the allowlist, params sane, and
coherent with the observed symptom. It blocks the indefensible — raising a memory
limit for an image-pull failure — while still permitting more than one reasonable
action per symptom. On refusal the model gets **one corrected retry** with the
rejection reason; the rule is never widened to admit a bad proposal.

**Remediator** maps an approved action to a single `kubectl` command, built as an
argument list (no shell, nothing to escape), and shows a dry run before applying.
Model-supplied parameters are treated as untrusted: a proposed memory limit is only
used if it parses and falls inside a sane window, otherwise a default is substituted.

**Verifier** confirms recovery, and is deliberately *stricter* than detection:
evidence is enough to open an incident, but every pod must be ready to close one. If
the fix didn't work, the change is reverted — and the rollback goes through the same
gates as any other write.

### The three actions

The system can do exactly three things, enforced in the type system and re-checked
by policy:

- `raise-memory-limit` — patch the container's memory ceiling.
- `rollback-deployment` — `kubectl rollout undo` to the last good revision.
- `patch-config` — also implemented as a revert. **Deliberately**: an autonomous
  system should not invent configuration and apply it to a live cluster. For a bad
  config the safe move is to return to a version known to work. Surgical config
  patching is a future upgrade behind stronger safeguards, not a v1 feature.

## Least privilege

The two halves of the system run as different Kubernetes identities, defined in
`manifests/rbac.yaml`:

- **`responder-diagnostician`** reads pods, logs and events. It has no create,
  update, patch or delete verb anywhere.
- **`responder-remediator`** can patch and roll back the deployment — and nothing
  else. It cannot read pod logs; that isn't its job.

Every `kubectl` call impersonates the appropriate identity (`--as`), so the API
server authorises against that ServiceAccount's Role. This is enforced by the
cluster, not by the code being well-behaved: a write attempted under the read-only
identity is rejected even if the diagnostician were compromised or buggy. Prove it:

```bash
./scripts/rbac-check.sh
```

It shows the diagnostician reading pods successfully, being **refused** when it
attempts a write, the remediator being allowed that same write, and the remediator
being refused when it tries to read logs. Note that a server-side dry run is still
an authorised write request, so previews are subject to the same boundary.

## Quick start

Requires Docker, `kind`, `kubectl`, Python 3, and [Ollama](https://ollama.com)
running with a model pulled (`ollama pull llama3.1:8b`).

```bash
python3 -m venv .venv && source .venv/bin/activate
./scripts/dev.sh install
./scripts/dev.sh check          # verifies the toolchain
cp .env.example .env            # set OLLAMA_MODEL if you use a different model

./scripts/dev.sh cluster-up
kubectl apply -f manifests/sample-app.yaml
kubectl apply -f manifests/rbac.yaml     # the two least-privilege identities
```

Break it, then let the responder fix it:

```bash
./scenarios/oom.sh              # or crashloop.sh / rollout.sh
python src/main.py once         # add --safe to approve the change yourself
./scenarios/reset.sh
```

### Interactive control panel

```bash
python src/server.py            # http://127.0.0.1:8420
```

Buttons to start the cluster, inject each failure, and run the responder — each one
showing the exact command it will run, with live output. "Diagnose & propose" stops
at the approval gate so you can read the root cause, the chosen action, the policy
verdict and the dry run, then approve or reject. If policy refuses the action, there
is nothing to approve.

The browser never sends a command — only an action id, looked up in a fixed
allowlist, on a loopback-only socket.

### Evaluation

```bash
python eval/harness.py --trials 10
python src/main.py dashboard     # static HTML report from the audit log
```

## What evaluation caught

The first eval run reported **100% remediation success and 0% symptom accuracy** —
fixing worked, detecting didn't. It exposed two bugs a hand demo would have hidden:
the watcher was firing during normal rollout churn (reporting a generic "unhealthy"
before any failure signature existed), and it was classifying from *all* pods, so a
leftover pod's stale `OOMKilled` hijacked the diagnosis of an unrelated crash loop.

Those combined to silently weaken the safety gate: a misdetected generic symptom
permitted every action, so an incoherent proposal slipped through the coherence check
and "recovered" by luck. Detection accuracy turned out to be a safety property, not
just a metric. Both are fixed; the trajectory across runs was 0% → 67/100/100% → 100%.

## Limitations

- Local only, by design. Pointing this at a real cluster would need the permission
  model below, plus far more conservative defaults.
- Three failure types. Image-pull credential errors, failed PVC binding and
  unschedulable pods are not handled.
- The model's self-reported confidence is unreliable (the same clear case has come
  back as 0.09, 0.9 and 1.0), so nothing is gated on it. Action and evidence are the
  trustworthy signals.
- Scoped to one namespace, with identities bound by Role rather than ClusterRole.
  A multi-namespace deployment would need its permission model revisited.

## Built with

Python, Pydantic for validated models at every boundary, `kubectl` for cluster
access, Ollama for local inference, and the Python standard library for the control
panel. No cloud services.

---

Kubernetes® is a registered trademark of The Linux Foundation. This project is an
independent personal project, built for use with Kubernetes, and is not affiliated
with, sponsored or endorsed by The Linux Foundation, CNCF, or the Kubernetes project.
