# STAGE 0 — FINANCIAL DOCTOR

## Repository Reconnaissance, Architecture & Implementation Plan

> **Status:** Greenfield. This document records the result of Stage 0 reconnaissance and
> establishes the smallest credible architecture for the Financial Doctor MVP.

---

## 1. Repository overview

The target workspace `C:\Projects\financialdoctor` is **empty**. There is:

- no source code,
- no `package.json`, `pyproject.toml`, or `requirements.txt`,
- no `.git` repository,
- no documentation,
- no configuration or environment files,
- no existing tests.

There is therefore **no existing Financial Doctor work to reconstitute, no unrelated
system to destabilize, and no reusable in-repo code.** Everything in this project must be
created from scratch.

Adjacent sibling directories under `C:\Projects` (`guardrailed-product`,
`fastapi-concurrency-performance_study`, `QiskitFallFest*`, `hackathon_v3`, etc.) are
**unrelated projects** (quantum computing, agentic MLOps, FastAPI concurrency research)
and are out of scope for this repository. They are referenced in this document **only** as
evidence of the author's established toolchain and project conventions, not as reusable
Financial Doctor components.

### Decision: where Financial Doctor lives

Given an empty repository, there is no integration decision to make against existing code.

**Financial Doctor is built as a single, self-contained application (`apps/`) inside this
repository**, not bolted onto an existing app and not split into microservices (see §4).

---

## 2. Current technology stack

Since the repository is empty, the stack is **proposed**, grounded in:

1. the product thesis (Razorpay-native, agentic financial intelligence),
2. the architectural principle (deterministic financial arithmetic in code, LLMs reason over
   results only),
3. the author's verified local toolchain and conventions (observed in sibling projects).

### Verified local toolchain

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.13.14 | Active interpreter |
| Node.js | v24.19.0 | Frontend runtime |
| npm | 12.0.2 | Frontend package manager |
| uv | 0.12.5 | Python dependency/venv manager (preferred over bare pip) |
| pip | 26.1.2 | Fallback package installer |
| git | 2.55.0 | VCS (repo not yet initialized) |
| Docker | **not installed** | Do not assume containers in the MVP |
| poetry | not installed | Not used |

### Proposed stack for Financial Doctor

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Frontend** | React + Vite + TypeScript | Matches author conventions; fast dev loop for a hackathon demo |
| **Backend** | Python 3.13 + FastAPI (`fastapi`, `uvicorn`, `httpx`) | Deterministic financial analytics is natural in Python; the project brief itself specifies a FastAPI backend |
| **Database** | SQLite (via `sqlite3` / SQLAlchemy) + optional JSON evidence files | Zero-infra persistence appropriate for a hackathon; no Docker available |
| **Languages** | Python (backend/analytics/policy), TypeScript (frontend) | — |
| **Package manager** | `uv` (backend), `npm` (frontend) | Already installed; fast and reproducible |
| **Deployment** | Local `uvicorn` dev server + Vite dev server; single-process | No container/Docker requirement for the MVP |
| **Testing** | `pytest` (backend), Vitest (frontend, optional) | Matches author conventions (`pytest>=8`) |
| **Config** | `.env` + `pydantic-settings` | `.env.example` convention observed in sibling repo |
| **Dev ergonomics** | `ruff` (lint) + `mypy` (types) | Lightweight, no heavy tooling |

---

## 3. Reusable components

There are **no reusable Financial Doctor components inside this repository** (it is empty).

**Reference patterns** (to mimic, not to import) from sibling projects:

- **FastAPI app layout** — `backend_api/app/{config.py, dependencies.py, main.py, routers/, schemas/, services/}` (from `guardrailed-product`). Adopt the same structure.
- **Config via `.env` + `pydantic-settings`** pattern.
- **`pyproject.toml` with `[project.optional-dependencies] dev = ["pytest"]`** and a single
  `tests/` directory (`testpaths = ["tests"]`).
