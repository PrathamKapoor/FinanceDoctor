# STAGE 6 — FINANCIAL DOCTOR

## Case Experience UI & Hackathon Demo Interface

> **Status:** Complete — backend 163 tests pass, `ruff` clean, `mypy` clean;
> frontend 22 tests pass, `eslint` clean, `tsc` clean, `vite build` clean.

Stages 1–5 built the deterministic core. Stage 6 is primarily a **frontend
integration and case-experience stage** that makes that architecture visible.
Nothing in the Stage 1–5 backend machine was redesigned; Stage 6 only adds a
safe demo-session wrapper and a React case journey that consumes it.

---

## 1. Design philosophy

The UI communicates one thesis, visibly:

> A financial system has a problem.
> The Financial Doctor investigates it.
> The AI forms a diagnosis.
> The system proposes treatment.
> Deterministic safety systems validate the treatment.
> A human approves it.
> Razorpay executes the intervention.
> The Financial Doctor measures the outcome.

Engineering that matters — anomaly detection, worker evidence, differential
diagnosis, policy checks, approval immutability, provider execution,
measured recovery — is shown on screen, never hidden behind generic charts.
Money is rendered from backend integer minor units; no financial quantity is
recomputed client-side beyond a display-only minor→major conversion.

The visual identity is restrained: clinical precision, slate + teal, generous
white space, no neon gradients, no glassmorphism, no hospital cosplay.

---

## 2. Primary user journey

One active case, one continuous scroll:

```text
SYMPTOM → INVESTIGATION → DIAGNOSIS → PRESCRIPTION → SAFETY CHECK
        → APPROVAL → TREATMENT → OUTCOME → TIMELINE → SUMMARY
```

A left rail (`JourneyStepper`) tracks where the case is, which stages are
complete, and which needs the human. Each section is gated by real backend
state — nothing renders until its upstream record exists.

Entry: on mount the app calls `POST /demo/case/start` and lands on the known
seeded incident (`PAYMENT_METHOD_FAILURE_SPIKE`, UPI, seed 42). The human
moment (approve / reject) and downstream effects (execute, simulate) are
explicit buttons that call real backend endpoints. A "Run full demo" shortcut
chains the same three calls through the real API for hands-free judging.

---

## 3. Case stages

| # | Stage | Source record |
|---|-------|----------------|
| 1 | Symptom / incident | Stage 1 analytics + ground truth (deterministic) |
| 2 | Investigation | Stage 3 M2.7 worker outputs |
| 3 | Diagnosis | Stage 3 M3 `DiagnosisOutput` + flattened evidence |
| 4 | Prescription | Stage 4 `ProposedAction` + targets |
| 5 | Safety check | Stage 4 `PolicyDecisionRecord` (12 checks) |
| 6 | Approval | Stage 4 `ApprovalRequest` (PENDING → APPROVED/REJECTED) |
| 7 | Treatment | Stage 4 `ActionExecution` (stub `CREATE_PAYMENT_LINK` batch) |
| 8 | Outcome | Stage 5 `InterventionOutcome` + `TreatmentEffectiveness` |

`stages` (complete / active / status) and `timeline` ship inside every
read-model response, so the stepper and timeline never drift from state.

---

## 4. Component architecture (`frontend/src/`)

```text
App.tsx                      case state machine, action dispatch, gating
api/client.ts                typed demo-case HTTP client (same-origin / proxy)
api/types.ts                 read-model contracts (mirrors backend/read_model.py)
lib/format.ts                display-only money/ratio/datetime formatting
lib/status.ts                status tone + humanization helpers
components/
  Header.tsx                 brand, Demo environment + stub provider badges
  JourneyStepper.tsx         8-stage rail (complete / active / pending)
  SymptomSection.tsx         hero metrics + incident summary card
  HealthChart.tsx            dependency-free SVG: baseline→spike + method deltas
  InvestigationSection.tsx   four M2.7 worker cards (finding, supports/contradicts, confidence)
  DiagnosisSection.tsx       leading diagnosis, confidence label, differential, EvidenceExplorer
  PrescriptionSection.tsx    action, eligible targets, backend-controlled targets table
  SafetySection.tsx          per-check pass/fail checklist + snapshot hash
  ApprovalSection.tsx        human approval gate + approve/reject
  TreatmentSection.tsx       execution sequence + provider reference
  OutcomeSection.tsx         recovered revenue, recovery rate, per-target breakdown, simulate
  CaseTimeline.tsx           ordered event timeline (symptom → outcome)
  CaseSummary.tsx            screenshot-worthy one-screen recap
styles/global.css            single design-token stylesheet (no framework)
test/fixtures.ts             deterministic fixtures mirroring seed-42 backend values
```

No chart library, no router, no state manager. React 18 + Vite 5 + TypeScript,
`fetch` client, CSS variables. The production build is ~174 kB JS (54 kB gzip).

---

## 5. Backend integration

Stage 6 added a minimal, safe integration layer — **no Stage 1–5 service was
modified**:

- `backend/app/services/demo/session.py` — `DemoCaseSession` +
  `DemoSessionStore` + `run_demo_case()`. Runs the exact golden closed-loop
  sequence (world → inject → `run_investigation` → bundle/workers/M3 → plan →
  snapshot → policy → PENDING approval), then holds every artifact.
- `backend/app/services/demo/read_model.py` — `build_read_model()` serializes
  the session into the single `CaseView` contract. Read-only; never invokes
  M3, never executes, never mutates financial state.
- `backend/app/routers/demo_case.py` — the UI's only backend surface:

