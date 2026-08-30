"""Сценарий 5: продавец сдаёт посылку → dispatched_at в экономике."""
from conftest import (
    P, build_checkout_payload, make_address, make_shipping,
    register_login, simulate_payment, sql,
)


def _checkout_and_pay(buyer, listing):
    addr = make_address(buyer, apartment=None)
    r = buyer.get(P["shipping_points"], params={"provider_key": "apiship", "city": "Москва"})
    points = r.json()
    points = points.get("items", points) if isinstance(points, dict) else points
    point = points[0]

    payload = build_checkout_payload(
        buyer,
        items=[{"listing_id": listing["id"], "seller_price": listing["price"]}],
        shipping=make_shipping(addr["id"], point),
    )
    r = buyer.post(P["checkout"], json=payload)
    assert r.status_code in (200, 201), f"checkout: {r.status_code} {r.text}"
    order_id = r.json().get("order_id") or r.json().get("id")
    
    # 🔑 ОТЛАДКА: проверяем, что shipping_address_id и carrier_code сохранились
    shipping_addr = sql("economy_db", f"SELECT shipping_address_id FROM orders WHERE id='{order_id}'")
    carrier = sql("economy_db", f"SELECT carrier_code FROM orders WHERE id='{order_id}'")
    print(f"[DEBUG] order shipping_address_id={shipping_addr}, carrier_code={carrier}")
    assert shipping_addr, "shipping_address_id пуст в заказе"
    assert carrier, "carrier_code пуст в заказе"
    
    simulate_payment(buyer, order_id)
    
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
    
    return order_id


def test_handover_sets_dispatched(seller_a, listing_a):
    buyer = register_login()
    order_id = _checkout_and_pay(buyer, listing_a)

    ship_id = sql(
        "logistics_db",
        f"SELECT id FROM shipping_orders WHERE order_id='{order_id}' LIMIT 1",
    )
    assert ship_id, "нет shipping_order после оплаты"

    r = seller_a.post(P["handover"], fmt={"id": order_id})
    assert r.status_code in (200, 201), f"dispatch: {r.status_code} {r.text}"

    st = sql("logistics_db", f"SELECT status FROM shipping_orders WHERE id='{ship_id}'")
    assert st in ("sent", "dispatched", "in_transit"), f"status={st}"

    disp = sql("economy_db", f"SELECT dispatched_at IS NOT NULL FROM orders WHERE id='{order_id}'")
    assert disp == "t", "dispatched_at не проставлен"