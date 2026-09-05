# 🩺 FinanceDoctor

> An agentic financial incident investigation and recovery platform that detects payment anomalies, investigates root causes using AI, enforces deterministic financial safety policies, and guides human-approved recovery workflows.

Merchants can see financial anomalies but struggle to understand **what changed**,
**why it changed**, **what should be done**, and **whether the intervention worked**.
FinanceDoctor closes that loop for payment failures — with real AI reasoning,
deterministic safety guarantees, and a fully working demo UI.

## Verified results (seeded demo incident)

A synthetic payment-failure spike injected into a deterministic 30-day merchant baseline:

```text
Baseline failure rate:  4.54%
Incident failure rate:  21.75%
Relative increase:      3.79×
Anomaly score:          z = 10.854  (detection threshold z = 3.0)
```

The detector flags a statistically significant payment failure incident. Per-method
evidence isolates the cause:

| Payment Method | Current Failure Rate | Baseline |
| -------------- | -------------------: | -------: |
| UPI            |               38.24% |    3.36% |
| Card           |                6.45% |    6.14% |
| Netbanking     |                2.04% |    4.82% |
| Wallet         |                0.00% |    5.19% |

The closed loop completes end to end:

```text
Outcome: PARTIALLY_RECOVERED

₹48,102 recovered

70 / 100 recovery targets converted
```

This result belongs to the deterministic demo/simulation environment — **no real
money moved**. It proves the full controlled lifecycle works: the same policy,
approval, provider-boundary, webhook, and measurement code paths run in production.

## The closed-loop system

```text
Detect
  ↓
Investigate
  ↓
Diagnose
  ↓
Validate Policy
  ↓
Human Approval
  ↓
Execute Recovery
  ↓
Observe Outcome
  ↓
Measure Financial Result
```

FinanceDoctor is **not merely a chatbot over financial data**. It separates:

* deterministic financial computation (all amounts, rates, anomaly scores in code),
* AI investigation (MiniMax M2.7 workers over pre-computed evidence),
* AI diagnosis (MiniMax M3 with differential hypotheses),
* deterministic safety policy (12 checks, zero LLM involvement),
* human approval (explicit gate, immutable action snapshot),
* provider execution (single verified write: Payment Link re-collection),
* outcome measurement (webhook-driven, deterministic aggregation).

## Real AI integration (honestly stated)

* **MiniMax M2.7 via GMI Cloud — LIVE.** Agentic investigation pipeline
  (temporal / payment-method / cohort / failure-reason workers). Real API
  requests verified over the actual pipeline.
* **MiniMax M3 via GMI Cloud — LIVE.** Diagnosis, differential analysis, and
  grounded read-only consultation. Real structured responses verified,
  including a live `PAYMENT_METHOD_DEGRADATION` + `CREATE_PAYMENT_LINK`
  diagnosis matching the deterministic golden diagnosis.
* LLM output is stochastic by nature: structured-output validation, bounded
  repair retries, and deterministic-template fallback exist so the system
  degrades gracefully instead of hallucinating. Deterministic model behavior
  is never claimed.

## Razorpay: transparent demo mode

```text
Razorpay Mode: Demo / Stub
```

The architecture preserves both adapters — `RazorpayAdapter ├── Demo/Stub
Adapter └── Live Adapter` — but credentials were not available for this
environment, so the demo runs the stub. Never claimed: real payment
recovered, real Razorpay payment link created, live transaction executed.
What runs is a **Razorpay-compatible recovery workflow simulated through the
deterministic provider adapter**: same boundary, same webhook handling, same
policy and approval gates. Razorpay exposes no "retry payment" API, so the
product never claims autonomous retries.

## 🛡️ Financial Safety by Design

### AI CAN:

* investigate evidence,
* generate hypotheses,
* diagnose incidents,
* explain financial events,
* recommend allowed actions.

### AI CANNOT:

* approve financial actions,
* execute provider calls directly,
* bypass the policy engine,
* modify financial policy,
* alter deterministic financial accounting.

Every financial action must pass:

```text
AI Recommendation
        ↓
Deterministic Policy Engine
        ↓
12 Safety Checks
        ↓
Human Approval
        ↓
Action Execution
```

Direct M3 → Razorpay access is prohibited by architecture (no imports, no
handles, no tools) — not merely by prompt wording. The consultation voice
interface is read-only and cannot approve, execute, or mutate anything.

## Provider matrix

| Component         | Mode                            |
| ----------------- | ------------------------------- |
| Financial Data    | Synthetic                       |
| Anomaly Detection | Deterministic                   |
| Investigation     | Live MiniMax M2.7 via GMI Cloud |
| Diagnosis         | Live MiniMax M3 via GMI Cloud   |
| Policy Engine     | Deterministic                   |
| Approval          | Human                           |
| Payment Recovery  | Demo Simulation                 |
| Outcome Tracking  | Deterministic                   |
| Consultation      | Live MiniMax M3                 |
| Speech            | Demo/Stub                       |

