# Arreglo · Los especialistas deben usar su herramienta

Parte del producto multiagente (`spec/06-multiagent.md`, ya en producción). Error encontrado en producción: el modelo
pequeño responde con texto como «necesito utilizar la herramienta get_employee» en vez de pedir la herramienta con el
JSON, y el agente toma ese texto como respuesta final. En LangSmith, `agent.employee` tiene una sola `model_call` y
ninguna herramienta. Las pruebas no lo ven porque el modelo simulado siempre pide la herramienta.

## Lo que debe hacer

1. **Reproducir el error** (dueño: `developer`).
   - El modelo simulado acepta `FAKE_MODEL_MODE=no_tools`. En ese modo nunca pide herramientas y responde con texto
     que menciona la herramienta (por ejemplo «necesito utilizar la herramienta get_employee»).
   - Solo vale con `MODEL_PROVIDER=fake`. Con otro proveedor se ignora.
2. **Datos desde el código** (dueño: `developer`).
   - Cuando el supervisor decide **por reglas**, ya conoce el dato: el id `EMP-xxxx`, el departamento o la persona.
     El código llama a la herramienta del especialista **antes** del modelo y le pasa el resultado como
     `"Resultado de la herramienta: ..."`. El modelo solo redacta la respuesta.
   - `tools_used` lleva esa herramienta (`get_employee` o `search_by_department`).
   - Si el supervisor decidió **con el modelo** (`method` igual a `model`), el especialista sigue como hoy: el modelo
     pide la herramienta.
3. **Revisor** (dueño: `security`).
   - Si `tools_used` va vacío, o la respuesta menciona `get_employee` o `search_by_department`, cambia la respuesta
     por `"No encontré datos para responder. Pregunta por un id como EMP-0001 o por un departamento."` y registra
     `output_rejected` con el motivo `no_tool_data` (nunca el texto de la respuesta).
   - Solo el motivo `no_tool_data` usa ese mensaje. Los demás motivos (por ejemplo `invented_id`) siguen con
     `"No pude generar una respuesta segura. Intenta de nuevo."`.
4. **Página** (dueño: `security`). Con un `400`, la página muestra el `detail` que mandó el servidor, no un error
   genérico.
5. **Pruebas** (dueño: `qa-unit`). Primero las que reproducen el error con `FAKE_MODEL_MODE=no_tools`: una por cada
   regla de los puntos 1 a 4. Tienen que **fallar antes del arreglo**. No hay pruebas de punta a punta nuevas.
6. **Documentación** (dueño: `architect`).
   - ADR `0019` datos desde el código, en `doc/adr/`.
   - `doc/architecture.md` actualizado (la herramienta se llama antes del modelo cuando el supervisor decide por
     reglas).
   - La fila del revisor en `doc/security-analysis.md`, con el motivo `no_tool_data`.

## Configuración

Variable nueva solo para pruebas: `FAKE_MODEL_MODE` (`no_tools`; vacía por omisión). Solo se lee con
`MODEL_PROVIDER=fake`. No va en `render.yaml`.

## Cómo se comprueba

- `verification unit`, `contract`, `qa`, `e2e` y `evaluate`. El contrato de esta spec es
  `verification/contract/test_contract_07.py`: con `MODEL_PROVIDER=fake` y `FAKE_MODEL_MODE=no_tools`, «¿Quién es
  EMP-0004?» da `200`, `tools_used` trae `get_employee` y la respuesta no menciona `get_employee`; «¿Quién trabaja en
  Tecnología?» da `200`, `tools_used` trae `search_by_department` y la respuesta no menciona `search_by_department`.
- Una persona aprueba el plan y aprueba publicar.
- `uv run python -m verification production <url>`: la prueba de humo.
- `LOAD_API_KEYS=<clave1,clave2,...> uv run python -m verification load <url>`: 50 peticiones, 10 a la vez,
  repartidas entre las claves; falla si el `error_rate` pasa de 1 %.