- **Read-only / immutability discipline** — `guardrailed-product` enforces that the product
  layer never writes research artifacts. Financial Doctor adopts the analogous principle
  inverted: the *policy engine* gates all writes, and the codebase must never let an LLM
  perform financial arithmetic or autonomously trigger a write.

Anything else must be built new. Do **not** pull unrelated code from sibling repos.

---

## 4. Proposed architecture

### Guiding constraints

- **Single process.** FastAPI app + optional separate Vite dev server. No microservices, no
  message broker, no Docker. Internal "components" are Python modules, not services.
- **Deterministic core.** All financial quantities (counts, deltas, averages, anomaly scores,
  totals) are computed in Python. The LLM layers only *read and explain* pre-computed numbers.
- **Unverified external APIs behind adapters.** Razorpay and MiniMax capabilities are not yet
  verified; both sit behind adapters with a **mock/stub implementation** that powers the demo
  until real keys are available.
- **No autonomous financial actions.** Every write must pass the deterministic policy engine
  and (for financial writes) require human approval.

### Layered architecture (logical, single process)

```
                    ┌─────────────────────────────┐
                    │         Frontend (React)     │
                    │   Incident feed / chat / txn │
                    └──────────────┬──────────────┘
                                   │ HTTPS / JSON
                    ┌──────────────▼──────────────┐
                    │     API (FastAPI backend)    │
                    │  routers · authz · task API  │
                    └──────────────┬──────────────┘
                                   │
      ┌────────────────────────────┼─────────────────────────────┐
      │                            │                             │
┌─────▼─────────────┐   ┌──────────▼───────────┐   ┌─────────────▼──────────┐
│ Razorpay Adapter  │   │ Financial State Layer │   │  Agent Orchestrator     │
│ (read/write gate) │──▶│ (ingest + normalize) │──▶│  (run investigation)    │
└───────────────────┘   └──────────┬───────────┘   └─────────────┬──────────┘
      ▲                            │                             │
      │  (writes only after       ┌▼──────────────────┐          │
      │   policy + approval)      │ Deterministic     │          │
      │                           │ Analytics Engine  │          │
      │                           └──────────────────┘          │
      │                            │   produces                  │
      │                            ▼                             │
      │                    ┌────────────────────┐                │
      │                    │   Evidence Store    │◀───────────────┘
      │                    └────────────────────┘     reads
      │                            │
      │                            ▼
      │                    ┌────────────────────┐
      │                    │ M2.7 Investigation │  (parallel workers)
      │                    │     Workers        │
      │                    └─────────┬──────────┘
      │                              ▼
      │                    ┌────────────────────┐
      │                    │  Evidence Bundle    │
      │                    └─────────┬──────────┘
      │                              ▼
      │                    ┌────────────────────┐
      │                    │   M3 Diagnosis      │  (senior reasoner)
      │                    └─────────┬──────────┘
      │                              ▼
      │                    ┌────────────────────┐
      │                    │  ProposedAction     │
      │                    └─────────┬──────────┘
      │                              ▼
      │                    ┌────────────────────┐
      │                    │   Policy Engine     │  (deterministic)
      │                    └─────────┬──────────┘
      │    APPROVE/HUMAN_APPROVAL_REQUIRED/REJECT
      │                              ▼
      │                    ┌────────────────────┐
      │                    │  Human Approval     │
      │                    └─────────┬──────────┘
      └──────────────────────────────┘  (approved write)
                                       ▼
                              ┌────────────────────┐
                              │ RazorpayAdapter    │  (execute)
                              └─────────┬──────────┘
                                        ▼
                              ┌────────────────────┐
                              │ Webhook/Event Layer│
                              └─────────┬──────────┘
                                        ▼
                              ┌────────────────────┐
                              │ Outcome Evaluator  │
                              └─────────┬──────────┘
                                        ▼
                                   Financial State (update)
```

### Component responsibilities (single process)

