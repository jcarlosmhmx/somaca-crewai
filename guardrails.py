"""Guardrails deterministas de SOMACA (AI Safety).

El LLM propone; Python verifica. Cada tarea de CrewAI tiene un guardrail que revisa su salida
ANTES de pasarla a la siguiente tarea. Si la salida no cumple, CrewAI devuelve el error al agente
y este reintenta (hasta `guardrail_max_retries`). Los guardrails cubren tres riesgos:

1. Formato: la salida debe ser JSON con las claves que exige `expected_output`.
2. Alucinación: los segmentos y montos citados deben existir y ser coherentes con las
   herramientas (no se aceptan segment_id inventados ni repartos que no conservan el total).
3. Coherencia de la auditoría: el Monitor no puede declarar "restricciones cumplidas" si la
   validación determinista del reparto dice lo contrario.

Además, `evaluar_decision_humana` aplica las reglas del lazo Human-in-the-Loop: la decisión
final siempre es de una persona, y el servidor vuelve a validar cualquier ajuste manual.

Este módulo NO importa CrewAI, para poder probarlo sin llaves ni red (tests/test_guardrails.py).
"""
from __future__ import annotations

import json
import re
from typing import Any

import eventos
from tools import logica

VEREDICTOS = ("aprobado", "aprobado_con_observaciones", "rechazado")
SOLICITUDES = ("pedir", "ceder", "mantener")

CLAVES = {
    "analisis": ("resumen_cpm", "cultural", "romantica", "observaciones"),
    "propuesta": ("campana", "diagnostico", "alternativas_evaluadas", "propuesta",
                  "utilidad_esperada", "solicitud_al_broker", "validacion"),
    "asignacion": ("presupuesto_cultural_mxn", "presupuesto_romantica_mxn", "segmento_final",
                   "justificacion", "aclaraciones_solicitadas", "validacion"),
    "auditoria": ("veredicto", "restricciones_cumplidas", "violaciones", "objetivos", "riesgos",
                  "resumen_ejecutivo"),
}


# --------------------------------------------------------------------------- utilidades
def texto_de(salida: Any) -> str:
    """Acepta un TaskOutput de CrewAI (usa .raw) o un str."""
    return str(getattr(salida, "raw", salida) or "")


def extraer_json(texto: str) -> dict:
    """Extrae el primer objeto JSON del texto (tolera bloques ```json y texto alrededor)."""
    t = texto.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, flags=re.S)
    if m:
        t = m.group(1)
    else:
        ini, fin = t.find("{"), t.rfind("}")
        if ini == -1 or fin <= ini:
            raise ValueError("La respuesta no contiene un objeto JSON.")
        t = t[ini:fin + 1]
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e.msg} (línea {e.lineno}).") from None
    if not isinstance(obj, dict):
        raise ValueError("Se esperaba un objeto JSON, no una lista o valor suelto.")
    return obj


def numero(v: Any, campo: str) -> float:
    """Convierte 250, "250", "250.00 MXN" o "$250" a float; si no puede, ValueError."""
    if isinstance(v, bool):
        raise ValueError(f"{campo} debe ser numérico.")
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v).replace(",", ""))
    if not m:
        raise ValueError(f"{campo} debe ser numérico (se recibió {v!r}).")
    return float(m.group(0))


def _faltantes(obj: dict, tarea: str) -> list[str]:
    return [k for k in CLAVES[tarea] if k not in obj]


def _segmentos_validos(campana: str) -> set[int]:
    return {s["segment_id"] for s in logica.inventario(campana)}


# --------------------------------------------------------------------------- reglas puras
def revisar_analisis(obj: dict) -> list[str]:
    errores = [f"Falta la clave '{k}'." for k in _faltantes(obj, "analisis")]
    for clave, campana in (("cultural", "Cultural"), ("romantica", "Romantica")):
        segs = (obj.get(clave) or {}).get("segmentos_recomendados") if isinstance(obj.get(clave), dict) else None
        if not isinstance(segs, list) or len(segs) != 2:
            errores.append(f"'{clave}.segmentos_recomendados' debe ser una lista de 2 segmentos.")
            continue
        validos = _segmentos_validos(campana)
        for s in segs:
            sid = s.get("segment_id") if isinstance(s, dict) else None
            try:
                sid = int(sid)
            except (TypeError, ValueError):
                errores.append(f"{campana}: segment_id inválido {sid!r}.")
                continue
            if sid not in validos:
                errores.append(f"{campana}: el segmento {sid} no existe en el inventario "
                               f"(válidos: {sorted(validos)}). No inventes segmentos.")
    return errores


