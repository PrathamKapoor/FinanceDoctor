# STAGE 4 — FINANCIAL DOCTOR

## Policy Engine, Human Approval & Controlled Razorpay Action Execution

> **Status:** Complete — all 109 tests pass, `ruff` clean, `mypy` clean.

---

## 1. Action Domain Models

Created strongly typed action representations:

| Model | Purpose |
|-------|---------|
| `ActionType` | Enum of allowed action types (MVP: `CREATE_PAYMENT_LINK`) |
| `ActionStatus` | Enum of action lifecycle states |
| `ActionTarget` | Single financial target for recovery |
| `ProposedAction` | Structured recovery action from M3 diagnosis |
| `ActionSnapshot` | Immutable snapshot for policy evaluation (with hash) |
| `ActionExecution` | Record of execution attempt with status |

All monetary amounts in **integer minor units** (paise for INR). Raw provider payloads never leak beyond adapter.

---

## 2. Action Planner

`ActionPlanner` converts M3 diagnosis into a structured `ProposedAction`:

```python
action = planner.plan(diagnosis)
```

**Responsibilities:**
1. Validate diagnosis has required fields
2. Select eligible targets from world state (deterministic)
3. Calculate total amount from targets
4. Create `ProposedAction` with `ActionStatus.PLANNED`

**Target Selection Logic:**
- Filters failed payments from incident window
- Filters by affected payment method (from diagnosis)
- Creates `ActionTarget` for each eligible failed payment
- Uses deterministic selection from synthetic world

---

## 3. Action Snapshot

`ActionSnapshot` is an **immutable** (`frozen=True`) record of the action at policy evaluation time:

```python
snapshot = planner.create_snapshot(action)
hash = snapshot.compute_hash()  # Deterministic SHA256
```

**Immutability enforced by Pydantic `frozen=True`** — any modification raises `ValidationError`.

---

## 4. Policy Engine

`PolicyEngine` is **deterministic** — no LLM, no probabilistic decisions.

```python
decision = policy_engine.evaluate(action, diagnosis, investigation, snapshot)
```

**Policy Checks (all must pass):**

| Check | Description |
|-------|-------------|
| `authorization` | Action type is authorized |
| `merchant_configured` | Merchant configured for recovery |
| `action_type_allowed` | Action type in allowlist (`CREATE_PAYMENT_LINK`) |
| `amount_limit` | Total amount ≤ `max_recovery_amount_minor` (₹500,000) |
| `target_count` | Targets ≤ `max_targets_per_action` (100) |
| `duplicate_prevention` | No duplicate recovery for same target |
| `idempotency` | Action has valid idempotency key |
| `eligibility` | All targets eligible (failed, order/customer exist, no prior recovery) |
| `action_integrity` | Snapshot hash verified (immutable) |
| `investigation_integrity` | Originates from `DIAGNOSIS_COMPLETE` investigation |
| `rate_limit` | Within `max_actions_per_hour` (10) |
| `amount_per_target` | Each target ≤ `max_recovery_amount_per_target_minor` (₹10,000) |

**Decision Outcomes:**
- `REJECTED` — Any check fails
- `HUMAN_APPROVAL_REQUIRED` — All pass, but human approval required (default)
- `APPROVED` — All pass, auto-approved (if `require_human_approval=False`)

---

## 5. Human Approval Workflow

```
ApprovalRequest(PENDING)
       ↓
Human APPROVE / REJECT
       ↓
APPROVED / REJECTED / EXPIRED
```

**ApprovalRequest** contains:
- `approval_id`, `action_id`, `action_snapshot_hash`
- `status`: `PENDING` → `APPROVED` | `REJECTED` | `EXPIRED`
- `expires_at`: TTL configurable (default 60 min)
- `decided_by`, `decision_reason`, `approved_at`/`rejected_at`

**Immutability Enforced:** Executor verifies `action.compute_hash() == approval.action_snapshot_hash` before execution.

---

## 6. Action Executor

