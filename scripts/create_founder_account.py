"""
DM AI OS -- Create Founder Account
===================================
Inserts the Founder (Owner) account into ALL relevant SQLite databases:

  1. Project_State/commercial_billing.db  -> subscriptions + admin_audit_log
  2. Project_State/assistant_factory.db   -> assistants table (enterprise assistant)
  3. Project_State/Storage/users.db       -> identity / user profile

Run from project root:
    python scripts/create_founder_account.py

No network required. Idempotent -- safe to run multiple times.
"""

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import timezone
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
STATE_DIR    = PROJECT_ROOT / "Project_State"
STATE_DIR.mkdir(parents=True, exist_ok=True)

BILLING_DB         = STATE_DIR / "commercial_billing.db"
ASSISTANT_DB       = STATE_DIR / "assistant_factory.db"
USERS_DB           = STATE_DIR / "Storage" / "users.db"
(STATE_DIR / "Storage").mkdir(parents=True, exist_ok=True)

# ── Founder Constants ─────────────────────────────────────────────────────────

sys.path.insert(0, str(PROJECT_ROOT))
try:
    from src.commercial.founder_access import (
        FOUNDER_TENANT_ID, FOUNDER_EMAIL, FOUNDER_NAME,
        FOUNDER_PLAN, FOUNDER_SPECIALISTS, FOUNDER_TEMPLATES, FOUNDER_FEATURES,
        get_founder_profile,
    )
except ImportError:
    # Fallback if src not importable (standalone execution)
    FOUNDER_TENANT_ID  = "founder_daniel"
    FOUNDER_EMAIL      = "daniel@dmorales.site"
    FOUNDER_NAME       = "Daniel Morales"
    FOUNDER_PLAN       = "founder"
    FOUNDER_SPECIALISTS = ["all"]
    FOUNDER_TEMPLATES  = ["all"]
    FOUNDER_FEATURES   = {"all": True, "billing_exempt": True}
    def get_founder_profile():
        return {"tenant_id": FOUNDER_TENANT_ID, "role": "owner", "plan": FOUNDER_PLAN}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("founder_setup")


# ─────────────────────────────────────────────────────────────────────────────
# 1. BILLING DB — subscriptions + audit_log
# ─────────────────────────────────────────────────────────────────────────────

def _add_column_if_missing(conn, table, column, col_type):
    """Safely add a column to an existing table if it doesn't exist."""
    existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        log.info(f"  Migrated: added column '{column}' to '{table}'")


def setup_billing_db():
    log.info(f"Billing DB -> {BILLING_DB}")
    with sqlite3.connect(str(BILLING_DB)) as conn:
        # Ensure tables exist (base schema from BillingEngine)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                tenant_id        TEXT PRIMARY KEY,
                user_email       TEXT NOT NULL,
                plan             TEXT NOT NULL,
                status           TEXT NOT NULL,
                payment_method   TEXT,
                amount_usd       REAL,
                amount_ars       REAL,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activated_at     TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id   TEXT PRIMARY KEY,
                tenant_id        TEXT NOT NULL,
                user_email       TEXT NOT NULL,
                plan             TEXT NOT NULL,
                payment_method   TEXT NOT NULL,
                amount_usd       REAL,
                amount_ars       REAL,
                operation_number TEXT,
                proof_details    TEXT,
                status           TEXT NOT NULL,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                action           TEXT NOT NULL,
                admin_identity   TEXT NOT NULL,
                target_tenant    TEXT,
                details          TEXT,
                timestamp        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Migrate: add columns that the original schema may not have
        _add_column_if_missing(conn, "subscriptions", "billing_exempt", "INTEGER DEFAULT 0")
        _add_column_if_missing(conn, "subscriptions", "role",           "TEXT DEFAULT 'user'")
        conn.commit()

        # Insert/update Founder subscription
        conn.execute("""
            INSERT OR REPLACE INTO subscriptions
                (tenant_id, user_email, plan, status, payment_method,
                 amount_usd, amount_ars, billing_exempt, role, activated_at)
            VALUES (?, ?, ?, 'ACTIVE', 'founder_grant',
                    0.0, 0.0, 1, 'owner', CURRENT_TIMESTAMP)
        """, (FOUNDER_TENANT_ID, FOUNDER_EMAIL, FOUNDER_PLAN))

        # Audit log entry
        conn.execute("""
            INSERT INTO admin_audit_log (action, admin_identity, target_tenant, details)
            VALUES ('FOUNDER_ACCOUNT_CREATED', 'system_setup', ?, ?)
        """, (FOUNDER_TENANT_ID, json.dumps({
            "email": FOUNDER_EMAIL,
            "name": FOUNDER_NAME,
            "plan": FOUNDER_PLAN,
            "role": "owner",
            "billing_exempt": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })))

        conn.commit()
    log.info("  DONE: Founder subscription ACTIVE (billing_exempt=True, role=owner)")


