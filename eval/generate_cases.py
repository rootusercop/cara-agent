"""
Benchmark case generator for CARA evaluation.

Generates 500 annotated test cases covering all five categories:
  - schema_only  (100 cases)
  - api_only     (100 cases)
  - schema_and_api (150 cases)
  - multi_account  (100 cases)
  - complex        (50 cases)

Each case is deterministically constructed from a template library so the
ground truth is known exactly (no guessing, no LLM involvement).

Usage:
    python eval/generate_cases.py --count 500 --out eval/dataset
    python eval/generate_cases.py --count 500 --start-index 16 --out eval/dataset
"""

from __future__ import annotations

import argparse
import json
import random
import string
from pathlib import Path


# ---------------------------------------------------------------------------
# Template primitives
# ---------------------------------------------------------------------------

TABLES = [
    "accounts", "users", "subscriptions", "payments", "orders",
    "products", "entitlements", "invoices", "transactions", "sessions",
    "notifications", "memberships", "policies", "claims", "profiles",
    "addresses", "devices", "tokens", "webhooks", "audit_logs",
    "rewards", "referrals", "promotions", "discounts", "coupons",
    "shipments", "inventory", "warehouses", "suppliers", "contracts",
    "tickets", "incidents", "reports", "dashboards", "analytics",
]

SQL_TYPES = {
    "id": ("VARCHAR(36)", "UUID"),
    "name": ("VARCHAR(100)", "VARCHAR(255)"),
    "amount": ("INT", "BIGINT"),
    "price": ("DECIMAL(10,2)", "DECIMAL(15,4)"),
    "status": ("VARCHAR(20)", "VARCHAR(50)"),
    "email": ("VARCHAR(100)", "VARCHAR(255)"),
    "count": ("SMALLINT", "INT"),
    "score": ("FLOAT", "DOUBLE PRECISION"),
    "data": ("TEXT", "JSONB"),
    "flag": ("BOOLEAN", "TINYINT"),
}

SERVICES = [
    "billing-service", "account-service", "notification-service",
    "payment-service", "order-service", "subscription-service",
    "analytics-service", "auth-service", "gateway-service",
    "reporting-service", "invest-service", "lending-service",
    "insurance-service", "rewards-service", "member-service",
]

ACCOUNT_TYPES = ["STANDARD", "INVEST", "LENDING", "CREDIT", "BUSINESS", "PREMIUM"]

HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
VERSION_PAIRS = [("v1", "v2"), ("v2", "v3"), ("v1", "v3"), ("2024-01", "2024-06")]


def _rand_field(seed: int) -> str:
    r = random.Random(seed)
    return r.choice([
        "user_id", "account_id", "member_id", "customer_id",
        "amount", "total", "balance", "price", "fee",
        "status", "state", "type", "category", "tier",
        "created_at", "updated_at", "deleted_at", "expires_at",
        "name", "email", "phone", "address", "country",
        "is_active", "is_verified", "is_deleted", "enabled",
        "description", "notes", "metadata", "tags",
        "score", "rank", "count", "quantity", "limit",
    ])


def _rand_table(seed: int) -> str:
    return random.Random(seed).choice(TABLES)


def _rand_service(seed: int) -> str:
    return random.Random(seed).choice(SERVICES)


def _rand_services(seed: int, n: int = 2) -> list[str]:
    r = random.Random(seed)
    return r.sample(SERVICES, min(n, len(SERVICES)))


# ---------------------------------------------------------------------------
# Schema-only case builders
# ---------------------------------------------------------------------------

def _make_schema_field_rename(idx: int) -> dict:
    """BREAKING: rename a column."""
    t = _rand_table(idx)
    old_f = _rand_field(idx)
    new_f = _rand_field(idx + 1000)
    while new_f == old_f:
        new_f = _rand_field(idx + 2000)

    old_sql = f"""CREATE TABLE {t} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    {old_f}     VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    {new_f}     VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    return {
        "category": "schema_only",
        "description": f"Column '{old_f}' renamed to '{new_f}' in the '{t}' table.",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 2,
            "api_change_count": 0,
            "breaking_change_count": 1,
            "safe_change_count": 1,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_schema_nullable_add(idx: int) -> dict:
    """SAFE: add a nullable column."""
    t = _rand_table(idx)
    new_f = _rand_field(idx + 500)
    old_sql = f"""CREATE TABLE {t} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    {new_f}     VARCHAR(255),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    return {
        "category": "schema_only",
        "description": f"Nullable column '{new_f}' added to '{t}' table (safe change).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 0,
            "breaking_change_count": 0,
            "safe_change_count": 1,
            "plan_must_include_expand": False,
            "plan_must_include_rollback": True,
            "requires_adapter": False,
            "minimum_plan_steps": 2,
        },
    }