| Component | Responsibility | Deterministic? |
|-----------|---------------|----------------|
| **Razorpay Adapter** | Normalize raw Razorpay payloads into internal entities (§8) | yes (mapping) |
| **Financial State Layer** | Own the authoritative, normalized view of a merchant's financial state; apply deltas | yes |
| **Deterministic Analytics Engine** | Compute counts, rates, baselines, anomaly scores, cohort stats, totals | **yes (pure code)** |
| **Evidence Store** | Persist normalized facts + computed metrics that workers/M3 read | data only |
| **Agent Orchestrator** | Drive the investigate→diagnose→propose pipeline; enforce ordering | orchestration |
| **M2.7 Investigation Workers** | Reason over pre-computed evidence along one dimension each (§6) | no (LLM) |
| **Evidence Bundle** | Structured, typed aggregation of worker findings + raw metrics | data |
| **M3 Diagnosis** | Rank hypotheses, explain, propose ONE intervention, strict JSON out | no (LLM) |
| **Policy Engine** | Deterministic approve/reject/needs-approval of a proposed action (§7) | **yes (pure code)** |
| **Human Approval** | Explicit in-band approval gate for financial writes | flow |
| **Webhook/Event Layer** | Receive Razorpay events, correlate to executions | routing |
| **Outcome Evaluator** | Measure recovery result, close the loop, update state | yes |

The **only** LLM touchpoints are M2.7 (workers) and M3 (diagnosis). Everything numeric flows
through the Deterministic Analytics Engine first.

---

## 5. Data model proposal

Principle: **minimal, and every entity must earn its place in the Payment Failure Incident
flow.** Modeled as SQLite tables predicated by a single merchant assumption (MVP demo runs a
single merchant; the schema still tags `merchant_id` for correctness).

### Core entities

| Entity | Justification | Key fields |
|--------|---------------|------------|
| **Merchant** | Anchor of the system; Razorpay account identity | `id`, `razorpay_merchant_id`, `name` |
| **Customer** | Failed-payment recovery targets a customer; enables cohort/contact | `id`, `merchant_id`, `razorpay_customer_id`, `email`, `phone`, `created_at` |
| **Order** | Razorpay Order is the unit a payment settles against; links customer→payment | `id`, `merchant_id`, `customer_id`, `razorpay_order_id`, `amount`, `currency`, `status`, `created_at` |
| **Payment** | The primary object; **failure detection happens here** | `id`, `order_id`, `razorpay_payment_id`, `amount`, `currency`, `status`, `method`, `error_code`, `error_description`, `attempt_count`, `created_at` |
| **PaymentAttempt** | Failure incidents involve retries across attempts; needed for deltas/baselines | `id`, `payment_id`, `attempt_index`, `status`, `error_code`, `created_at` |
| **Refund** | A legitimate recovery action for overcharge/bad capture; needed later but cheap now | `id`, `payment_id`, `razorpay_refund_id`, `amount`, `status`, `created_at` |
| **Invoice** | Razorpay Invoices/Payment Links are the *verified recovery vehicle* for re-collection | `id`, `customer_id`, `razorpay_invoice_id`, `short_url`, `amount`, `status`, `created_at` |
| **Settlement** | Outcome of settled payments; needed to measure recovery at settlement level | `id`, `payment_id`, `razorpay_settlement_id`, `amount`, `status`, `created_at` |
| **FinancialEvent** | Normalized, deduplicated inbound events from Razorpay webhooks | `id`, `source`, `event_type`, `payload`, `processed_at` |
| **Investigation** | One closed-loop run of the agent for one incident | `id`, `incident_id`, `status`, `created_at`, `completed_at` |
| **Hypothesis** | A competing explanation for the anomaly (M2.7/M3 generation) | `id`, `investigation_id`, `statement`, `supporting_evidence_refs`, `score` |
| **Evidence** | A single deterministically-derived fact/metric, machine-readable | `id`, `investigation_id`, `kind`, `value`, `unit`, `window`, `source` |
| **Recommendation** | M3's ranked output: leading hypothesis + proposed intervention | `id`, `investigation_id`, `leading_hypothesis_id`, `rationale`, `confidence` |
| **ProposedAction** | The concrete, typed action M3 proposes (single, bounded) | `id`, `recommendation_id`, `action_type`, `params` (JSON), `amount`, `target_ref` |
| **PolicyDecision** | Deterministic verdict on a ProposedAction | `id`, `proposed_action_id`, `verdict` (`APPROVE`/`REJECT`/`HUMAN_APPROVAL_REQUIRED`), `reasons[]`, `checks` (JSON) |
| **Execution** | Records an actually-performed Razorpay write (post-approval) | `id`, `policy_decision_id`, `provider_op_id`, `status`, `request`, `response`, `occurred_at` |
| **Outcome** | Post-action measurement: did it close the incident? | `id`, `execution_id`, `incident_id`, `resolution` (`RECOVERED`/`PARTIAL`/`UNRESOLVED`), `evidence_refs` |

