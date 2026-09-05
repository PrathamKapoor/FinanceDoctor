# STAGE 8C — FINANCIAL DOCTOR

## Demo Provider Finalization + Live MiniMax Integration

> **Status:** Hybrid demo verified live where APIs exist — M2.7/M3 via GMI
> Cloud on user-supplied credentials; Razorpay explicitly on demo stub;
> Speech stays on stub placeholder (GMI exposes no TTS route — verified 404).
> Backend 213+ passed, frontend 33 passed (final counts in report).

Target hybrid demo:

```text
Synthetic Financial Incident + Deterministic Razorpay Demo Provider
+ REAL MiniMax AI + REAL MiniMax Speech = HACKATHON-READY HYBRID DEMO
```

---

## 1. Why Razorpay uses Demo Mode

No Razorpay credentials are available, and the stage explicitly forbids
blocking on them or fabricating them. The deterministic stub therefore
remains the financial provider. This does not weaken the demo: the stub
implements the same `RazorpayAdapter` boundary, the same policy → approval →
executor pipeline runs, and the same signed-webhook outcome path measures
results. What changes is labeling, not architecture.

## 2. Why this does not invalidate the architecture

`RazorpayAdapter ├── Stub/Demo Adapter └── Live Adapter` is preserved; the
live adapter is intact for future use (`RAZORPAY_MODE=live` + test keys, with
startup refusal when keys are missing — Stage 8A rule untouched). The demo
exercises every safety boundary around the stub exactly as it would around
the live adapter.

## 3. Exact provider modes

```text
Razorpay:            STUB / DEMO (explicit; live refused without keys)
MiniMax M2.7:        LIVE via GMI Cloud (MiniMaxAI/MiniMax-M2.7)
MiniMax M3:          LIVE via GMI Cloud (MiniMaxAI/MiniMax-M3)
MiniMax Speech 2.8:  STUB placeholder (GMI exposes no TTS route — verified 404)
```

No `CONSULTATION_PROVIDER` / `GMI_API_KEY` variables were invented. GMI Cloud
uses OpenAI-compatible chat (`POST {base}/chat/completions`, Bearer auth),
so the existing client works unchanged against `MINIMAX_BASE_URL=
https://api.gmi-serving.com/v1` with GMI model ids
(`MiniMaxAI/MiniMax-M2.7`, `MiniMaxAI/MiniMax-M3`). Two minimal client
hardening changes were required by live behavior (see §7) — no architecture
changes.

## 4. How to configure MiniMax credentials (local, env only, never in code)

```bash
export MINIMAX_API_KEY=...            # required for any live MiniMax call
export MINIMAX_BASE_URL=https://api.gmi-serving.com/v1   # GMI Cloud endpoint
export MINIMAX_M27_MODEL=MiniMaxAI/MiniMax-M2.7
export MINIMAX_M3_MODEL=MiniMaxAI/MiniMax-M3
export MINIMAX_MAX_TOKENS=8192        # headroom for M2.7 reasoning traces
# RAZORPAY_MODE stays stub for the hackathon demo
# SPEECH_PROVIDER stays stub: GMI exposes no TTS route (verified HTTP 404,
# and no audio/speech models on GET /v1/models for this key)
```

## 5. How to switch between stub and hybrid modes

- **Demo-safe (default):** no keys set → everything deterministic. Fallback
  if APIs fail mid-presentation: unset the keys and restart.
- **Hybrid live:** set the MiniMax vars above and restart. `GET /health`
  reports `consultation: live`, `speech_provider: minimax`; the UI header
  switches from "Demo environment" to "Integration mode" with per-provider
  Live badges. Modes never switch silently — selection happens once at
  client/provider construction.

## 6. What is real vs simulated

| Component         | Mode            |
| ----------------- | --------------- |
| Financial Data    | Synthetic       |
| Anomaly Detection | Deterministic   |
| Investigation     | Live MiniMax M2.7 (verified valid worker output) |
| Diagnosis         | Live MiniMax M3 (verified, see caveat §7) |
| Policy Engine     | Deterministic   |
| Approval          | Human           |
| Payment Recovery  | Demo Simulation |
| Outcome Tracking  | Deterministic   |
| Consultation      | Live MiniMax M3 (verified grounded answer) |
| Speech            | Stub placeholder (no TTS route on GMI — verified 404) |

