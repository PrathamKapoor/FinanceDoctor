# STAGE 5 — FINANCIAL DOCTOR

## Outcome Evaluator & Closed-Loop Financial Feedback

> **Status:** Complete — 157 tests pass, `ruff` clean, `mypy` clean.

---

## 1. Outcome architecture

Stage 5 adds the **observation and measurement layer** that closes the loop begun in
Stages 1–4. The Financial Doctor does not declare success when it writes a prescription; it
declares success — or failure — based on the measured patient outcome.

```
SYMPTOM        (incident / anomaly)          Stage 1
   ↓
INVESTIGATION  (M2.7 workers)                Stage 3
   ↓
DIAGNOSIS      (M3)                          Stage 3
   ↓
PRESCRIPTION   (ProposedAction)              Stage 4
   ↓
APPROVAL       (Policy + human gate)         Stage 4
   ↓
TREATMENT      (CREATE_PAYMENT_LINK)         Stage 4
   ↓
FOLLOW-UP      (webhook)                     Stage 5
   ↓
MEASURED OUTCOME                            Stage 5
```

The loop is strictly bounded:

```
ACT → OBSERVE → MEASURE → RECORD
```

There is **no** autonomous second treatment. Stage 5 never models:

```
Outcome bad → M3 → automatically retry
Outcome bad → create another Payment Link
Outcome bad → automatically refund
```

A poor recovery result is surfaced as "treatment effectiveness insufficient" and nothing
else. No financial action occurs automatically.

---

## 2. Outcome domain model

*File:* `backend/app/schemas/outcome/intervention_outcome.py`

`InterventionOutcome` is the strongly-typed aggregate measurement of one recovery action.

| Field | Purpose |
|-------|---------|
| `outcome_id` | Synthetic stable identifier (`out_…`) |
| `action_id` | The `ProposedAction.action_id` that produced this intervention |
| `execution_id` | The `ActionExecution.execution_id` (set post-execution) |
| `investigation_id` | Upstream investigation |
| `diagnosis_id` | Upstream diagnosis |
| `approval_id` | The approval that authorized execution |
| `status` | `OutcomeStatus` (deterministic, §3) |
| `targets_total` / `targets_pending` / `targets_succeeded` / `targets_failed` / `targets_expired` | Target rollups, kept in sync by `OutcomeEvaluator` |
| `currency` | ISO-4217 (default `INR`) |
| `amount_targeted_minor` | Sum of expected target amounts (integer minor units) |
| `amount_recovered_minor` | Sum of recovered target amounts (integer minor units) |
| `conversion_rate` | Deterministic `succeeded / total` (`None` when `total == 0`) |
| `created_at` | Initialization timestamp (used for time-to-recovery metrics) |
| `first_observed_at` | Earliest provider-confirmed payment timestamp |
| `last_updated_at` | Last mutation timestamp |
| `finalized_at` | Set when a terminal status is reached |

Invariants are enforced by Pydantic validators:

- `targets_total == succeeded + failed + expired + pending`
- `amount_recovered_minor <= amount_targeted_minor`

---

## 3. Outcome status

*File:* `backend/app/schemas/outcome/enums.py`

### `OutcomeStatus` (aggregate)

```
PENDING
PARTIALLY_RECOVERED
RECOVERED
NO_RECOVERY
EXPIRED
FAILED
```

### `TargetOutcomeStatus` (per-target)

```
PENDING
PAID
FAILED
EXPIRED
```

The aggregate status is **derived deterministically** by `OutcomeEvaluator._derive_status`,
never chosen by an LLM:

| Condition | Aggregate status |
|-----------|------------------|
| `total == 0` | `FAILED` |
| `succeeded == total` | `RECOVERED` |
| `succeeded > 0` | `PARTIALLY_RECOVERED` |
| `pending > 0` (and `succeeded == 0`) | `PENDING` |
| everything terminal, none succeeded | `NO_RECOVERY` |

