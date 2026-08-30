"""Сценарий 7: авто-отмена по seller_fault (форс 73h) + оценка продавца покупателем."""
import time

import pytest

from conftest import P, RUN_SLOW, build_checkout_payload, make_address, register_login, sql

pytestmark = pytest.mark.skipif(not RUN_SLOW, reason="E2E_RUN_SLOW=1 не задан")


def test_autocancel_seller_fault_and_review(seller_a, listing_a):
    buyer = register_login()
    addr = make_address(buyer, apartment=None)
    r = buyer.get(P["shipping_points"], params={"provider_key": "apiship", "city": "Москва"})
    point = (r.json() if isinstance(r.json(), list) else r.json().get("items"))[0]

    payload = build_checkout_payload(
        buyer,
        items=[{"listing_id": listing_a["id"], "quantity": 1, "seller_price": listing_a["price"]}],
        address_id=addr["id"],
        shipping=[{"seller_id": listing_a["seller_id"], "method": "pickup", "point": point}],
    )

    r = buyer.post(P["checkout"], json=payload)
    assert r.status_code in (200, 201), r.text
    order_id = r.json().get("id") or r.json().get("order_id")

    sql("economy_db", f"UPDATE orders SET created_at = NOW() - INTERVAL '73 hours' WHERE id='{order_id}'")

    status = ""
    for _ in range(36):
        status = sql("economy_db", f"SELECT status FROM orders WHERE id='{order_id}'")
        if "cancel" in status:
            break
        time.sleep(5)
    assert "cancel" in status, f"заказ не отменён планировщиком: {status}"

    reason = sql("economy_db", f"SELECT COALESCE(cancel_reason,'') FROM orders WHERE id='{order_id}'")
    assert "seller" in reason, f"cancel_reason={reason}, ожидали seller_fault"

    r = buyer.post(
        P["review"],
        fmt={"id": listing_a["seller_id"]},
        json={"order_id": order_id, "rating": 2, "comment": "не сдал посылку"},
    )
    assert r.status_code in (200, 201), f"review: {r.status_code} {r.text}"