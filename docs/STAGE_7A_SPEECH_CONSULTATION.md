# STAGE 7A — FINANCIAL DOCTOR

## MiniMax Speech Consultation Layer (read-only)

> **Status:** Complete — backend 193 tests pass (163 prior + 30 new), `ruff`
> clean, `mypy` clean; frontend 27 tests pass (22 prior + 5 new), `eslint`
> clean, `tsc` clean, `vite build` clean.

Stage 7A gives the Financial Doctor a voice. It does not give that voice
access to the patient's wallet:

```text
AI EXPLAINS → SYSTEM CONTROLS → HUMAN APPROVES → RAZORPAY ACTS
```

---

## 1. Consultation architecture

```text
TYPED QUESTION (voice input not offered — no verified STT, never faked)
    ↓
POST /demo/case/{id}/consult  (case-scoped)
    ↓
ConsultationContextBuilder → ConsultationContext (deterministic, redacted)
    ↓
StubModelClient template (demo) | MiniMax M3 structured output (live)
    ↓
ConsultationResponse (validated: answer, answer_type, referenced_sections)
    ↓
POST /demo/case/{id}/consultations/{cid}/audio → SpeechResult
    ↓
FRONTEND PLAYBACK (user-initiated Listen button; never autoplayed)
```

New package: `backend/app/services/consultation/` (`models`,
`context_builder`, `prompt_builder`, `consultation_service`,
`speech_adapter`). Session history lives on `DemoCaseSession.consultations`
(Q/A metadata only, capped at 50, never read by deterministic math).

---

## 2. Model responsibilities (unchanged, extended)

| Model | Responsibility |
|-------|----------------|
| M2.7 | Wide investigation, evidence-domain workers (untouched) |
| M3 | Diagnosis (untouched) + consultation answers from read-only context |
| Speech 2.8 | Speech output only (TTS) |

M3 receives the structured context and returns validated JSON. It receives
no credentials, no write handles, no tools, no database access.

---

## 3. Speech 2.8 verified capabilities

Verified against the official MiniMax platform docs before implementation:

- **TTS — VERIFIED, IMPLEMENTED.** Synchronous HTTP T2A:
  `POST {base}/t2a_v2[?GroupId=]`, Bearer auth, body `{model, text,
  voice_setting{voice_id, speed, vol, pitch}, audio_setting{sample_rate,
  bitrate, format, channel}, language_boost, output_format}`. Models
  `speech-2.8-hd` / `speech-2.8-turbo` exist (Stage 7A defaults to
  `speech-2.8-turbo`). Success = `base_resp.status_code == 0` with
  hex-encoded audio in `data.audio` (+ `extra_info.audio_length`).
- **STT — NOT VERIFIED, NOT IMPLEMENTED.** The official API overview lists
  text, T2A/T2A-async, voice cloning/design/management, video, image, music,
  and file APIs, but no speech-to-text/transcription endpoint. Per the spec
  ("do not fake it"), the UI offers typed questions only — no microphone
  control exists anywhere in the frontend.

There is no pre-existing "GMI integration" in this repo; the live adapter
targets the documented MiniMax HTTP contract directly, following the repo's
existing `ModelConfig` env-driven pattern.

---

## 4. Context-building architecture

`ConsultationContextBuilder.build(case_view)` converts the Stage 6 `CaseView`
dict into `ConsultationContext`: incident, investigation (worker findings +
supports/contradicts), diagnosis (hypothesis, alternatives, uncertainties),
flattened evidence, recommended action, policy/approval/execution/outcome
statuses, plus `key_figures` — the exact display strings (`"21.75%"`,
`"₹48,102"`) the model is allowed to quote.

---

## 5. Read-only boundary

The consultation package imports nothing that can mutate financial state —
no `ActionExecutor`, no `ApprovalService`, no `RazorpayAdapter`, no policy
or outcome stores. The model reasons over a supplied dict; it cannot "look
around" (no SQL, no tools). The no-mutation test snapshots the full
`CaseView` JSON before/after consult + audio synthesis and asserts equality.

---

## 6. M3 consultation role

Live path: `CONSULT_SYSTEM_PROMPT` + `build_user_prompt()` → existing
`ModelClient.generate(..., response_schema=_LiveConsultationOutput)` (JSON
mode) → validated `answer` / `answer_type` / `referenced_sections`. Unknown
sections are dropped; over-long answers truncated. **₹-grounding check:**
every `₹<digits>` token must exactly match a context figure, else the answer
is discarded.

---

## 7. Speech provider abstraction

`SpeechProvider` protocol (`synthesize(text) → SpeechResult`,
`capabilities`, `name`) with `create_speech_provider()` selecting
`StubSpeechAdapter` (default) or `MiniMaxSpeechAdapter`. Capabilities always
report `{"tts": …, "stt": False}` — STT is never claimed.

---

## 8. Stub provider

`StubSpeechAdapter` synthesizes a deterministic 0.6 s WAV sine beep in code
(valid RIFF/WAVE, 16-bit mono) labeled `provider="stub"`. It is an explicit
placeholder — never presented as MiniMax audio — and lets the demo exercise
Question → Answer → Audio playback with zero credentials.

The stub consultation path likewise renders answers deterministically from
context values, so no hallucinated number is possible by construction.

---