`OutcomeStatus.EXPIRED` and `OutcomeStatus.FAILED` remain valid enum values and transition
targets but are **not auto-derived** in the MVP; failure/expiry collapse to `NO_RECOVERY` for
the aggregate. This matches the Stage 5 test contract (observation-window expiry → `NO_RECOVERY`).

### Allowed transition tables

`TARGET_TRANSITIONS`:

```
PENDING  → { PAID, FAILED, EXPIRED }
PAID     → {}   # terminal
FAILED   → {}   # terminal
EXPIRED  → {}   # terminal
```

`OUTCOME_TRANSITIONS`:

```
PENDING             → { PARTIALLY_RECOVERED, RECOVERED, NO_RECOVERY, EXPIRED, FAILED }
PARTIALLY_RECOVERED → { RECOVERED, NO_RECOVERY, EXPIRED }
RECOVERED           → {}   # terminal
NO_RECOVERY         → {}   # terminal
EXPIRED             → {}   # terminal
FAILED              → {}   # terminal
```

Any transition outside these tables raises `ValueError` (`assert_target_transition` /
`assert_outcome_transition`). Terminal states have no exits, which is what makes out-of-order
provider events non-corrupting.

---

## 4. Target outcome tracking

*File:* `backend/app/schemas/outcome/target_outcome.py`

Stage 4 may create Payment Links for many eligible recovery targets. Stage 5 tracks each
target individually via `RecoveryTargetOutcome`:

| Field | Purpose |
|-------|---------|
| `target_outcome_id` | Stable identifier (`tgo_…`) |
| `outcome_id` | Parent `InterventionOutcome` |
| `target_id` | Stable per-target key (`{action_id}:{payment_id}`) |
| `payment_id` / `order_id` / `customer_id` | Upstream references |
| `payment_method` / `failure_reason` | Diagnostic context |
| `payment_link_id` | Razorpay Payment Link ID (`plink_…`) |
| `provider_reference` | Internal provider reference (`reference_id`) |
| `currency` | ISO-4217 |
| `expected_amount_minor` | Targeted amount (integer minor) |
| `recovered_amount_minor` | Provider-confirmed recovered amount (integer minor) |
| `status` | `TargetOutcomeStatus` |
| `created_at` / `paid_at` / `failed_at` / `expired_at` | Lifecycle timestamps |
| `last_event_id` / `last_event_at` / `transition_count` | Event-ordering bookkeeping |

A batch action is **not** declared successful merely because one Payment Link was paid. The
aggregate reflects every target.

---

## 5. Execution → outcome boundary

*File:* `backend/app/services/outcome/outcome_initializer.py`

The hand-off is deterministic — no LLM call.

```
ActionExecution (SUCCEEDED)
       ↓
OutcomeInitializer.initialize_outcome_for_execution(...)
       ↓
InterventionOutcome created (PENDING)
       ↓
RecoveryTargetOutcome records registered
       ↓
OutcomeEvaluator.recalculate (reflects full target set)
```

`ActionExecutor.execute` (Stage 4, extended in Stage 5) calls the injected
`OutcomeInitializer` after a successful `CREATE_PAYMENT_LINK` batch, passing a per-target
manifest `{payment_id, amount_minor, payment_link_id, provider_reference, …}`.

Idempotency: re-initialization for the same `action_id` returns the existing outcome and
re-aggregates rather than creating a duplicate (guarded by `get_outcome_by_action`).

---

## 6. Webhook processing

*File:* `backend/app/services/outcome/outcome_webhook_handler.py`

`OutcomeWebhookHandler.process_event` performs:

1. **deduplicate** by deterministic provider event id (SHA256 of `event:resource_id:created_at`)
2. **filter** to supported events only —
   `payment_link.paid`, `payment_link.cancelled`, `payment.captured`, `payment.failed`
3. **locate** the provider resource → `RecoveryTargetOutcome` (by `payment_link_id`, then `payment_id`)
4. **apply** a deterministic target transition
5. **re-aggregate** the parent outcome
6. **record** audit events

Event → target transition mapping:

