"""Adapter factory — selects stub vs live based on configuration."""

from __future__ import annotations

from backend.app.adapters.razorpay.interface import RazorpayAdapter
from backend.app.adapters.razorpay.live import LiveRazorpayAdapter
from backend.app.adapters.razorpay.stub import StubRazorpayAdapter
from backend.app.config import get_settings
from backend.app.services.synthetic_data import MerchantWorld


async def create_razorpay_adapter(
    world: MerchantWorld | None = None,
) -> RazorpayAdapter:
    """Create the appropriate Razorpay adapter based on configuration.

    Args:
        world: Synthetic world (required for stub mode).

    Returns:
        RazorpayAdapter implementation (stub or live).
    """
    settings = get_settings()
    mode = getattr(settings, "razorpay_mode", "stub")

    if mode == "live":
        key_id = getattr(settings, "razorpay_key_id", None)
        key_secret = getattr(settings, "razorpay_key_secret", None)
        webhook_secret = getattr(settings, "razorpay_webhook_secret", None)

        if not key_id or not key_secret:
            raise RuntimeError(
                "RAZORPAY_MODE=live but RAZORPAY_KEY_ID/SECRET not configured"
            )

        return LiveRazorpayAdapter(  # type: ignore[return-value]
            key_id=key_id,
            key_secret=key_secret,
            webhook_secret=webhook_secret or "",
        )

    # Default: stub mode
    if world is None:
        raise RuntimeError("StubRazorpayAdapter requires a MerchantWorld")
    return StubRazorpayAdapter(world=world)  # type: ignore[return-value]