"""Market-фичи: курс ЦБ, price suggestions, прокси коллекций Discogs.

Проверяем маршрутизацию гейтвея и валидацию без зависимости от доступности
внешних API (Discogs/ЦБ): статусы маршрутов и схемы ответов.
"""
from conftest import register_login


def test_cbr_usd_rate():
    """GET /api/v1/prices/cbr/usd отдаёт курс (только для авторизованных)."""
    client = register_login()
    r = client.get("/prices/cbr/usd")
    assert r.status_code == 200, f"CBR rate: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("rate", 0) > 0, f"некорректный курс: {body}"
    assert body.get("rate_date"), f"нет даты курса: {body}"


def test_cbr_usd_rate_requires_auth():
    """Без токена /prices/cbr/usd недоступен (не входит в PUBLIC_GET_PREFIXES)."""
    from conftest import Api

    anon = Api()
    r = anon.get("/prices/cbr/usd")
    assert r.status_code == 401, f"ожидали 401, получили {r.status_code}"


def test_batch_suggestions_validation():
    """Batch suggestions: валидация схемы BatchSuggestionsIn."""
    client = register_login()

    r = client.post("/releases/price-suggestions/batch", json={})
    assert r.status_code == 422, f"пустое тело: {r.status_code}"

    r = client.post(
        "/releases/price-suggestions/batch",
        json={"discogs_ids": [], "condition": "VG+"},
    )
    assert r.status_code == 422, f"пустой список discogs_ids: {r.status_code}"

    r = client.post("/releases/price-suggestions/batch", json={"discogs_ids": [1]})
    assert r.status_code == 422, f"нет condition: {r.status_code}"


def test_single_price_suggestions_routing():
    """Маршрут /releases/{id}/price-suggestions живёт и публичен для GET.

   上游 может не знать релиз (404) или быть недоступен (502) — это нормально;
    важно, что маршрут не отдаёт 401/404-гейтвея/405.
    """
    from conftest import Api

    anon = Api()
    r = anon.get("/releases/999999999/price-suggestions")
    assert r.status_code in (200, 404, 502), f"неожиданный статус {r.status_code}"


def test_collections_proxy_routing():
    """Прокси коллекций: несуществующий пользователь → 404/502, но не 401/405."""
    from conftest import Api

    anon = Api()
    r = anon.get("/releases/collections/definitely_not_a_user_xyz/releases")
    assert r.status_code in (200, 404, 502), f"неожиданный статус {r.status_code}"