def _make_schema_not_null_no_default(idx: int) -> dict:
    """BREAKING: add NOT NULL column without DEFAULT."""
    t = _rand_table(idx)
    new_f = _rand_field(idx + 700)
    old_sql = f"""CREATE TABLE {t} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    amount      DECIMAL(10,2) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    amount      DECIMAL(10,2) NOT NULL,
    {new_f}     VARCHAR(50) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    return {
        "category": "schema_only",
        "description": f"NOT NULL column '{new_f}' added to '{t}' without a DEFAULT (breaking).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 0,
            "breaking_change_count": 1,
            "safe_change_count": 0,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_schema_column_removal(idx: int) -> dict:
    """BREAKING: remove a column."""
    t = _rand_table(idx)
    old_f = _rand_field(idx + 300)
    old_sql = f"""CREATE TABLE {t} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    {old_f}     VARCHAR(100),
    email       VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    return {
        "category": "schema_only",
        "description": f"Column '{old_f}' removed from '{t}' table (breaking for consumers).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 0,
            "breaking_change_count": 1,
            "safe_change_count": 0,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_schema_type_widen(idx: int) -> dict:
    """SAFE: widen a column type (INT -> BIGINT, VARCHAR(100) -> VARCHAR(255))."""
    t = _rand_table(idx)
    pairs = [("INT", "BIGINT"), ("SMALLINT", "INT"), ("VARCHAR(100)", "VARCHAR(255)"),
             ("DECIMAL(10,2)", "DECIMAL(15,4)"), ("FLOAT", "DOUBLE PRECISION")]
    old_type, new_type = pairs[idx % len(pairs)]
    col = _rand_field(idx + 400)
    old_sql = f"""CREATE TABLE {t} (
    id    VARCHAR(36) NOT NULL PRIMARY KEY,
    {col} {old_type} NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t} (
    id    VARCHAR(36) NOT NULL PRIMARY KEY,
    {col} {new_type} NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    return {
        "category": "schema_only",
        "description": f"Column '{col}' type widened from {old_type} to {new_type} in '{t}' (safe widening).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 0,
            "breaking_change_count": 0,
            "safe_change_count": 1,
            "plan_must_include_expand": False,
            "plan_must_include_rollback": True,
            "requires_adapter": False,
            "minimum_plan_steps": 2,
        },
    }


def _make_schema_type_narrow(idx: int) -> dict:
    """BREAKING: narrow a column type."""
    t = _rand_table(idx)
    pairs = [("BIGINT", "INT"), ("VARCHAR(255)", "VARCHAR(100)"),
             ("DECIMAL(15,4)", "DECIMAL(10,2)"), ("DOUBLE PRECISION", "FLOAT")]
    old_type, new_type = pairs[idx % len(pairs)]
    col = _rand_field(idx + 600)
    old_sql = f"""CREATE TABLE {t} (
    id    VARCHAR(36) NOT NULL PRIMARY KEY,
    {col} {old_type} NOT NULL
);"""
    new_sql = f"""CREATE TABLE {t} (
    id    VARCHAR(36) NOT NULL PRIMARY KEY,
    {col} {new_type} NOT NULL
);"""
    return {
        "category": "schema_only",
        "description": f"Column '{col}' type narrowed from {old_type} to {new_type} in '{t}' (breaking).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 0,
            "breaking_change_count": 1,
            "safe_change_count": 0,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_schema_multi_column_rename(idx: int) -> dict:
    """BREAKING: rename two columns simultaneously."""
    t = _rand_table(idx)
    old1, old2 = _rand_field(idx), _rand_field(idx + 100)
    new1, new2 = _rand_field(idx + 200), _rand_field(idx + 300)
    old_sql = f"""CREATE TABLE {t} (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    {old1}  VARCHAR(100),
    {old2}  VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t} (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    {new1}  VARCHAR(100),
    {new2}  VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    return {
        "category": "schema_only",
        "description": f"Two columns renamed in '{t}': '{old1}' -> '{new1}', '{old2}' -> '{new2}'.",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 4,
            "api_change_count": 0,
            "breaking_change_count": 2,
            "safe_change_count": 2,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 5,
        },
    }


SCHEMA_BUILDERS = [
    _make_schema_field_rename,
    _make_schema_nullable_add,
    _make_schema_not_null_no_default,
    _make_schema_column_removal,
    _make_schema_type_widen,
    _make_schema_type_narrow,
    _make_schema_multi_column_rename,
]


# ---------------------------------------------------------------------------
# API-only case builders
# ---------------------------------------------------------------------------

def _openapi_stub(version: str, path: str, field: str, method: str = "GET") -> str:
    return f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{version}"
paths:
  {path}:
    {method.lower()}:
      summary: Endpoint
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {field}: {{type: string}}
                  id: {{type: string}}
"""


def _make_api_endpoint_rename(idx: int) -> dict:
    """BREAKING: rename endpoint path."""
    old_v, new_v = VERSION_PAIRS[idx % len(VERSION_PAIRS)]
    res = _rand_table(idx).rstrip("s")  # singular
    old_path = f"/{old_v}/{res}s"
    new_path = f"/{new_v}/{res}s"
    field = _rand_field(idx + 100)
    return {
        "category": "api_only",
        "description": f"Endpoint path changed from '{old_path}' to '{new_path}'.",
        "old_api": _openapi_stub(old_v, old_path, field),
        "new_api": _openapi_stub(new_v, new_path, field),
        "expected": {
            "schema_change_count": 0,
            "api_change_count": 2,
            "breaking_change_count": 1,
            "safe_change_count": 1,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_api_response_field_add(idx: int) -> dict:
    """SAFE: add a response field."""
    v = "1.0"
    path = f"/api/{_rand_table(idx)}"
    old_f = _rand_field(idx)
    new_f = _rand_field(idx + 500)
    old_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    get:
      summary: Endpoint
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {old_f}: {{type: string}}
"""
    new_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    get:
      summary: Endpoint
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {old_f}: {{type: string}}
                  {new_f}: {{type: string}}
"""
    return {
        "category": "api_only",
        "description": f"Response field '{new_f}' added to '{path}' (safe, additive change).",
        "old_api": old_spec,
        "new_api": new_spec,
        "expected": {
            "schema_change_count": 0,
            "api_change_count": 1,
            "breaking_change_count": 0,
            "safe_change_count": 1,
            "plan_must_include_expand": False,
            "plan_must_include_rollback": True,
            "requires_adapter": False,
            "minimum_plan_steps": 2,
        },
    }


def _make_api_request_field_removal(idx: int) -> dict:
    """BREAKING: remove a required request field."""
    v = "1.0"
    path = f"/api/{_rand_table(idx)}"
    old_f = _rand_field(idx + 200)
    old_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    post:
      summary: Create
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [{old_f}, name]
              properties:
                {old_f}: {{type: string}}
                name: {{type: string}}
      responses:
        "201":
          description: Created
"""
    new_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    post:
      summary: Create
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name: {{type: string}}
      responses:
        "201":
          description: Created
"""
    return {
        "category": "api_only",
        "description": f"Required request field '{old_f}' removed from POST '{path}' (breaking).",
        "old_api": old_spec,
        "new_api": new_spec,
        "expected": {
            "schema_change_count": 0,
            "api_change_count": 1,
            "breaking_change_count": 1,
            "safe_change_count": 0,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_api_response_field_removal(idx: int) -> dict:
    """BREAKING: remove a response field."""
    v = "1.0"
    path = f"/api/{_rand_table(idx)}"
    old_f = _rand_field(idx + 300)
    kept_f = _rand_field(idx + 400)
    old_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    get:
      summary: Get
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {kept_f}: {{type: string}}
                  {old_f}: {{type: string}}
"""
    new_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    get:
      summary: Get
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {kept_f}: {{type: string}}
"""
    return {
        "category": "api_only",
        "description": f"Response field '{old_f}' removed from GET '{path}' (breaking for consumers).",
        "old_api": old_spec,
        "new_api": new_spec,
        "expected": {
            "schema_change_count": 0,
            "api_change_count": 1,
            "breaking_change_count": 1,
            "safe_change_count": 0,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_api_response_type_change(idx: int) -> dict:
    """BREAKING: change response field type."""
    v = "1.0"
    path = f"/api/{_rand_table(idx)}"
    field = _rand_field(idx + 600)
    old_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    get:
      summary: Get
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {field}: {{type: integer}}
"""
    new_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    get:
      summary: Get
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {field}: {{type: string}}
"""
    return {
        "category": "api_only",
        "description": f"Response field '{field}' type changed from integer to string in GET '{path}' (breaking).",
        "old_api": old_spec,
        "new_api": new_spec,
        "expected": {
            "schema_change_count": 0,
            "api_change_count": 1,
            "breaking_change_count": 1,
            "safe_change_count": 0,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_api_multiple_fields_add(idx: int) -> dict:
    """SAFE: add two response fields."""
    v = "1.0"
    path = f"/api/{_rand_table(idx)}"
    base_f = _rand_field(idx)
    new_f1 = _rand_field(idx + 700)
    new_f2 = _rand_field(idx + 800)
    old_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {base_f}: {{type: string}}
"""
    new_spec = f"""openapi: "3.0.0"
info:
  title: Service API
  version: "{v}"
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {base_f}: {{type: string}}
                  {new_f1}: {{type: string}}
                  {new_f2}: {{type: string}}
"""
    return {
        "category": "api_only",
        "description": f"Two response fields '{new_f1}' and '{new_f2}' added to '{path}' (safe).",
        "old_api": old_spec,
        "new_api": new_spec,
        "expected": {
            "schema_change_count": 0,
            "api_change_count": 2,
            "breaking_change_count": 0,
            "safe_change_count": 2,
            "plan_must_include_expand": False,
            "plan_must_include_rollback": True,
            "requires_adapter": False,
            "minimum_plan_steps": 2,
        },
    }


API_BUILDERS = [
    _make_api_endpoint_rename,
    _make_api_response_field_add,
    _make_api_request_field_removal,
    _make_api_response_field_removal,
    _make_api_response_type_change,
    _make_api_multiple_fields_add,
]


# ---------------------------------------------------------------------------
# Combined schema + API case builders
# ---------------------------------------------------------------------------

def _make_combined_field_rename(idx: int) -> dict:
    """BREAKING: field rename propagated to both schema and API."""
    t = _rand_table(idx)
    old_f = _rand_field(idx)
    new_f = _rand_field(idx + 1000)
    while new_f == old_f:
        new_f = _rand_field(idx + 2000)
    path = f"/api/{t}"
    old_sql = f"""CREATE TABLE {t} (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    {old_f} VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t} (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    {new_f} VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    old_api = f"""openapi: "3.0.0"
info: {{title: API, version: "1.0"}}
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {old_f}: {{type: string}}
"""
    new_api = f"""openapi: "3.0.0"
info: {{title: API, version: "1.0"}}
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {new_f}: {{type: string}}
"""
    return {
        "category": "schema_and_api",
        "description": f"Field '{old_f}' renamed to '{new_f}' in both schema and API for '{t}'.",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "old_api": old_api,
        "new_api": new_api,
        "expected": {
            "schema_change_count": 2,
            "api_change_count": 2,
            "breaking_change_count": 2,
            "safe_change_count": 2,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 5,
        },
    }


def _make_combined_safe_addition(idx: int) -> dict:
    """SAFE: add optional field to both schema and API."""
    t = _rand_table(idx)
    new_f = _rand_field(idx + 500)
    path = f"/api/{t}"
    old_sql = f"""CREATE TABLE {t} (
    id    VARCHAR(36) NOT NULL PRIMARY KEY,
    name  VARCHAR(100) NOT NULL
);"""
    new_sql = f"""CREATE TABLE {t} (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    name    VARCHAR(100) NOT NULL,
    {new_f} VARCHAR(255)
);"""
    old_api = f"""openapi: "3.0.0"
info: {{title: API, version: "1.0"}}
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {{type: string}}
                  name: {{type: string}}
"""
    new_api = f"""openapi: "3.0.0"
info: {{title: API, version: "1.0"}}
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {{type: string}}
                  name: {{type: string}}
                  {new_f}: {{type: string}}
"""
    return {
        "category": "schema_and_api",
        "description": f"Optional field '{new_f}' added to both schema and API for '{t}' (safe).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "old_api": old_api,
        "new_api": new_api,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 1,
            "breaking_change_count": 0,
            "safe_change_count": 2,
            "plan_must_include_expand": False,
            "plan_must_include_rollback": True,
            "requires_adapter": False,
            "minimum_plan_steps": 2,
        },
    }


def _make_combined_type_cascade(idx: int) -> dict:
    """BREAKING: schema type change cascades to API response type."""
    t = _rand_table(idx)
    col = _rand_field(idx + 300)
    path = f"/api/{t}"
    old_sql = f"""CREATE TABLE {t} (
    id   VARCHAR(36) NOT NULL PRIMARY KEY,
    {col} INT NOT NULL
);"""
    new_sql = f"""CREATE TABLE {t} (
    id   VARCHAR(36) NOT NULL PRIMARY KEY,
    {col} BIGINT NOT NULL
);"""
    old_api = f"""openapi: "3.0.0"
info: {{title: API, version: "1.0"}}
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {col}: {{type: integer, format: int32}}
"""
    new_api = f"""openapi: "3.0.0"
info: {{title: API, version: "1.0"}}
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {col}: {{type: integer, format: int64}}
"""
    return {
        "category": "schema_and_api",
        "description": f"Column '{col}' widened INT->BIGINT in schema, API format updated int32->int64.",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "old_api": old_api,
        "new_api": new_api,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 1,
            "breaking_change_count": 2,
            "safe_change_count": 0,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


COMBINED_BUILDERS = [
    _make_combined_field_rename,
    _make_combined_safe_addition,
    _make_combined_type_cascade,
]


# ---------------------------------------------------------------------------
# Multi-account case builders
# ---------------------------------------------------------------------------

def _make_multi_account_selective_removal(idx: int) -> dict:
    """BREAKING for one account type: remove a field used only by one account type."""
    t = _rand_table(idx)
    acct = ACCOUNT_TYPES[idx % len(ACCOUNT_TYPES)]
    old_f = _rand_field(idx + 200)
    old_sql = f"""CREATE TABLE {t} (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    {old_f}      DECIMAL(15,4),
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t} (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    return {
        "category": "multi_account",
        "description": (
            f"Field '{old_f}' removed from '{t}'. "
            f"Only {acct} account consumers are impacted."
        ),
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 0,
            "breaking_change_count": 1,
            "safe_change_count": 0,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 4,
        },
    }


def _make_multi_account_safe_add(idx: int) -> dict:
    """SAFE: add an account_type-gated field."""
    t = _rand_table(idx)
    new_f = _rand_field(idx + 600)
    acct = ACCOUNT_TYPES[(idx + 2) % len(ACCOUNT_TYPES)]
    old_sql = f"""CREATE TABLE {t} (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL
);"""
    new_sql = f"""CREATE TABLE {t} (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    {new_f}      VARCHAR(100) DEFAULT NULL
);"""
    return {
        "category": "multi_account",
        "description": f"Nullable field '{new_f}' added for {acct} account type (safe).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 1,
            "api_change_count": 0,
            "breaking_change_count": 0,
            "safe_change_count": 1,
            "plan_must_include_expand": False,
            "plan_must_include_rollback": True,
            "requires_adapter": False,
            "minimum_plan_steps": 2,
        },
    }


