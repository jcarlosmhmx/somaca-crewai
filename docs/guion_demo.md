# Guion de la demostración en vivo (5 minutos)

**Objetivo ante el comité:** mostrar un caso realista, el razonamiento multiagente transparente (logs en vivo, contexto, delegación y guardrails) y el lazo Human-in-the-Loop (auditar, ver alertas de veto y aprobar o ajustar).

## Preparación (antes de la sesión)

1. `python -m pytest -q` pasa en la laptop de la demo.
2. `.env` con `OPENAI_API_KEY` y saldo; `curl localhost:8000/salud` → `"llave_configurada": true`.
3. Hacer **una corrida de ensayo** completa el mismo día, para tenerla en el Historial por si la corrida en vivo tarda.
4. API y Streamlit abiertos; navegador con zoom al 125 % y la pestaña **Resumen** visible.
5. Plan B listo: modo **Respaldo grabado (Fase 3)** en la barra lateral (no necesita internet).

## Minuto a minuto

| Tiempo | Pantalla | Quién | Qué se dice y se hace |
|---|---|---|---|
| 0:00–0:40 | Resumen | Ingrid | Caso: corte del 14-nov, quedan 500 MXN. Cultural tiene CPL de 31.25 MXN (fuera de meta) y Romántica ROAS de 4.32x. «¿Cómo repartimos lo que queda?». Señalar la etiqueta *Datos sintéticos* y las restricciones del PEAS. |
| 0:40–0:55 | Flujo de agentes | Juan Carlos | Pulsar **▶ Ejecutar SOMACA** (modo CrewAI en vivo). Explicar el flujo: Analista → Cultural ∥ Romántica → Broker → Monitor. |
| 0:55–2:30 | Flujo de agentes | Juan Carlos | Narrar el registro en vivo: 🔧 herramientas con cifras reales, 📋 paso de contexto entre tareas, 🤝 **delegación del Broker**, 🛡️ **guardrails** (si alguno rechaza, mostrar el reintento: es la evidencia de AI Safety). |
| 2:30–3:30 | Auditoría y decisión | Arantza | Veredicto del Monitor. **Alertas**: «aprobado con observaciones», metas no alcanzadas. Tabla PEAS calculada en Python: recomendación frente a no optimizar (más leads, menor CPL). Guardrails re-ejecutados: todos ✅. |
| 3:30–4:30 | Auditoría y decisión | Víctor | **Human-in-the-Loop**: elegir *Ajustar*, mover el control a 350/150 → aparece «Inválido: excede ±20 %» (el servidor lo rechazaría). Regresar a un reparto válido o *Aprobar*: el sistema exige marcar «revisé las observaciones» y escribir un comentario. Registrar decisión. |
| 4:30–5:00 | Auditoría / Historial | Víctor | Descargar el reporte `.md` y mostrar la decisión en el Historial: «SOMACA recomienda, la persona decide y queda registro». |

## Si algo falla

| Situación | Acción (≤ 15 s) |
|---|---|
| La corrida en vivo tarda más de 2:30 | Seguir narrando el registro; en la barra lateral, abrir la corrida de ensayo del Historial para la parte de auditoría. |
| Error de red o de llave (`corrida_fallida`) | Barra lateral → **Respaldo grabado (Fase 3)**, velocidad 2× → Ejecutar. Decirlo abiertamente: «es la corrida real del 30 de octubre reproducida; las herramientas y los guardrails se ejecutan de verdad». |
| La API no responde | Reiniciar: `uvicorn api.main:app --port 8000`. La GUI se reconecta sola. |

## Frases clave

- «Cada número que dice un agente viene de una herramienta; si inventa un segmento o un reparto que no cuadra, el guardrail lo rechaza y el agente reintenta».
- «El Monitor no tiene la última palabra: el servidor vuelve a validar y la persona decide».
- «La mejora proyectada es modesta (+1.5 leads); lo que demostramos es una arquitectura auditable, no una promesa de optimización».
