from __future__ import annotations

import asyncio
from typing import Optional

import stripe

from app.config import settings


def _api_key() -> str:
    return settings.stripe_secret_key or ""


async def create_checkout_session(
    user_id: str,
    email: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    def _create():
        stripe.api_key = _api_key()
        return stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
            customer_email=email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": user_id},
            subscription_data={"metadata": {"user_id": user_id}},
        )

    session = await asyncio.to_thread(_create)
    return {"payment_url": session.url, "session_id": session.id}


def verify_webhook(payload: bytes, sig_header: str) -> Optional[dict]:
    """Return parsed event dict or None on failure."""
    try:
        stripe.api_key = _api_key()
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret or ""
        )
        return dict(event)
    except (stripe.SignatureVerificationError, ValueError):
        return None
