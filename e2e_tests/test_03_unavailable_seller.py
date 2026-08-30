"""Сценарий 3: чекаут с проблемным продавцом → честный 400 от экономики.

У тестовых продавцов нет настроенного приёма платежей
(seller_yookassa_account пуст) — экономика отказывает в создании заказа.
Проверка «продавец без адреса» на фронте делается через
/shipping/calculate → unavailable_seller_ids (см. сценарий 4).
"""
from conftest import P, build_checkout_payload, make_listing, make_seller, register_login


def test_checkout_blocked_for_problem_seller():
    seller = make_seller(with_apartment=True)
    listing = make_listing(seller)

    buyer = register_login()
    payload = build_checkout_payload(
        buyer,
        items=[
            {
                "listing_id": listing["id"],
                "seller_price": listing["price"],
            }
        ],
    )

    r = buyer.post(P["checkout"], json=payload)
    assert r.status_code == 400, f"ожидали 400, получили {r.status_code}: {r.text}"

    body = r.text.lower()
    assert any(
        needle in body
        for needle in ("адрес", "address", "seller", "продавец", "yookassa", "платеж", "платёж")
    ), f"неожиданное сообщение 400: {r.text}"