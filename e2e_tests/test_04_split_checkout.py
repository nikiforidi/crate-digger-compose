"""Сценарий 4 (ядро рефакторинга): сплит-корзина двух продавцов.

Ожидаем: 1 Order + 2 OrderItem в economy_db и 2 строки shipping_orders
с одним order_id в logistics_db. Адрес без квартиры → только ПВЗ.
"""
import json

from conftest import P, make_address, register_login, sql


def _pick_point(buyer, city="Москва"):
    r = buyer.get(P["shipping_points"], params={"provider_key": "apiship", "city": city})
    assert r.status_code == 200, r.text
    points = r.json()
    points = points.get("items", points) if isinstance(points, dict) else points
    assert points, "нет ПВЗ в ответе shipping/points"
    return points[0]


def test_calculate_only_pickup_without_apartment(listing_a, listing_b):
    buyer = register_login()
    addr = make_address(buyer, apartment=None)  # без квартиры
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
    assert "courier" not in blob, f"курьер доступен без квартиры: {body}"


def test_split_checkout_creates_two_shipments(listing_a, listing_b):
    buyer = register_login()
    addr = make_address(buyer, apartment=None)
    point = _pick_point(buyer)

    r = buyer.post(
        P["checkout"],
        json={
            "items": [
                {"listing_id": listing_a["id"], "quantity": 1},
                {"listing_id": listing_b["id"], "quantity": 1},
            ],
            "address_id": addr["id"],
            "shipping": [
                {
                    "seller_id": listing_a["seller_id"],
                    "method": "pickup",
                    "point": point,
                },
                {
                    "seller_id": listing_b["seller_id"],
                    "method": "pickup",
                    "point": point,
                },
            ],
        },
    )
    assert r.status_code in (200, 201), f"checkout: {r.status_code} {r.text}"
    order = r.json()
    order_id = order.get("id") or order.get("order_id")
    assert order_id, f"нет order id в ответе: {order}"

    # economy: один заказ, две позиции
    assert sql("economy_db", f"SELECT count(*) FROM orders WHERE id='{order_id}'") == "1"
    assert sql("economy_db", f"SELECT count(*) FROM order_items WHERE order_id='{order_id}'") == "2"

    # logistics: ДВЕ строки shipping_orders с одним order_id (unique снят)
    assert sql("logistics_db", f"SELECT count(*) FROM shipping_orders WHERE order_id='{order_id}'") == "2"

    # point_snapshot сохранён в обеих строках
    snaps = sql(
        "logistics_db",
        f"SELECT count(*) FROM shipping_orders WHERE order_id='{order_id}' AND point_snapshot IS NOT NULL",
    )
    assert snaps == "2", f"point_snapshot не заполнен: {snaps}"