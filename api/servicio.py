"""Capa de servicio de la API (sin FastAPI): persistencia, ejecución del Crew y lazo humano.

Separar esta capa de las rutas permite probarla sin servidor (tests/test_servicio.py) y deja
api/main.py como una capa delgada de HTTP.

Modos de ejecución:
- "crewai": corre el Crew real con el LLM de .env (OpenAI, Anthropic u Ollama).
- "replay": reproduce la corrida grabada de la Fase 3 (data/demo/corrida_grabada.json). Es el
  respaldo de la demo en vivo; la GUI lo rotula como tal.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import eventos
import escenario
import guardrails as g
from config import llave_configurada, nombre_modelo

RAIZ = Path(__file__).resolve().parents[1]
REPLAY = RAIZ / "data" / "demo" / "corrida_grabada.json"

ETAPAS = [  # (clave de salida, tarea, agente) en el orden del flujo
    ("analisis", "T1 Análisis de mercado", "Analista de Mercado de Meta Ads"),
    ("cultural", "T2 Propuesta Cultural", "Agente de Campaña Cultural"),
    ("romantica", "T3 Propuesta Romántica", "Agente de Campaña Romántica"),
    ("asignacion", "T4 Asignación del presupuesto", "Broker de Presupuesto"),
    ("auditoria", "T5 Auditoría", "Monitor Global de Cumplimiento"),
]
AGENTE_A_CLAVE = {agente: clave for clave, _, agente in ETAPAS}
TERMINALES = ("completada", "fallida")


def _db_path() -> Path:
    return Path(os.getenv("SOMACA_DB", str(RAIZ / "data" / "somaca.db")))


# --------------------------------------------------------------------------- persistencia
ESQUEMA = """
CREATE TABLE IF NOT EXISTS ejecuciones (
  id TEXT PRIMARY KEY, creada REAL, terminada REAL, estado TEXT, modo TEXT, modelo TEXT,
  entradas TEXT, error TEXT, uso_tokens TEXT);
CREATE TABLE IF NOT EXISTS eventos (
  ejecucion_id TEXT, seq INTEGER, ts REAL, tipo TEXT, datos TEXT, PRIMARY KEY (ejecucion_id, seq));
CREATE TABLE IF NOT EXISTS salidas (
  ejecucion_id TEXT, clave TEXT, tarea TEXT, agente TEXT, raw TEXT, PRIMARY KEY (ejecucion_id, clave));
CREATE TABLE IF NOT EXISTS decisiones (
  ejecucion_id TEXT PRIMARY KEY, ts REAL, accion TEXT, cultural_mxn REAL, romantica_mxn REAL,
  comentario TEXT, responsable TEXT, veredicto_monitor TEXT, validacion TEXT);
