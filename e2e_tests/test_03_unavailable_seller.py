"""Сценарий 3: чекаут с продавцом без адреса отправления → 400 + amber-блок на фронте."""
from conftest import P, make_listing, make_seller, register_login


def test_checkout_blocked_without_seller_address():
    # продавец активирован, но адрес отправления удалён
    seller = make_seller(with_apartment=True)
    listing = make_listing(seller)

    # удаляем адрес отправления (endpoint из фронтового клиента)
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
            "city": "Москва", "street": "Арбат", "house": "1", "apartment": "5",
            "latitude": 55.749, "longitude": 37.585, "address_string": "Москва, Арбат, 1",
        },
    ).json()

    r = buyer.post(
        P["checkout"],
        json={
            "items": [{"listing_id": listing["id"], "quantity": 1}],
            "address_id": addr["id"],
        },
    )
    assert r.status_code == 400, f"ожидали 400, получили {r.status_code}: {r.text}"
    assert "адрес" in r.text.lower() or "seller" in r.text.lower(), r.text