"""Калибровка: проверка доступности стека и дамп реальных маршрутов gateway.

Запуск: pytest e2e_tests/test_00_calibration.py -v -s
Если какой-то роут из P отличается — смотрим вывод и правим только словарь P в conftest.
"""
import httpx

from conftest import API, P, gw_openapi, new_credentials, register, login, sql


def test_stack_reachable():
    r = httpx.get("http://localhost/health", timeout=10)
    assert r.status_code == 200


def test_auth_flow():
    email, _ = new_credentials()
    register(email)
    api = login(email)
    r = api.get(P["me"])
    assert r.status_code == 200, r.text


def test_db_accessible():
    assert sql("economy_db", "SELECT 1") == "1"
    assert sql("logistics_db", "SELECT 1") == "1"


def test_dump_gateway_paths(gw_openapi):
    if not gw_openapi:
        print("\n[calibration] openapi gateway недоступен — сверяем P вручную по 404")
        return
    print("\n[calibration] реальные пути gateway:")
    for path in sorted(gw_openapi):
        print("  ", path)
    # подсказки: где расхождения с P
    for key, want in P.items():
        base = want.split("{")[0]
        if not any(p.startswith(base.rstrip("/")) or base.rstrip("/") in p for p in gw_openapi):
            print(f"  ⚠ P['{key}'] = {want} — не найден в openapi, проверь роут")