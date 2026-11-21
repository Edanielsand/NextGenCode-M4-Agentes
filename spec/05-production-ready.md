# Reto · Producción real: datos protegidos, resiliencia y operación

Parte del producto de la sesión 4. Lo lleva a producción: protege los datos personales, valida lo que sale del
modelo, resiste fallas del gateway, corre con varios procesos y se puede operar con un tablero y métricas de negocio.

## Lo que debe hacer

1. **PII enmascarada** (dueño: `security`).
   - Detecta con expresiones regulares: correo, teléfono de 10 dígitos, RFC, CURP, NSS (11 dígitos) y tarjeta de
     16 dígitos.
   - En la pregunta, cada coincidencia se cambia por `[CORREO]`, `[TELEFONO]`, `[RFC]`, `[CURP]`, `[NSS]` o
     `[TARJETA]` **antes** de que llegue al modelo. En la respuesta se hace lo mismo antes de devolverla.
   - Cada detección se registra en el log con el evento `pii_detected`: lleva `pii_type`, `count` y `direction`
     (`input` o `output`). **El valor nunca va al log**, ni en la traza ni en un mensaje de error.
2. **Validación de salida** (dueño: `security`).
   - La respuesta no puede venir vacía, no puede pasar de `MAX_ANSWER_CHARS` caracteres y no puede traer PII sin
     enmascarar ni algo que parezca una clave (por ejemplo `sk-...`, `Bearer ...` o una cadena larga de
     caracteres aleatorios).
   - Si falla, `/ask` responde `200` con `"No pude generar una respuesta segura. Intenta de nuevo."` y registra
     `output_rejected` con el motivo (`empty`, `too_long`, `pii` o `secret`), nunca con el texto rechazado.
3. **Reintentos** (dueño: `costs`).
   - Si el gateway da timeout o un error 5xx, se reintenta hasta `MODEL_MAX_RETRIES` veces con espera
     exponencial (0.5 s, 1 s, 2 s...).
   - Si se acaban los reintentos, se responde el `502` de siempre.
   - La espera se inyecta (como el reloj): las pruebas no esperan de verdad. Un 4xx no se reintenta.
   - El costo de los intentos fallidos no se cobra dos veces: `cost_usd` es el de la llamada que respondió.
4. **Concurrencia** (dueño: `deploy`; documentación: `observability`).
   - El contenedor arranca `uvicorn` con `--workers ${WEB_CONCURRENCY:-2}`. `render.yaml` define
     `WEB_CONCURRENCY`.
   - `README.md` dice que `/metrics` es **por proceso**: con varios workers cada petición ve las cifras de uno.
   - El estado compartido en memoria (límite de peticiones, caché, métricas) no debe romper nada con varios
     procesos; el `request_id` sigue siendo distinto en cada petición.
5. **Tablero** (dueño: `observability`).
   - `GET /dashboard` **no pide clave**: un navegador no puede mandar `X-API-Key` al abrir una URL. Responde `200`
     con una página HTML sin cifras y sin ninguna clave dentro.
   - La página le pide la clave a la persona y la guarda en `sessionStorage` (la misma de la página principal).
     Con ella lee `/metrics` cada 5 segundos, mandándola en `X-API-Key`. `/metrics` sigue exigiendo la clave
     (`401` sin clave o inválida).
   - La página muestra: peticiones, `error_rate`, p50 y p95 contra el SLO, costo acumulado, costo promedio por
     petición, rutas de modelo, llamadas con caché y PII por tipo. Sin clave válida no muestra cifras.
   - La clave nunca va en el código de la página.
6. **Métricas de negocio en `/metrics`** (dueño: `observability`). Se agregan a las que ya existen:
   - `questions_by_department`: preguntas por departamento (objeto nombre → número).
   - `tool_usage`: usos por herramienta (objeto nombre → número).
   - `cache_hit_pct`: porcentaje de peticiones respondidas con caché (0 a 100).
   - `pii_by_type`: detecciones por tipo (objeto `CORREO`, `RFC`... → número).
7. **LangSmith** (dueño: `observability`).
   - Cada traza lleva como metadatos `request_id`, `client`, `route`, `model` y `cost_usd`.
   - Con `HIDE_INPUTS` y `HIDE_OUTPUTS` en `true` no va el texto de la pregunta ni de la respuesta.
8. **Documentación** (dueño: `architect`; la fila de compliance, `security`).
   - ADR nuevos en `doc/adr/`: `0013` PII, `0014` validación de salida, `0015` reintentos, `0016` tablero.
   - `doc/architecture.md` con un diagrama `mermaid` de cómo queda en producción.
   - `doc/cost-analysis.md`: costo por petición, efecto de los reintentos y de las palancas. `costs` entrega las
     cifras; `architect` lo redacta, porque `costs` no escribe en `doc/`.
   - `doc/security-analysis.md`: tabla con control, riesgo que cubre, dónde está en el código y cómo se comprueba.
   - `doc/compliance-checklist.md`: una fila por cada regla nueva (puntos 1 a 4 y 7).
9. **CI** (dueño: `deploy`). `.github/workflows/ci.yml` se queda igual. Si cambia el contenedor, el job `docker`
   tiene que seguir pasando.

Pruebas unitarias (dueño: `qa-unit`): una por cada regla de los puntos 1 a 7, con el modelo y la espera simulados.

## Pruebas de punta a punta (las agrega `qa-e2e`)

- La página `/dashboard` abre sin clave; al escribir la clave en la página muestra las cifras de peticiones y
  `error_rate`.
- Sin clave, el tablero no muestra cifras.
- Una pregunta con un correo no lo deja visible en la respuesta de la página.

## Configuración nueva

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MAX_ANSWER_CHARS` | `2000` | Largo máximo de una respuesta válida |
| `MODEL_MAX_RETRIES` | `2` | Reintentos ante timeout o 5xx del gateway |
| `WEB_CONCURRENCY` | `2` | Workers de uvicorn en el contenedor |

## Cómo se comprueba

- `verification unit`, `contract`, `qa`, `e2e` y `evaluate`, como en la sesión 4. El contrato de esta sesión es
  `verification/contract/test_contract_05.py`. Para el tablero: `/dashboard` sin clave da `200` y su HTML no trae
  la clave de la fábrica; `/metrics` sin clave da `401` y con clave da `200`.
- Una persona aprueba el plan y aprueba publicar.
- `uv run python -m verification production <url>`: la prueba de humo.
- `LOAD_API_KEY=<clave> uv run python -m verification load <url>`: 50 peticiones, 10 a la vez; falla si el
  `error_rate` pasa de 1 %.
- `COST_API_KEY=<clave> uv run python scripts/cost_real.py <url_linea_base> <url_normal>`: costo real de las dos
  configuraciones en `output/cost-real.md`.
