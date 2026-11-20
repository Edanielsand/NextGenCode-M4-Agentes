"""Contrato del reto: datos protegidos, tablero, métricas de negocio y concurrencia."""

from concurrent.futures import ThreadPoolExecutor

import httpx

from verification.server import FACTORY_KEY

RFC = "GOMS800101AB1"
EMAIL = "sofia.gomez@example.com"
BUSINESS_METRICS = ("questions_by_department", "tool_usage", "cache_hit_pct",
                    "pii_by_type")


def test_pii_in_the_question_never_reaches_the_log(api_workers):
    client, log = api_workers
    question = f"¿Quién es EMP-0004? Mi RFC es {RFC} y mi correo es {EMAIL}"
    response = client.post("/ask", json={"question": question})
    assert response.status_code == 200
    assert RFC not in response.text and EMAIL not in response.text
    text = log.read_text(encoding="utf-8", errors="replace")
    assert RFC not in text and EMAIL not in text
    assert text.count('"pii_detected"') >= 2, "faltan los eventos pii_detected"


def test_dashboard_is_public_and_carries_no_key(api):
    response = httpx.get(f"{api.base_url}/dashboard")
    assert response.status_code == 200
    assert FACTORY_KEY not in response.text, "la página trae la clave"


def test_metrics_still_need_a_key(api):
    assert httpx.get(f"{api.base_url}/metrics").status_code == 401
    assert api.get("/metrics").status_code == 200


def test_metrics_include_the_business_metrics(api):
    api.post("/ask", json={"question": "Lista el departamento de Finanzas"})
    metrics = api.get("/metrics").json()
    missing = [name for name in BUSINESS_METRICS if name not in metrics]
    assert not missing, f"faltan en /metrics: {missing}"


def test_twenty_simultaneous_questions_get_distinct_request_ids(api_workers):
    client, _ = api_workers

    def ask(_):
        return client.post("/ask", json={"question": "¿Quién es EMP-0004?"})

    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(ask, range(20)))
    assert [r.status_code for r in responses] == [200] * 20
    ids = {r.json()["request_id"] for r in responses}
    assert len(ids) == 20