"""


@contextmanager
def conexion() -> Iterator[sqlite3.Connection]:
    ruta = _db_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(ESQUEMA)
        yield con
        con.commit()
    finally:
        con.close()


def _ahora() -> float:
    return time.time()


class Grabadora:
    """Sink del bus de eventos: numera y guarda cada evento de UNA ejecución."""

    def __init__(self, ejecucion_id: str):
        self.id = ejecucion_id
        self.seq = 0
        self.lock = threading.Lock()

    def __call__(self, evento: dict) -> None:
        with self.lock:
            self.seq += 1
            datos = {k: v for k, v in evento.items() if k not in ("ts", "tipo")}
            with conexion() as con:
                con.execute("INSERT INTO eventos VALUES (?,?,?,?,?)",
                            (self.id, self.seq, evento.get("ts", _ahora()), evento["tipo"],
                             json.dumps(datos, ensure_ascii=False, default=str)))
                if evento["tipo"] == "tarea_completada":
                    clave = AGENTE_A_CLAVE.get(datos.get("agente", "")) or _clave_por_tarea(datos.get("tarea", ""))
                    if clave:
                        tarea, agente = next((t, a) for c, t, a in ETAPAS if c == clave)
                        con.execute("INSERT OR REPLACE INTO salidas VALUES (?,?,?,?,?)",
                                    (self.id, clave, tarea, agente, datos.get("salida", "")))


def _clave_por_tarea(nombre: str) -> str | None:
    for clave, tarea, _ in ETAPAS:
        if nombre and (nombre == tarea or nombre.startswith(tarea.split(" ")[0] + " ")):
            return clave
    return None


# --------------------------------------------------------------------------- ejecución
_lock_ejecucion = threading.Lock()
_activa: dict = {"id": None}


class Ocupado(RuntimeError):
    pass


def ejecucion_activa() -> str | None:
    return _activa["id"]


def iniciar(modo: str = "crewai", velocidad: float | None = None) -> dict:
    """Crea una ejecución y la lanza en un hilo. Solo una a la vez (el Crew no es reentrante)."""
    modo = modo if modo in ("crewai", "replay") else "crewai"
    if modo == "crewai" and not llave_configurada():
        raise ValueError(f"No hay llave de API para {nombre_modelo()}. Configúrala en .env "
                         "o usa el modo 'replay' (respaldo).")
    with _lock_ejecucion:
        if _activa["id"]:
            raise Ocupado(f"Ya hay una ejecución en curso: {_activa['id']}")
        eid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        _activa["id"] = eid
    entradas = escenario.entradas()
    modelo = nombre_modelo() if modo == "crewai" else json.loads(REPLAY.read_text("utf-8"))["modelo_original"]
    with conexion() as con:
        con.execute("INSERT INTO ejecuciones VALUES (?,?,?,?,?,?,?,?,?)",
                    (eid, _ahora(), None, "en_cola", modo, modelo, json.dumps(entradas), None, None))
    destino = _correr_crewai if modo == "crewai" else _correr_replay
    hilo = threading.Thread(target=_envoltura, args=(eid, destino, velocidad), daemon=True, name=f"crew-{eid}")
    hilo.start()
    return obtener(eid)


def _envoltura(eid: str, destino, velocidad) -> None:
    grab = Grabadora(eid)
    eventos.suscribir(grab)
    try:
        with conexion() as con:
            con.execute("UPDATE ejecuciones SET estado='en_ejecucion' WHERE id=?", (eid,))
        eventos.emitir("corrida_iniciada", ejecucion_id=eid)
        uso = destino(eid, velocidad)
        with conexion() as con:
            con.execute("UPDATE ejecuciones SET estado='completada', terminada=?, uso_tokens=? WHERE id=?",
                        (_ahora(), json.dumps(uso) if uso else None, eid))
        eventos.emitir("corrida_completada", ejecucion_id=eid)
    except Exception as e:  # noqa: BLE001 - cualquier fallo se reporta a la GUI, no se oculta
        with conexion() as con:
            con.execute("UPDATE ejecuciones SET estado='fallida', terminada=?, error=? WHERE id=?",
                        (_ahora(), f"{type(e).__name__}: {e}", eid))
        eventos.emitir("corrida_fallida", ejecucion_id=eid, error=f"{type(e).__name__}: {e}",
                       detalle=eventos.recortar(traceback.format_exc(), 2000))
    finally:
        eventos.desuscribir(grab)
        with _lock_ejecucion:
            _activa["id"] = None


def _correr_crewai(eid: str, _velocidad) -> dict | None:
    from crew import build_crew  # import diferido: la API arranca aunque CrewAI tarde en cargar

    entradas = escenario.entradas()
    crew = build_crew(log_file=str(RAIZ / "logs" / f"corrida_{eid}.log"))
    resultado = crew.kickoff(inputs=entradas)
    # El resultado final es la fuente autoritativa de las salidas completas de cada tarea.
    with conexion() as con:
        for (clave, tarea, agente), salida in zip(ETAPAS, getattr(resultado, "tasks_output", []) or []):
            con.execute("INSERT OR REPLACE INTO salidas VALUES (?,?,?,?,?)",
                        (eid, clave, tarea, agente, getattr(salida, "raw", str(salida))))
    uso = getattr(resultado, "token_usage", None)
    if uso is None:
        return None
    return uso.model_dump() if hasattr(uso, "model_dump") else {"texto": str(uso)}


def _correr_replay(eid: str, velocidad: float | None) -> dict:
    datos = json.loads(REPLAY.read_text("utf-8"))
    vel = velocidad or float(os.getenv("REPLAY_VELOCIDAD", "1.0"))
    previo = 0.0
    for ev in datos["eventos"]:
        espera = (ev["t"] - previo) / max(vel, 0.01)
        previo = ev["t"]
        if espera > 0:
            time.sleep(espera)
        cuerpo = {k: v for k, v in ev.items() if k not in ("t", "tipo")}
        eventos.emitir(ev["tipo"], modo="replay", **cuerpo)
    return {"nota": "Reproducción: el consumo real de la corrida original está en logs/uso_tokens.txt"}


# --------------------------------------------------------------------------- consultas
def _fila(row) -> dict:
    d = dict(row)
    for k in ("entradas", "uso_tokens"):
        if d.get(k):
            d[k] = json.loads(d[k])
    return d


def listar() -> list[dict]:
    with conexion() as con:
        filas = con.execute("SELECT e.*, d.accion AS decision FROM ejecuciones e "
                            "LEFT JOIN decisiones d ON d.ejecucion_id = e.id ORDER BY creada DESC").fetchall()
    return [_fila(r) for r in filas]


def obtener(eid: str) -> dict:
    with conexion() as con:
        row = con.execute("SELECT * FROM ejecuciones WHERE id=?", (eid,)).fetchone()
        if row is None:
            raise KeyError(eid)
        evs = con.execute("SELECT tipo, datos FROM eventos WHERE ejecucion_id=? ORDER BY seq", (eid,)).fetchall()
        n_salidas = {r["clave"] for r in con.execute("SELECT clave FROM salidas WHERE ejecucion_id=?", (eid,))}
    d = _fila(row)
    d["etapas"] = _etapas([(r["tipo"], json.loads(r["datos"])) for r in evs], n_salidas, d["estado"])
    d["num_eventos"] = len(evs)
    return d


def _etapas(evs: list[tuple[str, dict]], con_salida: set, estado: str) -> list[dict]:
    """Estado de cada tarea a partir de los eventos: pendiente → en_curso → completada/fallida."""
    est = {c: {"clave": c, "tarea": t, "agente": a, "estado": "pendiente", "herramientas": 0,
               "guardrail": None, "delegaciones": 0} for c, t, a in ETAPAS}
    for tipo, d in evs:
        clave = AGENTE_A_CLAVE.get(d.get("agente", "")) or _clave_por_tarea(d.get("tarea", ""))
        if not clave:
            continue
        e = est[clave]
        if e["estado"] == "pendiente":
            e["estado"] = "en_curso"
        if tipo == "herramienta":
            e["herramientas"] += 1
        elif tipo == "paso" and d.get("delegacion") and d.get("clase") == "AgentAction":
            e["delegaciones"] += 1
        elif tipo == "guardrail":
            e["guardrail"] = "aprobado" if d.get("ok") else "rechazado"
        elif tipo == "tarea_completada":
            e["estado"] = "completada"
    for c in con_salida:
        est[c]["estado"] = "completada"
    if estado == "fallida":
        for e in est.values():
            if e["estado"] == "en_curso":
                e["estado"] = "fallida"
    return list(est.values())


def eventos_desde(eid: str, desde: int = 0, limite: int = 500) -> list[dict]:
    with conexion() as con:
        filas = con.execute("SELECT seq, ts, tipo, datos FROM eventos WHERE ejecucion_id=? AND seq>? "
                            "ORDER BY seq LIMIT ?", (eid, desde, limite)).fetchall()
    return [{"seq": r["seq"], "ts": r["ts"], "tipo": r["tipo"], **json.loads(r["datos"])} for r in filas]


def flujo_sse(eid: str, desde: int = 0, intervalo: float = 0.4, latido: float = 15.0) -> Iterator[str]:
    """Genera mensajes Server-Sent Events hasta que la ejecución termina y no quedan eventos."""
    obtener(eid)  # KeyError si no existe
    ultimo, ultimo_envio = desde, _ahora()
    while True:
        nuevos = eventos_desde(eid, ultimo)
        for ev in nuevos:
            ultimo = ev["seq"]
            ultimo_envio = _ahora()
            yield f"id: {ev['seq']}\nevent: {ev['tipo']}\ndata: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
        if not nuevos:
            if obtener(eid)["estado"] in TERMINALES and not eventos_desde(eid, ultimo, 1):
                yield "event: fin\ndata: {}\n\n"
                return
            if _ahora() - ultimo_envio > latido:
                ultimo_envio = _ahora()
                yield ": latido\n\n"  # comentario SSE: mantiene viva la conexión
            time.sleep(intervalo)


# --------------------------------------------------------------------------- auditoría y HITL
def salidas(eid: str) -> dict:
    with conexion() as con:
        filas = con.execute("SELECT * FROM salidas WHERE ejecucion_id=?", (eid,)).fetchall()
    out = {}
    for r in filas:
        try:
            obj, err = g.extraer_json(r["raw"]), None
        except ValueError as e:
            obj, err = None, str(e)
        out[r["clave"]] = {"tarea": r["tarea"], "agente": r["agente"], "json": obj, "error_json": err,
                           "raw": r["raw"]}
    return out


def decision(eid: str) -> dict | None:
    with conexion() as con:
        row = con.execute("SELECT * FROM decisiones WHERE ejecucion_id=?", (eid,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["validacion"] = json.loads(d["validacion"]) if d["validacion"] else None
    return d


def auditoria(eid: str) -> dict:
    """Todo lo que el humano necesita para decidir, con verificaciones deterministas propias."""
    ej = obtener(eid)
    s = salidas(eid)
    asig = (s.get("asignacion") or {}).get("json")
    aud = (s.get("auditoria") or {}).get("json")

    revisiones = []  # re-ejecución de los guardrails sobre lo guardado (no se confía en el log)
    gr = g.crear_guardrails(ej["entradas"]["presupuesto_restante"])
    for clave, tarea, agente in ETAPAS:
        if clave in s:
            ok, motivo = gr[clave](s[clave]["raw"])
            revisiones.append({"tarea": tarea, "agente": agente, "ok": ok, "detalle": "" if ok else motivo})
        else:
            revisiones.append({"tarea": tarea, "agente": agente, "ok": None, "detalle": "Sin salida todavía."})

    reparto, peas = None, None
    if asig:
        try:
            c = g.numero(asig.get("presupuesto_cultural_mxn"), "cultural")
            r = g.numero(asig.get("presupuesto_romantica_mxn"), "romantica")
            from tools import logica
            reparto = logica.validar_reparto(c, r)
            peas = escenario.evaluar_peas({"Cultural": c, "Romantica": r}, asig.get("segmento_final"))
        except ValueError as e:
            reparto = {"valido": False, "violaciones": [str(e)]}

    veredicto = str((aud or {}).get("veredicto", "")).lower() or None
    alertas = []
    if veredicto == "rechazado":
        alertas.append({"nivel": "veto", "texto": "El Monitor Global rechazó el reparto: no se puede aprobar tal cual."})
    if reparto and not reparto.get("valido"):
        alertas.append({"nivel": "veto", "texto": "El reparto viola restricciones del PEAS: "
                        + "; ".join(reparto.get("violaciones", []))})
    if veredicto == "aprobado_con_observaciones":
        alertas.append({"nivel": "observacion", "texto": "Aprobado con observaciones: revisa riesgos y "
                        "objetivos no cumplidos antes de aprobar."})
    if peas:
        no = [m["metrica"] for m in peas["metricas"] if m["cumple"] is False]
        if no:
            alertas.append({"nivel": "observacion", "texto": "Metas PEAS no alcanzadas en la proyección: " + ", ".join(no)})
    if ej["modo"] == "replay":
        alertas.append({"nivel": "info", "texto": "Modo respaldo: reproducción de la corrida grabada de la Fase 3."})

    return {"ejecucion": ej, "salidas": s, "guardrails": revisiones, "validacion_reparto": reparto,
            "evaluacion_peas": peas, "veredicto_monitor": veredicto, "alertas": alertas,
            "decision": decision(eid)}


class Conflicto(RuntimeError):
    pass


def registrar_decision(eid: str, accion: str, cultural_mxn=None, romantica_mxn=None, comentario: str = "",
                       responsable: str = "", acepta_observaciones: bool = False) -> dict:
    ej = obtener(eid)
    if ej["estado"] != "completada":
        raise Conflicto("La ejecución aún no termina; espera el veredicto del Monitor.")
    previa = decision(eid)
    if previa:
        raise Conflicto(f"Esta ejecución ya tiene una decisión registrada ({previa['accion']}).")
    if not (responsable or "").strip():
        raise g.DecisionInvalida("Indica quién toma la decisión (responsable).")
    s = salidas(eid)
    reg = g.evaluar_decision_humana(accion, (s.get("asignacion") or {}).get("json"),
                                    (s.get("auditoria") or {}).get("json"), cultural_mxn, romantica_mxn,
                                    comentario, acepta_observaciones)
    with conexion() as con:
        con.execute("INSERT INTO decisiones VALUES (?,?,?,?,?,?,?,?,?)",
                    (eid, _ahora(), reg["accion"], reg["cultural_mxn"], reg["romantica_mxn"], reg["comentario"],
                     responsable.strip(), reg["veredicto_monitor"],
                     json.dumps(reg["validacion"]) if reg["validacion"] else None))
    return decision(eid)


def reporte_markdown(eid: str) -> str:
    """Resumen descargable de la ejecución y la decisión humana (requerimiento R14 de la Fase 4)."""
    a = auditoria(eid)
    ej, aud = a["ejecucion"], (a["salidas"].get("auditoria") or {}).get("json") or {}
    asig = (a["salidas"].get("asignacion") or {}).get("json") or {}
    lin = [f"# SOMACA · Reporte de ejecución {eid}", "",
           f"- Modo: **{ej['modo']}** · Modelo: `{ej['modelo']}` · Estado: {ej['estado']}",
           f"- Corte: iteración {ej['entradas']['iteracion_corte']} ({ej['entradas']['fecha_corte']}) · "
           f"Presupuesto restante: {ej['entradas']['presupuesto_restante']} MXN · Semilla {ej['entradas']['semilla']}",
           "- Datos: **sintéticos** (simulador de Meta Ads, no cuenta real).", "",
           "## Recomendación del Broker",
           f"- Cultural: {asig.get('presupuesto_cultural_mxn')} MXN · Romántica: {asig.get('presupuesto_romantica_mxn')} MXN",
           f"- Segmento final: {asig.get('segmento_final')}", f"- Justificación: {asig.get('justificacion', '')}", "",
           f"## Veredicto del Monitor: {a['veredicto_monitor']}"]
    for r in aud.get("resumen_ejecutivo", []) if isinstance(aud.get("resumen_ejecutivo"), list) else [aud.get("resumen_ejecutivo", "")]:
        lin.append(f"- {r}")
    if a["evaluacion_peas"]:
        lin += ["", "## Evaluación determinista contra el PEAS", "| Métrica | Meta | Proyectado | Línea base | Cumple |",
                "|---|---|---|---|---|"]
        for m in a["evaluacion_peas"]["metricas"]:
            cumple = "—" if m["cumple"] is None else ("Sí" if m["cumple"] else "No")
            lin.append(f"| {m['metrica']} | {m['meta']} | {m['proyectado']} | {m['linea_base']} | {cumple} |")
    lin += ["", "## Guardrails"] + [f"- {r['tarea']}: {'OK' if r['ok'] else r['detalle'] or 'pendiente'}"
                                    for r in a["guardrails"]]
    d = a["decision"]
    lin += ["", "## Decisión humana"]
    if d:
        lin.append(f"- {d['accion'].upper()} por {d['responsable']} el "
                   f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(d['ts']))}: "
                   f"Cultural {d['cultural_mxn']} MXN, Romántica {d['romantica_mxn']} MXN. Comentario: {d['comentario']}")
    else:
        lin.append("- Pendiente.")
    lin += ["", "> La recomendación no se ejecuta en Meta Ads: SOMACA solo propone; la persona decide."]
    return "\n".join(lin)
