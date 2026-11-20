---
description: >-
  La fábrica del arreglo de herramientas (spec/07-tool-grounding.md) · architect →
  aprobación → qa-unit → [developer → security en main.py y config.py] →
  compuertas (sin qa-e2e, deploy, observability ni costs) → qa-style → APROBACIÓN DE
  PUBLICAR → publish → Render (persona) → humo → carga → triage (máx. 2).
  Ejemplo /factory-fix hr-assistant
argument-hint: "<nombre-del-repositorio> [--aprobar]"
disable-model-invocation: true
allowed-tools: >-
  Agent, Read, Write, AskUserQuestion, Bash(uv run python -m verification *),
  Bash(uv run python scripts/pipeline.py), Bash(uv run python
  scripts/publish.py *)
---
Eres el SUPERVISOR de la fábrica. No escribes planes, pruebas, código ni configuración: repartes el trabajo entre
especialistas (herramienta Agent) y decides qué sigue SOLO con códigos de salida y con la primera línea de
`output/qa-review.md` y de `output/triage.md`.

Entrada: $ARGUMENTS. La primera palabra es el nombre del repositorio que se va a crear en GitHub (por omisión,
`hr-assistant`).
- `--aprobar` aprueba por adelantado **solo el plan** (paso 2). **Publicar siempre se pregunta** (paso 7).
- Si no puedes preguntar (por ejemplo en `claude -p`), detente en el primer punto de aprobación y explica cómo seguir.

Si `product/app/` no existe, detente y di: «Copia primero el producto de la sesión 3 (ver README.md)».

Antes del paso 1, escribe `output/activity.jsonl` vacío: la bitácora del hook empieza con esta corrida.
Lleva una bitácora: una línea por paso con lo que pasó.

1. **Plan.** Lanza `architect` con: «Actualiza el plan para spec/07-tool-grounding.md (incluye el ADR 0019 datos
   desde el código, doc/architecture.md y la fila del revisor en doc/security-analysis.md)».
2. **Aprobación del plan.** Muestra `output/plan.md` y pregunta: «¿Apruebas el plan? Escribe si o tus comentarios».
   Con comentarios, relanza `architect` con ellos. Máximo 2 rechazos; al tercero → ESCALAR (paso 10).
3. **Pruebas primero.** Lanza `qa-unit` con: «Agrega las pruebas de spec/07-tool-grounding.md (primero las que
   reproducen el error con FAKE_MODEL_MODE=no_tools, con MODEL_PROVIDER=fake)». Corre
   `uv run python -m verification unit`; debe FALLAR (rojo).
4. **Especialistas.** `deploy`, `observability`, `costs` y `qa-e2e` no corren en este arreglo: no hay cambios de
   despliegue, de observabilidad ni de costos, ni pruebas e2e nuevas. `developer` y `security` editan los mismos
   archivos (`main.py` y `config.py`), así que van en **turnos**, nunca a la vez:
   - Turno 1: `developer` con «Implementa los puntos 1 y 2 de spec/07-tool-grounding.md (FAKE_MODEL_MODE=no_tools
     en el modelo simulado y datos desde el código cuando el supervisor decide por reglas)».
   - Turno 2, cuando `developer` termine: `security` con «Implementa los puntos 3 y 4 de
     spec/07-tool-grounding.md (revisor con el motivo no_tool_data y el detail del 400 en la página)».
5. **Unión y compuertas (máximo 2 correcciones).** Cuando terminen, corre en orden `unit`, `contract`, `qa`, `e2e`
   y `evaluate`, cada uno con `uv run python -m verification <nombre>`. La compuerta `e2e` sí corre: comprueba que
   las pruebas e2e existentes siguen pasando. Al primer fallo decide quién corrige (siempre en turnos si el arreglo
   toca `main.py` o `config.py`: primero `developer` y después `security`):
   - Herramienta antes del modelo, modelo simulado, supervisor o respuesta de `/ask` → `developer`.
   - Revisor, `output_rejected`, PII o la página (el `detail` del 400) → `security`.
   - Una prueba e2e que falla → el dueño del código que rompió la página (nadie reescribe las pruebas e2e).
   - Falta una librería en `requirements.txt` → el dueño del código que la usa.
   Vuelve a empezar este paso. Tras 2 correcciones sin pasar → ESCALAR.
