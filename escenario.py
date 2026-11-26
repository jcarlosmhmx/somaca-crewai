"""Escenario del caso de prueba y evaluación determinista contra las métricas PEAS.

No depende de CrewAI: lo usan crew.py (entradas del kickoff), la API (vista Resumen y
Auditoría) y las pruebas. La evaluación PEAS no la hace el LLM: se calcula en Python con las
mismas herramientas que usan los agentes, para que el humano compare la recomendación contra
una línea base sin depender de lo que el Monitor haya escrito.
"""
from __future__ import annotations

from datetime import date, timedelta

import simulador as sim
from tools import logica

CAMPANAS = sim.CAMPANAS  # ("Cultural", "Romantica")


def entradas() -> dict:
    """Variables de entrada del caso de prueba (se interpolan en las descripciones de las tareas)."""
    cfg = sim.cargar("restricciones_objetivos.json")
    ipd = cfg["iteraciones_por_dia"]
    corte = cfg["iteracion_corte"]
    inicio = date.fromisoformat(cfg["fecha_inicio"])
    ultimo = inicio + timedelta(days=cfg["duracion_dias"] - 1)
    primer_restante = inicio + timedelta(days=corte // ipd)
    filas = sim.simular(sim.semilla())
    restante = sum(
        [r for r in filas if r["campana"] == c and r["iteracion"] == corte][0]["presupuesto_disponible"]
        for c in CAMPANAS
    )
    return {
        "iteracion_corte": corte,
        "fecha_corte": (inicio + timedelta(days=(corte - 1) // ipd)).isoformat(),
        "primer_dia_restante": primer_restante.isoformat(),
        "ultimo_dia": ultimo.isoformat(),
        "presupuesto_restante": round(restante, 2),
        "semilla": sim.semilla(),
    }


def resumen() -> dict:
    """Datos de la vista Resumen: entradas, objetivos, restricciones, pesos y métricas al corte."""
    cfg = sim.cargar("restricciones_objetivos.json")
    return {
        "entradas": entradas(),
        "presupuesto_total_mxn": cfg["presupuesto_total_mxn"],
        "objetivos": cfg["objetivos"],
        "restricciones": cfg["restricciones"],
        "economia": cfg["economia"],
        "pesos": {c: {k: v for k, v in w.items() if k.startswith("w")}
                  for c, w in sim.cargar("pesos_utilidad.json").items() if not c.startswith("_")},
        "campanas": {c: logica.metricas(c) for c in CAMPANAS},
        "datos_sinteticos": True,
    }


def serie() -> list[dict]:
    """Serie por iteración hasta el corte (gasto y leads acumulados) para la gráfica del Resumen."""
    corte = entradas()["iteracion_corte"]
    out, acum = [], {c: {"gasto": 0.0, "leads": 0} for c in CAMPANAS}
    for r in sim.simular(sim.semilla()):
        if r["iteracion"] > corte:
            break
        a = acum[r["campana"]]
        a["gasto"] += r["gasto"]
        a["leads"] += r["conversiones"]
        out.append({"iteracion": r["iteracion"], "fecha": r["fecha"], "campana": r["campana"],
                    "gasto_acum": round(a["gasto"], 2), "leads_acum": a["leads"], "ctr": r["ctr"],
                    "cpm_efectivo": r["cpm_efectivo"]})
    return out


def _clave_campana(d: dict, campana: str):
    """Lee d['Cultural'] / d['Romantica'] tolerando 'romántica', 'romantica', etc."""
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        try:
            if logica.normalizar_campana(k) == campana:
                return v
        except ValueError:
            continue
    return None


def proyectar_reparto(montos: dict, segmentos: dict) -> dict:
    """Proyección a 12 días de un reparto {campana: mxn} con {campana: segment_id}."""
    filas, gasto, leads, ingresos, imp_obs, imp_rest, clics_obs = {}, 0.0, 0.0, 0.0, 0, 0.0, 0
    for c in CAMPANAS:
        p = logica.proyectar_escenario(c, int(segmentos[c]), float(montos[c]))
        acum = logica.metricas(c)["acumulado"]
        t = p["totales_12_dias"]
        filas[c] = {"segment_id": p["segment_id"], "segmento": p["segmento"], "presupuesto_mxn": float(montos[c]),
                    "leads": t["leads"], "cpl": t["cpl"], "roas": t["roas"], "ctr_acumulado": acum["ctr"],
                    "utilidad": p["utilidad"]["utilidad"]}
        gasto += t["gasto"]
        leads += t["leads"]
        ingresos += t["roas"] * t["gasto"]
        imp_obs += acum["impresiones"]
        clics_obs += acum["clics"]
        imp_rest += p["restante"]["impresiones"]
    return {"por_campana": filas,
            "total": {"gasto": round(gasto, 2), "leads": round(leads, 1),
                      "cpl": round(gasto / leads, 2) if leads else None,
                      "roas": round(ingresos / gasto, 2) if gasto else None,
                      "ctr_acumulado": round(clics_obs / imp_obs, 4) if imp_obs else None,
                      "impresiones": round(imp_obs + imp_rest),
                      "utilidad_sistema": round(sum(f["utilidad"] for f in filas.values()), 4)}}


def linea_base() -> dict:
    """Sin optimizar: mismo segmento inicial y el saldo actual de cada campaña."""
    m = {c: logica.metricas(c) for c in CAMPANAS}
    return proyectar_reparto({c: m[c]["presupuesto_disponible"] for c in CAMPANAS},
                             {c: m[c]["segmento_actual"]["segment_id"] for c in CAMPANAS})


def evaluar_peas(montos: dict, segmentos: dict | None = None) -> dict:
    """Compara una recomendación contra los objetivos PEAS (C.1) y contra la línea base."""
    obj = sim.cargar("restricciones_objetivos.json")["objetivos"]
    base = linea_base()
    if segmentos is None or any(_clave_campana(segmentos, c) is None for c in CAMPANAS):
        segmentos = {c: base["por_campana"][c]["segment_id"] for c in CAMPANAS}
    else:
        segmentos = {c: int(_clave_campana(segmentos, c)) for c in CAMPANAS}
    montos = {c: float(_clave_campana(montos, c) if _clave_campana(montos, c) is not None else montos[c])
              for c in CAMPANAS}
    rec = proyectar_reparto(montos, segmentos)
    t = rec["total"]

    def fila(nombre, meta_txt, valor, cumple, base_valor, nota=""):
        return {"metrica": nombre, "meta": meta_txt, "proyectado": valor, "cumple": cumple,
                "linea_base": base_valor, "nota": nota}

    b = base["total"]
    metricas = [
        fila("Leads (12 días)", f"{obj['leads_min']}–{obj['leads_max']}", t["leads"],
             obj["leads_min"] <= t["leads"], b["leads"]),
        fila("CPL global (MXN)", f"≤ {obj['cpl_max_mxn']}", t["cpl"],
             t["cpl"] is not None and t["cpl"] <= obj["cpl_max_mxn"], b["cpl"]),
        fila("CTR acumulado", f"≥ {obj['ctr_min']:.1%}", t["ctr_acumulado"],
             t["ctr_acumulado"] is not None and t["ctr_acumulado"] >= obj["ctr_min"], b["ctr_acumulado"],
             "Observado al corte; la proyección no modela cambios de CTR."),
        fila("Impresiones (12 días)", f"≥ {obj['impresiones_min']:,}", t["impresiones"],
             t["impresiones"] >= obj["impresiones_min"], b["impresiones"]),
        fila("ROAS global", f"≥ {obj['roas_min']}x", t["roas"],
             t["roas"] is not None and t["roas"] >= obj["roas_min"], b["roas"],
             "Ingresos con supuesto sintético: 10 % lead→reserva × 900 MXN."),
        fila("Conversión lead→reserva", f"≥ {obj['conv_lead_a_reserva_min']:.0%}", None, None, None,
             "No verificable: el simulador lo fija como supuesto (10 %)."),
    ]
    return {"recomendacion": rec, "linea_base": base, "metricas": metricas,
            "mejora_vs_base": {"leads": round(t["leads"] - b["leads"], 1),
                               "cpl": round((t["cpl"] or 0) - (b["cpl"] or 0), 2),
                               "utilidad_sistema": round(t["utilidad_sistema"] - b["utilidad_sistema"], 4)}}