def revisar_propuesta(obj: dict, campana: str, presupuesto_restante: float) -> list[str]:
    errores = [f"Falta la clave '{k}'." for k in _faltantes(obj, "propuesta")]
    prop = obj.get("propuesta")
    if isinstance(prop, dict):
        try:
            sid = int(prop.get("segment_id"))
            if sid not in _segmentos_validos(campana):
                errores.append(f"propuesta.segment_id {sid} no pertenece a la campaña {campana}.")
        except (TypeError, ValueError):
            errores.append("propuesta.segment_id debe ser un entero.")
        try:
            monto = numero(prop.get("presupuesto_restante_mxn"), "propuesta.presupuesto_restante_mxn")
            if monto < 0 or monto > presupuesto_restante + 0.01:
                errores.append(f"propuesta.presupuesto_restante_mxn={monto} fuera de [0, {presupuesto_restante}].")
        except ValueError as e:
            errores.append(str(e))
    elif "propuesta" in obj:
        errores.append("'propuesta' debe ser un objeto.")
    sol = obj.get("solicitud_al_broker")
    if isinstance(sol, dict) and str(sol.get("tipo", "")).lower() not in SOLICITUDES:
        errores.append(f"solicitud_al_broker.tipo debe ser uno de {SOLICITUDES}.")
    return errores


def revisar_asignacion(obj: dict) -> tuple[list[str], dict | None]:
    """Devuelve (errores, validación determinista del reparto)."""
    errores = [f"Falta la clave '{k}'." for k in _faltantes(obj, "asignacion")]
    try:
        c = numero(obj.get("presupuesto_cultural_mxn"), "presupuesto_cultural_mxn")
        r = numero(obj.get("presupuesto_romantica_mxn"), "presupuesto_romantica_mxn")
    except ValueError as e:
        return errores + [str(e)], None
    val = logica.validar_reparto(c, r)
    if not val["valido"]:
        errores.append("El reparto no pasa validar_reparto_presupuesto: " + "; ".join(val["violaciones"])
                       + " Ajusta los montos y vuelve a validar.")
    seg = obj.get("segmento_final")
    if isinstance(seg, dict):
        for campana in ("Cultural", "Romantica"):
            v = seg.get(campana, seg.get(campana.lower(), seg.get("Romántica") if campana == "Romantica" else None))
            try:
                if v is not None and int(v) not in _segmentos_validos(campana):
                    errores.append(f"segmento_final de {campana} ({v}) no existe en su inventario.")
            except (TypeError, ValueError):
                errores.append(f"segmento_final de {campana} debe ser un entero.")
    return errores, val


def revisar_auditoria(obj: dict, validacion_reparto: dict | None) -> list[str]:
    errores = [f"Falta la clave '{k}'." for k in _faltantes(obj, "auditoria")]
    ver = str(obj.get("veredicto", "")).strip().lower()
    if ver not in VEREDICTOS:
        errores.append(f"veredicto debe ser uno de {VEREDICTOS} (se recibió {ver!r}).")
    if validacion_reparto is not None and obj.get("restricciones_cumplidas") is True \
            and not validacion_reparto["valido"]:
        errores.append("Declaraste restricciones_cumplidas=true, pero la validación determinista del "
                       "reparto falla: " + "; ".join(validacion_reparto["violaciones"]))
    if validacion_reparto is not None and not validacion_reparto["valido"] and ver == "aprobado":
        errores.append("No puedes aprobar un reparto que viola las restricciones.")
    return errores


