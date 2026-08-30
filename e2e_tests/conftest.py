"""E2E-тесты рефакторинга доставки.

Контракт (по реальному коду economy-service):
- POST /orders/checkout принимает ОДИН объект `shipping` на весь заказ;
- сплит по продавцам делает сама экономика после оплаты
  (по одной строке shipping_orders на продавца).

Запуск:
    pytest e2e_tests -v                     # быстрый набор
    E2E_RUN_SLOW=1 pytest e2e_tests -v      # + авто-отмена 72h
"""
import base64
import os
import subprocess
import uuid

import httpx
import pytest

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost").rstrip("/")
API = f"{BASE_URL}/api/v1"

DB_CONTAINER = os.getenv("E2E_DB_CONTAINER", "ci-db-1")
GW_CONTAINER = os.getenv("E2E_GW_CONTAINER", "ci-gateway-1")
ECONOMY_CONTAINER = os.getenv("E2E_ECONOMY_CONTAINER", "ci-economy-service-1")

ADMIN_EMAIL = os.getenv("E2E_ADMIN_EMAIL", "admin@crate.market")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "admin123")
PASSWORD = "E2e!Passw0rd#2026"

RUN_SLOW = os.getenv("E2E_RUN_SLOW", "") == "1"

# 1x1 PNG для обложки листинга
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