```text
POST /demo/case/start          seed → inject → investigate → diagnose → plan → policy → approval(PENDING)
GET  /demo/case/{id}           full aggregated read-model (CaseView)
POST /demo/case/{id}/approve   ApprovalService.approve (human gate)
POST /demo/case/{id}/reject    ApprovalService.reject
POST /demo/case/{id}/execute   ActionExecutor.execute (approval-gated; refuses unless APPROVED)
POST /demo/case/{id}/simulate  StubProviderSimulator → signed webhooks → outcome boundary
```

Also wired: `app.state.demo_store`, `GET /demo/case/{id}` for refresh, CORS
for the Vite dev server, and `CaseController` completing the pre-existing
`services/case/` stub as a thin facade (fixes a dangling import).

The frontend consumes real contracts at every step: incident metrics,
evidence, diagnosis, policy checks, approval, execution, and outcome are all
read from — or confirmed by — the backend. There is no local UI copy of
approval or execution state to go stale.

---

## 6. Demo mode

`POST /demo/case/start` loads the known seeded incident (seed 42, same world
the golden tests exercise), runs the deterministic stub M2.7/M3 pipeline
instantly, and parks at `HUMAN_APPROVAL_REQUIRED` with `PENDING` approval.
Badges label the environment ("Demo environment", "Stub provider") on every
screen. The demo needs **no** live Razorpay or MiniMax credentials.

Because stub models answer synchronously, the UI reports genuinely-completed
stages as complete — it never shows a fake "Investigating…" spinner for work
that already finished. Timeline timestamps are real wall-clock completions,
with the incident entry using the deterministic 2026-07-31 window.

`POST …/simulate` is the only outcome advancer, and it dispatches signed
`payment_link.paid` / `payment_link.cancelled` webhooks through the verified
`OutcomeWebhookHandler` — the default is a ~70%-paid / 1-expired partial
recovery that leaves pending targets, i.e. `PARTIALLY_RECOVERED` with real
recovered revenue.

---

## 7. Live mode

Verified live Razorpay/MiniMax clients from Stages 2–3 remain wired behind
the same adapters (`RAZORPAY_MODE`, `MINIMAX_*`). The UI never calls a
provider directly: any live path still routes `…/execute` through policy +
approval, and any live webhook still enters via the verified boundary. The
current build targets the stub for hackathon reliability.

---

## 8. Approval UX

The approval is a visually distinct gate (amber "Human approval required"
panel), not a checkbox. It states plainly that the AI recommended, the
policy engine validated, and a human must approve the exact immutable action
before any Razorpay operation. Approve/Reject are large, keyboard-focusable,
color-plus-text differentiated destructive actions calling the real approval
API; the UI shows `APPROVED`/`REJECTED` only after backend confirmation.
Execute is blocked (`409`) until approval is granted — verified by backend
test and enforced by the executor, not the frontend.

---

## 9. Policy visualization

`SafetySection` renders all 12 Stage 4 checks individually (authorization,
merchant configured, action type allowlist, amount limit, target count,
duplicate prevention, idempotency, eligibility, action integrity,
investigation integrity, rate limit, per-target amount), each with its
pass/fail state, backend message, and the immutable snapshot SHA-256.
A `REJECTED` decision (or any failed check) shows a blocked state and the
approval gate never opens.

---

## 10. Outcome visualization

`OutcomeSection` shows recovered revenue (₹ minor→major), recovery and
revenue-recovery rates, per-target recovered / pending / unrecovered /
expired breakdown, and conversion rate — all from `InterventionOutcome` +
`TreatmentEffectiveness`. Partial, pending, full, and failed states each
render distinctly (status tone + label, never color alone).

---

## 11. Error handling

Meaningful states, never infinite spinners: backend unavailable (entry
screen, retry), investigation failure, rejected policy (blocked gate), approval
conflict/expired (`409` surfaced inline), execution failure (execution
screen shows provider error), outcome-unavailable (simulate disabled until an
execution exists). Each action error preserves case context and offers retry.

Loading copy names the real step ("Loading financial evidence",
"Executing…", "Simulating webhook…"), not generic "Loading…".

---

## 12. Testing strategy

Backend (`tests/demo/test_demo_case.py`, 6 tests): exact Stage 1 values
(z = 10.854, 4.54 % → 21.75 %, 3.79×), leading diagnosis, action type,
12 policy checks, execute-before-approval `409`, reject-blocks-execute,
full HTTP journey → `PARTIALLY_RECOVERED` with recovered amount > 0.

Frontend (22 tests, Vitest + React Testing Library): format helpers;
incident metrics; diagnosis + confidence labeling (no fabricated %);
differential + evidence explorer; all-checks policy render and failed-check
block; approve/reject call-through and post-decision state; execution
success/failure visibility; partial/pending outcome rendering; mocked
end-to-end approve → execute → simulate journey.

---

## Final verification

```text
Case interface:
  incident/symptom: PASS
  investigation: PASS
  diagnosis: PASS
  evidence explorer: PASS
  prescription: PASS
  policy visualization: PASS
  approval UX: PASS
  execution UX: PASS
  outcome UX: PASS
  case timeline: PASS

Backend integration:
  real backend contracts: PASS
  approval boundary preserved: PASS
  direct provider access from frontend: NO

Demo mode:
  seeded case: PASS
  complete journey: PASS
  stub provider: PASS

Safety:
  policy bypass: NO
  approval bypass: NO
  direct Razorpay access: NO
  arbitrary financial modification: NO

Tests:
  backend: 163 passed (157 prior + 6 new)
  frontend: 22 passed

Lint:
  PASS (ruff; eslint 0 errors, 0 warnings)

Typecheck:
  PASS (mypy; tsc)

Build:
  PASS (vite build)
```

Stage 7 is not started. The interface is the explanation of why the
Financial Doctor can be trusted:

```text
AI REASONS → POLICY CONSTRAINS → HUMAN APPROVES → RAZORPAY ACTS → SYSTEM MEASURES
```