MULTI_ACCOUNT_BUILDERS = [
    _make_multi_account_selective_removal,
    _make_multi_account_safe_add,
]


# ---------------------------------------------------------------------------
# Complex case builders
# ---------------------------------------------------------------------------

def _make_complex_multi_field_rename(idx: int) -> dict:
    """BREAKING: three fields renamed in both schema and API."""
    t = _rand_table(idx)
    pairs = [
        (_rand_field(idx), _rand_field(idx + 100)),
        (_rand_field(idx + 200), _rand_field(idx + 300)),
        (_rand_field(idx + 400), _rand_field(idx + 500)),
    ]
    path = f"/api/{t}"
    old_cols = "\n    ".join(f"{o}  VARCHAR(100)" for o, _ in pairs)
    new_cols = "\n    ".join(f"{n}  VARCHAR(100)" for _, n in pairs)
    old_sql = f"CREATE TABLE {t} (\n    id  VARCHAR(36) NOT NULL PRIMARY KEY,\n    {old_cols}\n);"
    new_sql = f"CREATE TABLE {t} (\n    id  VARCHAR(36) NOT NULL PRIMARY KEY,\n    {new_cols}\n);"

    old_props = "\n                  ".join(f"{o}: {{type: string}}" for o, _ in pairs)
    new_props = "\n                  ".join(f"{n}: {{type: string}}" for _, n in pairs)
    old_api = f"""openapi: "3.0.0"
info: {{title: API, version: "1.0"}}
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {old_props}
"""
    new_api = f"""openapi: "3.0.0"
info: {{title: API, version: "1.0"}}
paths:
  {path}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  {new_props}
"""
    return {
        "category": "complex",
        "description": f"Three fields renamed simultaneously in '{t}' schema and API (phased migration required).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "old_api": old_api,
        "new_api": new_api,
        "expected": {
            "schema_change_count": 6,
            "api_change_count": 6,
            "breaking_change_count": 6,
            "safe_change_count": 6,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 5,
        },
    }