> **Stage 5 refinement.** The `Outcome` entity was finalized in Stage 5 as
> `InterventionOutcome` + per-target `RecoveryTargetOutcome` (see
> `backend/app/schemas/outcome/` and `docs/STAGE_5_OUTCOMES.md`). The aggregate status is
> `PENDING` / `PARTIALLY_RECOVERED` / `RECOVERED` / `NO_RECOVERY` / `EXPIRED` / `FAILED`,
> derived deterministically by `OutcomeEvaluator` from provider-confirmed target states.
> Finalization is driven by observation windows, not an LLM.

### Justification of exclusions

- **No `Settlement`-level ledger/accounting.** MVP measures a single recovery outcome, not a
  general ledger (explicitly out of scope per constraints).
- **No `User`/`Admin` account model beyond minimal auth.** Hackathon scope; §7 encodes
  authorization as a policy check, not a full RBAC system.
- **No `LLMConversation`/chat-history entity.** Financial Doctor is not a generic chatbot;
  interaction is structured around investigations.

### Relationship summary

```
Merchant 1─n Customer 1─n Order 1─n Payment 1─n PaymentAttempt
                                        │
                                        ├─n Refund
                                        └─n Settlement
Investigation 1─n Hypothesis
Investigation 1─n Evidence
Investigation 1─1 Recommendation 1─1 ProposedAction 1─1 PolicyDecision
PolicyDecision 1─1 Execution 1─1 Outcome
FinancialEvent → (correlates to) Payment/PaymentAttempt/Refund/Settlement
```

---

## 6. Agent architecture

All LLM calls use a **`ModelClient` interface** abstracting provider specifics (BaseMiniMax /
OpenAI-compatible HTTP) so the demo can run against **stubbed/deterministic fakes** when keys
are absent or response schemas are unverified.

### Model routing

| Role | Model | Character |
|------|-------|-----------|
| **Investigation Workers** | MiniMax **M2.7** | Parallel, cheap, evidence-oriented. Many small structured calls. |
| **Senior Reasoner** | MiniMax **M3** | One high-quality call. Diagnosis, hypothesis ranking, intervention proposal. |
| **Voice (optional)** | MiniMax **Speech 2.8** | STT/TTS wrapper around the same agent (never the source of truth). |
| **Music 3.0** | — | **Out of scope for the MVP.** Revisit only if demonstrable value emerges. |

### M2.7 — investigation workers

Responsibilities: **analyze one dimension of a pre-computed evidence bundle** and return
structured findings. M2.7 never computes totals/rates; it receives them as inputs.

Suggested worker dimensions (parallel, each returns typed findings + confidence):

