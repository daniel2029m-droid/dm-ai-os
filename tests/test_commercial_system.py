"""
Tests de Comercial & Billing (Stripe, Mercado Pago, Super Admin & Access Control)
===================================================================================
Valida:
1. Configuración centralizada (.env)
2. Live ARS conversion para Mercado Pago
3. Webhook oficial de Stripe (checkout.session.completed -> auto tenant activation)
4. Mercado Pago manual proof submission -> status PENDING_REVIEW
5. Login de Super Admin autenticado por HASH (sin hardcode de contraseña)
6. Aprobación y Rechazo por parte de Administrador
7. Control de Acceso (Solo ACTIVE ingresa a la plataforma)

Ejecutar: python -m pytest tests/test_commercial_system.py -v
"""

import pytest
from pathlib import Path


class TestCommercialConfig:
    """Valida la lectura centralizada de variables de entorno y constantes."""

    def test_env_constants_loaded(self):
        from src.commercial.config import (
            STRIPE_PAYMENT_LINK,
            MP_ALIAS,
            MP_CVU,
            MP_ACCOUNT_HOLDER,
            ADMIN_PASSWORD,
        )
        assert "stripe.com" in STRIPE_PAYMENT_LINK
        assert MP_ALIAS == "monetiza.dm"
        assert MP_CVU == "0000003100044063397420"
        assert MP_ACCOUNT_HOLDER == "Daniel Alberto Morales"
        assert ADMIN_PASSWORD != ""


class TestBillingEngine:
    """Valida flujos de Stripe, Mercado Pago, Admin Auth y Control de Acceso."""

    def test_admin_login_verification(self, tmp_path):
        from src.commercial.billing_engine import BillingEngine
        engine = BillingEngine(db_path=tmp_path / "billing.db")

        from src.commercial.config import ADMIN_PASSWORD
        assert engine.verify_admin_login(ADMIN_PASSWORD) is True
        assert engine.verify_admin_login("wrong_password_123") is False

    def test_mp_payment_details_ars_conversion(self, tmp_path):
        from src.commercial.billing_engine import BillingEngine
        engine = BillingEngine(db_path=tmp_path / "billing.db")

        details = engine.get_mp_payment_details(plan_id="professional")
        assert details["plan_id"] == "professional"
        assert details["amount_usd"] == 99.0
        assert details["amount_ars"] > 0
        assert details["alias"] == "monetiza.dm"

    def test_stripe_checkout_completed_auto_activation(self, tmp_path):
        from src.commercial.billing_engine import BillingEngine
        engine = BillingEngine(db_path=tmp_path / "billing.db")

        session_data = {
            "customer_email": "stripe_buyer@domain.com",
            "plan": "professional",
            "amount_total": 9900
        }

        res = engine.handle_stripe_checkout_completed(session_data)
        assert res["status"] == "success"
        assert res["subscription_status"] == "ACTIVE"
        assert engine.is_tenant_active(res["tenant_id"]) is True

    def test_mercado_pago_proof_submission(self, tmp_path):
        from src.commercial.billing_engine import BillingEngine
        engine = BillingEngine(db_path=tmp_path / "billing.db")

        res = engine.submit_mercado_pago_proof(
            user_email="mp_client@domain.com",
            plan_id="professional",
            operation_number="OP-987654321",
        )
        assert res["status"] == "pending_review"
        tenant_id = res["tenant_id"]
        assert engine.is_tenant_active(tenant_id) is False  # Pending review cannot access dashboard

    def test_admin_approve_transaction(self, tmp_path):
        from src.commercial.billing_engine import BillingEngine
        engine = BillingEngine(db_path=tmp_path / "billing.db")

        submit_res = engine.submit_mercado_pago_proof(
            user_email="user_approve@domain.com",
            plan_id="starter",
            operation_number="OP-111222333",
        )
        tx_id = submit_res["transaction_id"]
        tenant_id = submit_res["tenant_id"]

        assert engine.is_tenant_active(tenant_id) is False

        approve_res = engine.approve_transaction(tx_id, admin_id="super_admin")
        assert approve_res["status"] == "success"
        assert engine.is_tenant_active(tenant_id) is True  # Active now!

    def test_admin_reject_transaction(self, tmp_path):
        from src.commercial.billing_engine import BillingEngine
        engine = BillingEngine(db_path=tmp_path / "billing.db")

        submit_res = engine.submit_mercado_pago_proof(
            user_email="user_reject@domain.com",
            plan_id="starter",
            operation_number="OP-999000",
        )
        tx_id = submit_res["transaction_id"]
        tenant_id = submit_res["tenant_id"]

        reject_res = engine.reject_transaction(tx_id, reason="Comprobante ilisible")
        assert reject_res["status"] == "rejected"
        assert engine.is_tenant_active(tenant_id) is False


class TestCommercialApiEndpoints:
    """Valida los endpoints HTTP públicos y administrativos de FastApi."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_get_checkout_page(self, client):
        response = client.get("/checkout")
        assert response.status_code == 200
        assert "DM AI OS Commercial Platform" in response.text
        assert "monetiza.dm" in response.text

    def test_get_mp_details_endpoint(self, client):
        response = client.get("/v1/billing/mp-details?plan_id=professional")
        assert response.status_code == 200
        data = response.json()
        assert data["alias"] == "monetiza.dm"
        assert data["amount_ars"] > 0

    def test_stripe_webhook_endpoint(self, client):
        payload = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer_email": "webhook_test@domain.com",
                    "plan": "professional",
                    "amount_total": 9900
                }
            }
        }
        response = client.post("/v1/billing/stripe-webhook", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_admin_login_endpoint(self, client):
        from src.commercial.config import ADMIN_PASSWORD
        response = client.post("/v1/admin/login", json={"password": ADMIN_PASSWORD})
        assert response.status_code == 200
        assert "access_token" in response.json()

        # Invalid pass
        response_invalid = client.post("/v1/admin/login", json={"password": "wrong"})
        assert response_invalid.status_code == 401
