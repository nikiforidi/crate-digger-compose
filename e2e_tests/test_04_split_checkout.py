"""Сценарий 4 (ядро рефакторинга): сплит-корзина двух продавцов.

Контракт:
- чекаут принимает ОДИН объект shipping на заказ;
- после оплаты экономика сама создаёт по одной строке shipping_orders на продавца.
"""
import json

from conftest import (
    P,
    build_checkout_payload,
    make_address,
    make_shipping,
    register_login,
    simulate_payment,
    sql,
)


def _pick_point(buyer, city="Москва"):
    r = buyer.get(P["shipping_points"], params={"provider_key": "apiship", "city": city})
    assert r.status_code == 200, r.text
    points = r.json()
    points = points.get("items", points) if isinstance(points, dict) else points
    assert points, "нет ПВЗ в ответе shipping/points"
    return points[0]


def test_calculate_only_pickup_without_apartment(listing_a, listing_b):
    """Без квартиры доступен только ПВЗ (фронт фильтрует курьера сам)."""
    buyer = register_login()
    addr = make_address(buyer, apartment=None)
    r = buyer.post(
        P["shipping_calculate"],
        json={
            "address_id": addr["id"],
            "items_count": 2,
            "seller_ids": [listing_a["seller_id"], listing_b["seller_id"]],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    blob = json.dumps(body, ensure_ascii=False).lower()
    assert "pickup" in blob or "пвз" in blob, f"нет ПВЗ-опций: {body}"


def test_split_checkout_creates_two_shipments(listing_a, listing_b):
    buyer = register_login()
    addr = make_address(buyer, apartment=None)
    point = _pick_point(buyer)

    payload = build_checkout_payload(
        buyer,
        items=[
            {"listing_id": listing_a["id"], "seller_price": listing_a["price"]},
            {"listing_id": listing_b["id"], "seller_price": listing_b["price"]},
        ],
        shipping=make_shipping(addr["id"], point),
    )

    r = buyer.post(P["checkout"], json=payload)
    assert r.status_code in (200, 201), f"checkout: {r.status_code} {r.text}"
    order = r.json()
    order_id = order.get("order_id") or order.get("id")
    assert order_id, f"нет order id в ответе: {order}"

    # один заказ, две позиции
    assert sql("economy_db", f"SELECT count(*) FROM orders WHERE id='{order_id}'") == "1"
    assert sql("economy_db", f"SELECT count(*) FROM order_items WHERE order_id='{order_id}'") == "2"

    # оплата (mock) → экономика сама создаёт отправки в логистике
    simulate_payment(buyer, order_id)
    assert sql("economy_db", f"SELECT status FROM orders WHERE id='{order_id}'") == "paid"

    # ДВЕ строки shipping_orders с одним order_id (unique на order_id снят)
    assert sql("logistics_db", f"SELECT count(*) FROM shipping_orders WHERE order_id='{order_id}'") == "2"
    sellers = sql(
        "logistics_db",
        f"SELECT count(DISTINCT seller_id) FROM shipping_orders WHERE order_id='{order_id}'",
    )
    assert sellers == "2", f"ожидали 2 разных продавцов, получили {sellers}"