UI wording: "Demo simulation" badges on Treatment/Outcome, "(simulated)"
on the summary recovery figure, "Payment Link workflow simulated — no real
transaction". Never claimed: Razorpay confirmation, real money recovered,
real transaction executed. AI components may show Live badges only when
`/health` confirms live providers.

## 7. Live MiniMax verification — what was proven, what was learned

Verified live evidence (key via env only, nothing secret logged):
- `GET /v1/models` → key accepted; `MiniMaxAI/MiniMax-M2.7/-M3` listed; no
  audio/speech models exist for this key.
- Live M2.7 temporal worker → valid `TemporalWorkerOutput` citing real
  evidence (baseline mean 0.0451, July-31 spike, supports TEMPORAL_SPIKE).
- Live M3 diagnosis → `PAYMENT_METHOD_DEGRADATION` + `CREATE_PAYMENT_LINK`,
  matching the deterministic golden diagnosis on the seeded case.
- Live M3 consultation ("Doctor, did the treatment work?") → grounded answer
  (PARTIALLY_RECOVERED, 70/100, ₹48,102 of ₹66,974, 70.0%), attributed
  `model="MiniMaxAI/MiniMax-M3"`, case state byte-identical afterwards.
- TTS: `POST /v1/t2a_v2` → HTTP 404. GMI Cloud serves chat, not MiniMax TTS.
  Speech stays on the stub placeholder — by evidence, not by default.

Two minimal client hardening changes were required by observed live behavior
(no architecture changes; all defaults unchanged):
1. `model` routing: workers now pin the M2.7 id, M3 keeps its own
   (previously every live call silently used the M3 id).
2. Robustness: Markdown-fence stripping, up to 2 bounded schema-repair
   retries, 429/5xx retry with backoff honoring Retry-After, and
   `MINIMAX_MAX_TOKENS` ceiling (M2.7 reasoning traces overflow small budgets).

Caveats (honest): the GMI-served models conform to strict schemas
stochastically — one M3 run needed repair, another needed two; a full 9-call
single-burst `run_demo_case` tripped the key's tight quota (HTTP 429,
retried, then surfaced without crashing). Every stage is verified live
individually through the real code paths; the full burst remains
quota-limited, not code-limited. For the hackathon, stub reasoning stays the
reliable default and live mode is one env change away.

## 8. Original verification procedure (reference)

1. Export keys per §4; boot (startup refuses misconfiguration loudly).
2. `GET /health` → `consultation: live`, header shows Integration mode.
3. Start case → investigation/diagnosis served by live M2.7/M3 through the
   real pipeline (answers labeled with the configured model name, never
   "stub" — Stage 8C attribution fix).
4. Ask Financial Doctor → grounded answer (₹-grounding enforced, fallback to
   template on any violation) → Listen → stub placeholder audio plays
   (live TTS unavailable on GMI; text answer is always retained).
5. Approve → execute (stub payment link) → simulate → measured outcome.

## 8. Failure fallback

M2.7/M3 failure → case intact, grounded stub template labeled `model="stub"`,
no mutation, no false live claim. Speech failure → text retained, audio
marked unavailable, no crash. Razorpay failure → normalized provider error
(the 8B-fixed `normalize_razorpay_error` path), auditable execution record,
no false success, no retry storm.

## 9. Security boundaries (unchanged, re-verified)

Consultation → Razorpay/executor/approval/policy/outcome: NO (no imports, no
handles; audio endpoint voices stored answers only). Secrets in env only;
health exposes modes, never keys. Frontend secret scan: NONE.

## 10. Future Razorpay integration path

Set `RAZORPAY_MODE=live` with **test-mode** keys; the intact live adapter
(`POST /payment_links`, Basic auth, HMAC webhooks) takes over behind the
unchanged policy → approval → executor pipeline. Production money is never
in scope. Live public webhook round-trip remains PENDING (no public
deployment) and is not claimed.
