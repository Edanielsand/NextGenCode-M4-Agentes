"""Prueba de carga contra el producto publicado.

Uso: ``LOAD_API_KEYS=<clave1,clave2,...> uv run python -m verification load
<url> [--n 50] [--concurrency 10]``

Las claves de los clientes de prueba se leen de ``LOAD_API_KEYS``, separadas
por coma (si no existe, de ``LOAD_API_KEY``): nunca van en el comando ni en el
chat, porque quedarían en el historial. Las peticiones se reparten entre las
claves por turnos, para no chocar con el límite por cliente del producto.
Termina con código distinto de 0 si el ``error_rate`` pasa de 1 %.
"""

import argparse
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

MAX_ERROR_RATE = 0.01
DETAILS_PER_CODE = 3
MAX_DETAIL_CHARS = 300
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


def format_breakdown(outcomes: list[str]) -> str:
    """Desglose por resultado, p. ej. ``200: 17, 429: 30, red (ReadTimeout): 3``.

    :param outcomes: una etiqueta por petición: el código HTTP o ``red (Tipo)``
    :return: pares ``etiqueta: cantidad``; primero los códigos, de menor a mayor
    :rtype: str
    """
    counts: dict[str, int] = {}
    for label in outcomes:
        counts[label] = counts.get(label, 0) + 1
    ordered = sorted(counts, key=lambda label: (not label.isdigit(), int(label) if label.isdigit() else 0, label))
    return ", ".join(f"{label}: {counts[label]}" for label in ordered)


def extract_detail(response: httpx.Response) -> str | None:
    """Campo ``detail`` del cuerpo JSON, o ``None``; nunca encabezados ni la clave."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or "detail" not in body:
        return None
    return str(body["detail"])[:MAX_DETAIL_CHARS]


def parse_keys(environ: os._Environ | dict) -> list[str]:
    """Claves de los clientes de prueba.

    Lee ``LOAD_API_KEYS`` (separadas por coma); si no existe o queda vacía,
    usa ``LOAD_API_KEY``.

    :param environ: variables de entorno
    :return: claves sin espacios ni vacíos; lista vacía si no hay ninguna
    :rtype: list[str]
    """
    raw = environ.get("LOAD_API_KEYS", "") or environ.get("LOAD_API_KEY", "")
    return [key.strip() for key in raw.split(",") if key.strip()]


def key_for(keys: list[str], index: int) -> str:
    """Clave de la petición ``index``: reparto por turnos entre los clientes."""
    return keys[index % len(keys)]


def run_load(url: str, keys: list[str], total: int, concurrency: int) -> dict:
    """Manda ``total`` peticiones a ``/ask``, ``concurrency`` a la vez.

    Cada petición lleva en ``X-API-Key`` la clave que le toca por turnos.
    """
    # Render despierta el servicio dormido en hasta un minuto
    with httpx.Client(timeout=90) as client:

        def one(index: int) -> tuple[bool, float, str, str | None]:
            start = time.perf_counter()
            detail = None
            try:
                response = client.post(
                    f"{url}/ask", json=QUESTION,
                    headers={"X-API-Key": key_for(keys, index)})
                success = response.status_code == 200
                label = str(response.status_code)
                if not success:
                    detail = extract_detail(response)
            except httpx.HTTPError as error:
                success = False
                label = f"red ({type(error).__name__})"
            return success, time.perf_counter() - start, label, detail

        began = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            full = list(pool.map(one, range(total)))
        summary = summarize([(ok, secs) for ok, secs, _, _ in full], time.perf_counter() - began)
        summary["breakdown"] = format_breakdown([label for _, _, label, _ in full])
        details: dict[str, list[str]] = {}
        for ok, _, label, detail in full:
            samples = details.setdefault(label, [])
            if not ok and detail is not None and len(samples) < DETAILS_PER_CODE:
                samples.append(detail)
        summary["details"] = {label: found for label, found in details.items() if found}
        return summary


def main(args: list[str]) -> int:
    """Corre la carga e imprime el resumen; 0 si el error_rate es de 1 % o menos."""
    parser = argparse.ArgumentParser(prog="python -m verification load")
    parser.add_argument("url")
    parser.add_argument("--n", type=int, default=50, help="peticiones en total")
    parser.add_argument("--concurrency", type=int, default=10, help="a la vez")
    options = parser.parse_args(args)
    keys = parse_keys(os.environ)
    if not keys:
        print("Uso: LOAD_API_KEYS=<clave1,clave2,...> python -m verification load <url>")
        return 2
    summary = run_load(options.url.rstrip("/"), keys, options.n, options.concurrency)
    print(f"clientes:   {len(keys)}")
    print(f"peticiones: {summary['requests']}")
    print(f"exitos:     {summary['successes']}")
    print(f"errores:    {summary['errors']} (error_rate {summary['error_rate']:.1%})")
    print(f"p50:        {summary['p50_ms']:.0f} ms")
    print(f"p95:        {summary['p95_ms']:.0f} ms")
    print(f"pet/s:      {summary['rps']:.1f}")
    if summary.get("breakdown"):
        print(f"desglose:   {summary['breakdown']}")
    for label, samples in summary.get("details", {}).items():
        for sample in samples:
            print(f"detail {label}: {sample}")
    return 0 if summary["error_rate"] <= MAX_ERROR_RATE else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