# ─────────────────────────────────────────────────────────────────────────────
# 2. ASSISTANT FACTORY DB — enterprise founder assistant
# ─────────────────────────────────────────────────────────────────────────────

def setup_assistant_db():
    log.info(f"Assistant DB -> {ASSISTANT_DB}")
    with sqlite3.connect(str(ASSISTANT_DB)) as conn:
        # Ensure table exists (base schema)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assistants (
                assistant_id    TEXT PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                business_type   TEXT NOT NULL,
                display_name    TEXT,
                status          TEXT DEFAULT 'ACTIVE',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migrate: add config_json and status columns if not present
        _add_column_if_missing(conn, "assistants", "config_json", "TEXT")
        _add_column_if_missing(conn, "assistants", "status", "TEXT DEFAULT 'ACTIVE'")
        conn.commit()

        founder_config = {
            "role":               "owner",
            "plan":               FOUNDER_PLAN,
            "billing_exempt":     True,
            "specialists":        FOUNDER_SPECIALISTS,
            "templates":          FOUNDER_TEMPLATES,
            "features":           FOUNDER_FEATURES,
            "unlimited_tenants":  True,
            "unlimited_assistants": True,
            "admin_access":       True,
            "dashboard_access":   True,
        }

        conn.execute("""
            INSERT OR REPLACE INTO assistants
                (assistant_id, tenant_id, business_type, display_name, config_json, status)
            VALUES (?, ?, 'enterprise_founder', ?, ?, 'ACTIVE')
        """, (
            f"ast_founder_{FOUNDER_TENANT_ID}",
            FOUNDER_TENANT_ID,
            f"DM AI OS — Founder Assistant ({FOUNDER_NAME})",
            json.dumps(founder_config, ensure_ascii=False),
        ))

        conn.commit()
    log.info("  DONE: Founder enterprise assistant created with all specialists + templates")


# ─────────────────────────────────────────────────────────────────────────────
# 3. IDENTITY DB — user profile for 'daniel'
# ─────────────────────────────────────────────────────────────────────────────

def setup_identity_db():
    log.info(f"Identity DB -> {USERS_DB}")
    with sqlite3.connect(str(USERS_DB)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     TEXT PRIMARY KEY,
                name        TEXT,
                data_json   TEXT,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        profile_data = {
            "user_id":        "daniel",
            "name":           FOUNDER_NAME,
            "email":          FOUNDER_EMAIL,
            "role":           "owner",
            "plan":           FOUNDER_PLAN,
            "subscription":   "free",
            "billing_exempt": True,
            "tenant_id":      FOUNDER_TENANT_ID,
            "features":       FOUNDER_FEATURES,
            "specialists":    FOUNDER_SPECIALISTS,
            "templates":      FOUNDER_TEMPLATES,
            "preferences":    {
                "language": "es",
                "theme":    "dark",
                "timezone": "America/Argentina/Buenos_Aires",
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        conn.execute("""
            INSERT OR REPLACE INTO users (user_id, name, data_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, ("daniel", FOUNDER_NAME, json.dumps(profile_data, ensure_ascii=False)))

        conn.commit()
    log.info("  DONE: Identity profile updated: daniel -> owner/founder")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  DM AI OS -- FOUNDER ACCOUNT SETUP")
    print("="*60)
    print(f"  Tenant ID : {FOUNDER_TENANT_ID}")
    print(f"  Email     : {FOUNDER_EMAIL}")
    print(f"  Name      : {FOUNDER_NAME}")
    print(f"  Plan      : {FOUNDER_PLAN}")
    print(f"  Role      : owner")
    print(f"  Billing   : EXEMPT (free forever)")
    print("="*60 + "\n")

    errors = []

    try:
        setup_billing_db()
    except Exception as e:
        log.error(f"  ❌ Billing DB error: {e}")
        errors.append(("billing_db", str(e)))

    try:
        setup_assistant_db()
    except Exception as e:
        log.error(f"  ❌ Assistant DB error: {e}")
        errors.append(("assistant_db", str(e)))

    try:
        setup_identity_db()
    except Exception as e:
        log.error(f"  ❌ Identity DB error: {e}")
        errors.append(("identity_db", str(e)))

    print("\n" + "="*60)
    if not errors:
        print("  [OK] FOUNDER ACCOUNT CREATED SUCCESSFULLY")
        print()
        print("  Owner Login:")
        print("    URL      -> http://localhost:8000/panel/owner")
        print("    URL PROD -> https://app.dmorales.site/panel/owner")
        print("    Password -> (set in .env ADMIN_PASSWORD or default: dmorales2026-7)")
        print()
        print("  Dashboard:")
        print("    URL      -> http://localhost:8000/panel/dashboard")
        print("    URL PROD -> https://app.dmorales.site/panel/dashboard")
        print()
        print("  Tenant ID for API calls: founder_daniel")
        print("="*60 + "\n")
    else:
        print(f"  [!] COMPLETED WITH {len(errors)} ERROR(S):")
        for db, err in errors:
            print(f"     - {db}: {err}")
        print("="*60 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
