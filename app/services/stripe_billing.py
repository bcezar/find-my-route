from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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


async def get_active_subscription(customer_id: str) -> Optional[dict]:
    def _fetch():
        stripe.api_key = _api_key()
        subs = stripe.Subscription.list(customer=customer_id, status="active", limit=1)
        if not subs.data:
            return None
        sub = subs.data[0]
        item = sub["items"]["data"][0] if sub["items"]["data"] else None
        amount = (item["price"]["unit_amount"] or 0) / 100 if item else 0
        currency = (item["price"]["currency"] or "usd").upper() if item else "USD"
        next_date = None
        if sub.get("current_period_end"):
            next_date = datetime.fromtimestamp(
                sub["current_period_end"], tz=timezone.utc
            ).strftime("%Y-%m-%d")
        return {
            "id": sub["id"],
            "status": "ACTIVE",
            "value": amount,
            "currency": currency,
            "nextDueDate": next_date,
            "billingType": "STRIPE",
            "provider": "stripe",
        }

    return await asyncio.to_thread(_fetch)


async def cancel_subscription(subscription_id: str) -> str:
    """Cancel at period end. Returns the period-end datetime string."""
    def _cancel():
        stripe.api_key = _api_key()
        sub = stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
        return datetime.fromtimestamp(
            sub["current_period_end"], tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

    return await asyncio.to_thread(_cancel)


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
