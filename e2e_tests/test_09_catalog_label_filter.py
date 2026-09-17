"""Фильтр каталога по лейблу: механика пост-фильтрации.

Листинги без привязки к релизу (free listings) не имеют лейбла и должны
исключаться из выдачи при активном фильтре label, но присутствовать без него.
Внешние API (Discogs) для этого теста не нужны.
"""
from conftest import Api, make_listing, make_seller


def test_label_filter_excludes_release_less_listings():
    seller = make_seller()
    listing = make_listing(seller)  # free listing, status=active

    anon = Api()

    # Без фильтра листинг присутствует в каталоге
    r = anon.get("/catalog/", params={"limit": 50})
    assert r.status_code == 200, r.text
    ids = [item["listing"]["id"] for item in r.json()]
    assert listing["id"] in ids, "свободный листинг не найден в каталоге без фильтра"

    # С фильтром по несуществующему лейблу листинг исключается (нет релиза)
    r = anon.get("/catalog/", params={"label": "NonexistentLabelXYZ", "limit": 50})
    assert r.status_code == 200, r.text
    ids = [item["listing"]["id"] for item in r.json()]
    assert listing["id"] not in ids, (
        "свободный листинг попал в выдачу с фильтром по лейблу"
    )


def test_label_filter_respects_pagination_params():
    """Фильтр label совместим с limit/offset и не ломает схему ответа."""
    anon = Api()
    r = anon.get("/catalog/", params={"label": "BlueNote", "limit": 5, "offset": 0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) <= 5