"""Сценарий 4 (ядро рефакторинга): сплит-корзина двух продавцов."""
import json

from conftest import (
    P, build_checkout_payload, make_address, make_shipping,
    register_login, simulate_payment, sql,
)


def _pick_point(buyer, city="Москва"):
    r = buyer.get(P["shipping_points"], params={"provider_key": "apiship", "city": city})
    assert r.status_code == 200, r.text
    points = r.json()
    points = points.get("items", points) if isinstance(points, dict) else points
    assert points, "нет ПВЗ в ответе shipping/points"
    return points[0]


def test_calculate_only_pickup_without_apartment(listing_a, listing_b):
    buyer = register_login()
    addr = make_address(buyer, apartment=None)
    r = buyer.post(
        P["shipping_calculate"],
        json={
            "address_id": addr["id"],
            "items_count": 2,
            "sellers": [
                {"seller_id": listing_a["seller_id"], "items_count": 1},
                {"seller_id": listing_b["seller_id"], "items_count": 1},
            ],
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

    # 🔑 ОТЛАДКА: проверяем, что shipping_address_id и carrier_code сохранились
    shipping_addr = sql("economy_db", f"SELECT shipping_address_id FROM orders WHERE id='{order_id}'")
    carrier = sql("economy_db", f"SELECT carrier_code FROM orders WHERE id='{order_id}'")
    print(f"[DEBUG] order shipping_address_id={shipping_addr}, carrier_code={carrier}")
    assert shipping_addr, "shipping_address_id пуст в заказе"
    assert carrier, "carrier_code пуст в заказе"

    # оплата → economy создаёт отправки (по одной на seller_id)
    simulate_payment(buyer, order_id)
    assert sql("economy_db", f"SELECT status FROM orders WHERE id='{order_id}'") == "paid"

    # 🔑 ОТЛАДКА: проверяем логи экономики
    import subprocess
    logs = subprocess.run(
        ["docker", "compose", "--env-file", ".env.testing", "-f", "docker-compose.testing.yml", 
         "logs", "economy-service", "--tail=100"],
        capture_output=True, text=True
    )
    print("[DEBUG] economy-service logs (last 100 lines):")
    print(logs.stdout)
    print(logs.stderr)

    ship_count = sql(
        "logistics_db",
        f"SELECT count(*) FROM shipping_orders WHERE order_id='{order_id}'",
    )
    assert ship_count == "2", f"ожидали 2 shipping_orders, получили {ship_count}"
    sellers = sql(
        "logistics_db",
        f"SELECT count(DISTINCT seller_id) FROM shipping_orders WHERE order_id='{order_id}'",
    )
    assert sellers == "2", f"ожидали 2 разных продавцов, получили {sellers}"