def _make_complex_table_split(idx: int) -> dict:
    """BREAKING: split one table into two."""
    base = _rand_table(idx)
    t1 = f"{base}_core"
    t2 = f"{base}_extended"
    old_sql = f"""CREATE TABLE {base} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    metadata    JSONB,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""
    new_sql = f"""CREATE TABLE {t1} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE {t2} (
    id          VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES {t1}(id),
    description TEXT,
    metadata    JSONB
);"""
    return {
        "category": "complex",
        "description": f"Table '{base}' split into '{t1}' (core) and '{t2}' (extended).",
        "old_schema": old_sql,
        "new_schema": new_sql,
        "expected": {
            "schema_change_count": 3,
            "api_change_count": 0,
            "breaking_change_count": 1,
            "safe_change_count": 2,
            "plan_must_include_expand": True,
            "plan_must_include_rollback": True,
            "requires_adapter": True,
            "minimum_plan_steps": 5,
        },
    }


COMPLEX_BUILDERS = [
    _make_complex_multi_field_rename,
    _make_complex_table_split,
]


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

CATEGORY_CONFIG = {
    "schema_only":   (100, SCHEMA_BUILDERS),
    "api_only":      (100, API_BUILDERS),
    "schema_and_api": (150, COMBINED_BUILDERS),
    "multi_account": (100, MULTI_ACCOUNT_BUILDERS),
    "complex":        (50, COMPLEX_BUILDERS),
}


def generate_cases(count: int = 500, start_index: int = 16) -> list[dict]:
    """Generate `count` benchmark cases starting at case number `start_index`."""
    cases = []
    idx = start_index

    # Distribute across categories proportionally
    total_target = count
    category_counts = {}
    remaining = total_target
    cats = list(CATEGORY_CONFIG.keys())
    for i, cat in enumerate(cats):
        natural, _ = CATEGORY_CONFIG[cat]
        frac = natural / sum(n for n, _ in CATEGORY_CONFIG.values())
        if i == len(cats) - 1:
            category_counts[cat] = remaining
        else:
            n = max(1, round(total_target * frac))
            category_counts[cat] = n
            remaining -= n

    for cat in cats:
        _, builders = CATEGORY_CONFIG[cat]
        n = category_counts[cat]
        for i in range(n):
            builder = builders[i % len(builders)]
            spec = builder(idx * 13 + i * 7)  # deterministic seeds
            case = {
                "case_id": f"case_{idx:03d}",
                "title": spec["description"][:80],
                "category": spec["category"],
                "description": spec["description"],
                "expected": spec["expected"],
            }
            cases.append({
                "case_id": f"case_{idx:03d}",
                "spec": spec,
                "ground_truth": {k: v for k, v in case.items()},
            })
            idx += 1

    return cases


def write_cases(cases: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for entry in cases:
        case_id = entry["case_id"]
        spec = entry["spec"]
        gt = entry["ground_truth"]
        case_dir = out_dir / case_id
        case_dir.mkdir(exist_ok=True)

        if "old_schema" in spec and spec["old_schema"]:
            (case_dir / "old_schema.sql").write_text(spec["old_schema"])
            (case_dir / "new_schema.sql").write_text(spec["new_schema"])
        if "old_api" in spec and spec["old_api"]:
            (case_dir / "old_api.yaml").write_text(spec["old_api"])
            (case_dir / "new_api.yaml").write_text(spec["new_api"])

        (case_dir / "ground_truth.json").write_text(
            json.dumps(gt, indent=2)
        )

    print(f"Wrote {len(cases)} cases to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CARA benchmark cases")
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--start-index", type=int, default=16)
    parser.add_argument("--out", default="eval/dataset")
    args = parser.parse_args()

    cases = generate_cases(count=args.count, start_index=args.start_index)
    write_cases(cases, Path(args.out))


if __name__ == "__main__":
    main()
