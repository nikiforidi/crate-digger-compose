"""Сценарий 3: чекаут с продавцом без адреса отправления → 400.

Economy проверяет ЮKassa раньше адреса, поэтому при отсутствии и того, и другого
вернётся «продавец не настроил платежи» — это тоже честная бизнес-валидация 400.
"""
from conftest import P, build_checkout_payload, make_listing, make_seller, register_login


def test_checkout_blocked_without_seller_address():
    seller = make_seller(with_apartment=True)
    listing = make_listing(seller)

    r = seller.get(P["addresses"])
    assert r.status_code == 200
    addrs = r.json()
    addrs = addrs.get("items", addrs) if isinstance(addrs, dict) else addrs
    for a in addrs:
        rd = seller.delete(P["address_delete"], fmt={"id": a["id"]})
        assert rd.status_code in (200, 204), rd.text

    buyer = register_login()
    addr = buyer.post(
        P["addresses"],
        json={
            "city": "Москва",
            "street": "Арбат",
            "house": "1",
            "apartment": "5",
            "recipient_name": "E2E Buyer",
            "phone": "+7 999 111-11-11",
            "latitude": 55.749,
            "longitude": 37.585,
        },
    ).json()

    payload = build_checkout_payload(
        buyer,
        # 🔑 ИСПРАВЛЕНО: добавляем seller_id для автогенерации shipping
        items=[{"listing_id": listing["id"], "seller_id": listing["seller_id"], "quantity": 1, "seller_price": listing["price"]}],
        address_id=addr["id"],
    )

    r = buyer.post(P["checkout"], json=payload)
    assert r.status_code == 400, f"ожидали 400, получили {r.status_code}: {r.text}"
    
    body = r.text.lower()
    assert any(
        needle in body
        for needle in ("адрес", "address", "seller", "продавец", "yookassa", "платеж", "платёж")
    ), f"неожиданное сообщение 400: {r.text}"