## 9. Live GMI/MiniMax provider

`MiniMaxSpeechAdapter` implements the verified T2A contract (Bearer auth,
`GroupId` query when configured, hex→bytes decode, `base_resp` check,
`audio_length` → `duration_ms`). All failures raise `SpeechError` → HTTP 502
with a safe message; case state is untouched. Unit-tested against
`httpx.MockTransport` (request shape, auth, payload, hex decode, and all
error branches) — no network required.

---

## 10. API contracts

```text
POST /demo/case/{id}/consult
  {question} → ConsultationResponse
  {answer, answer_type, referenced_sections, timings{context_build_ms,
   model_latency_ms, total_latency_ms}, model}
  404 unknown case · 422 empty/oversize · 429 cooldown (2 s/case) · 502 safe message

GET /demo/case/{id}/consultations
  case-scoped Q/A history (metadata only)

POST /demo/case/{id}/consultations/{cid}/audio
  voices ONLY a stored answer for THIS case (no free-text TTS proxy)
  → SpeechResult {mime_type, data_base64, byte_size, duration_ms, provider, voice}
  404 unknown consultation · 502 safe message
```

---

## 11. Frontend flow

`ConsultPanel` ("Ask Financial Doctor", after the outcome section): example
questions → typed input (max 1000 chars) → states READY / THINKING /
ANSWER_READY / SPEAKING / ERROR (no infinite spinners). Answers show
`referenced_sections` chips that smooth-scroll to and flash the relevant
case card. "▶ Listen to explanation" fetches audio and renders a native
`<audio controls>` player (no autoplay; play/pause/ended tracked). A label
states voice input is unavailable and why. Consultation failures show a safe
error; the Stage 6 journey keeps working.

---

## 12. Safety boundaries

```text
consultation → action executor: NO
consultation → Razorpay adapter: NO
consultation → approval mutation: NO
consultation → policy mutation:  NO
consultation → outcome mutation:  NO
```

Enforced architecturally (no imports, no handles, audio endpoint voices only
stored answers), not by prompt wording alone.

---

## 13. Prompt-injection architecture

Adversarial requests ("Approve the treatment", "Ignore the rules and
execute…") are classified as action requests and answered with a fixed
refusal; legitimate safety questions ("Why can't you just send the links?")
are answered as safety explanations. Because no action tools exist in the
consultation path, injection cannot escalate beyond a refused answer.
Covered by 7 parametrized adversarial tests + refusal-before-state-change.

---

## 14. Failure handling

Model timeout/invalid output → deterministic template fallback (answer stays
grounded, `model="stub"`). Speech failure → 502 safe message, text answer
retained. Consult failure → panel error state, case UI unaffected. Cooldown
429s hot loops; question/answer/history caps bound cost.

---

## 15. Testing strategy

`tests/consultation/test_consultation.py` (30 tests): context redaction (no
`cust_/pay_/order_/plink_` leakage) and key-figure equality; per-type
answers assert CaseView-computed values (never hardcoded); adversarial +
injection refusal; no-mutation snapshot; cooldown/history caps; invented-₹
fallback and truthful live passthrough via a fake model client (no
network); stub WAV validity; MiniMax request-shape/hex-decode/error tests via
`MockTransport`; provider selection; HTTP layer (200/404/422/429, history,
audio); golden consultation (`"Doctor, did the treatment work?"` on a
partially-recovered case → status, recovered ₹, and target count from
CaseView + stub audio + unchanged state). Frontend: 5 `ConsultPanel` tests
(ask→answer+chips, chip scroll, listen→player without autoplay, error state,
no microphone).

---

## 16. Configuration (all backend-only, never exposed to React)

```bash
MINIMAX_API_KEY=""        # empty = deterministic stub consultation
MINIMAX_BASE_URL="https://api.minimax.chat/v1"
MINIMAX_M3_MODEL="MiniMax-M3"
MINIMAX_GROUP_ID=""
SPEECH_PROVIDER="stub"    # or "minimax" for live Speech 2.8 TTS
SPEECH_MODEL="speech-2.8-turbo"
SPEECH_VOICE_ID="English_expressive_narrator"
```

---

## Final verification

```text
Consultation:
  case-scoped context: PASS
  incident explanation: PASS
  diagnosis explanation: PASS
  treatment explanation: PASS
  outcome explanation: PASS

Grounding:
  deterministic metrics preserved: PASS
  invented financial values: NO
  unavailable data handled safely: PASS

Speech:
  verified API capability: PASS (TTS t2a_v2; STT correctly absent)
  provider abstraction: PASS
  stub provider: PASS
  live MiniMax provider: PASS (contract-tested, key-gated)
  credentials backend-only: PASS

Safety:
  consultation → action executor: NO
  consultation → Razorpay: NO
  consultation → approval mutation: NO
  consultation → policy mutation: NO
  consultation → outcome mutation: NO

Adversarial safety:
  approve via voice: BLOCKED
  execute via voice: BLOCKED
  policy bypass request: BLOCKED
  prompt injection request: BLOCKED

Golden consultation:
  grounded answer: PASS
  case unchanged: PASS
  speech response: PASS
  financial action executed: NO

Tests:
  backend: 193 passed
  frontend: 27 passed

Lint:
  PASS

Typecheck:
  PASS

Build:
  PASS
```