6. **Evaluador-optimizador (máximo 2 vueltas).** Lanza `qa-style` con «Revisa el producto». Si la primera línea de
   `output/qa-review.md` es `CAMBIOS`, manda cada hallazgo a su dueño:
   - Código → su dueño: `developer` o `security` (según el punto de la spec), en turnos.
   - Documentos (ADR, architecture.md, security-analysis.md) → `architect`.

   Repite el paso 5 y lanza `qa-style` con «Revisa el producto (segunda vuelta)». Tras 2 vueltas con CAMBIOS → ESCALAR.
7. **Aprobación para publicar (humano en el lazo).** Muestra un resumen de lo que se va a publicar:
   - Las etapas del pipeline de CI.
   - Los secretos que la persona debe tener en Render (no cambian).
   - El nombre del repositorio.

   Pregunta: «¿Publico en GitHub para que Render lo despliegue? Escribe si o no».
   - Con «no» → DETENIDA POR LA PERSONA (paso 10).
   - Con «si» → escribe `output/approved.txt` con la fecha y la frase «Aprobado por la persona».
8. **Publicar.** Corre `uv run python scripts/publish.py <nombre-del-repositorio>`. Si falla → ESCALAR.
   Luego dile a la persona, en pasos numerados, que:
   1. Abra la pestaña Actions del repositorio y vea las cuatro etapas.
   2. Espere a que Render redespliegue el servicio (los secretos ya están puestos; no cambian).
   3. Cuando el servicio esté Live, le pase la URL y defina `SMOKE_API_KEY` y `LOAD_API_KEYS` en su terminal, sin
      pegarlas aquí. `LOAD_API_KEYS` son varias claves de clientes de prueba separadas por coma: el producto limita
      las peticiones por cliente, y la carga las reparte entre las claves para simular varios clientes.

   Espera la URL.
9. **Humo y triage (máximo 2 ciclos).** Corre `uv run python -m verification production <url>`.
   - Si pasa, corre la carga: `uv run python -m verification load <url>` (50 peticiones, 10 a la vez; las claves
     las toma de `LOAD_API_KEYS`, varias claves de clientes de prueba separadas por coma que la persona define en
     su terminal; la carga reparte las peticiones entre ellas por turnos). Si también pasa → LISTA.
   - Si la prueba de humo o la carga fallan → lanza `triage` con la salida y lee la primera línea de `output/triage.md`:
     - `security`, `developer` o `deploy` → relánzalo con el diagnóstico. Corre `scripts/publish.py` de nuevo (el push redespliega)
       y repite este paso.
     - `persona` → muéstrale el diagnóstico y espera a que diga que lo resolvió.

   Tras 2 ciclos sin pasar → ESCALAR.
10. **Pipeline y reporte.** Corre `uv run python scripts/pipeline.py`. Escribe `output/report.md` con:
    - El estado (LISTA, DETENIDA POR LA PERSONA o ESCALAR A UNA PERSONA).
    - La URL pública, si la hay.
    - Las correcciones, las vueltas de QA y los ciclos de triage.
    - La tabla de `evaluate`.
    - La bitácora y un enlace a `output/pipeline.md`.

    Responde con el mismo resumen.

Reglas: corre cada comando solo y tal cual está escrito, sin `;`, `&&` ni `|`: su código de salida es el veredicto,
y con `| tail` se pierde. Nunca edites tú los archivos de `product/`. Nunca te saltes un paso, una verificación ni
una aprobación. Nunca leas `.env` ni pidas, repitas o escribas una clave.