# --------------------------------------------------------------------------- guardrails CrewAI
def crear_guardrails(presupuesto_restante: float) -> dict:
    """Fábrica de guardrails con estado compartido (el del Monitor necesita el del Broker).

    Cada guardrail recibe un TaskOutput y devuelve (True, salida) o (False, "mensaje para el agente").
    También emite eventos para que la GUI muestre cuándo un guardrail aprueba o rechaza.
    """
    estado: dict[str, Any] = {"validacion_reparto": None}

    def _envolver(nombre: str, agente: str, revisar):
        def guardrail(salida):
            texto = texto_de(salida)
            try:
                obj = extraer_json(texto)
                errores = revisar(obj)
            except ValueError as e:
                errores = [str(e)]
            eventos.emitir("guardrail", guardrail=nombre, agente=agente, ok=not errores, errores=errores)
            if errores:
                return False, ("Tu respuesta no pasó el guardrail '" + nombre + "'. Corrige y responde "
                               "SOLO con el JSON pedido. Problemas: " + " | ".join(errores))
            return True, texto  # se conserva la salida original del agente
        guardrail.__name__ = f"guardrail_{nombre}"
        return guardrail

    def _asignacion(obj):
        errores, val = revisar_asignacion(obj)
        estado["validacion_reparto"] = val
        return errores

    return {
        "analisis": _envolver("analisis_json_y_segmentos", "Analista de Mercado de Meta Ads", revisar_analisis),
        "cultural": _envolver("propuesta_cultural", "Agente de Campaña Cultural",
                              lambda o: revisar_propuesta(o, "Cultural", presupuesto_restante)),
        "romantica": _envolver("propuesta_romantica", "Agente de Campaña Romántica",
                               lambda o: revisar_propuesta(o, "Romantica", presupuesto_restante)),
        "asignacion": _envolver("reparto_conserva_total_y_limites", "Broker de Presupuesto", _asignacion),
        "auditoria": _envolver("auditoria_coherente", "Monitor Global de Cumplimiento",
                               lambda o: revisar_auditoria(o, estado["validacion_reparto"])),
        "_estado": estado,
    }


# --------------------------------------------------------------------------- Human-in-the-Loop
class DecisionInvalida(ValueError):
    """La decisión humana no se puede registrar (motivo legible para la GUI)."""

    def __init__(self, motivo: str, violaciones: list[str] | None = None, veto: bool = False):
        super().__init__(motivo)
        self.motivo = motivo
        self.violaciones = violaciones or []
        self.veto = veto


def evaluar_decision_humana(accion: str, asignacion: dict | None, auditoria: dict | None,
                            cultural_mxn: float | None = None, romantica_mxn: float | None = None,
                            comentario: str = "", acepta_observaciones: bool = False) -> dict:
    """Reglas del lazo humano. Devuelve el registro a guardar o lanza DecisionInvalida.

    - aprobar: toma el reparto del Broker. Exige validación determinista vigente. Si el Monitor
      emitió 'rechazado' hay VETO: solo se puede ajustar o rechazar. Si emitió
      'aprobado_con_observaciones', la persona debe reconocer las observaciones y comentar.
    - ajustar: la persona escribe sus propios montos; el servidor los vuelve a validar.
    - rechazar: exige comentario (queda en la bitácora para la siguiente corrida).
    """
    accion = (accion or "").lower()
    comentario = (comentario or "").strip()
    ver = str((auditoria or {}).get("veredicto", "")).lower()

    if accion == "rechazar":
        if not comentario:
            raise DecisionInvalida("Para rechazar escribe el motivo; queda en la bitácora de auditoría.")
        return {"accion": "rechazar", "cultural_mxn": None, "romantica_mxn": None, "validacion": None,
                "veredicto_monitor": ver, "comentario": comentario}

    if accion == "aprobar":
        if not asignacion:
            raise DecisionInvalida("No hay reparto del Broker que aprobar.")
        if ver == "rechazado":
            raise DecisionInvalida("Veto: el Monitor Global rechazó el reparto. Ajusta los montos o recházalo.",
                               veto=True)
        if ver == "aprobado_con_observaciones" and not (acepta_observaciones and comentario):
            raise DecisionInvalida("El Monitor aprobó con observaciones: marca que las revisaste y "
                                   "escribe un comentario antes de aprobar.")
        c = numero(asignacion.get("presupuesto_cultural_mxn"), "presupuesto_cultural_mxn")
        r = numero(asignacion.get("presupuesto_romantica_mxn"), "presupuesto_romantica_mxn")
    elif accion == "ajustar":
        if cultural_mxn is None or romantica_mxn is None:
            raise DecisionInvalida("Para ajustar indica el monto de ambas campañas.")
        if not comentario:
            raise DecisionInvalida("Para ajustar explica brevemente por qué cambias la recomendación.")
        c, r = float(cultural_mxn), float(romantica_mxn)
    else:
        raise DecisionInvalida(f"Acción desconocida: {accion!r}. Usa aprobar, ajustar o rechazar.")

    val = logica.validar_reparto(c, r)
    if not val["valido"]:
        raise DecisionInvalida("El reparto no cumple las restricciones del PEAS.", val["violaciones"])
    return {"accion": accion, "cultural_mxn": round(c, 2), "romantica_mxn": round(r, 2), "validacion": val,
            "veredicto_monitor": ver, "comentario": comentario}
