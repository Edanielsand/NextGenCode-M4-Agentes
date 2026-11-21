"""Costo real: manda el conjunto de evaluación a dos URL y compara.

Uso: ``COST_API_KEY=<clave> uv run python scripts/cost_real.py <url_linea_base>
<url_normal>``

El producto no admite un encabezado que pida la línea base: esa configuración
se elige con variables (``ROUTING=false``, ``HISTORY_WINDOW``). Por eso se
pasan dos URL: una con la línea base y otra con la configuración normal. La
clave se lee de ``COST_API_KEY``, nunca de un argumento. Escribe
``output/cost-real.md``.
"""

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from verification.evaluate import EVAL_SET, is_correct  # noqa: E402  # pylint: disable=wrong-import-position

OUTPUT = ROOT / "output" / "cost-real.md"


def measure(url: str, key: str, cases: list[dict]) -> dict:
    """Pregunta cada caso a ``url`` y suma costo, tokens y calidad."""
    correct, cost, tokens = 0, 0.0, 0
    with httpx.Client(timeout=90, headers={"X-API-Key": key}) as client:
        for case in cases:
            response = client.post(f"{url}/ask", json={"question": case["question"]})
            response.raise_for_status()
            body = response.json()
            correct += is_correct(body["answer"], case)
            cost += body["cost_usd"]
            tokens += body["input_tokens"] + body.get("output_tokens", 0)
    return {
        "cost_usd": cost,
        "tokens": tokens,
        "avg_cost_usd": cost / len(cases),
        "quality": correct / len(cases),
    }


def render(runs: dict[str, dict]) -> str:
    """Tabla en Markdown con una fila por corrida."""
    lines = [
        "# Costo real",
        "",
        "| Corrida | Costo total (USD) | Tokens | Costo promedio (USD) | Calidad |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, run in runs.items():
        lines.append(
            f"| {name} | {run['cost_usd']:.6f} | {run['tokens']} "
            f"| {run['avg_cost_usd']:.6f} | {run['quality']:.0%} |"
        )
    return "\n".join(lines) + "\n"


def main(args: list[str]) -> int:
    """Corre las dos mediciones y guarda la tabla; 0 si terminó."""
    key = os.environ.get("COST_API_KEY", "")
    if len(args) != 2 or not key:
        print("Uso: COST_API_KEY=<clave> python scripts/cost_real.py "
              "<url_linea_base> <url_normal>")
        return 2
    cases = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    runs = {
        "linea base": measure(args[0].rstrip("/"), key, cases),
        "normal": measure(args[1].rstrip("/"), key, cases),
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(render(runs), encoding="utf-8")
    print(render(runs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
