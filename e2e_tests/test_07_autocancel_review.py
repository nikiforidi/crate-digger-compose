"""Сценарий 7: авто-отмена по seller_fault + оценка продавца.

Авто-отмену запускаем детерминированно (вызовом джоба в контейнере экономики),
т.к. фоновый цикл спит 3600с. Включается через E2E_RUN_SLOW=1.
"""
import pytest

from conftest import (
    P,
    RUN_SLOW,
    build_checkout_payload,
    make_address,
    make_shipping,
    register_login,
    simulate_payment,
    sql,
    trigger_auto_cancel,
)

pytestmark = pytest.mark.skipif(not RUN_SLOW, reason="E2E_RUN_SLOW=1 не задан")


def test_autocancel_seller_fault_and_review(seller_a, listing_a):
    buyer = register_login()
    addr = make_address(buyer, apartment=None)
    r = buyer.get(P["shipping_points"], params={"provider_key": "apiship", "city": "Москва"})
    points = r.json()
    points = points.get("items", points) if isinstance(points, dict) else points
    point = points[0]

    payload = build_checkout_payload(
        buyer,
        items=[{"listing_id": listing_a["id"], "seller_price": listing_a["price"]}],
        shipping=make_shipping(addr["id"], point),
    )
    r = buyer.post(P["checkout"], json=payload)
    assert r.status_code in (200, 201), r.text
    order_id = r.json().get("order_id") or r.json().get("id")
    simulate_payment(buyer, order_id)

    # форсим возраст заказа > 72h и запускаем джоб авто-отмены
    sql("economy_db", f"UPDATE orders SET created_at = NOW() - INTERVAL '73 hours' WHERE id='{order_id}'")
    trigger_auto_cancel()

    status = sql("economy_db", f"SELECT status FROM orders WHERE id='{order_id}'")
    assert "cancel" in status, f"заказ не отменён: {status}"

    reason = sql("economy_db", f"SELECT COALESCE(cancellation_reason,'') FROM orders WHERE id='{order_id}'")
    assert "seller" in reason, f"cancellation_reason={reason}"

    fault = sql("economy_db", f"SELECT seller_fault FROM orders WHERE id='{order_id}'")
    assert fault == "t", f"seller_fault={fault}"

    # покупатель ставит оценку продавцу
    r = buyer.post(
        P["review"],
        fmt={"id": listing_a["seller_id"]},
        json={"order_id": order_id, "rating": 2, "comment": "не сдал посылку"},
    )
    assert r.status_code in (200, 201), f"review: {r.status_code} {r.text}"