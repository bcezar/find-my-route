from __future__ import annotations

from datetime import date
from typing import Optional

import httpx

from app.config import settings


def _headers() -> dict:
    return {
        "access_token": settings.asaas_api_key or "",
        "Content-Type": "application/json",
    }


async def get_or_create_customer(
    user_id: str,
    email: str,
    name: str,
    cpf_cnpj: str,
) -> str:
    """Return the Asaas customer ID, creating one if it doesn't exist yet."""
    async with httpx.AsyncClient() as client:
        # Search by externalReference (our user_id) to avoid duplicates
        r = await client.get(
            f"{settings.asaas_base_url}/customers",
            headers=_headers(),
            params={"externalReference": user_id},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("data"):
            return data["data"][0]["id"]

        # Create new customer
        r = await client.post(
            f"{settings.asaas_base_url}/customers",
            headers=_headers(),
            json={
                "name": name or email,
                "email": email,
                "cpfCnpj": cpf_cnpj,
                "externalReference": user_id,
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["id"]


async def create_subscription(
    customer_id: str,
    user_id: str,
    billing_type: str,
    success_url: str,
) -> dict:
    """
    Create a monthly Pro subscription and return the payment URL for the first charge.
    billing_type: 'PIX' | 'CREDIT_CARD'
    """
    async with httpx.AsyncClient() as client:
        next_due = date.today().isoformat()
        r = await client.post(
            f"{settings.asaas_base_url}/subscriptions",
            headers=_headers(),
            json={
                "customer": customer_id,
                "billingType": billing_type,
                "value": settings.pro_price,
                "nextDueDate": next_due,
                "cycle": "MONTHLY",
                "description": "FindMyRoute Pro",
                "externalReference": user_id,
            },
            timeout=10,
        )
        r.raise_for_status()
        sub = r.json()
        sub_id = sub["id"]

        # Fetch the first payment generated for this subscription
        r2 = await client.get(
            f"{settings.asaas_base_url}/payments",
            headers=_headers(),
            params={"subscription": sub_id},
            timeout=10,
        )
        r2.raise_for_status()
        payments = r2.json().get("data", [])

        payment_url: Optional[str] = None
        if payments:
            p = payments[0]
            payment_url = p.get("invoiceUrl") or p.get("bankSlipUrl")

        return {
            "subscription_id": sub_id,
            "payment_url": payment_url,
        }
