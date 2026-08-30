"""E2E-тесты рефакторинга доставки.

Запуск:
    pip install -r e2e_tests/requirements.txt
    pytest e2e_tests -v                     # быстрый набор
    E2E_RUN_SLOW=1 pytest e2e_tests -v      # + авто-отмена 72h (долгий)

Все маршруты выверены по openapi-6.json из релиза gateway.
"""
import os
import subprocess
import uuid

import httpx
import pytest

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost").rstrip("/")
API = f"{BASE_URL}/api/v1"

DB_CONTAINER = os.getenv("E2E_DB_CONTAINER", "ci-db-1")
GW_CONTAINER = os.getenv("E2E_GW_CONTAINER", "ci-gateway-1")

ADMIN_EMAIL = os.getenv("E2E_ADMIN_EMAIL", "admin@crate.market")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "admin123")
PASSWORD = "E2e!Passw0rd#2026"

RUN_SLOW = os.getenv("E2E_RUN_SLOW", "") == "1"

# ─────────────── маршруты (выверено по openapi) ───────────────
P = {
    "register": "/auth/register",
    "login": "/auth/login",
    "me": "/auth/me",
    # addresses
    "addresses": "/addresses",
    "address_delete": "/addresses/{id}",
    # shipping
    "shipping_calculate": "/shipping/calculate",
    "shipping_points": "/shipping/points",
    "handover": "/shipping/orders/{id}/dispatch",  # 🔑 dispatch вместо handover
    # economy
    "checkout": "/orders/checkout",
    "order": "/orders/{id}",
    "payment_methods": "/orders/payment-methods",
    # listings
    "listing_create": "/listings/free",  # 🔑 свободный листинг (FreeListingCreate)
    # seller requests
    "seller_apply": "/auth/requests/me/request-seller",  # 🔑 без requestBody
    "admin_requests": "/auth/requests/seller",
    "admin_approve": "/auth/requests/{id}/approve",
    # reviews
    "review": "/sellers/{id}/reviews",
}


# ─────────────── хелперы окружения ───────────────
def docker_exec(container, *cmd, check=True):
    return subprocess.run(
        ["docker", "exec", container, *cmd],
        capture_output=True, text=True, check=check,
    )


def sql(db: str, query: str) -> str:
    r = docker_exec(DB_CONTAINER, "psql", "-U", "postgres", "-d", db, "-tAc", query)
    return r.stdout.strip()


class Api:
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
    r = a.post(P["register"], json={"email": email, "password": PASSWORD})
    assert r.status_code in (200, 201, 202, 409), f"register: {r.status_code} {r.text}"


def login(email: str, password: str = PASSWORD) -> Api:
    a = Api()
    r = a.post(P["login"], json={"email": email, "password": password})
    if r.status_code in (404, 422):
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
        "recipient_name": "E2E User",
        "phone": "+7 999 000-00-00",
        "latitude": 55.760,
        "longitude": 37.605,
    }
    r = api.post(P["addresses"], json=body)
    assert r.status_code in (200, 201), f"address: {r.status_code} {r.text}"
    return r.json()


def make_seller(with_apartment: bool = True) -> Api:
    """Регистрирует пользователя, подаёт заявку продавца и активирует её через админа."""
    user = register_login()
    # Создаем адрес (он понадобится для логистики)
    make_address(user, apartment="12" if with_apartment else None)
    
    # Подаем заявку БЕЗ тела (в openapi нет requestBody)
    r = user.post(P["seller_apply"])
    assert r.status_code in (200, 201, 202), f"seller_apply: {r.status_code} {r.text}"
    
    approve_last_seller_request()
    
    # 🔑 КРИТИЧНО: после approve роль в БД обновилась, но JWT содержит старую роль "user"
    # Делаем refresh для получения нового токена с ролью "seller"
    r_refresh = user.post("/auth/refresh")
    assert r_refresh.status_code == 200, f"refresh: {r_refresh.status_code} {r_refresh.text}"
    new_token = r_refresh.json().get("access_token")
    assert new_token, f"refresh не вернул access_token: {r_refresh.text}"
    
    # Возвращаем Api с обновлённым токеном
    return Api(new_token)


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
    # 🔑 ИСПРАВЛЕНО: FreeListingCreate требует artist и year
    r = seller.post(
        P["listing_create"],
        json={
            "title": f"Vinyl E2E {uuid.uuid4().hex[:6]}",
            "artist": "E2E Artist",
            "year": 2024,
            "condition": "M",
            "price": float(price),
            "description": "test pressing",
            "genre": "Rock",
            "format": "Vinyl",
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
    try:
        r = docker_exec(GW_CONTAINER, "curl", "-s", "http://localhost:8000/openapi.json")
        import json
        return json.loads(r.stdout).get("paths", {})
    except Exception:
        return {}