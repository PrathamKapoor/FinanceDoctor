# STAGE 3 — FINANCIAL DOCTOR

## Agentic Investigation Engine — M2.7 Workers + M3 Diagnosis

> **Status:** Complete — all 94 tests pass, `ruff` clean, `mypy` clean.

---

## 1. ModelClient Abstraction

Created a provider-independent `ModelClient` protocol with two implementations:

| Implementation | Purpose |
|----------------|---------|
| `StubModelClient` | Deterministic, no network calls, used for testing and demo |
| `MiniMaxModelClient` | Live MiniMax API client (requires credentials) |

**Interface** (`backend/app/agents/models.py`):
```python
class ModelClient(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_schema: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        ...

    async def close(self) -> None: ...
```

**Configuration** (`ModelConfig`):
- `MINIMAX_M27_MODEL` — M2.7 model identifier
- `MINIMAX_M3_MODEL` — M3 model identifier  
- `MINIMAX_API_KEY` — API key (empty = stub mode)
- `MINIMAX_BASE_URL` — API base URL
- `MINIMAX_GROUP_ID` — Group ID

Default mode is **stub** (no network calls). Live mode requires explicit credentials.

---

## 2. M2.7 Investigation Workers

Four specialized workers, each analyzing one evidence dimension:

| Worker | Dimension | Key Output Fields |
|--------|-----------|-------------------|
| `TemporalWorker` | Time-of-day / day-of-week | `anomaly_detected`, `peak_window` |
| `PaymentMethodWorker` | Method-level failure rates | `affected_methods`, `max_delta` |
| `CohortWorker` | NEW vs RETURNING customers | `affected_cohorts`, `returning_bias` |
| `FailureReasonWorker` | Failure reason distribution | `dominant_reason`, `dominance_ratio` |

**Critical rule**: Workers **never calculate financial metrics**. They receive pre-computed deterministic evidence slices and return structured interpretations.

**Structured Output Schema** (`WorkerOutputBase`):
```python
worker: str                    # "temporal", "payment_method", etc.
finding: str                   # Natural language finding citing evidence IDs
evidence_ids: list[str]        # Must reference actual evidence store IDs
supports: list[SupportedHypothesis]   # Hypotheses supported
contradicts: list[SupportedHypothesis] # Hypotheses contradicted
confidence: float              # 0.0-1.0 (model-assessed, not calibrated)
```

**Supported Hypotheses** (enum):
- `PAYMENT_METHOD_DEGRADATION`
- `TEMPORAL_SPIKE`
- `CUSTOMER_BEHAVIOR_CHANGE`
- `FRAUD_SPIKE`
- `INFRASTRUCTURE_ISSUE`
- `CHECKOUT_PROBLEM`
- `GENERAL_PAYMENT_FAILURE`

**Prompts** (`backend/app/agents/prompts/`):
- `m27_temporal.txt`
- `m27_payment_method.txt`
- `m27_cohort.txt`
- `m27_failure_reason.txt`

Each prompt explicitly instructs: **NEVER invent numbers**, **cite evidence IDs**, **distinguish correlation from causation**, **state uncertainty**.

---

## 3. Evidence Bundle Assembly

The `EvidenceBundle` (from Stage 1) is enriched with M2.7 worker findings:

```python
EvidenceBundle(
    incident: IncidentSummary,
    overall: WindowComparison,
    temporal: list[TimeBucketStat],
    baseline_daily: list[TimeBucketStat],
    payment_methods: list[MethodStat],
    cohorts: list[CohortStat],
    failure_reasons: list[ReasonStat],
    monetary: MonetaryStat,
    anomaly: AnomalyResult,
)
```

Worker outputs are attached to the bundle for M3 consumption.

---

## 4. M3 Senior Financial Doctor

Single high-quality reasoning call that:
1. Receives complete EvidenceBundle + all M2.7 worker outputs
2. Evaluates **7 competing hypotheses** against ALL evidence
3. Selects leading hypothesis with model-assessed confidence
4. Identifies supporting/contradicting evidence IDs
5. Ranks alternative hypotheses with scores
6. Proposes **exactly one bounded intervention** (`CREATE_PAYMENT_LINK` or `ISSUE_REFUND`)
7. States uncertainties explicitly

**DiagnosisOutput Schema**:
```python
diagnosis_id: str
incident_type: str
leading_hypothesis: str
confidence: float          # model-assessed, NOT calibrated probability
summary: str               # Natural language, cites evidence IDs
supporting_evidence_ids: list[str]
contradicting_evidence_ids: list[str]
alternative_hypotheses: list[dict]  # hypothesis, score, reason
recommended_action_type: str       # "CREATE_PAYMENT_LINK" | "ISSUE_REFUND"
action_rationale: str
uncertainties: list[str]
```

**Prompt** (`m3_diagnosis.txt`) enforces:
- NEVER invent numbers
- Cite evidence IDs for EVERY claim
- Distinguish correlation from causation
- Consider ALL hypotheses, score alternatives
- State uncertainties explicitly
- Action MUST be from allowlist

---

## 5. Investigation Orchestrator & State Machine

`InvestigationOrchestrator` drives the pipeline:

```
CREATED
    ↓
EVIDENCE_PREPARING    (validate anomaly, configure windows)
    ↓
WORKERS_RUNNING       (run 4 M2.7 workers concurrently)
    ↓
EVIDENCE_ASSEMBLED    (build EvidenceBundle, persist to store)
    ↓
DIAGNOSIS_RUNNING     (M3 diagnosis)
    ↓
DIAGNOSIS_COMPLETE    (store diagnosis_ref)
    ↓
FAILED (terminal)     (on any error)
```

