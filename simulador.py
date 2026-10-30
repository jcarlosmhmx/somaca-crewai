"""Simulador sintético de Meta Ads para SOMACA (Fase 3).

Genera con semilla fija el historial de 12 días (48 iteraciones de 6 h) de las
dos campañas, a partir de los datos del dominio en data/. Cada iteración:

    CPM efectivo = punto medio del CPM del segmento * (1 + variación del período) * ruido
    impresiones  = gasto / CPM * 1000
    clics        ~ Binomial(impresiones, CTR del segmento * ruido)
    leads        ~ Binomial(clics, tasa de conversión del segmento)
    ingresos     = leads * tasa lead->reserva * ingreso por reserva   (supuestos)

Uso:  python simulador.py          (escribe data/metricas_simuladas.csv)
"""
from __future__ import annotations

import csv
import json
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np

DATA = Path(__file__).parent / "data"
# Semilla por defecto: 13. Elegida entre 500 semillas con un criterio fijado de antemano
# (ver docs/supuestos_datos.md); la 42 daba un empate accidental entre campañas a la iteración 24.
DEFAULT_SEED = 13
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
CAMPANAS = ("Cultural", "Romantica")
COLUMNAS = [
    "iteracion", "fecha", "hora_inicio", "dia_semana", "periodo", "campana",
    "segment_id", "gasto", "presupuesto_disponible", "impresiones",
    "impresiones_acum", "clics", "ctr", "cpc", "cpm_efectivo", "cpm_mercado",
    "conversiones", "conversiones_acum", "ingresos_estimados", "roi_acum",
]


def semilla() -> int:
    """Semilla activa: variable SIM_SEED si existe, si no DEFAULT_SEED."""
    return int(os.getenv("SIM_SEED", str(DEFAULT_SEED)))


def cargar(nombre: str) -> dict:
    return json.loads((DATA / nombre).read_text(encoding="utf-8"))


def periodo_de(fecha: date, eventos=()) -> str:
    """Clasifica una fecha (precedencia: evento > temporada alta > fin de semana > laboral)."""
    if fecha.isoformat() in eventos:
        return "eventos_especiales"
    if fecha.month in (7, 8, 12):
        return "temporada_alta"
    if fecha.weekday() >= 4:  # viernes, sábado, domingo
        return "fin_de_semana"
    return "dia_laboral"


def simular(seed: int = DEFAULT_SEED) -> list[dict]:
    cfg = cargar("restricciones_objetivos.json")
    inv = {s["segment_id"]: s for s in cargar("inventario_audiencias.json")["segmentos"]}
    periodos = {p["clave"]: p for p in cargar("cpm_estacionalidad.json")["periodos"]}
    eco = cfg["economia"]
    rng = np.random.default_rng(seed)
    inicio = date.fromisoformat(cfg["fecha_inicio"])
    ipd = cfg["iteraciones_por_dia"]
    horas = 24 // ipd

    estado = {
        c: {
            "seg": cfg["segmento_inicial"][c],
            "disp": float(cfg["reparto_inicial"][c]),
            "diario": cfg["reparto_inicial"][c] / cfg["duracion_dias"],
            "imp": 0, "gasto": 0.0, "leads": 0, "ing": 0.0,
        }
        for c in CAMPANAS
    }
    filas: list[dict] = []
    for it in range(1, cfg["duracion_dias"] * ipd + 1):
        dia, franja = divmod(it - 1, ipd)
        fecha = inicio + timedelta(days=dia)
        per = periodo_de(fecha, cfg["eventos_especiales"])
        p = periodos[per]
        cpm_mercado = rng.uniform(p["cpm_min"], p["cpm_max"])
        for c in CAMPANAS:
            st = estado[c]
            seg = inv[st["seg"]]
            cpm = (seg["cpm_min"] + seg["cpm_max"]) / 2 * (1 + p["variacion"]) * rng.lognormal(0, 0.08)
            gasto = min(st["disp"], st["diario"] / ipd)
            imp = int(gasto / cpm * 1000)
            ctr_esp = float(np.clip(seg["ctr_base"] * rng.lognormal(0, 0.15), 0, 0.05))
            # El sensor CTR del PEAS satura en 5 %: con pocas impresiones la varianza lo superaría.
            clics = min(int(rng.binomial(imp, ctr_esp)), int(0.05 * imp))
            conv = rng.uniform(seg["conv_min"], seg["conv_max"])
            leads = int(rng.binomial(clics, conv))
            ing = leads * eco["tasa_lead_a_reserva"] * eco["ingreso_por_reserva_mxn"]

            st["disp"] = max(0.0, st["disp"] - gasto)
            st["imp"] += imp
            st["gasto"] += gasto
            st["leads"] += leads
            st["ing"] += ing
            filas.append({
                "iteracion": it,
                "fecha": fecha.isoformat(),
                "hora_inicio": franja * horas,
                "dia_semana": DIAS_ES[fecha.weekday()],
                "periodo": per,
                "campana": c,
                "segment_id": st["seg"],
                "gasto": round(gasto, 4),
                "presupuesto_disponible": round(st["disp"], 2),
                "impresiones": imp,
                "impresiones_acum": st["imp"],
                "clics": clics,
                "ctr": round(clics / imp, 4) if imp else 0.0,
                "cpc": round(gasto / clics, 2) if clics else 0.0,
                "cpm_efectivo": round(cpm, 2),
                "cpm_mercado": round(cpm_mercado, 2),
                "conversiones": leads,
                "conversiones_acum": st["leads"],
                "ingresos_estimados": round(ing, 2),
                "roi_acum": round((st["ing"] - st["gasto"]) / st["gasto"], 3) if st["gasto"] else 0.0,
            })
    return filas


def resumen(filas: list[dict], hasta_iteracion: int | None = None) -> dict:
    """Totales por campaña (opcionalmente solo hasta cierta iteración)."""
    out = {}
    for c in CAMPANAS:
        f = [r for r in filas if r["campana"] == c and (hasta_iteracion is None or r["iteracion"] <= hasta_iteracion)]
        gasto = sum(r["gasto"] for r in f)
        imp = sum(r["impresiones"] for r in f)
        clics = sum(r["clics"] for r in f)
        leads = sum(r["conversiones"] for r in f)
        ing = sum(r["ingresos_estimados"] for r in f)
        out[c] = {
            "gasto": round(gasto, 4), "impresiones": imp, "clics": clics, "leads": leads,
            "ctr": round(clics / imp, 4) if imp else 0.0,
            "cpl": round(gasto / leads, 2) if leads else None,
            "ingresos": round(ing, 2),
            "roas": round(ing / gasto, 2) if gasto else 0.0,
            "roi": round((ing - gasto) / gasto, 2) if gasto else 0.0,
        }
    return out


def escribir_csv(filas: list[dict], ruta: Path) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)


if __name__ == "__main__":
    seed = semilla()
    filas = simular(seed)
    escribir_csv(filas, DATA / "metricas_simuladas.csv")
    print(f"seed={seed} filas={len(filas)}")
    print(json.dumps(resumen(filas), indent=2, ensure_ascii=False))
