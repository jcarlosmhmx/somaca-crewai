# SOMACA – Sistema Multiagente para campañas de Meta Ads (Fase 3)

Prototipo con **CrewAI** para el Hotel Parador Monte Carmelo.
Repositorio: https://github.com/jcarlosmhmx/somaca-crewai
Materia: Inteligencia Artificial – Maestría en Big Data e IA, Universidad Anáhuac Puebla.

## Arquitectura

`Analista de Mercado → [Campaña Cultural ∥ Campaña Romántica] → Broker de Presupuesto → Monitor Global`
(`Process.sequential` con contexto entre tareas; las dos campañas con `async_execution`).

## Estructura

| Ruta | Contenido |
|---|---|
| `main.py` | Punto de entrada |
| `config.py` | LLM y semilla desde `.env` |
| `agents.py` / `tasks.py` / `crew.py` | Agentes, tareas y ensamble del Crew |
| `tools/` | Herramientas `@tool` |
| `data/` | Datos del dominio y del simulador (JSON/CSV, semilla fija) |
| `logs/` | Log de la corrida final (`demo_final.log`) |
| `docs/` | Bloques A–D y diagrama del flujo |
| `notebooks/` | Notebook de demostración (Colab) |
| `tests/` | Pruebas de las herramientas |

## Instalación

Requiere Python 3.10–3.13.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y llena la llave de tu proveedor
python main.py
```

## Equipo

Juan Carlos Morales · Arantza Solano · Ingrid Orellán · Víctor Luna

## Datos y simulador

- `data/*.json`: datos del dominio (PEAS) y restricciones. `python simulador.py` genera `data/metricas_simuladas.csv` (semilla `SIM_SEED`, 13 por defecto, 96 filas: 48 iteraciones × 2 campañas).
- Fuentes, supuestos y hallazgos: `docs/supuestos_datos.md`.
- Pruebas: `python -m pytest tests`.