| Worker | Dimension | Deterministic inputs it receives |
|--------|-----------|----------------------------------|
| `TemporalWorker` | Time-of-day / day-of-week / period baselines | failure rate vs. time windows, spike/z-score |
| `PaymentMethodWorker` | Method-level failure profile | per-method failure rates, attempt counts |
| `CohortWorker` | Customer cohort behavior | new vs. returning, geolocation, device |
| `TransactionWorker` | Amount/currency/characteristic signals | amount buckets, currency distribution |
| `RelationshipWorker` | Order↔payment↔attempt consistency | mismatch counts, partial captures, retries |

Each worker:

1. receives a **constrained evidence slice** (typed, with units),
2. proposes/weighs hypotheses with confidence,
3. requests specific additional evidence if needed (via a strict "evidence request" output),
4. returns **strict structured output** (validated against a Pydantic schema; invalid output
   → retry with a trimmed prompt or fall back to the deterministic default).

### M3 — senior reasoner

Receives the **Evidence Bundle** (deterministic metrics + M2.7 worker findings) and:

1. evaluates **competing hypotheses** against the evidence,
2. **explains** the evidence in natural language (no arithmetic invented — it quotes the
   provided numbers),
3. selects the **leading hypothesis** with calibrated confidence,
4. proposes **exactly one bounded intervention** as a `ProposedAction`,
5. returns **strict structured output** (Pydantic-validated; `action_type` must belong to a
   fixed allowlist recognized by the Policy Engine).

M3 output is **advisory only** — it flows directly into the deterministic Policy Engine and
cannot trigger a write by itself.

---

## 7. Policy architecture

The Policy Engine is **deterministic Python code**, not an LLM. It maps `ProposedAction` →
`PolicyDecision`.

```
         M3 ProposedAction
                │
                ▼
┌───────────────────────────────────────────────┐
│              Policy Engine (code)             │
│  1. authenticate + authorize actor           │
│  2. validate action_type against allowlist   │
│  3. amount-limit checks                      │
│  4. eligibility (state preconditions)        │
│  5. duplicate prevention + idempotency       │
│  6. rate limits                              │
│  7. approval requirement determination       │
└───────────────────────────────────────────────┘
                │
                ▼
   APPROVE / REJECT / HUMAN_APPROVAL_REQUIRED
```

### Checks (each produces a pass/fail + reason, recorded on `PolicyDecision.checks`)

| Check | Rule (MVP) |
|-------|-----------|
| **Authorization** | Actions require a role/token from the API layer; `customer-facing` recovery requires an authenticated operator (demo: dev token in `.env`) |
| **Action type allowlist** | `action_type` ∈ `{CREATE_PAYMENT_LINK, ISSUE_REFUND}`. Unknown types → `REJECT`. |
| **Amount limits** | Recovery amount must equal the failed amount (payment-link) or be ≤ the captured amount and ≤ a configurable `MAX_AUTO_*_AMOUNT` (refund). Anything above limit → `HUMAN_APPROVAL_REQUIRED`. |
| **Eligibility** | Preconditions verified against Financial State (e.g. payment still in `failed`/`overpaid` state and not already resolved; order not already paid). |
| **Duplicate prevention** | Same incident + same action type already executed → `REJECT` (block re-issuing duplicate refunds/links). |
| **Idempotency** | Every proposed action carries a deterministic `idempotency_key` (incident + action hash); re-submission returns the existing `PolicyDecision`/`Execution`. |
| **Rate limits** | Max N proposed actions per incident and per merchant per window → `HUMAN_APPROVAL_REQUIRED`/`REJECT`. |
| **Approval requirement** | All financial **writes** default to `HUMAN_APPROVAL_REQUIRED`. Read-only/analysis proposals are auto-approved and never touch Razorpay. |

### Deterministic invariants

- The engine performs **zero** arithmetic that an LLM supplied. All limit comparisons use
  amounts computed by the Analytics Engine or state layer.
