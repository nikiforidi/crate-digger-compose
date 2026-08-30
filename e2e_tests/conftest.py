"""E2E-тесты рефакторинга доставки.

Запуск:
    pip install -r e2e_tests/requirements.txt
    pytest e2e_tests -v                     # быстрый набор
    E2E_RUN_SLOW=1 pytest e2e_tests -v      # + авто-отмена 72h (долгий)

Все маршруты — в словаре P. Если роут отличается — правим только там.
Проверки в БД идут через `docker exec <db> psql` (порты БД наружу не проброшены).
"""
import os
import subprocess
import uuid

import httpx
import pytest

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost").rstrip("/")
API = f"{BASE_URL}/api/v1"

DB_CONTAINER = os.getenv("E2E_DB_CONTAINER", "crate-digger-compose-db-1")
GW_CONTAINER = os.getenv("E2E_GW_CONTAINER", "crate-digger-compose-gateway-1")

ADMIN_EMAIL = os.getenv("E2E_ADMIN_EMAIL", "admin@crate.market")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "admin123")
PASSWORD = "E2e!Passw0rd#2026"

RUN_SLOW = os.getenv("E2E_RUN_SLOW", "") == "1"

# ─────────────── маршруты (единственная точка правки) ───────────────
P = {
    "register": "/auth/register",
    "login": "/auth/login",
    "me": "/auth/me",
    # адреса покупателя/продавца
    "addresses": "/addresses",
    "address_delete": "/addresses/{id}",
    # логистика
    "shipping_calculate": "/shipping/calculate",
    "shipping_points": "/shipping/points",
    "handover": "/shipping/orders/{id}/handover",  # «Отнесу в ПВЗ сам»
    # economy
    "checkout": "/orders/checkout",
    "order": "/orders/{id}",
    "payment_methods": "/orders/payment-methods",
    # marketplace
    "listing_create": "/listings",
    "seller_apply": "/sellers/apply",
    "admin_requests": "/admin/seller-requests",
    "admin_approve": "/admin/seller-requests/{id}/approve",
    # review-service
    "review": "/sellers/{id}/reviews",
}


# ─────────────── хелперы окружения ───────────────
def docker_exec(container, *cmd, check=True):
    return subprocess.run(
        ["docker", "exec", container, *cmd],
        capture_output=True, text=True, check=check,
    )


def sql(db: str, query: str) -> str:
    """SQL в БД стека (economy_db / logistics_db / marketplace_db / auth_db)."""
    r = docker_exec(DB_CONTAINER, "psql", "-U", "postgres", "-d", db, "-tAc", query)
    return r.stdout.strip()


class Api:
    """Тонкий клиент gateway с токеном."""

    def __init__(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.c = httpx.Client(base_url=API, timeout=60, headers=headers)
        self.token = token

    def get(self, path, **kw):
        return self.c.get(path.format(**kw.pop("fmt", {})), **kw)

    def post(self, path, **kw):
        fmt = kw.pop("fmt", {})
        return self.c.post(path.format(**fmt), **kw)

    def delete(self, path, **kw):
        fmt = kw.pop("fmt", {})
        return self.c.delete(path.format(**fmt), **kw)


# ─────────────── auth ───────────────
def new_credentials():
    return f"e2e-{uuid.uuid4().hex[:10]}@crate.market", PASSWORD


def register(email: str):
    a = Api()
    r = a.post(P["register"], json={"email": email, "password": PASSWORD, "full_name": "E2E"})
    assert r.status_code in (200, 201, 202, 409), f"register: {r.status_code} {r.text}"


def login(email: str, password: str = PASSWORD) -> Api:
    a = Api()
    r = a.post(P["login"], json={"email": email, "password": password})
    if r.status_code in (404, 422):  # OAuth2 form fallback
        r = a.post(P["login"], data={"username": email, "password": password})
    assert r.status_code == 200, f"login({email}): {r.status_code} {r.text}"
    token = r.json().get("access_token")
    assert token, f"login({email}): нет access_token в ответе: {r.text}"
    return Api(token)


def register_login() -> Api:
    email, _ = new_credentials()
    register(email)
    return login(email)


# ─────────────── адреса / продавцы / лоты ───────────────
def make_address(api: Api, apartment=None) -> dict:
    body = {
        "city": "Москва",
        "street": "Тверская",
        "house": "7",
        "apartment": apartment,
        "latitude": 55.760,
        "longitude": 37.605,
        "address_string": "Москва, Тверская, 7",
    }
    r = api.post(P["addresses"], json=body)
    assert r.status_code in (200, 201), f"address: {r.status_code} {r.text}"
    return r.json()


def make_seller(with_apartment: bool = True) -> Api:
    """Регистрирует пользователя, подаёт заявку продавца и активирует её через админа."""
    user = register_login()
    addr = make_address(user, apartment="12" if with_apartment else None)
    r = user.post(
        P["seller_apply"],
        json={
            "address_id": addr["id"],
            "recipient_name": "E2E Seller",
            "recipient_phone": "+7 999 000-00-00",
        },
    )
    assert r.status_code in (200, 201), f"seller_apply: {r.status_code} {r.text}"
    approve_last_seller_request()
    return user


def approve_last_seller_request():
    admin = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    r = admin.get(P["admin_requests"])
    assert r.status_code == 200, f"admin_requests: {r.status_code} {r.text}"
    items = r.json()
    items = items.get("items", items) if isinstance(items, dict) else items
    assert items, "admin_requests: список заявок пуст"
    req = items[-1]
    r2 = admin.post(P["admin_approve"], fmt={"id": req["id"]})
    assert r2.status_code in (200, 201), f"admin_approve: {r2.status_code} {r2.text}"


def make_listing(seller: Api, price: int = 1500) -> dict:
    r = seller.post(
        P["listing_create"],
        json={
            "title": f"Vinyl E2E {uuid.uuid4().hex[:6]}",
            "description": "test pressing",
            "price": price,
            "category": "vinyl",
            "condition": "M",
            "city": "Москва",
        },
    )
    assert r.status_code in (200, 201), f"listing: {r.status_code} {r.text}"
    return r.json()


# ─────────────── фикстуры ───────────────
@pytest.fixture()
def buyer() -> Api:
    return register_login()


@pytest.fixture(scope="session")
def seller_a() -> Api:
    return make_seller(with_apartment=True)


@pytest.fixture(scope="session")
def seller_b() -> Api:
    return make_seller(with_apartment=True)


@pytest.fixture(scope="session")
def listing_a(seller_a) -> dict:
    return make_listing(seller_a, price=1500)


@pytest.fixture(scope="session")
def listing_b(seller_b) -> dict:
    return make_listing(seller_b, price=2000)


@pytest.fixture(scope="session")
def gw_openapi() -> dict:
    """Реальные маршруты gateway — для калибровки словаря P."""
    try:
        r = docker_exec(GW_CONTAINER, "curl", "-s", "http://localhost:8000/openapi.json")
        import json

        return json.loads(r.stdout).get("paths", {})
    except Exception:
        return {}