State transitions are validated; invalid transitions raise `ValueError`.

---

## 6. Traceability & Auditability

Every model invocation produces a `ModelCallTrace`:

```python
trace_id: str
investigation_id: str | None
worker: str | None      # "temporal", "payment_method", "cohort", "failure_reason", "m3"
model: str              # "MiniMax-M2.7", "MiniMax-M3", "stub"
prompt_version: str
started_at: datetime
completed_at: datetime | None
status: str             # "started", "completed", "failed"
input_evidence_ids: list[str]
output_summary: str | None
error: str | None
latency_ms: int | None
```

Traces stored in `TraceStore` (in-memory, replaceable with persistent store).

---

## 6. API Endpoints (Development)

| Endpoint | Purpose |
|----------|---------|
| `POST /investigations` | Create + run investigation (accepts seed, num_orders, etc.) |
| `GET /investigations/{id}` | Get investigation status |
| `GET /investigations/{id}/diagnosis` | Get diagnosis |
| `GET /investigations/{id}/traces` | Get model call traces |
| `GET /investigations/traces` | Get all traces |

---

## 7. Testing

**94 tests pass** (including 20 new Stage 3 tests):

| Test Module | Tests | Coverage |
|-------------|-------|----------|
| `test_investigation.py` | 20 | Worker schemas, M2.7 workers, M3 diagnosis, orchestrator, state machine, golden test |
| `test_adapter.py` | 26 | Stub adapter read/write, idempotency, webhook, normalization |
| `test_money.py` | 5 | Integer minor-unit arithmetic |
| `test_synthetic_data.py` | 6 | Determinism, record counts, baseline health |
| `test_incident.py` | 6 | Reproducibility, ground truth, targeted spike |
| `test_analytics.py` | 8 | Explicit expected values on controlled fixture |
| `test_anomaly.py` | 4 | Healthy not anomalous, incident triggers, deterministic score |
| `test_evidence.py` | 5 | Bundle metrics, flatten, serialization, store round-trip |
| `test_invariants.py` | 7 | Financial invariants |
| `test_api.py` | 6 | Health, seed, inject, metrics, evidence endpoints |

---

## 7. Golden Investigation Test

The known `PAYMENT_METHOD_FAILURE_SPIKE` (seed=42) **must** produce:

```
anomaly detected: YES
leading hypothesis: PAYMENT_METHOD_DEGRADATION
affected method: UPI
UPI failure rate: 0.3824 (baseline 0.0336)
UPI delta: +0.3488
NETWORK_ERROR dominance: 82.8%
RETURNING cohort delta: +0.1884 > NEW delta: +0.1384
anomaly z-score: 10.85
recommended action: CREATE_PAYMENT_LINK
```

**Verified**: All assertions pass in `TestGoldenInvestigation`.

---

## 8. Safety & Architectural Invariants

| Invariant | Enforcement |
|-----------|-------------|
| No LLM financial arithmetic | Workers receive pre-computed evidence only |
| No LLM Razorpay calls | M3 cannot call adapter; only proposes action |
| No unsupported actions | Diagnosis schema restricts `action_type` to allowlist |
| No invented evidence | Workers must cite `evidence_ids` that exist in bundle |
| No autonomous writes | Pipeline stops at `DIAGNOSIS_COMPLETE`; Stage 4 adds policy + approval |

---

## 8. Final Verification Report

| Check | Result |
|-------|--------|
| **ModelClient abstraction** | ✅ Protocol + Stub + MiniMax implementations |
| **M2.7 workers (4)** | ✅ Temporal, PaymentMethod, Cohort, FailureReason |
| **M3 diagnosis** | ✅ Structured output, hypothesis ranking, action proposal |
| **InvestigationOrchestrator** | ✅ State machine, concurrent workers, evidence assembly |
| **EvidenceBundle assembly** | ✅ Enriched with worker outputs |
| **State machine** | ✅ Validated transitions, observable logging |
| **Traceability** | ✅ ModelCallTrace for every model call |
| **API endpoints** | ✅ Investigation CRUD + traces |
| **Prompts** | ✅ 5 versioned prompt files |
| **Model config** | ✅ Environment-based, stub default |
| **Golden incident test** | ✅ PAYMENT_METHOD_DEGRADATION, UPI, NETWORK_ERROR, CREATE_PAYMENT_LINK |
| **Financial arithmetic in LLM** | **NO** — all metrics deterministic |
| **Razorpay writes executed** | **NO** — pipeline stops at diagnosis |
| **Tests** | **94 passed** |
| **Ruff** | **PASS** |
| **Mypy** | **PASS** |

---

## 9. Documentation

Created:
- `docs/STAGE_3_INVESTIGATION.md` (this file)
- Updated `docs/STAGE_0_ARCHITECTURE.md` if needed

---

## 10. Remaining Blockers for Stage 4

| Blocker | Status |
|---------|--------|
| Policy Engine implementation | Not yet started |
| Human approval workflow | Not yet started |
| Action planner/executor | Not yet started |
| Outcome evaluator | Not yet started |
| React frontend | Not yet started |

---

**Stage 3 is complete.** The deterministic financial substrate (Stage 1) and verified Razorpay boundary (Stage 2) now connect to a fully-tested agentic investigation engine that produces structured, evidence-backed diagnoses for the Payment Failure Incident. The pipeline is ready for Stage 4 (Policy Engine + Human Approval + Action Execution).