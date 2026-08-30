def test_checkout_blocked_for_problem_seller():
    seller = make_seller(with_apartment=True)
    listing = make_listing(seller)

    # удаляем адрес отправления
    r = seller.get(P["addresses"])
    addrs = r.json()
    addrs = addrs.get("items", addrs) if isinstance(addrs, dict) else addrs
    for a in addrs:
        seller.delete(P["address_delete"], fmt={"id": a["id"]})

    buyer = register_login()
    addr = buyer.post(
        P["addresses"],
        json={
            "city": "Москва", "street": "Арбат", "house": "1",
            "apartment": "5", "recipient_name": "E2E Buyer",
            "phone": "+7 999 111-11-11",
            "latitude": 55.749, "longitude": 37.585,
        },
    ).json()

    # 🔑 ИСПРАВЛЕНО: sellers вместо seller_ids (реальный контракт логистики)
    r = buyer.post(
        P["shipping_calculate"],
        json={
            "address_id": addr["id"],
            "items_count": 1,
            "sellers": [
                {"seller_id": listing["seller_id"], "items_count": 1}
            ],
        },
    )
    assert r.status_code == 200, r.text
    unavailable = r.json().get("unavailable_seller_ids", [])
    assert listing["seller_id"] in unavailable, (
        f"продавец без адреса должен попасть в unavailable_seller_ids, получили: {r.json()}"
    )