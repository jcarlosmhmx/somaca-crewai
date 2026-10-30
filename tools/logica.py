"""Lógica pura de las herramientas (sin dependencia de CrewAI).

Todas las funciones devuelven dict/list serializables; los envoltorios @tool de
herramientas.py las convierten a JSON. Los errores de entrada lanzan ValueError.
"""
from __future__ import annotations

import os
import statistics
import unicodedata
from datetime import date, timedelta
from functools import cache

import simulador as sim

TOL = 1e-9


# --------------------------------------------------------------------------- utilidades
@cache
def _cfg() -> dict:
    return sim.cargar("restricciones_objetivos.json")


@cache
def _segmentos() -> dict:
    return {s["segment_id"]: s for s in sim.cargar("inventario_audiencias.json")["segmentos"]}


@cache
def _periodos() -> dict:
    return {p["clave"]: p for p in sim.cargar("cpm_estacionalidad.json")["periodos"]}


@cache
def _filas() -> tuple:
    return tuple(sim.simular(int(os.getenv("SIM_SEED", "42"))))


def normalizar_campana(campana: str) -> str:
    """Acepta 'Romántica', 'romantica', 'CULTURAL', etc. y devuelve la clave interna."""
    txt = unicodedata.normalize("NFD", str(campana)).encode("ascii", "ignore").decode().strip().lower()
    for c in sim.CAMPANAS:
        if txt == c.lower():
            return c
    raise ValueError(f"Campaña desconocida: {campana!r}. Usa 'Cultural' o 'Romantica'.")


def _segmento(campana: str, segment_id: int) -> dict:
    seg = _segmentos().get(int(segment_id))
    if seg is None or seg["campana"] != campana:
        validos = [i for i, s in _segmentos().items() if s["campana"] == campana]
        raise ValueError(f"segment_id {segment_id} no es válido para {campana}. Opciones: {validos}.")
    return seg


def _filas_campana(campana: str, hasta: int) -> list[dict]:
    return [r for r in _filas() if r["campana"] == campana and r["iteracion"] <= hasta]


def _hasta(hasta_iteracion: int | None) -> int:
    total = _cfg()["duracion_dias"] * _cfg()["iteraciones_por_dia"]
    h = _cfg()["iteracion_corte"] if hasta_iteracion is None else int(hasta_iteracion)
    if not 1 <= h <= total:
        raise ValueError(f"hasta_iteracion debe estar entre 1 y {total}.")
    return h


