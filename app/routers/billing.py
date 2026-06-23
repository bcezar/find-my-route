from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from app import storage
from app.config import settings
from app.limiter import limiter
from app.services import billing

router = APIRouter()


class CheckoutRequest(BaseModel):
    cpf_cnpj: str
    billing_type: Literal["PIX", "CREDIT_CARD"] = "PIX"


async def _require_auth(request: Request) -> dict:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Autenticação necessária.")
    user = await storage.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
    return user


@router.post("/billing/checkout")
@limiter.limit("5/minute")
async def checkout(request: Request, body: CheckoutRequest = Body(...)):
    if not settings.asaas_api_key:
        raise HTTPException(status_code=501, detail="Pagamentos não configurados.")

    user = await _require_auth(request)

    if user.get("is_pro"):
        raise HTTPException(status_code=400, detail="Você já possui o Plano Pro.")

    cpf_cnpj = body.cpf_cnpj.replace(".", "").replace("-", "").replace("/", "").strip()
    if len(cpf_cnpj) not in (11, 14):
        raise HTTPException(status_code=422, detail="CPF ou CNPJ inválido.")

    try:
        customer_id = await billing.get_or_create_customer(
            user_id=user["id"],
            email=user["email"],
            name=user.get("name") or user["email"],
            cpf_cnpj=cpf_cnpj,
        )
        await storage.set_asaas_customer_id(user["id"], customer_id)

        success_url = f"{settings.app_base_url}/?upgraded=1"
        result = await billing.create_subscription(
            customer_id=customer_id,
            user_id=user["id"],
            billing_type=body.billing_type,
            success_url=success_url,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao criar cobrança: {exc}") from exc

    if not result.get("payment_url"):
        raise HTTPException(status_code=502, detail="Não foi possível obter o link de pagamento.")

    return {"payment_url": result["payment_url"]}


@router.get("/billing/account")
@limiter.limit("30/minute")
async def account(request: Request):
    user = await _require_auth(request)
    customer_id = user.get("asaas_customer_id")

    subscription = None
    payments = []

    if settings.asaas_api_key and customer_id:
        try:
            subscription = await billing.get_active_subscription(customer_id)
        except Exception:
            pass
        try:
            payments = await billing.list_payments(customer_id)
        except Exception:
            pass

    return {
        "user": {
            "id":             user["id"],
            "email":          user["email"],
            "name":           user.get("name"),
            "is_pro":         user.get("is_pro", False),
        },
        "subscription": subscription,
        "payments":     payments,
    }


@router.delete("/billing/subscription")
@limiter.limit("5/minute")
async def cancel_subscription(request: Request):
    if not settings.asaas_api_key:
        raise HTTPException(status_code=501, detail="Pagamentos não configurados.")

    user = await _require_auth(request)
    customer_id = user.get("asaas_customer_id")
    if not customer_id:
        raise HTTPException(status_code=404, detail="Nenhuma assinatura encontrada.")

    try:
        sub = await billing.get_active_subscription(customer_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao buscar assinatura: {exc}") from exc

    if not sub:
        raise HTTPException(status_code=404, detail="Nenhuma assinatura ativa encontrada.")

    try:
        await billing.cancel_subscription(sub["id"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao cancelar assinatura: {exc}") from exc

    # Keep Pro active for 30 days from today (last paid period)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    await storage.set_pro_expires_at(user["id"], expires_at)

    return {"ok": True, "pro_expires_at": expires_at[:10]}


@router.post("/billing/webhook")
async def billing_webhook(request: Request):
    # Verify origin via header token
    token = request.headers.get("asaas-access-token", "")
    if settings.asaas_webhook_token and token != settings.asaas_webhook_token:
        raise HTTPException(status_code=403, detail="Webhook token inválido.")

    payload = await request.json()
    event = payload.get("event", "")
    payment = payload.get("payment", {})

    # Identify user: prefer externalReference on payment, fall back to subscription's externalReference
    user_id: Optional[str] = payment.get("externalReference")
    if not user_id:
        customer_id = payment.get("customer")
        if customer_id:
            user = await storage.get_user_by_asaas_customer(customer_id)
            user_id = user["id"] if user else None

    if not user_id:
        # Unknown user — acknowledge without error so Asaas doesn't retry
        return {"ok": True}

    if event in ("PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"):
        await storage.set_user_pro(user_id, True)
        await storage.set_pro_expires_at(user_id, None)  # renewed — no expiry
    elif event in ("PAYMENT_REFUNDED", "PAYMENT_CHARGEBACK_REQUESTED", "PAYMENT_CHARGEBACK_DISPUTE"):
        await storage.set_user_pro(user_id, False)
        await storage.set_pro_expires_at(user_id, None)

    return {"ok": True}
