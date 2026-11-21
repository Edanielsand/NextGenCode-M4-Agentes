"""Contrato del arreglo de herramientas: el especialista usa su herramienta aunque el modelo no la pida."""

import socket

import pytest

from verification.server import running_product


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def api_no_tools():
    """El producto con el modelo simulado que nunca pide herramientas."""
    with running_product(_free_port(), MODEL_PROVIDER="fake", FAKE_MODEL_MODE="no_tools") as client:
        yield client


def test_an_employee_question_uses_get_employee_without_leaking_its_name(api_no_tools):
    response = api_no_tools.post("/ask", json={"question": "¿Quién es EMP-0004?"})
    assert response.status_code == 200
    body = response.json()
    assert "get_employee" in body["tools_used"]
    assert "get_employee" not in body["answer"]


def test_a_department_question_uses_search_by_department_without_leaking_its_name(api_no_tools):
    response = api_no_tools.post("/ask", json={"question": "¿Quién trabaja en Tecnología?"})
    assert response.status_code == 200
    body = response.json()
    assert "search_by_department" in body["tools_used"]
    assert "search_by_department" not in body["answer"]


def test_without_tool_data_the_reviewer_replaces_the_answer_with_the_safe_message(api_no_tools):
    # Pregunta ambigua: decide el modelo, el especialista no recibe datos del código y el modelo
    # simulado no pide la herramienta, así que el revisor debe cambiar la respuesta.
    response = api_no_tools.post("/ask", json={"question": "Hola, necesito ayuda"})
    assert response.status_code == 200
    body = response.json()
    assert body["tools_used"] == []
    assert body["answer"] == (
        "No encontré datos para responder. Solo atiendo preguntas de Recursos Humanos. Pregunta por un id de empleado como EMP-0001 o por un departamento."
    )