- `REJECT` is terminal for the pipeline (`Outcome = UNRESOLVED`, no side effects).
- `HUMAN_APPROVAL_REQUIRED` produces no write until an explicit approve action arrives via the
  API with an `approval` token.

---

## 8. Razorpay integration boundary

**Razorpay capabilities are NOT verified at this stage.** The adapter below is an abstraction
(`RazorpayAdapter`) with a `StubRazorpayAdapter` for demo mode. Nothing here is claimed to be
confirmed against the current Razorpay API until a later verification step.

### Adapter interface (operations the MVP *needs*)

Legend: `R` = read, `W` = write, `EV` = webhook/event, `AP` = requires human approval,
`VERIFY` = requires API verification before implementation.

| # | Operation | Kind | Approval | Verify | Purpose in MVP |
|---|-----------|------|----------|--------|----------------|
| 1 | Fetch payments (filtered by status/order/date) | R | — | VERIFY | Populate Financial State + detect `failed` |
| 2 | Fetch payment by id | R | — | VERIFY | Incident root-cause detail |
| 3 | Fetch orders | R | — | VERIFY | Order↔payment relationship worker |
| 4 | Fetch refunds | R | — | VERIFY | Identify overcharge/duplicate-capture recovery |
| 5 | Fetch settlements | R | — | VERIFY | Outcome measurement at settlement level |
| 6 | Fetch customers | R | — | VERIFY | Cohort / contact for recovery |
| 7 | Create **Payment Link** (re-collection) | W | **AP** | VERIFY | **Primary recovery action** for failed payment |
| 8 | Create **Refund** | W | **AP** | VERIFY | Secondary recovery (overcharge); gated + limited |
| 9 | Receive **webhook** (`payment.failed`, `payment.captured`, `refund.processed`, `order.paid`) | EV | — | VERIFY | Drive the webhook/outcome loop |

### Non-assumptions (explicit)

- **No arbitrary payment retries.** Razorpay does not expose "retry this failed card payment"
  as a first-class operation. The MVP's legitimate recovery path is **re-initiation via
  Payment Link / fresh Order**, not a retry.
- **No capability invented.** Auto-capture settings, UPI-intent re-prompt, or chargeback
  reversal are all listed as *unverified* and are NOT part of the MVP.
- **Every write** (`W`) requires (a) Policy Engine `HUMAN_APPROVAL_REQUIRED` → explicit
  approval, and (b) API verification completed first. Until verification, the demo runs on
  `StubRazorpayAdapter` only.

---

## 9. MVP boundary

The MVP implements **exactly one incident type**:

### Payment Failure Incident

```
Detect payment failure anomaly
        ↓
Analyze deterministic evidence
        ↓
M2.7 investigation
        ↓
M3 diagnosis
        ↓
Policy validation
        ↓
Human approval
        ↓
One verified Razorpay recovery action  (Payment Link re-collection)
        ↓
Outcome
```

### MUST HAVE

- Razorpay-in-the-loop data ingestion + normalization (or a **deterministic seed/`StubRazorpayAdapter`** feeding realistic synthetic data).
- Deterministic failure-detection (failure-rate spikes vs baseline; failed payment count).
- Deterministic Analytics Engine producing the evidence bundle.
- Evidence Store persistence.
- M2.7 investigation workers (temporal, payment-method, cohort, transaction, relationship).
- M3 diagnosis producing a single `ProposedAction`.
- Deterministic Policy Engine with the checks in §7.
- Human approval gate (in-band API + simple UI toggle).
- ONE verified recovery action: **Payment Link re-collection** (stubbed until verified).
- Webhook/event ingestion feeding the Outcome Evaluator.
- Outcome Evaluator closing the loop (RECOVERED / PARTIAL / UNRESOLVED).
- Minimal React dashboard: incident list → investigation view → evidence → diagnosis → approval.
- Structured, schema-validated LLM output with deterministic fallback.

### DEMO ENHANCEMENT