def estabilidad(campana: str, hasta: int) -> float:
    """1 - coeficiente de variación de las conversiones diarias, acotado a [0, 1]."""
    ipd = _cfg()["iteraciones_por_dia"]
    filas = _filas_campana(campana, hasta)
    dias = hasta // ipd
    if dias < 2:
        return 0.5
    diarias = [sum(r["conversiones"] for r in filas if (r["iteracion"] - 1) // ipd == d) for d in range(dias)]
    media = statistics.fmean(diarias)
    if media == 0:
        return 0.0
    return round(max(0.0, min(1.0, 1 - statistics.pstdev(diarias) / media)), 3)


# --------------------------------------------------------------------------- herramientas
def consultar_cpm(fecha: str) -> dict:
    """Período de mercado y rango de CPM (MXN) para una fecha ISO (AAAA-MM-DD)."""
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD.") from None
    clave = sim.periodo_de(f, _cfg()["eventos_especiales"])
    p = _periodos()[clave]
    return {
        "fecha": f.isoformat(), "dia_semana": sim.DIAS_ES[f.weekday()], "periodo": clave,
        "cpm_min": p["cpm_min"], "cpm_max": p["cpm_max"], "variacion_vs_base": p["variacion"],
        "justificacion": p["justificacion"],
    }


def inventario(campana: str) -> list[dict]:
    """Segmentos de audiencia disponibles para una campaña."""
    c = normalizar_campana(campana)
    return [
        {k: s[k] for k in ("segment_id", "nombre", "conv_min", "conv_max", "cpm_min", "cpm_max", "ctr_base", "fuente")}
        for s in _segmentos().values() if s["campana"] == c
    ]


def metricas(campana: str, hasta_iteracion: int | None = None) -> dict:
    """Métricas acumuladas de una campaña hasta una iteración (por defecto, la de corte)."""
    c = normalizar_campana(campana)
    h = _hasta(hasta_iteracion)
    filas = _filas_campana(c, h)
    seg = _segmentos()[filas[-1]["segment_id"]]
    total = _cfg()["duracion_dias"] * _cfg()["iteraciones_por_dia"]
    campos = ("iteracion", "fecha", "periodo", "gasto", "impresiones", "clics", "ctr", "conversiones", "cpm_efectivo")
    return {
        "campana": c,
        "hasta_iteracion": h,
        "iteraciones_totales": total,
        "iteraciones_restantes": total - h,
        "segmento_actual": {"segment_id": seg["segment_id"], "nombre": seg["nombre"]},
        "presupuesto_disponible": filas[-1]["presupuesto_disponible"],
        "acumulado": sim.resumen(list(_filas()), h)[c],
        "estabilidad": estabilidad(c, h),
        "ultimas_iteraciones": [{k: r[k] for k in campos} for r in filas[-4:]],
    }


def utilidad(campana: str, conversiones: float, roi: float, estabilidad_: float) -> dict:
    """U = w1*conv_norm + w2*roi_norm + w3*estabilidad, con cada término normalizado a [0, 1].

    conv_norm = conversiones / (leads_max / 2)      (meta de leads por campaña; tope 1)
    roi_norm  = ROI / (ROAS_min - 1)                (ROAS 2.5x equivale a ROI 1.5; tope [0, 1])
    Las conversiones deben ser totales proyectados a los 12 días.
    """
    c = normalizar_campana(campana)
    w = sim.cargar("pesos_utilidad.json")[c]
    obj = _cfg()["objetivos"]
    conv_n = max(0.0, min(1.0, conversiones / (obj["leads_max"] / 2)))
    roi_n = max(0.0, min(1.0, roi / (obj["roas_min"] - 1)))
    est = max(0.0, min(1.0, estabilidad_))
    u = w["w1_conversiones"] * conv_n + w["w2_roi"] * roi_n + w["w3_estabilidad"] * est
    return {
        "campana": c, "utilidad": round(u, 4),
        "terminos_normalizados": {"conversiones": round(conv_n, 3), "roi": round(roi_n, 3), "estabilidad": round(est, 3)},
        "pesos": {k: w[k] for k in ("w1_conversiones", "w2_roi", "w3_estabilidad")},
    }


def proyectar_escenario(campana: str, segment_id: int, presupuesto_mxn: float, desde_iteracion: int | None = None) -> dict:
    """Valores esperados si, desde la iteración de corte, se gasta `presupuesto_mxn` en `segment_id`."""
    c = normalizar_campana(campana)
    seg = _segmento(c, segment_id)
    if presupuesto_mxn < 0:
        raise ValueError("presupuesto_mxn no puede ser negativo.")
    cfg = _cfg()
    ipd = cfg["iteraciones_por_dia"]
    total = cfg["duracion_dias"] * ipd
    desde = (cfg["iteracion_corte"] + 1) if desde_iteracion is None else int(desde_iteracion)
    if not 2 <= desde <= total:
        raise ValueError(f"desde_iteracion debe estar entre 2 y {total}.")
    inicio = date.fromisoformat(cfg["fecha_inicio"])
    variaciones = [
        _periodos()[sim.periodo_de(inicio + timedelta(days=(it - 1) // ipd), cfg["eventos_especiales"])]["variacion"]
        for it in range(desde, total + 1)
    ]
    var_prom = statistics.fmean(variaciones)
    cpm = (seg["cpm_min"] + seg["cpm_max"]) / 2 * (1 + var_prom)
    imp = presupuesto_mxn / cpm * 1000
    clics = imp * seg["ctr_base"]
    leads_proy = clics * (seg["conv_min"] + seg["conv_max"]) / 2
    eco = cfg["economia"]
    ing_proy = leads_proy * eco["tasa_lead_a_reserva"] * eco["ingreso_por_reserva_mxn"]

    obs = sim.resumen(list(_filas()), desde - 1)[c]
    gasto_t = obs["gasto"] + presupuesto_mxn
    leads_t = obs["leads"] + leads_proy
    ing_t = obs["ingresos"] + ing_proy
    roi_t = (ing_t - gasto_t) / gasto_t if gasto_t else 0.0
    est = estabilidad(c, desde - 1)
    return {
        "campana": c, "segment_id": seg["segment_id"], "segmento": seg["nombre"],
        "presupuesto_proyectado_mxn": round(presupuesto_mxn, 2),
        "cpm_esperado": round(cpm, 2),
        "restante": {"impresiones": round(imp), "clics": round(clics, 1), "leads": round(leads_proy, 1)},
        "totales_12_dias": {
            "gasto": round(gasto_t, 2), "leads": round(leads_t, 1),
            "cpl": round(gasto_t / leads_t, 2) if leads_t else None,
            "roas": round(ing_t / gasto_t, 2) if gasto_t else 0.0, "roi": round(roi_t, 2),
        },
        "utilidad": utilidad(c, leads_t, roi_t, est),
    }


def validar_accion(campana: str, cambio_presupuesto_pct: float = 0.0, cambio_puja_pct: float = 0.0,
                   cambios_audiencia: int = 0, pausar: bool = False, roi_actual: float | None = None) -> dict:
    """Valida una acción de campaña contra las restricciones del PEAS (C.3)."""
    c = normalizar_campana(campana)
    r = _cfg()["restricciones"]
    violaciones, advertencias = [], []
    if abs(cambio_presupuesto_pct) > r["max_cambio_presupuesto"] + TOL:
        violaciones.append(f"Cambio de presupuesto {cambio_presupuesto_pct:+.0%} excede el máximo de ±{r['max_cambio_presupuesto']:.0%} por iteración.")
    if abs(cambio_puja_pct) > r["max_cambio_puja"] + TOL:
        violaciones.append(f"Cambio de puja/CPM {cambio_puja_pct:+.0%} excede el máximo de ±{r['max_cambio_puja']:.0%}.")
    if cambios_audiencia > r["max_cambios_audiencia_por_iteracion"]:
        violaciones.append(f"{cambios_audiencia} cambios de audiencia; el máximo es {r['max_cambios_audiencia_por_iteracion']} por iteración.")
    if pausar:
        if roi_actual is None:
            violaciones.append("Para pausar se necesita roi_actual (solo se permite si ROI < 0.5x).")
        elif roi_actual >= r["roi_minimo_para_operar"]:
            violaciones.append(f"No se puede pausar: ROI actual {roi_actual:.2f} ≥ {r['roi_minimo_para_operar']}x.")
    elif roi_actual is not None and roi_actual < r["roi_minimo_para_operar"]:
        advertencias.append(f"ROI {roi_actual:.2f} < {r['roi_minimo_para_operar']}x: la regla permite (y sugiere) pausar la campaña.")
    return {"campana": c, "valido": not violaciones, "violaciones": violaciones, "advertencias": advertencias}


def validar_reparto(nuevo_cultural: float, nuevo_romantica: float, hasta_iteracion: int | None = None) -> dict:
    """Valida un nuevo reparto del presupuesto restante entre las dos campañas."""
    h = _hasta(hasta_iteracion)
    actual = {c: _filas_campana(c, h)[-1]["presupuesto_disponible"] for c in sim.CAMPANAS}
    nuevo = {"Cultural": float(nuevo_cultural), "Romantica": float(nuevo_romantica)}
    lim = _cfg()["restricciones"]["max_cambio_presupuesto"]
    violaciones, cambios = [], {}
    if min(nuevo.values()) < 0:
        violaciones.append("Los presupuestos no pueden ser negativos.")
    if abs(sum(nuevo.values()) - sum(actual.values())) > 0.01:
        violaciones.append(f"El total ({sum(nuevo.values()):.2f}) debe conservar el presupuesto restante ({sum(actual.values()):.2f}).")
    for c in sim.CAMPANAS:
        cambios[c] = round((nuevo[c] - actual[c]) / actual[c], 4) if actual[c] else 0.0
        if abs(cambios[c]) > lim + TOL:
            violaciones.append(f"{c}: cambio {cambios[c]:+.1%} excede ±{lim:.0%}.")
    return {"valido": not violaciones, "presupuesto_actual": actual, "presupuesto_nuevo": nuevo,
            "cambio_pct": cambios, "violaciones": violaciones}
