"""API REST + SSE de SOMACA (FastAPI). Capa delgada sobre api/servicio.py.

Arranque:  uvicorn api.main:app --reload --port 8000
Documentación interactiva (OpenAPI):  http://localhost:8000/docs

Comunicación con la GUI:
- REST para comandos y consultas (iniciar corrida, auditoría, decisión humana).
- Server-Sent Events (GET /ejecuciones/{id}/eventos) para el monitor en vivo: el servidor empuja
  cada paso de los agentes (herramientas, delegaciones, guardrails, tareas) en cuanto ocurre.
"""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

import escenario
import guardrails as g
from api import servicio
from config import llave_configurada, nombre_modelo

app = FastAPI(
    title="SOMACA API",
    version="1.0.0",
    description="Sistema multiagente (CrewAI) para repartir el presupuesto de Meta Ads del Hotel Parador "
                "Monte Carmelo, con supervisión humana (Human-in-the-Loop). Datos sintéticos.",
)


# --------------------------------------------------------------------------- modelos (Pydantic)
class NuevaEjecucion(BaseModel):
    modo: Literal["crewai", "replay"] = Field("crewai", description="crewai = Crew real con el LLM de .env; "
                                                                     "replay = respaldo grabado de la Fase 3")
    velocidad: float | None = Field(None, gt=0, le=20, description="Solo replay: 1 = tiempo original, 2 = doble")


class Decision(BaseModel):
    accion: Literal["aprobar", "ajustar", "rechazar"]
    responsable: str = Field(..., min_length=1, max_length=80)
    comentario: str = Field("", max_length=2000)
    acepta_observaciones: bool = False
    cultural_mxn: float | None = Field(None, ge=0)
    romantica_mxn: float | None = Field(None, ge=0)


def _404(eid: str):
    raise HTTPException(404, f"No existe la ejecución {eid}")


# --------------------------------------------------------------------------- rutas
@app.get("/salud", tags=["sistema"])
def salud():
    return {"ok": True, "modelo": nombre_modelo(), "llave_configurada": llave_configurada(),
            "ejecucion_activa": servicio.ejecucion_activa(), "replay_disponible": servicio.REPLAY.exists()}


@app.get("/escenario", tags=["datos"])
def get_escenario():
    """Vista Resumen: entradas del corte, métricas por campaña, objetivos, restricciones y pesos PEAS."""
    return escenario.resumen()


@app.get("/escenario/serie", tags=["datos"])
def get_serie():
    """Gasto y leads acumulados por iteración hasta el corte (sensores del PEAS)."""
    return escenario.serie()


@app.get("/escenario/linea-base", tags=["datos"])
def get_linea_base():
    """Proyección sin optimizar (mismo segmento y saldo actual) para comparar recomendaciones."""
    return escenario.linea_base()


@app.get("/reparto/validar", tags=["datos"])
def validar_reparto(cultural: float = Query(..., ge=0), romantica: float = Query(..., ge=0)):
    """Vista previa de la validación determinista (la misma que usan el Broker, el Monitor y la decisión)."""
    from tools import logica
    return logica.validar_reparto(cultural, romantica)


@app.post("/ejecuciones", status_code=202, tags=["ejecuciones"])
def post_ejecucion(body: NuevaEjecucion):
    """Lanza el Crew en segundo plano y devuelve 202 con el identificador de la ejecución."""
    try:
        return servicio.iniciar(body.modo, body.velocidad)
    except servicio.Ocupado as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.get("/ejecuciones", tags=["ejecuciones"])
def get_ejecuciones():
    return servicio.listar()


@app.get("/ejecuciones/{eid}", tags=["ejecuciones"])
def get_ejecucion(eid: str):
    try:
        return servicio.obtener(eid)
    except KeyError:
        _404(eid)


@app.get("/ejecuciones/{eid}/eventos", tags=["ejecuciones"])
def get_eventos(eid: str, desde: int = Query(0, ge=0), last_event_id: str | None = Header(None)):
    """Flujo SSE (text/event-stream). Admite reconexión con el encabezado Last-Event-ID."""
    try:
        servicio.obtener(eid)
    except KeyError:
        _404(eid)
    inicio = int(last_event_id) if (last_event_id or "").isdigit() else desde
    return StreamingResponse(servicio.flujo_sse(eid, inicio), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/ejecuciones/{eid}/eventos.json", tags=["ejecuciones"])
def get_eventos_json(eid: str, desde: int = Query(0, ge=0)):
    """Alternativa por sondeo (polling) a SSE."""
    return servicio.eventos_desde(eid, desde)


@app.get("/ejecuciones/{eid}/auditoria", tags=["human-in-the-loop"])
def get_auditoria(eid: str):
    """Salidas por tarea, guardrails re-ejecutados, validación del reparto, evaluación PEAS y alertas."""
    try:
        return servicio.auditoria(eid)
    except KeyError:
        _404(eid)


@app.post("/ejecuciones/{eid}/decision", tags=["human-in-the-loop"])
def post_decision(eid: str, body: Decision):
    """Registra la decisión humana. El servidor vuelve a validar cualquier monto antes de guardarlo."""
    try:
        return servicio.registrar_decision(eid, body.accion, body.cultural_mxn, body.romantica_mxn,
                                           body.comentario, body.responsable, body.acepta_observaciones)
    except KeyError:
        _404(eid)
    except servicio.Conflicto as e:
        raise HTTPException(409, str(e)) from None
    except g.DecisionInvalida as e:
        raise HTTPException(422, {"motivo": e.motivo, "violaciones": e.violaciones, "veto": e.veto}) from None


@app.get("/ejecuciones/{eid}/reporte", response_class=PlainTextResponse, tags=["human-in-the-loop"])
def get_reporte(eid: str):
    """Reporte en Markdown de la ejecución y la decisión (para descargar o adjuntar)."""
    try:
        return PlainTextResponse(servicio.reporte_markdown(eid), media_type="text/markdown; charset=utf-8")
    except KeyError:
        _404(eid)
