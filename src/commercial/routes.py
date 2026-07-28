"""
Commercial API Router — Endpoints for Stripe, Mercado Pago, Billing & Owner/Super Admin
===================================================================================
Adds commercial SaaS endpoints to FastAPI application without altering existing APIs.
- GET  /checkout (Commercial Pricing & Stripe/MP Options)
- GET  /v1/billing/mp-details (Live ARS conversion)
- POST /v1/billing/stripe-webhook (Stripe `checkout.session.completed` handler)
- POST /v1/billing/submit-mp-proof (Mercado Pago proof handler)
- GET  /panel/owner & POST /v1/auth/owner-login (Super Admin / Owner authentication)
- GET  /panel/dashboard (Super Admin Control Panel)
- GET  /v1/owner/transactions & POST /v1/owner/transactions/{tx_id}/approve|reject
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Security
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from .billing_engine import billing_engine
from .views import get_commercial_checkout_html, get_admin_dashboard_html, get_admin_login_html

commercial_router = APIRouter()
security = HTTPBearer()


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class MPProofRequest(BaseModel):
    user_email: str
    plan_id: str = "professional"
    operation_number: str
    proof_details: Optional[str] = None

class AdminLoginRequest(BaseModel):
    password: str

class StripeWebhookPayload(BaseModel):
    type: str
    data: Dict[str, Any]


# ── Super Admin Token Auth Helper ─────────────────────────────────────────────

def verify_admin_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    if token != "super_admin_jwt_active_session_token":
        raise HTTPException(status_code=401, detail="Invalid Super Admin Credentials")
    return "super_admin"


# ── Public Commercial Endpoints ───────────────────────────────────────────────

from pathlib import Path

_PUBLIC_INDEX = Path(__file__).parent.parent.parent / "public" / "index.html"

@commercial_router.get("/", response_class=HTMLResponse)
async def main_landing_page():
    """Serves main platform UI."""
    try:
        if _PUBLIC_INDEX.exists():
            return _PUBLIC_INDEX.read_text(encoding="utf-8")
        with open("public/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return get_commercial_checkout_html()


@commercial_router.get("/checkout", response_class=HTMLResponse)
async def checkout_page():
    """Renders the public Commercial SaaS Checkout & Pricing page."""
    return get_commercial_checkout_html()



@commercial_router.get("/v1/billing/mp-details")
async def get_mp_details(plan_id: str = "professional"):
    """Returns Mercado Pago payment details converted dynamically to ARS."""
    return billing_engine.get_mp_payment_details(plan_id=plan_id)


@commercial_router.post("/v1/billing/stripe-webhook")
async def stripe_webhook(request: Request):
    """
    Official Stripe Webhook listener.
    Listens for `checkout.session.completed` event to automatically activate tenants.
    """
    payload = await request.json()
    event_type = payload.get("type", "")

    if event_type == "checkout.session.completed":
        session_data = payload.get("data", {}).get("object", {})
        res = billing_engine.handle_stripe_checkout_completed(session_data)
        return JSONResponse(content=res)

    return JSONResponse(content={"status": "ignored", "event_type": event_type})


@commercial_router.post("/v1/billing/submit-mp-proof")
async def submit_mp_proof(req: MPProofRequest):
    """Stores Mercado Pago manual proof and sets tenant status to PENDING_REVIEW."""
    res = billing_engine.submit_mercado_pago_proof(
        user_email=req.user_email,
        plan_id=req.plan_id,
        operation_number=req.operation_number,
        proof_details=req.proof_details
    )
    return JSONResponse(content=res)


# ── Owner / Admin Auth & Dashboard Endpoints ─────────────────────────────────

@commercial_router.get("/panel/owner", response_class=HTMLResponse)
@commercial_router.get("/owner/login", response_class=HTMLResponse)
@commercial_router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page():
    """Renders the Super Admin / Owner Access Page."""
    return get_admin_login_html()


@commercial_router.post("/v1/auth/owner-login")
@commercial_router.post("/v1/owner/login")
@commercial_router.post("/v1/admin/login")
async def admin_login_api(req: AdminLoginRequest):
    """Validates Super Admin password from env without hardcoding, returning token."""
    if billing_engine.verify_admin_login(req.password):
        return {"status": "success", "access_token": "super_admin_jwt_active_session_token", "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Contraseña de administrador incorrecta")


@commercial_router.get("/panel/dashboard", response_class=HTMLResponse)
@commercial_router.get("/owner/dashboard", response_class=HTMLResponse)
@commercial_router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page():
    """Renders the Super Admin Control Dashboard."""
    return get_admin_dashboard_html()


@commercial_router.get("/v1/owner/transactions")
@commercial_router.get("/v1/admin/transactions")
async def admin_list_transactions(admin: str = Depends(verify_admin_token)):
    """Lists all Stripe & Mercado Pago transactions for Super Admin review."""
    return billing_engine.list_transactions()


@commercial_router.get("/v1/owner/subscriptions")
@commercial_router.get("/v1/admin/subscriptions")
async def admin_list_subscriptions(admin: str = Depends(verify_admin_token)):
    """Lists all tenant SaaS subscriptions."""
    return billing_engine.list_subscriptions()


@commercial_router.post("/v1/owner/transactions/{tx_id}/approve")
@commercial_router.post("/v1/admin/transactions/{tx_id}/approve")
async def admin_approve_transaction(tx_id: str, admin: str = Depends(verify_admin_token)):
    """Approves a Mercado Pago proof, activating tenant & provisioning platform."""
    res = billing_engine.approve_transaction(transaction_id=tx_id, admin_id=admin)
    return JSONResponse(content=res)


@commercial_router.post("/v1/owner/transactions/{tx_id}/reject")
@commercial_router.post("/v1/admin/transactions/{tx_id}/reject")
async def admin_reject_transaction(tx_id: str, admin: str = Depends(verify_admin_token)):
    """Rejects a Mercado Pago proof."""
    res = billing_engine.reject_transaction(transaction_id=tx_id, admin_id=admin)
    return JSONResponse(content=res)