## Architecture

```text
Synthetic Financial Environment
          ↓
Deterministic Anomaly Detection
          ↓
Evidence Bundle
          ↓
MiniMax M2.7 Investigation
          ↓
MiniMax M3 Diagnosis
          ↓
Deterministic Policy Engine
          ↓
Human Approval
          ↓
Demo Provider Execution
          ↓
Outcome Tracking
          ↓
Deterministic Financial Accounting
```

Core principle: LLMs are **not** the source of truth for financial arithmetic.
Financial quantities (counts, rates, deltas, averages, anomaly scores, totals)
are computed deterministically by code. AI reasons over and explains those
pre-computed results — and every rupee it quotes is validated against them.

## Running the project

Prerequisites: Python 3.13 + [`uv`](https://docs.astral.sh/uv/), Node.js 18+
for the frontend. No Docker required. No credentials required for the demo.

```bash
# 1. Backend dependencies
uv sync --dev

# 2. (Optional) inspect the deterministic financial substrate
uv run python -m backend.cli inspect --seed --inject

# 3. Backend API
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# → GET http://127.0.0.1:8000/health  (reports stub/live provider modes)
```

```bash
# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev     # Vite on http://127.0.0.1:5173, proxies API to :8000
```

Open http://127.0.0.1:5173 — the case auto-starts. Suggested journey: review
the incident → approve the treatment → execute → simulate the provider
webhook → ask Financial Doctor *"Doctor, did the treatment work?"* → listen.

Production single-process run (serves API + built frontend, no Docker):

```bash
cp .env.example .env   # stub defaults demo safely; edit only to go live
cd frontend && npm install && npm run build && cd ..
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Hybrid/live AI configuration (GMI Cloud key via environment only, never in code):

```bash
export MINIMAX_API_KEY=...                          # required for live AI
export MINIMAX_BASE_URL=https://api.gmi-serving.com/v1
export MINIMAX_M27_MODEL=MiniMaxAI/MiniMax-M2.7
export MINIMAX_M3_MODEL=MiniMaxAI/MiniMax-M3
export MINIMAX_MAX_TOKENS=8192                      # headroom for reasoning traces
# RAZORPAY_MODE stays stub; SPEECH stays stub (no TTS route on GMI)
```

Demo-safe fallback: unset the keys and restart — everything deterministic,
zero credentials, zero network.

## 🖥️ Demo

Screenshots and demo video coming soon.

## Testing & quality

```text
Backend tests: 217 passed
Frontend tests: 33 passed

Ruff: PASS
Mypy: PASS

ESLint: PASS
TypeScript: PASS

Production Build: PASS
```

```bash
uv run pytest
uv run ruff check .
uv run mypy backend
cd frontend && npm test && npm run lint && npm run typecheck && npm run build
```

## Documentation

* [Architecture](docs/STAGE_0_ARCHITECTURE.md) — system design and stage plan
* [Razorpay boundary](docs/STAGE_2_RAZORPAY.md) · [capability matrix](docs/STAGE_2_RAZORPAY_CAPABILITIES.md) — verified provider surface
* [Outcome tracking](docs/STAGE_5_OUTCOMES.md) — closed-loop measurement
* [Case interface](docs/STAGE_6_CASE_INTERFACE.md) — frontend journey
* [Speech consultation](docs/STAGE_7A_SPEECH_CONSULTATION.md) — read-only voice layer
* [Live integration](docs/STAGE_8B_LIVE_INTEGRATION.md) — credential-gated verification
* [Hybrid demo](docs/STAGE_8C_HYBRID_DEMO.md) — GMI Cloud live AI + demo provider modes

## Project layout

```text
backend/
  cli.py                 # developer data-inspection command
  money.py               # integer minor-unit money arithmetic
  app/
    main.py              # FastAPI app (health, CORS, static frontend serving)
    config.py            # pydantic-settings + startup validation (fail fast, no silent fallback)
    db/                  # SQLAlchemy engine + ORM models
    schemas/             # enums + typed evidence/analytics/action/outcome schemas
    services/            # synthetic data, analytics, evidence, incidents, state
      demo/              # demo-case session + read-only read-model
      case/              # CaseController facade
      consultation/      # read-only Q&A + Speech 2.8 TTS abstraction
    routers/             # health + demo-case endpoints
    agents/              # M2.7 workers, M3 diagnosis, investigation orchestrator
    adapters/razorpay/   # stub + live adapters, factory, webhook boundary
frontend/                # case journey + Ask Financial Doctor panel (React + Vite + TS)
tests/
  demo/                  # demo-case journey tests
  consultation/          # consultation + speech tests
  live/                  # live provider wire-contract tests (mocked transport, no network)
```
