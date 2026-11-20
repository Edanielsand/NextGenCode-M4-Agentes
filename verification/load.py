"""Prueba de carga contra el producto publicado.

Uso: ``LOAD_API_KEY=<clave> uv run python -m verification load <url> [--n 50]
[--concurrency 10]``

La clave se lee de la variable ``LOAD_API_KEY``: nunca va en el comando ni en
el chat, porque quedaría en el historial. Termina con código distinto de 0 si
el ``error_rate`` pasa de 1 %.
"""

import argparse
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

MAX_ERROR_RATE = 0.01
QUESTION = {"question": "¿Quién es EMP-0004?"}


def percentile(values: list[float], pct: float) -> float:
    """Percentil ``pct`` (0 a 100) por el método del rango más cercano."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(results: list[tuple[bool, float]], elapsed: float) -> dict:
    """Resume ``(éxito, segundos)`` de cada petición.

    :param results: un par por petición
    :param elapsed: segundos totales de la corrida
    :return: peticiones, éxitos, errores, error_rate, p50_ms, p95_ms y rps
    :rtype: dict
    """
    total = len(results)
    ok = sum(1 for success, _ in results if success)
    millis = [seconds * 1000 for _, seconds in results]
    return {
        "requests": total,
        "successes": ok,
        "errors": total - ok,
        "error_rate": (total - ok) / total if total else 1.0,
        "p50_ms": percentile(millis, 50),
        "p95_ms": percentile(millis, 95),
        "rps": total / elapsed if elapsed > 0 else 0.0,
    }


def run_load(url: str, key: str, total: int, concurrency: int) -> dict:
    """Manda ``total`` peticiones a ``/ask``, ``concurrency`` a la vez."""
    # Render despierta el servicio dormido en hasta un minuto
    with httpx.Client(timeout=90, headers={"X-API-Key": key}) as client:

        def one(_: int) -> tuple[bool, float]:
            start = time.perf_counter()
            try:
                response = client.post(f"{url}/ask", json=QUESTION)
                success = response.status_code == 200
            except httpx.HTTPError:
                success = False
            return success, time.perf_counter() - start

        began = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(one, range(total)))
        return summarize(results, time.perf_counter() - began)


def main(args: list[str]) -> int:
    """Corre la carga e imprime el resumen; 0 si el error_rate es de 1 % o menos."""
    parser = argparse.ArgumentParser(prog="python -m verification load")
    parser.add_argument("url")
    parser.add_argument("--n", type=int, default=50, help="peticiones en total")
    parser.add_argument("--concurrency", type=int, default=10, help="a la vez")
    options = parser.parse_args(args)
    key = os.environ.get("LOAD_API_KEY", "")
    if not key:
        print("Uso: LOAD_API_KEY=<clave> python -m verification load <url>")
        return 2
    summary = run_load(options.url.rstrip("/"), key, options.n, options.concurrency)
    print(f"peticiones: {summary['requests']}")
    print(f"exitos:     {summary['successes']}")
    print(f"errores:    {summary['errors']} (error_rate {summary['error_rate']:.1%})")
    print(f"p50:        {summary['p50_ms']:.0f} ms")
    print(f"p95:        {summary['p95_ms']:.0f} ms")
    print(f"pet/s:      {summary['rps']:.1f}")
    return 0 if summary["error_rate"] <= MAX_ERROR_RATE else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