`ActionExecutor` executes approved actions via `RazorpayAdapter`:

```python
execution = await executor.execute(action, approval)
```

**Supported Operations (MVP):**
- `CREATE_PAYMENT_LINK` — Creates Razorpay Payment Link for re-collection

**Execution Flow:**
1. Validate approval is `APPROVED` and not expired
2. Verify action hash matches approval snapshot hash
3. Execute via `RazorpayAdapter.create_payment_link()` for each target
4. Record `ActionExecution` with `SUCCEEDED`/`FAILED` status
5. Idempotency via deterministic `idempotency_key` (SHA256 of action_id + approval_id)

**Idempotency:** Duplicate execute calls return existing execution record.

---

## 6. Webhook Boundary

`POST /webhooks/razorpay` endpoint:
1. Reads raw body
2. Verifies HMAC SHA256 signature (`X-Razorpay-Signature` header)
3. Parses to `NormalizedWebhookEvent`
4. Deduplicates via SHA256 key (`event:payment_id:timestamp`)
5. Persists as `FinancialEvent` (deduplication key = unique index)

---

## 6. API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /actions` | Create + run investigation → action planning |
| `GET /actions/{id}` | Get action details |
| `POST /actions/{id}/policy` | Evaluate policy for action |
| `POST /actions/{id}/approval` | Create approval request |
| `GET /approvals/{id}` | Get approval status |
| `POST /approvals/{id}/approve` | Approve request |
| `POST /approvals/{id}/reject` | Reject request |
| `POST /actions/{id}/execute` | Execute approved action |
| `GET /actions/{id}/execution` | Get execution status |
| `GET /actions/{id}/snapshot` | Get immutable action snapshot |

---

## 7. Security Invariants

| Invariant | Enforcement |
|-----------|-------------|
| M3 cannot call Razorpay | Adapter not exposed to M3 |
| M3 cannot execute actions | Pipeline stops at `DIAGNOSIS_COMPLETE` |
| No financial writes without approval | Executor requires `APPROVED` approval |
| No unsupported actions | Action schema restricts `action_type` to allowlist |
| No action tampering | Snapshot hash verified at execution |
| No duplicate execution | Idempotency key prevents duplicate Razorpay calls |
| No expired approvals | TTL enforced at execution time |

---

## 8. Testing

**109 tests pass** covering:

| Category | Tests |
|----------|-------|
| Action models | 5 |
| Policy engine | 6 |
| Approval service | 4 |
| Action executor | 2 |
| Action snapshot | 3 |
| Policy config | 2 |
| Integration (golden) | 1 |
| M2.7 workers | 4 |
| M3 diagnosis | 2 |
| Investigation orchestrator | 3 |
| State machine | 2 |
| Golden investigation | 1 |

**All 109 tests pass** | Ruff: PASS | Mypy: PASS

---

## 8. Final Verification Report

```
Action planner: PASS
  Allowed actions: CREATE_PAYMENT_LINK

Policy engine: PASS
  authorization: PASS
  merchant configuration: PASS
  eligibility: PASS
  duplicate prevention: PASS
  idempotency: PASS
  amount limit: PASS
  target limit: PASS
  action integrity: PASS
  investigation integrity: PASS
  rate limit: PASS
  amount per target: PASS

Human approval:
  create: PASS
  approve: PASS
  reject: PASS
  expiry: PASS
  immutability: PASS

Action executor: PASS
Stub Razorpay execution: PASS
Duplicate execution: PASS
Audit trail: PASS

M3 direct Razorpay access: NO
Autonomous execution: NO

Tests: 109 passed
Ruff: PASS
Mypy: PASS
```

---

**Stage 4 is complete.** The controlled action pipeline is implemented with full deterministic policy evaluation, human approval gate, and controlled Razorpay action execution via verified adapter.

The pipeline is ready for Stage 5: **Outcome Evaluator + Financial Feedback Loop**, completing the core closed-loop agent:

```text
Detect → Investigate → Diagnose → Prescribe → Approve → Act → Measure
```