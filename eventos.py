"""Bus mínimo de eventos de la corrida (sin dependencias externas).

Los agentes, las herramientas, los guardrails y los callbacks de CrewAI publican aquí lo que
ocurre ("agente pensó", "herramienta X devolvió Y", "guardrail rechazó"). La API se suscribe y
reenvía cada evento a la GUI por Server-Sent Events (SSE), de modo que el usuario ve en vivo
cómo se transfieren el contexto, las tareas y la delegación entre agentes.

Si nadie está suscrito (por ejemplo, al correr `python main.py`), emitir() no hace nada.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

Sink = Callable[[dict], None]

_lock = threading.Lock()
_sinks: list[Sink] = []


def suscribir(sink: Sink) -> None:
    with _lock:
        _sinks.append(sink)


def desuscribir(sink: Sink) -> None:
    with _lock:
        if sink in _sinks:
            _sinks.remove(sink)


def emitir(tipo: str, **datos: Any) -> None:
    """Publica un evento. Nunca lanza excepciones: un fallo de la GUI no debe tumbar el Crew."""
    evento = {"ts": time.time(), "tipo": tipo, **datos}
    with _lock:
        sinks = list(_sinks)
    for s in sinks:
        try:
            s(evento)
        except Exception:  # noqa: BLE001 - la observabilidad es de mejor esfuerzo
            pass


_local = threading.local()


def agente_actual() -> str | None:
    """Rol del agente que está ejecutando una herramienta en este hilo (o None)."""
    return getattr(_local, "agente", None)


def con_agente(func: Callable, rol: str) -> Callable:
    """Envuelve la función de una herramienta para que sus eventos lleven el rol del agente.

    CrewAI ejecuta cada herramienta en el hilo del agente que la llamó (las tareas async corren en
    su propio hilo), así que basta con marcar el hilo durante la llamada.
    """
    def envuelta(*args, **kwargs):
        previo = getattr(_local, "agente", None)
        _local.agente = rol
        try:
            return func(*args, **kwargs)
        finally:
            _local.agente = previo
    envuelta.__name__ = getattr(func, "__name__", "herramienta")
    envuelta.__doc__ = getattr(func, "__doc__", None)
    return envuelta


def recortar(texto: Any, n: int = 1200) -> str:
    """Convierte a texto y recorta para que los eventos no saturen la GUI."""
    t = str(texto)
    return t if len(t) <= n else t[:n] + f"… (+{len(t) - n} caracteres)"
