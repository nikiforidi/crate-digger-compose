"""Сценарий 3: продавец без адреса отправления блокируется на этапе расчёта доставки.

Проверка адресов продавцов делается в logistics через /shipping/calculate
(возвращает unavailable_seller_ids). На самом чекауте economy такой проверки нет.
"""
from conftest import P, make_listing, make_seller, register_login


def test_checkout_blocked_for_problem_seller():
    seller = make_seller(with_apartment=True)
    listing = make_listing(seller)

    # удаляем адрес отправления
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

    # проверяем через /shipping/calculate
    r = buyer.post(
        P["shipping_calculate"],
        json={
            "address_id": addr["id"],
            "items_count": 1,
            "seller_ids": [listing["seller_id"]],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    unavailable = body.get("unavailable_seller_ids", [])
    assert listing["seller_id"] in unavailable, (
        f"продавец без адреса должен попасть в unavailable_seller_ids, получили: {body}"
    )