- Text consultation interface against the completed investigation (optional).
- Speech 2.8 voice consultation (`Text → Speech → agent → Speech`), clearly optional.
- Screenshot/document evidence attachment viewed in the incident timeline.
- Replay of a canned incident with synthetic Razorpay data and a **fake webhook** (deterministic demo without live keys).

### DEFERRED

- Refund/overcharge incident (second incident).
- Settlement reconciliation incident (third incident).
- More than one merchant / multi-tenant auth.
- Music 3.0 integration.
- Autonomous (no-human) financial actions.
- Real Razorpay audit-grade ledger/accounting.
- Additional Razorpay operations not listed in §8.
- Full CI/CD, Docker deployment, production observability.

**Scope guard:** any new incident, new Razorpay op, or new modality outside this list requires
an explicit Stage-0-equivalent decision before implementation.

---

## 10. Multimodal architecture

### Text — primary

The core interaction is the structured investigation flow and the minimal dashboard. Text is
first-class and mandatory.

### Screenshot / document — additional evidence

Attached as `Evidence` rows of `kind = attachment` with a content-type and (later) OCR/im.
They are **supplementary context for M3**, never a substitute for deterministic metrics, and
are optional for the MVP.

### Speech 2.8 — optional consultation interface

```
User voice
    ↓
Speech 2.8 (STT)
    ↓
Financial Doctor agent   (queries existing Evidence Store / investigation)
    ↓
Structured response (M3, quoting deterministic evidence)
    ↓
Speech 2.8 (TTS)
    ↓
Voice response
```

Constraints:

- Voice is a **read-only consultation overlay**. It cannot drive writes; any action it
  surfaces still routes through the Policy Engine + human approval.
- Voice is **not mandatory** and not shipped in the MUST HAVE slice.
- `Speech 2.8` wrappers sit behind the same `ModelClient` abstraction; unverifiable responses
  fall back to text.
- **Stage 7A update (implemented, see `docs/STAGE_7A_SPEECH_CONSULTATION.md`):**
  TTS via the verified HTTP T2A contract (`speech-2.8-turbo`) is live behind
  `SPEECH_PROVIDER`; no public MiniMax speech-to-text endpoint could be
  verified, so voice input is typed-only (never faked) and only spoken
  answers use Speech 2.8.

### Music 3.0 — excluded

No MVP role. Revisit only if it objectively improves the product; not planned.

---

## 11. Evaluation framework

The system will be measured (eventually, not in Stage 0) along these axes:

| Metric | Definition | Primary signals |
|--------|-----------|-----------------|
| **Anomaly detection accuracy** | True/false positive rate of failure detection | labeled synthetic incident set |
| **Diagnosis accuracy** | Leading hypothesis matches ground-truth root cause | seeded root-cause labels |
| **Evidence sufficiency** | Did the bundle contain enough to reach the correct diagnosis? | recall of required evidence |
| **Evidence precision** | Fraction of bundle items actually relevant | relevance labels per incident |
| **Hypothesis calibration** | M3 confidence vs. empirical correctness | Brier/ECE over a run-set |
| **Action accuracy** | ProposedAction matches the correct recovery | ground-truth action labels |
| **Policy violation rate** | Failed policy checks / blocked invalid actions | policy engine audit log |
| **False intervention rate** | Actions taken on incidents that needed none | outcome labels |
| **Recovery outcome** | RECOVERED / PARTIAL / UNRESOLVED rate | Outcome Evaluator |
| **Model routing** | Was M2.7 vs M3 vs deterministic chosen correctly? | routing/fallback log |
| **Latency** | End-to-end incident time; per-stage cost | timing spans |
| **Tool-call efficiency** | Structured calls per successful diagnosis | call count vs. outcome |

Hardware for future evals: a **seeded synthetic Razorpay dataset** with known root causes
(e.g. "bank declined", "insufficient funds", "method outage", "card expired") mapped to
expected diagnoses and expected recovery actions.

---

## 12. Development stages

