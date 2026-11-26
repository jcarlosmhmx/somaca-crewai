"""Ensamble del Crew: Process.sequential con contexto entre tareas.

Flujo: Analista → [Cultural ∥ Romántica (async)] → Broker → Monitor.
Se eligió sequential (no hierarchical) porque las dependencias de datos son claras y un
manager LLM adicional encarecería la corrida sin aportar valor.

Fase final: cada tarea lleva un guardrail determinista (guardrails.py) y el Crew publica sus
pasos en el bus de eventos (eventos.py) para que la API los transmita en vivo a la GUI:
- herramientas: cada agente recibe su propia copia, marcada con su rol;
- delegaciones e inicio de tareas: oyentes del bus de eventos de CrewAI;
- respuestas finales y tareas completadas: step_callback y task_callback.
"""
import os
import threading

from crewai import Crew, Process

import eventos
from agents import crear_agentes
from escenario import entradas  # noqa: F401 (se reexporta para main.py y las pruebas)
from guardrails import crear_guardrails
from tasks import crear_tareas


# --------------------------------------------------------------------------- observabilidad
def _paso_callback(rol: str):
    """step_callback por agente: publica la respuesta final (AgentFinish) o el paso intermedio."""
    def cb(paso):
        datos = {
            "agente": rol,
            "clase": type(paso).__name__,
            "pensamiento": eventos.recortar(getattr(paso, "thought", "") or "", 600),
        }
        herramienta = getattr(paso, "tool", None)
        if herramienta and "coworker" not in str(herramienta).lower():
            datos["herramienta"] = str(herramienta)
        salida = getattr(paso, "output", None) or getattr(paso, "result", None)
        if salida:
            datos["salida"] = eventos.recortar(salida, 600)
        eventos.emitir("paso", **datos)
    return cb


def _tarea_callback(salida):
    # Salida COMPLETA: la API la guarda y la auditoría necesita el JSON íntegro.
    eventos.emitir("tarea_completada", tarea=getattr(salida, "name", None) or "",
                   agente=str(getattr(salida, "agent", "")), salida=str(getattr(salida, "raw", salida)))


def _herramientas_por_agente(agente) -> None:
    """Da a cada agente copias de sus herramientas que marcan el hilo con su rol."""
    copias = []
    for t in agente.tools or []:
        func = getattr(t, "func", None)
        if func is None:
            copias.append(t)
            continue
        copias.append(t.model_copy(update={"func": eventos.con_agente(func, agente.role)}))
    agente.tools = copias


_oyentes = {"instalados": False}
_oyentes_lock = threading.Lock()


def _argumentos(args) -> dict:
    if isinstance(args, dict):
        return args
    try:
        import json
        return json.loads(args)
    except (TypeError, ValueError):
        return {"texto": str(args)}


def _instalar_oyentes() -> None:
    """Oyentes del bus de eventos de CrewAI (una sola vez por proceso; de mejor esfuerzo)."""
    with _oyentes_lock:
        if _oyentes["instalados"]:
            return
        _oyentes["instalados"] = True
    try:
        from crewai.events import (TaskStartedEvent, ToolUsageFinishedEvent, ToolUsageStartedEvent,
                                   crewai_event_bus)
    except ImportError:
        return

    @crewai_event_bus.on(TaskStartedEvent)
    def _tarea_iniciada(_fuente, ev):
        tarea = getattr(ev, "task", None)
        agente = getattr(getattr(tarea, "agent", None), "role", None)
        eventos.emitir("tarea_iniciada", tarea=getattr(tarea, "name", None) or "", agente=agente)

    @crewai_event_bus.on(ToolUsageStartedEvent)
    def _delegacion_inicia(_fuente, ev):
        if "coworker" not in (ev.tool_name or "").lower():
            return
        a = _argumentos(ev.tool_args)
        pregunta = a.get("question") or a.get("task") or a.get("texto") or ""
        eventos.emitir("paso", agente=ev.agent_role, clase="AgentAction", herramienta=ev.tool_name,
                       delegacion=True, pensamiento="",
                       entrada=eventos.recortar(f"{a.get('coworker', '')}: {pregunta}", 500))

    @crewai_event_bus.on(ToolUsageFinishedEvent)
    def _delegacion_responde(_fuente, ev):
        if "coworker" not in (ev.tool_name or "").lower():
            return
        a = _argumentos(ev.tool_args)
        eventos.emitir("paso", agente=a.get("coworker") or "Compañero", clase="AgentFinish", delegacion=True,
                       pensamiento="", salida=eventos.recortar(ev.output, 600))


def build_crew(llm=None, log_file: str | None = None, con_guardrails: bool = True) -> Crew:
    _instalar_oyentes()
    agentes = crear_agentes(llm)
    for agente in agentes.values():
        agente.step_callback = _paso_callback(agente.role)
        _herramientas_por_agente(agente)
    g = crear_guardrails(entradas()["presupuesto_restante"]) if con_guardrails else None
    tareas = crear_tareas(agentes, g)
    return Crew(
        agents=list(agentes.values()),
        tasks=tareas,
        process=Process.sequential,
        verbose=True,
        task_callback=_tarea_callback,
        output_log_file=log_file or os.getenv("LOG_FILE", "logs/corrida.log"),
    )
