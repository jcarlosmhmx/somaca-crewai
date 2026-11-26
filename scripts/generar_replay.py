"""Genera data/demo/corrida_grabada.json: la corrida final de la Fase 3 en formato de eventos.

Sirve como RESPALDO de la demostración en vivo (sin internet o sin saldo en la API): la GUI la
reproduce con el rótulo «Modo respaldo». Para no presentar nada inventado:

- Las salidas de las 5 tareas se copian textualmente de logs/corrida.log.txt (corrida real del
  30-oct-2026 con claude-haiku-5-5).
- Las llamadas a herramientas se vuelven a ejecutar con la lógica determinista (semilla 13) usando
  los argumentos que aparecen en esas salidas; por eso sus resultados son exactos.
- Las delegaciones del Broker se toman de su campo 'aclaraciones_solicitadas'.
- Los guardrails se ejecutan de verdad sobre cada salida.
- No se reconstruyen "pensamientos" del LLM: el log original no los guardó.

Uso:  python scripts/generar_replay.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import guardrails as g  # noqa: E402
from escenario import entradas  # noqa: E402
from tools import logica  # noqa: E402

LOG = RAIZ / "logs" / "corrida.log.txt"
SALIDA = RAIZ / "data" / "demo" / "corrida_grabada.json"

AGENTES = {
    "analisis": "Analista de Mercado de Meta Ads",
    "cultural": "Agente de Campaña Cultural",
    "romantica": "Agente de Campaña Romántica",
    "asignacion": "Broker de Presupuesto",
    "auditoria": "Monitor Global de Cumplimiento",
}
TAREAS = {
    "analisis": "T1 Análisis de mercado",
    "cultural": "T2 Propuesta Cultural",
    "romantica": "T3 Propuesta Romántica",
    "asignacion": "T4 Asignación del presupuesto",
    "auditoria": "T5 Auditoría",
}
HERR = {"consultar_cpm": "consultar_cpm_mercado", "inventario": "leer_inventario_audiencias",
        "metricas": "leer_metricas_campana", "proyectar_escenario": "proyectar_escenario",
        "validar_accion": "validar_restricciones", "validar_reparto": "validar_reparto_presupuesto",
        "utilidad": "calcular_utilidad"}


def salidas_log() -> dict:
    texto = LOG.read_text(encoding="utf-8")
    bloques = re.findall(r'agent="([^"]+)", status="completed", output="(.*?)"\n(?=\d{4}-\d{2}-\d{2} |\Z)',
                         texto, flags=re.S)
    por_agente = dict(bloques)
    return {k: por_agente[v] for k, v in AGENTES.items()}


def main() -> None:
    sal = salidas_log()
    obj = {k: g.extraer_json(v) for k, v in sal.items()}
    e = entradas()
    eventos: list[dict] = []
    t = 0.0

    def ev(dt: float, tipo: str, **datos):
        nonlocal t
        t += dt
        eventos.append({"t": round(t, 2), "tipo": tipo, **datos})

    def herramienta(dt, agente, fn, *args):
        try:
            res, ok = json.dumps(fn(*args), ensure_ascii=False), True
        except ValueError as err:
            res, ok = json.dumps({"error": str(err)}, ensure_ascii=False), False
        ev(dt, "herramienta", agente=agente, herramienta=HERR[fn.__name__], ok=ok,
           entrada=json.dumps({"args": list(args)}, ensure_ascii=False), salida=res[:900])

    def tarea(dt, clave, inicio=True):
        if inicio:
            ev(dt, "tarea_iniciada", tarea=TAREAS[clave], agente=AGENTES[clave])

    def cerrar(dt, clave, gr):
        ok, motivo = gr[clave](sal[clave])
        # el guardrail ya emitió su evento en vivo; aquí se registra para la reproducción
        ev(dt, "guardrail", agente=AGENTES[clave], guardrail=gr[clave].__name__.replace("guardrail_", ""),
           ok=ok, errores=[] if ok else [motivo])
        ev(0.6, "tarea_completada", tarea=TAREAS[clave], agente=AGENTES[clave], salida=sal[clave])

    gr = g.crear_guardrails(e["presupuesto_restante"])

    # T1 — Analista
    tarea(0.5, "analisis")
    inicio = date.fromisoformat(e["primer_dia_restante"])
    fin = date.fromisoformat(e["ultimo_dia"])
    d = inicio
    while d <= fin:
        herramienta(1.2, AGENTES["analisis"], logica.consultar_cpm, d.isoformat())
        d += timedelta(days=1)
    for c in ("Cultural", "Romantica"):
        herramienta(1.5, AGENTES["analisis"], logica.inventario, c)
    cerrar(3.0, "analisis", gr)

    # T2 ∥ T3 — campañas en paralelo (se intercalan sus eventos)
    tarea(0.5, "cultural")
    tarea(0.1, "romantica")
    cola = {}
    for clave, campana in (("cultural", "Cultural"), ("romantica", "Romantica")):
        pasos = [(logica.metricas, (campana, e["iteracion_corte"]))]
        for alt in obj[clave]["alternativas_evaluadas"]:
            pasos.append((logica.proyectar_escenario, (campana, int(alt["segment_id"]), float(alt["presupuesto"]))))
        prop = obj[clave]["propuesta"]
        saldo = logica.metricas(campana)["presupuesto_disponible"]
        cambio = round((float(prop["presupuesto_restante_mxn"]) - saldo) / saldo, 4)
        if clave == "cultural":
            # Registrado en la salida de Cultural: "Un intento previo con el valor 20 fue rechazado
            # por error de unidades (+2000 %); el valor correcto es 0.2".
            pasos.append((logica.validar_accion, (campana, 20.0, 0.0, 1)))
        pasos.append((logica.validar_accion, (campana, cambio, float(prop.get("cambio_puja_pct") or 0),
                                              1 if prop.get("cambio_audiencia") else 0)))
        cola[clave] = pasos
    while cola["cultural"] or cola["romantica"]:
        for clave in ("cultural", "romantica"):
            if cola[clave]:
                fn, args = cola[clave].pop(0)
                herramienta(0.9, AGENTES[clave], fn, *args)
    cerrar(2.0, "cultural", gr)
    cerrar(1.0, "romantica", gr)

    # T4 — Broker (delegación + validación)
    tarea(0.5, "asignacion")
    a = obj["asignacion"]
    for aclar in a.get("aclaraciones_solicitadas", []):
        ev(2.5, "paso", agente=AGENTES["asignacion"], clase="AgentAction", herramienta="Ask question to coworker",
           delegacion=True, entrada=f"{aclar['destinatario']}: {aclar['pregunta']}", pensamiento="")
        ev(4.0, "paso", agente=aclar["destinatario"], clase="AgentFinish", salida=aclar["respuesta"],
           pensamiento="", delegacion=True)
    herramienta(1.5, AGENTES["asignacion"], logica.validar_reparto,
                float(a["presupuesto_cultural_mxn"]), float(a["presupuesto_romantica_mxn"]))
    cerrar(2.0, "asignacion", gr)

    # T5 — Monitor
    tarea(0.5, "auditoria")
    herramienta(1.5, AGENTES["auditoria"], logica.validar_reparto,
                float(a["presupuesto_cultural_mxn"]), float(a["presupuesto_romantica_mxn"]))
    for clave, campana in (("cultural", "Cultural"), ("romantica", "Romantica")):
        prop = obj[clave]["propuesta"]
        seg_final = int(a["segmento_final"].get(campana, prop["segment_id"]))
        actual = logica.metricas(campana)["segmento_actual"]["segment_id"]
        herramienta(1.2, AGENTES["auditoria"], logica.validar_accion, campana, 0.0, 0.0, int(seg_final != actual))
    cerrar(3.0, "auditoria", gr)

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({
        "_nota": "Reproducción de la corrida final de la Fase 3 (30-oct-2026, anthropic/claude-haiku-5-5, "
                 "semilla 13). Salidas de tareas textuales del log; herramientas re-ejecutadas con la "
                 "lógica determinista. Generado por scripts/generar_replay.py.",
        "modelo_original": "anthropic/claude-haiku-5-5",
        "fecha_original": "2026-10-30",
        "duracion_original_s": 173,
        "entradas": e,
        "eventos": eventos,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(eventos)} eventos, {t:.1f} s de línea de tiempo → {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