| Provider event | Target transition |
|----------------|-------------------|
| `payment_link.paid` | `PAID` |
| `payment.captured` | `PAID` |
| `payment.failed` | `FAILED` |
| `payment_link.cancelled` | `EXPIRED` |

The handler does **not** call the Razorpay adapter, does **not** call an LLM, and does **not**
create another `ActionExecution`.

---

## 7. Webhook security reuse

Stage 5 **reuses** the verified Stage 2 boundary rather than reimplementing it:

- HMAC SHA256 signature verification — `verify_signature` uses
  `hmac.compare_digest(signature, expected)` over the exact raw body bytes against the
  webhook secret.
- `process_raw_payload` verifies the signature before normalizing to `NormalizedWebhookEvent`
  and raises `WebhookProcessingError("invalid signature")` on mismatch.
- Raw provider payloads never leak beyond the adapter/handler; only normalized fields are
  persisted.

The FastAPI `POST /webhooks/razorpay` route (Stage 2) remains the ingress; Stage 5 layers
outcome processing on top of the same verification/dedup discipline.

---

## 8. Webhook idempotency

Each event is assigned a deterministic id — `sha256(f"{event}:{resource_id}:{created_at}")`.
A `seen`-event set (plus the `last_event_id` guard at the target schema) guarantees:

```
same webhook → same event id → processed once
```

Duplicate events:
- do **not** double-count recovered revenue
- do **not** double-increment recovered targets
- record a single `OUTCOME_WEBHOOK_DUPLICATE` audit event (not a full trail)

Tested in `test_duplicate_event_counted_once` and `test_duplicate_does_not_recount_target`.

---

## 9. Financial amount accounting

All monetary arithmetic is integer minor units (paise). No floating point.

- `expected_amount_minor`, `recovered_amount_minor`, `amount_targeted_minor`,
  `amount_recovered_minor` are all `int`.
- Recovered amount extraction uses `int(...)` on minor units only.
- `amount_remaining_minor = amount_targeted_minor - amount_recovered_minor` (clamped at 0).
- `conversion_rate = succeeded / total`; `recovery_rate`, `revenue_recovery_rate` are computed
  with plain float division for ratio display only — never for totals (and guarded to `None`
  when the denominator is zero).

No monetary arithmetic is sent to M2.7 or M3.

---

## 10. Outcome aggregation

*File:* `backend/app/services/outcome/outcome_evaluator.py`

`OutcomeEvaluator.recalculate(outcome_id)`:

1. loads target outcomes for the outcome
2. computes `targets_total`, `succeeded`, `failed`, `expired`, `pending`
3. computes recovered/targeted amounts
4. computes conversion rate
5. derives aggregate status deterministically (§3)
6. updates the outcome (forward-only; a terminal outcome is never reopened)
7. records `OUTCOME_RECALCULATED` audit (actor `SYSTEM`)

Example (the Stage 5 golden batch):

```
10 Payment Links
7 paid, 2 pending, 1 expired
→ targets_total=10, succeeded=7, pending=2, expired=1
→ conversion_rate = 0.7
→ aggregate = PARTIALLY_RECOVERED
```

---

## 11. Treatment effectiveness metrics

*File:* `backend/app/schemas/outcome/metrics.py`

`TreatmentEffectiveness` carries:

```
targets_total
targets_recovered
targets_pending
targets_unrecovered          (failed + expired)

amount_targeted_minor
amount_recovered_minor
amount_remaining_minor

recovery_rate                 (targets_recovered / targets_total)
revenue_recovery_rate         (amount_recovered / amount_targeted)

time_to_first_recovery_seconds
time_to_last_recovery_seconds
```

Any metric that cannot yet be computed is `None` — never a fabricated value.
`time_to_first_recovery_seconds` is derived from the earliest `paid_at` of a PAID target;
`time_to_last_recovery_seconds` from the latest.

---

## 12. Outcome observation window / finalization

*File:* `backend/app/services/outcome/outcome_evaluator.py` (`finalize_expired`)

An intervention must not remain `PENDING` forever. Finalization rules:

```
all targets resolved        → already terminal (no-op)
OR
observation window elapsed  → pending targets transition to EXPIRED
                              → aggregate recalculated
```

