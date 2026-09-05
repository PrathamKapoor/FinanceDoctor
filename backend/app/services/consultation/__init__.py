"""Read-only financial consultation layer (Stage 7A).

Architecture:

```text
USER QUESTION (typed text — STT unverified, never faked)
    ↓
ConsultationRequest (case-scoped)
    ↓
ConsultationContextBuilder → ConsultationContext (deterministic, redacted)
    ↓
ConsultService → StubModelClient (deterministic template) | MiniMax M3 (live)
    ↓
ConsultationResponse (validated)
    ↓
SpeechAdapter.synthesize() → SpeechResult (audio)
    ↓
FRONTEND PLAYBACK (user-initiated, never autoplayed)
```

The consultation package imports NOTHING that can mutate financial state:
no ActionExecutor, no ApprovalService, no RazorpayAdapter, no policy or
outcome stores. Voice explains; it never authorizes.
"""

from backend.app.services.consultation.consultation_service import (
    ConsultationError,
    ConsultRateLimited,
    ConsultService,
)
from backend.app.services.consultation.context_builder import (
    ConsultationContextBuilder,
)
from backend.app.services.consultation.models import (
    AnswerType,
    ConsultationContext,
    ConsultationRecord,
    ConsultationRequest,
    ConsultationResponse,
    ConsultationSection,
    ConsultationTimings,
    SpeechResult,
)
from backend.app.services.consultation.prompt_builder import (
    CONSULT_SYSTEM_PROMPT,
    build_user_prompt,
)
from backend.app.services.consultation.speech_adapter import (
    MiniMaxSpeechAdapter,
    SpeechConfig,
    SpeechError,
    StubSpeechAdapter,
    create_speech_provider,
)

__all__ = [
    "AnswerType",
    "ConsultRateLimited",
    "ConsultService",
    "ConsultationContext",
    "ConsultationContextBuilder",
    "ConsultationError",
    "ConsultationRecord",
    "ConsultationRequest",
    "ConsultationResponse",
    "ConsultationSection",
    "ConsultationTimings",
    "CONSULT_SYSTEM_PROMPT",
    "MiniMaxSpeechAdapter",
    "SpeechConfig",
    "SpeechError",
    "SpeechResult",
    "StubSpeechAdapter",
    "build_user_prompt",
    "create_speech_provider",
]
