# Reto · HR Assistant multiagente en producción

Parte del producto del reto de producción (`spec/05-production-ready.md`, ya en producción). Cada pregunta pasa por
cuatro etapas en orden: **guardián, supervisor, especialista y revisor**. El guardián y el revisor son código. El
supervisor decide con reglas y solo llama al modelo pequeño si la pregunta no es clara.

## Lo que debe hacer

1. **Guardián** (dueño: `security`).
   - Corre antes que todo, también antes del enmascarado de PII y de cualquier llamada al modelo.
   - Bloquea la inyección de prompt con una lista de frases, sin importar mayúsculas ni acentos. Por ejemplo:
     «ignora tus instrucciones», «prompt del sistema» y «actúa como».
   - Si la pregunta coincide, `/ask` responde `400` con `"La pregunta no se puede procesar."` **sin llamar al
     modelo** (ni al pequeño del supervisor).
   - Registra `input_blocked` con el motivo (la frase de la lista que coincidió), **nunca el texto de la pregunta**.
   - Si pasa, enmascara la PII con `pii.py`, como hoy (punto 1 de la spec 05).
2. **Supervisor** (dueño: `developer`).
   - Elige el especialista **con reglas, en este orden** (gana la primera que aplique):
     1. Si la pregunta trae un id `EMP-xxxx`, va al de empleado.
     2. Si nombra un departamento del directorio, va al de departamento, aunque la pregunta diga «quién».
     3. Si nombra a una persona, va al de empleado.
     4. Si ninguna aplica, le pregunta al modelo pequeño cuál elegir (`employee` o `department`). Si el modelo
        responde algo distinto, va al de empleado.
   - Registra la decisión con el evento `supervisor_decision`: `specialist` y `method` (`rules` o `model`).
3. **Especialistas** (dueño: `developer`).
   - Salen del agente actual y cada uno tiene su prompt corto.
   - El de **empleado** solo tiene la herramienta `get_employee`. El de **departamento** solo tiene
     `search_by_department`. Ninguno puede llamar a la herramienta del otro.
4. **Revisor** (dueño: `security`).
   - Corre después del especialista. Usa `output_guard.py` (punto 2 de la spec 05) y enmascara la PII como hoy.
   - Si la respuesta nombra un id `EMP-xxxx` que no está en el directorio, cambia la respuesta por
     `"No pude generar una respuesta segura. Intenta de nuevo."` y registra `output_rejected` con el motivo
     `invented_id` (nunca el texto ni el id).
5. **Respuesta de `/ask`** (dueño: `developer`). Agrega a lo que ya devuelve:
   - `specialist`: `"employee"` o `"department"`.
   - `agents`: la lista de etapas que corrieron, en orden. En una pregunta normal:
     `["guard", "supervisor", "employee", "reviewer"]` (o `"department"` en el tercer lugar).
6. **Auditoría** (dueño: `security`). Los argumentos de las herramientas en el evento `audit` van enmascarados con
   `pii.py`. Hoy van sin enmascarar.
7. **Observabilidad** (dueño: `observability`).
   - En LangSmith, un run por etapa debajo del run de la petición: `agent.guard`, `agent.supervisor`,
     `agent.employee` o `agent.department`, y `agent.reviewer`.
   - `/metrics` agrega: `by_specialist` (objeto especialista → número), `supervisor_decisions` (objeto `rules` /
     `model` → número) e `input_blocked` (número de preguntas bloqueadas por el guardián).
   - El tablero (`/dashboard`) también las muestra.
8. **Despliegue** (dueño: `deploy`). Quita `RATE_LIMIT_PER_MINUTE` de `render.yaml`. El límite se queda en `30` por
   omisión en el código.
9. **Documentación** (dueño: `architect`).
   - ADR nuevos en `doc/adr/` (el `0016` todavía no existe y se escribe en esta corrida): `0016` tablero, `0017` pipeline multiagente y `0018` guardián.
   - `doc/architecture.md` con el diagrama `mermaid` del pipeline de cuatro etapas.
   - `doc/security-analysis.md`: filas nuevas para el guardián, el revisor con `invented_id` y la auditoría
     enmascarada (control, riesgo, dónde está en el código y cómo se comprueba).

Pruebas unitarias (dueño: `qa-unit`): una por cada regla de los puntos 1 a 7, con el modelo simulado. **No hay
pruebas de punta a punta nuevas**: ya estamos en el tope de 6.

## Configuración

No hay variables nuevas. `RATE_LIMIT_PER_MINUTE` sale de `render.yaml` y se queda en `30` por omisión.

## Cómo se comprueba

- `verification unit`, `contract`, `qa`, `e2e` y `evaluate`. El contrato de esta spec es
  `verification/contract/test_contract_06.py`: una pregunta con «ignora tus instrucciones» da `400`; «¿Quién es
  EMP-0004?» da `200` con `specialist` igual a `employee` y `agents` con las cuatro etapas; «¿Quién trabaja en
  Tecnología?» da `200` con `specialist` igual a `department`; `/metrics` trae `by_specialist`,
  `supervisor_decisions` e `input_blocked`.
- Una persona aprueba el plan y aprueba publicar.
- `uv run python -m verification production <url>`: la prueba de humo.
- `LOAD_API_KEYS=<clave1,clave2,...> uv run python -m verification load <url>`: 50 peticiones, 10 a la vez,
  repartidas entre las claves; falla si el `error_rate` pasa de 1 %.