The observation window is a configurable `observation_window_seconds` (default `7 * 24 * 3600`,
one week; tests override to 0). No background scheduler is required. Finalization is triggered:

- after webhook processing (implicitly via recalculate on each event), and
- when `POST /outcomes/{id}/evaluate` is called, and
- when the outcome status endpoint is queried.

---

## 13. Event ordering

Provider events may arrive out of order. `RecoveryTargetOutcome.transition` enforces:

- `PAID`, `FAILED`, `EXPIRED` are terminal and cannot be overwritten.
- A same-event-id replay is a silent no-op.
- An event older than the recorded `last_event_at` cannot roll a terminal state backward.

The webhook handler catches `ValueError` from an illegal transition and returns
`{"status": "ignored"}` — the state is not mutated.

---

## 14. Audit trail

*File:* `backend/app/schemas/outcome/audit.py`, `backend/app/services/outcome/outcome_store.py`

`AuditStore` records structured `AuditEvent`s. Each event preserves `timestamp`, `actor`,
`entity_type`, `entity_id`, `previous_state`, `new_state`, `reason`, `reference_id`.

Event kinds (`AuditEventType`):

```
OUTCOME_INITIALIZED
TARGET_REGISTERED
TARGET_PAYMENT_CONFIRMED
TARGET_MARKED_FAILED
TARGET_EXPIRED
OUTCOME_RECALCULATED
OUTCOME_FINALIZED
OUTCOME_WEBHOOK_DUPLICATE
OUTCOME_WEBHOOK_IGNORED
OUTCOME_WEBHOOK_UNRELATED
OUTCOME_PAYMENT_LINK_EXPIRED
```

Actor discriminator (`AuditActor`):

- `PROVIDER` — for provider-confirmed state transitions
- `SYSTEM` — for deterministic aggregation/initialization/finalization
- `HUMAN` — for human-driven decisions

---

## 15. Case summary lineage

*File:* `backend/app/services/outcome/case_summary.py`, `backend/app/schemas/outcome/metrics.py`

`FinancialCaseSummary` is **deterministically assembled** from structured records (never from
an LLM). It connects:

```
incident (symptom)
   ↓
investigation
   ↓
diagnosis
   ↓
action (prescription)
   ↓
approval
   ↓
execution (treatment)
   ↓
outcome
```

`CaseSummaryService` accepts resolvers for each upstream store and walks the ID lineage. The
output `lineage` list is the contract a future UI consumes, and `treatment_effectiveness` is
the deterministic metrics computed by `OutcomeEvaluator`.

---

## 16. API contracts

*File:* `backend/app/routers/outcome.py`, `backend/app/routers/case.py`

| Endpoint | Purpose |
|----------|---------|
| `GET /outcomes/{outcome_id}` | Outcome aggregate + effectiveness (read-only) |
| `GET /outcomes/{outcome_id}/targets` | Per-target outcomes |
| `POST /outcomes/{outcome_id}/evaluate` | Recalculate + finalize expiry (does **not** execute an action) |
| `GET /outcomes/{outcome_id}/audit` | Outcome audit trail |
| `GET /outcomes/{outcome_id}/audit/targets/{target_outcome_id}` | Target audit trail |
| `GET /outcomes/{outcome_id}/case` | Case summary for an outcome |
| `GET /cases/{action_id}` | Case summary for an action |
| `GET /outcomes/metrics` | Webhook/aggregation observability counts |

There is deliberately **no** `PUT /outcomes/...` or arbitrary mutation endpoint. The only way
state advances is via the verified webhook boundary or deterministic recalculation. The
evaluation endpoint recalculates and evaluates existing state only.

---

## 17. Stub provider simulation

*File:* `backend/app/services/outcome/stub_provider.py`

`StubProviderSimulator` wraps the Stage 2 `StubRazorpayAdapter` and lets tests exercise the
**same** production webhook/outcome path without live credentials:

