"""Калибровка: проверка доступности стека и дамп реальных маршрутов gateway."""
import httpx
from conftest import API, P, gw_openapi, new_credentials, register, login, sql

GATEWAY_URL = "http://localhost:8000"  # напрямую в Gateway, без Nginx

def test_stack_reachable():
    r = httpx.get(f"{GATEWAY_URL}/health", timeout=10)
    assert r.status_code == 200, f"Gateway health check failed: {r.status_code} {r.text}"

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
    for key, want in P.items():
        base = want.split("{")[0]
        if not any(p.startswith(base.rstrip("/")) or base.rstrip("/") in p for p in gw_openapi):
            print(f"  ⚠ P['{key}'] = {want} — не найден в openapi, проверь роут")