# ─────────────── маршруты (выверено по openapi gateway) ───────────────
P = {
    "register": "/auth/register",
    "login": "/auth/login",
    "me": "/auth/me",
    "refresh": "/auth/refresh",
    # адреса
    "addresses": "/addresses",
    "address_delete": "/addresses/{id}",
    # логистика
    "shipping_calculate": "/shipping/calculate",
    "shipping_points": "/shipping/points",
    "handover": "/shipping/orders/{id}/dispatch",
    # economy
    "checkout": "/orders/checkout",
    "order": "/orders/{id}",
    "payment_mock": "/payments/mock/simulate-payment",
    # листинги
    "listing_create": "/listings/free",
    "listing_get": "/listings/{id}",
    "listing_cover": "/listings/{id}/cover",
    "listing_audio_status": "/listings/{id}/audio-status",
    "listing_moderate": "/listings/{id}/moderate",
    "listing_submit": "/listings/{id}/submit-for-moderation",
    # продавцы
    "seller_apply": "/auth/requests/me/request-seller",
    "admin_requests": "/auth/requests/seller",
    "admin_approve": "/auth/requests/{id}/approve",
    # отзывы
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


def trigger_auto_cancel() -> str:
    """Детерминированный запуск авто-отмены внутри контейнера экономики
    (фоновый цикл спит 3600с, ждать его в тестах нереально)."""
    script = (
        "import asyncio\n"
        "from app.database import AsyncSessionLocal\n"
        "from app.jobs.auto_cancel import auto_cancel_unshipped\n"
        "async def main():\n"
        "    async with AsyncSessionLocal() as db:\n"
        "        print(await auto_cancel_unshipped(db))\n"
        "asyncio.run(main())\n"
    )
    r = docker_exec(ECONOMY_CONTAINER, "python", "-c", script)
    return r.stdout.strip()


class Api:
    def __init__(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.c = httpx.Client(base_url=API, timeout=60, headers=headers)
        self.token = token
        self._profile = None

    def get(self, path, **kw):
        return self.c.get(path.format(**kw.pop("fmt", {})), **kw)

    def post(self, path, **kw):
        fmt = kw.pop("fmt", {})
        return self.c.post(path.format(**fmt), **kw)

    def delete(self, path, **kw):
        fmt = kw.pop("fmt", {})
        return self.c.delete(path.format(**fmt), **kw)

    @property
    def profile(self):
        if self._profile is None and self.token:
            r = self.get(P["me"])
            if r.status_code == 200:
                self._profile = r.json()
        return self._profile


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
    assert token, f"login({email}): нет access_token: {r.text}"
    return Api(token)


def register_login() -> Api:
    email, _ = new_credentials()
    register(email)
    return login(email)


# ─────────────── адреса / продавцы / листинги ───────────────
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
    user = register_login()
    make_address(user, apartment="12" if with_apartment else None)

    r = user.post(P["seller_apply"])
    assert r.status_code in (200, 201, 202), f"seller_apply: {r.status_code} {r.text}"

    approve_last_seller_request()

    # после approve роль обновилась в БД — нужен свежий JWT
    r_refresh = user.post(P["refresh"])
    assert r_refresh.status_code == 200, f"refresh: {r_refresh.status_code} {r_refresh.text}"
    new_token = r_refresh.json().get("access_token")
    assert new_token, f"refresh не вернул access_token: {r_refresh.text}"
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
    r = seller.post(
        P["listing_create"],
        json={
            "title": f"Vinyl E2E {uuid.uuid4().hex[:6]}",
            "artist": "E2E Artist",
            "year": 2024,
            "condition": "Mint",
            "price": float(price),
            "description": "test pressing",
            "genre": "Rock",
            "format": "Vinyl",
        },
    )
    assert r.status_code in (200, 201), f"listing: {r.status_code} {r.text}"
    listing = r.json()

    if listing.get("status") != "active":
        c = seller.post(
            P["listing_cover"],
            fmt={"id": listing["id"]},
            files={"file": ("cover.png", PNG_1X1, "image/png")},
        )
        assert c.status_code in (200, 201), f"cover upload: {c.status_code} {c.text}"

        a = seller.post(
            P["listing_audio_status"],
            fmt={"id": listing["id"]},
            json={"has_audio": True},
        )
        assert a.status_code in (200, 201), f"audio-status: {a.status_code} {a.text}"

        s = seller.post(P["listing_submit"], fmt={"id": listing["id"]})
        assert s.status_code in (200, 201), f"submit-for-moderation: {s.status_code} {s.text}"

        admin = login(ADMIN_EMAIL, ADMIN_PASSWORD)
        m = admin.post(
            P["listing_moderate"],
            fmt={"id": listing["id"]},
            json={"action": "approve"},
        )
        assert m.status_code in (200, 201), f"moderate: {m.status_code} {m.text}"

        g = seller.get(P["listing_get"], fmt={"id": listing["id"]})
        assert g.status_code == 200, f"listing_get: {g.status_code} {g.text}"
        listing = g.json()

    assert listing.get("status") == "active", f"listing не active: {listing.get('status')}"
    return listing


# ─────────────── чекаут / оплата ───────────────
def build_checkout_payload(buyer: Api, items: list[dict], shipping: dict | None = None) -> dict:
    """Payload под реальную CheckoutRequest экономики:
    {buyer_id, customer_email, items[], shipping?} — shipping один на заказ."""
    profile = buyer.profile
    if not profile:
        r = buyer.get(P["me"])
        assert r.status_code == 200, f"/me failed: {r.status_code} {r.text}"
        profile = r.json()
        buyer._profile = profile

    buyer_id = profile.get("id") or profile.get("user_id")
    customer_email = profile.get("email")
    assert buyer_id and customer_email, f"в профиле нет id/email: {profile}"

    payload = {
        "buyer_id": buyer_id,
        "customer_email": customer_email,
        "items": [
            {
                "listing_id": item["listing_id"],
                "seller_price": item["seller_price"],
            }
            for item in items
        ],
    }
    if shipping:
        payload["shipping"] = shipping
    return payload


def make_shipping(address_id: str, point: dict | None = None) -> dict:
    """Один объект доставки на заказ (схема ShippingRequest экономики)."""
    point = point or {}
    return {
        "address_id": address_id,
        "carrier_code": point.get("provider_key", "apiship"),
        "service_code": "pvz",
        "shipping_cost": 350.0,
        "tariff_id": point.get("tariff_id", 200),
        "pickup_point_id": str(point.get("id", 407)),
    }


def simulate_payment(api: Api, order_id, success: bool = True) -> dict:
    """Mock-оплата (ЮKassa в test-mode)."""
    r = api.post(
        P["payment_mock"],
        params={"order_id": str(order_id), "success": str(success).lower()},
    )
    assert r.status_code == 200, f"simulate-payment: {r.status_code} {r.text}"
    body = r.json()
    expected = "paid" if success else "cancelled"
    assert body.get("new_status") == expected, f"simulate-payment: {body}"
    return body


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