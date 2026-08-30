"""Сценарий 5: продавец сдаёт посылку → статус «Передана в доставку» + dispatched_at."""
from conftest import P, register_login, sql


def make_address(api, apartment=None):
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


def _checkout_one(buyer, listing, seller_id):
    addr = make_address(buyer, apartment=None)
    r = buyer.get(P["shipping_points"], params={"provider_key": "apiship", "city": "Москва"})
    point = (r.json() if isinstance(r.json(), list) else r.json().get("items"))[0]
    r = buyer.post(
        P["checkout"],
        json={
            "items": [{"listing_id": listing["id"], "quantity": 1}],
            "address_id": addr["id"],
            "shipping": [{"seller_id": seller_id, "method": "pickup", "point": point}],
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_handover_sets_dispatched(seller_a, listing_a):
    buyer = register_login()
    order = _checkout_one(buyer, listing_a, listing_a["seller_id"])
    order_id = order.get("id") or order.get("order_id")

    ship_id = sql(
        "logistics_db",
        f"SELECT id FROM shipping_orders WHERE order_id='{order_id}' LIMIT 1",
    )
    assert ship_id, "нет shipping_order для заказа"

    r = seller_a.post(P["handover"], fmt={"id": ship_id})
    assert r.status_code in (200, 201), f"handover: {r.status_code} {r.text}"

    # logistics: статус передана
    st = sql("logistics_db", f"SELECT status FROM shipping_orders WHERE id='{ship_id}'")
    assert "hand" in st or "dispatch" in st or "transit" in st, f"status={st}"

    # economy: dispatched_at проставлен
    disp = sql("economy_db", f"SELECT dispatched_at IS NOT NULL FROM orders WHERE id='{order_id}'")
    assert disp == "t", "dispatched_at не проставлен"