Implementation dependency graph (order, not schedule). **Not executed in Stage 0.**

```
  1. Data model                     (SQLite schema + SQLAlchemy/Pydantic models)
          │
  2. Deterministic analytics        (Analytics Engine → Financial State → Evidence Store)
          │
  3. Razorpay adapter               (interface + StubRazorpayAdapter + synthetic seed data)
          │                          (pairs with a Razorpay API verification pass)
  4. Investigation engine            (Agent Orchestrator + ModelClient abstraction + fakes)
          │
  5. M2.7 workers                    (five parallel dimension workers + schema validation)
          │
  6. M3 diagnosis                    (hypothesis ranking + strict structured output)
          │
  7. Policy engine                   (deterministic checks in §7)
          │
  8. Action execution                (approved write via RazorpayAdapter)
          │
  9. Webhook / outcome loop          (FinancialEvent ingest → Outcome Evaluator → state update)
          │
 10. Multimodal input                (text first; screenshot attachment)
          │
 11. Speech 2.8                      (optional STT/TTS consultation overlay)
          │
 12. Frontend                        (React incident dashboard → investigation → approval)
          │
 13. Benchmark                       (synthetic labeled dataset + §11 metrics)
          │
 14. Integration                     (wire together; run the full loop end-to-end)
          │
 15. Demo mode                       (deterministic canned incident replay; fake webhook)
```

### Stage dependencies (fan-in)

- `2` depends on `1` (schema). `3` depends on `2` for normalization targets but can be stubbed
  first to unblock `4`.
- `5`, `6` depend on `4` and parallelize against `2`'s output (`Evidence Store`).
- `7` depends only on `6`'s output contract (`ProposedAction`), so `7` can be built in parallel
  with `5`/`6`.
- `8` depends on `3` (adapter) + `7` (policy).
- `9` depends on `3` + `7`.
- `12` depends on `4`–`9` for its data contracts; the READ-only UI can start against `3` early.
- `15` (demo) is the final capstone, exercising `2`–`9` with zero live keys.

### Stage 6 note — case interface (implemented, see `docs/STAGE_6_CASE_INTERFACE.md`)

Item `12` (frontend) was delivered as a single active-case journey
(`frontend/`: React + Vite + TypeScript, no chart library, no router) over a
new aggregated read-model. To support it, one minimal integration layer was
added — `services/demo/` (session + read-only read-model), `routers/demo_case.py`
(start / get / approve / reject / execute / simulate), and
`services/case/case_controller.py` completing this document's pre-existing
Stage 6 stub. No Stage 1–5 service was modified; the demo runs the golden
seed-42 incident through policy → human approval → stub execution → verified
webhook outcome with zero live keys.

---

## Appendix A — current test/build check status (Stage 0)

As part of Stage 0 close-out, the following was attempted:

- **Test suite:** none exists (empty repository). `pytest` found no tests to run.
- **Build/lint/typecheck:** none defined (no `pyproject.toml`, `package.json`, or lockfiles).
- **Version control:** no `.git` repository initialized.

**Result:** No existing tests or build checks exist to pass or fail. The baseline for Stage 1
is a **truly clean slate**; the first implementing stage must also introduce `pyproject.toml`
(with `pytest`, `ruff`, `mypy`) and the initial test scaffolding.

---

## Appendix B — open items requiring verification before/at Stage 1

1. **Razorpay API surface** — confirm operations in §8 against current docs (payment-link
   creation, refund, webhook events, fetch endpoints) and obtain a test-mode key.
2. **MiniMax API surface** — confirm `M2.7` / `M3` / `Speech 2.8` access method, response
   schema, and pricing; establish the `ModelClient` contract and fallback stubs.
3. **Repository init** — `git init`, `.gitignore`, Python project scaffolding via `uv`.
4. **Single-merchant demo assumption** — confirm the hackathon demo runs one test merchant and
   one synthetic/frozen dataset.