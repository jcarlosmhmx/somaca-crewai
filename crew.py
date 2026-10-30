"""Ensamble del Crew: Process.sequential con contexto entre tareas.

Flujo: Analista → [Cultural ∥ Romántica (async)] → Broker → Monitor.
Se eligió sequential (no hierarchical) porque las dependencias de datos son claras y un
manager LLM adicional encarecería la corrida sin aportar valor.
"""
import os
from datetime import date, timedelta

from crewai import Crew, Process

import simulador as sim
from agents import crear_agentes
from tasks import crear_tareas


def entradas() -> dict:
    """Variables de entrada del caso de prueba (se interpolan en las tareas)."""
    cfg = sim.cargar("restricciones_objetivos.json")
    ipd = cfg["iteraciones_por_dia"]
    corte = cfg["iteracion_corte"]
    inicio = date.fromisoformat(cfg["fecha_inicio"])
    ultimo = inicio + timedelta(days=cfg["duracion_dias"] - 1)
    primer_restante = inicio + timedelta(days=corte // ipd)
    filas = sim.simular(sim.semilla())
    restante = sum(
        [r for r in filas if r["campana"] == c and r["iteracion"] == corte][0]["presupuesto_disponible"]
        for c in sim.CAMPANAS
    )
    return {
        "iteracion_corte": corte,
        "fecha_corte": (inicio + timedelta(days=(corte - 1) // ipd)).isoformat(),
        "primer_dia_restante": primer_restante.isoformat(),
        "ultimo_dia": ultimo.isoformat(),
        "presupuesto_restante": round(restante, 2),
        "semilla": sim.semilla(),
    }


def build_crew(llm=None, log_file: str | None = None) -> Crew:
    agentes = crear_agentes(llm)
    tareas = crear_tareas(agentes)
    return Crew(
        agents=list(agentes.values()),
        tasks=tareas,
        process=Process.sequential,
        verbose=True,
        output_log_file=log_file or os.getenv("LOG_FILE", "logs/corrida.log"),
    )