```
Payment Link created (stub adapter)
       ↓
mark_payment_link_paid / mark_payment_link_expired
       ↓
build_payment_link_paid_payload → verified (HMAC-signed) payload + body
       ↓
OutcomeWebhookHandler.process_event
       ↓
Outcome updated
```

Tests do not directly `outcome.status = RECOVERED`; they dispatch a signed
`payment_link.paid` webhook through the handler and assert the resulting state.

---

## 18. Test strategy

*Files:* `tests/outcome/*`

| Module | Coverage |
|--------|----------|
| `test_outcome_schemas.py` | Enums, transition tables, schema invariants, amount/count validators, metric scaffolding |
| `test_outcome_evaluator.py` | Aggregation, status derivation, idempotent recalc, finalization, effectiveness metrics, audit |
| `test_outcome_webhook.py` | HMAC rejection, dedup, `payment_link.paid` handling, out-of-order safety, unrelated events, audit actor |
| `test_golden_closed_loop.py` | Golden Stages 1–5 pipeline + partial-recovery batch |

### Golden closed-loop test

`seed=42` → `PAYMENT_METHOD_FAILURE_SPIKE` → anomaly detected → M2.7 investigation → M3
diagnosis (`PAYMENT_METHOD_DEGRADATION`) → `CREATE_PAYMENT_LINK` → policy
(`HUMAN_APPROVAL_REQUIRED`) → human approval → execution → stub Payment Link → simulated
payment → `payment_link.paid` webhook → target `PAID` → `OutcomeEvaluator` → recovery metrics
→ case summary.

It verifies the full lineage: `incident_id`, `investigation_id`, `diagnosis_id`, `action_id`,
`approval_id`, `execution_id`, `provider_reference`, `outcome_id`, and asserts:

- `target outcome = PAID`
- `amount_recovered_minor > 0`
- recovery metrics are deterministic

### Partial recovery batch

10 targets → 7 `PAID`, 2 `PENDING`, 1 `EXPIRED` → `targets_total=10`, `recovered=7`,
`pending=2`, `unrecovered=1`, `recovery_rate=0.7`, aggregate `PARTIALLY_RECOVERED`.

### Duplicate webhook

`payment_link.paid` delivered twice → recovered amount counted once, target `PAID` once,
aggregate totals unchanged after the duplicate.

### Out-of-order event

`PAID` followed by an older/irrelevant `FAILED`/`PENDING` → terminal success is not corrupted.
The transition policy documents the terminal states as non-overwritable.

---

## 19. Safety invariants

| Invariant | Enforcement |
|-----------|-------------|
| Outcome evaluation cannot execute another action | `OutcomeWebhookHandler` / `/outcomes/{id}/evaluate` never construct `ActionExecutor` or call the adapter |
| No autonomous retry | No code path maps `NO_RECOVERY`/`PARTIALLY_RECOVERED` → a new action |
| No autonomous refund | No refund code path in Stage 5 |
| No recursive agent loop | The loop is bounded `ACT → OBSERVE → MEASURE → RECORD` |
| No LLM financial arithmetic | All amounts in integer minor units, computed in code |
| No LLM status decision | Status transitions live in the transition tables + `OutcomeEvaluator` |

---

## 20. Performance observability

`OutcomeWebhookHandler.metrics` exposes:

```
events_processed
events_duplicated
events_unrelated
events_ignored
targets_evaluated
aggregation_latency_ms_avg
```

These are collected with `time.perf_counter()` per webhook processing call. No premature
optimization; the goal is observability.

---

## Final verification

| Check | Result |
|-------|--------|
| Outcome initialization on execution | ✅ |
| Per-target tracking + provider references | ✅ |
| Deterministic aggregation | ✅ |
| HMAC reuse + dedup + out-of-order safety | ✅ |
| Integer-minor financial arithmetic | ✅ |
| Golden closed-loop (Stages 1–5) | ✅ |
| Partial recovery batch | ✅ |
| Duplicate / out-of-order webhook | ✅ |
| No autonomous follow-up action | ✅ |
| `pytest` | **157 passed** |
| `ruff check .` | **PASS** |
| `mypy backend` | **PASS** |