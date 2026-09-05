# STAGE 8B — FINANCIAL DOCTOR

## Live API Integration & End-to-End Verification

> **Status:** Partially complete — every verifiable-without-credentials check
> passes; real credential calls are BLOCKED on credentials (none exist in this
> environment and none were provided). Nothing is faked: anything requiring a
> live key is marked PENDING/BLOCKED, never PASS.

---

## 1. Provider configuration (exact variable names, nothing invented)

| Provider | Variables (existing) | Modes |
|----------|----------------------|-------|
| Razorpay | `RAZORPAY_MODE` (`stub`\|`live`), `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | stub default; live refuses to boot without keys |
| MiniMax M2.7/M3 | `MINIMAX_API_KEY` (empty = stub), `MINIMAX_BASE_URL`, `MINIMAX_M27_MODEL`, `MINIMAX_M3_MODEL`, `MINIMAX_GROUP_ID` | stub default |
| Speech 2.8 | `SPEECH_PROVIDER` (`stub`\|`minimax`), `SPEECH_MODEL`, `SPEECH_VOICE_ID` (same `MINIMAX_*` key/base) | stub default |
| Deployment | `ENVIRONMENT`, `CORS_ORIGINS` | — |

Notes: there is no `CONSULTATION_PROVIDER` variable — consultation liveness
follows `MINIMAX_API_KEY` presence. There is no `GMI_API_KEY` — the MiniMax
key is the credential. No new names were introduced.

---

## 2. Razorpay Test Mode setup

1. Use Razorpay **test mode** keys only — never production money.
2. `RAZORPAY_MODE=live`, `RAZORPAY_KEY_ID=<test key>`,
   `RAZORPAY_KEY_SECRET=<test secret>`,
   `RAZORPAY_WEBHOOK_SECRET=<test webhook secret>`.
3. The backend refuses to start live mode with missing keys (Stage 8A
   `validate_startup`; also enforced in the adapter factory).
4. Drive the real pipeline: start case → policy → approve → execute. The
   executor calls `POST /payment_links` with Basic auth; test mode returns a
   real `plink_…` id and `short_url`.

---

## 3. MiniMax/GMI configuration

`MINIMAX_API_KEY=<key>` (+ optional `MINIMAX_BASE_URL`, model overrides).
With a key set, investigation workers use live M2.7-shaped chat calls and
consultation uses live M3 structured output; without it, deterministic stubs
run and consultation falls back to grounded templates. Speech needs
`SPEECH_PROVIDER=minimax` as well — startup refuses minimax speech without a
key rather than silently serving stub audio.

---

## 4. Verified M2.7 integration

`MiniMaxModelClient` wire contract verified through the real client code with
a mocked transport (`tests/live/test_live_wire_contracts.py`): POST path
`/chat/completions`, Bearer auth, configured model id, system+user messages,
JSON-mode `response_format`, structured parse, malformed/HTTP errors raise.
Real M2.7 call through the investigation pipeline: **BLOCKED on credentials.**

---

## 5. Verified M3 integration

Same client contract as §4, plus M3-through-consultation wiring verified:
a transport-backed live client answering valid grounded JSON flows through
`ConsultService` (answer preserved, model name recorded, sections from the
deterministic map, ₹-grounding enforced). M3 has no Razorpay access, no
executor access, no write authority, no policy bypass — by construction (no
imports/handles exist). Real M3 call: **BLOCKED on credentials.**

---

## 6. Verified Speech 2.8 TTS integration

Verified T2A contract (`POST {base}/t2a_v2`, `speech-2.8-turbo`,
hex audio, `base_resp.status_code == 0`) implemented in
`MiniMaxSpeechAdapter` and unit-tested (request shape, auth, payload, hex
decode, all error branches) in Stage 7A. STT was never verified to exist and
is not attempted. Real synthesis call: **BLOCKED on credentials.**

---

## 7. Razorpay live adapter verification

`LiveRazorpayAdapter` wire contract verified with a mocked transport:
`POST /payment_links` with Basic auth and amount/currency/reference payload;
201 parses provider id/short URL/status; 401 → `ProviderAuthenticationError`;
409 → `ProviderConflictError`; 5xx → `ProviderUnavailableError`; 404 reads →
`None`; HMAC webhook verify true/false. Real Test Mode call through the
controlled pipeline: **BLOCKED on credentials.**

**Bug found and fixed by this verification (Stage 8A-adjacent):**
`normalize_razorpay_error` crashed with `TypeError` (duplicate
`provider_code` keyword) on every live error path — invisible in stub mode.
Fixed at a single point (overlay Razorpay's code after construction);
covered by the new tests. Without this fix, a live 401 would have raised the
wrong exception type.

---

## 8. Webhook verification status

- Deterministic signed webhook boundary (`payment_link.paid` → dedup →
  outcome): **PASS** (existing suite + stub-provider path).
- Live public webhook round-trip (public URL → Razorpay dashboard → real
  event): **PENDING** — no public deployment exists in this stage, and no
  live claim is made.

---

## 9. Stub vs live modes

| Component | Stub (default, no keys) | Live (keys required) |
|-----------|-------------------------|----------------------|
| Incident/analytics/policy/outcome | Deterministic, always | Same code, same math |
| M2.7/M3 | Deterministic stubs | `MINIMAX_API_KEY` |
| Speech | Placeholder WAV | `SPEECH_PROVIDER=minimax` + key |
| Razorpay | In-memory stub | `RAZORPAY_MODE=live` + test keys |
| Mode display | "Demo environment" | "Integration mode" + per-provider badges from `/health` |

Demo mode works with zero credentials and is never removed. Live modes fail
fast at startup when misconfigured — never silent fallback.

---

## 10. Fallback behavior

- M3/model failure → deterministic grounded template (`model="stub"`),
  case UI unaffected; internal traceability preserved via model field.
- Speech failure → 502 with safe message; text answer retained; audio marked
  unavailable (backend test + UI error state).
- Razorpay failure → normalized `ProviderError` (never false "success");
  execution failure recorded; no retry storm (executor idempotency).
- Missing credentials → startup refusal (live) or stub default (demo).

---

## 11. Secrets handling

Keys live only in environment/`.env` (gitignored, never committed). No key
appears in source, React code, README examples, logs, health output, or test
assertions. Debug output prints `configured: true/false` and modes only.
The one live-shaped test credential in the suite (`rzp_test_id`) is a dummy
string used solely against a mocked transport. Frontend secret scan: NONE.

---

## 12. Exact limitations (what is NOT claimed)

- No real MiniMax request has been made from this environment (no key).
- No real Razorpay request has been made (no key; production money never
  touched, test mode mandated when keys arrive).
- No live public webhook round-trip exists.
- Live adapter verification is wire-contract level (mocked transport), not
  network level.
- To complete: set the keys per §2–§3 and run the runbook below; no code
  changes are required.

**Live verification runbook (no code changes needed):**

```bash
# 1. credentials only via environment
export RAZORPAY_MODE=live RAZORPAY_KEY_ID=rzp_test_... RAZORPAY_KEY_SECRET=...
export MINIMAX_API_KEY=... SPEECH_PROVIDER=minimax
# 2. boot (fails fast if anything is missing)
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# 3. journey: POST /demo/case/start → consult → audio → approve → execute
#    (real plink_… id in treatment.provider_reference) → simulate
# 4. confirm header badges read "Integration mode" / Live providers
```

---

## Final demo provider matrix (actual statuses)

```text
Component                     Mode              Status

Anomaly Detection             Deterministic     PASS
Investigation Pipeline        Real Application  PASS

MiniMax M2.7                  STUB (wire contract PASS)   PASS*
MiniMax M3                    STUB (wire contract PASS)   PASS*
MiniMax Speech 2.8            STUB (wire contract PASS)   PASS*

Razorpay Payment Links        STUB (wire contract PASS)   PASS*

Webhook Signature Validation  Real Boundary     PASS

Live Public Webhook           PENDING

Policy Engine                 Deterministic     PASS
Human Approval                Real Application  PASS
Outcome Measurement           Deterministic     PASS
```

`*` = live credential calls BLOCKED on credentials; stub behavior + live
wire contracts verified, demo mode fully working.

---

## Update (Stage 8C — GMI Cloud credentials supplied)

The BLOCKED items above were resolved as far as the provider allows (see
`docs/STAGE_8C_HYBRID_DEMO.md` for evidence): M2.7/M3 verified live via GMI
Cloud (`MiniMaxAI/MiniMax-M2.7`, `MiniMaxAI/MiniMax-M3`); Speech 2.8 proven
unavailable on GMI (HTTP 404, no audio models listed) so the stub
placeholder stands by evidence; Razorpay remains stub by stage decision.
