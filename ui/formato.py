"""Formato de cifras y de eventos para la GUI (sin Streamlit, para poder probarlo)."""
from __future__ import annotations

import json

CORTO = {
    "Analista de Mercado de Meta Ads": "Analista",
    "Agente de Campaña Cultural": "Cultural",
    "Agente de Campaña Romántica": "Romántica",
    "Broker de Presupuesto": "Broker",
    "Monitor Global de Cumplimiento": "Monitor",
}
VEREDICTO = {
    "aprobado": ("Aprobado", "ok"),
    "aprobado_con_observaciones": ("Aprobado con observaciones", "warn"),
    "rechazado": ("Rechazado", "bad"),
}
ESTADO_ETAPA = {"pendiente": ("Pendiente", "mute"), "en_curso": ("En curso", "info"),
                "completada": ("Completada", "ok"), "fallida": ("Fallida", "bad")}


def mxn(v) -> str:
    if v is None:
        return "Sin datos"
    return f"${float(v):,.2f} MXN"


def pct(v, decimales: int = 2) -> str:
    return "Sin datos" if v is None else f"{float(v) * 100:.{decimales}f} %"


def corto(agente: str | None) -> str:
    return CORTO.get(agente or "", agente or "")


def _limpio(texto, n: int = 180) -> str:
    t = " ".join(str(texto or "").split()).replace("`", "'")
    return t if len(t) <= n else t[:n] + "…"


def resumen_salida_herramienta(nombre: str, salida: str) -> str:
    """Una línea legible con lo esencial de cada herramienta (la salida completa va en el detalle)."""
    try:
        d = json.loads(salida)
    except (TypeError, ValueError):
        return _limpio(salida, 120)
    if isinstance(d, dict) and "error" in d:
        return "error: " + _limpio(d["error"], 140)
    if nombre == "consultar_cpm_mercado":
        return f"{d['fecha']} ({d['dia_semana']}): {d['periodo']}, CPM {d['cpm_min']}–{d['cpm_max']} MXN"
    if nombre == "leer_inventario_audiencias" and isinstance(d, list):
        return f"{len(d)} segmentos: " + ", ".join(str(s["segment_id"]) for s in d)
    if nombre == "leer_metricas_campana":
        a = d["acumulado"]
        return (f"{d['campana']}: {a['leads']} leads, CPL {a['cpl']}, CTR {a['ctr'] * 100:.2f} %, "
                f"ROAS {a['roas']}x, saldo {d['presupuesto_disponible']}")
    if nombre == "proyectar_escenario":
        t = d["totales_12_dias"]
        return (f"{d['campana']} seg. {d['segment_id']} con {d['presupuesto_proyectado_mxn']} MXN → "
                f"{t['leads']} leads, CPL {t['cpl']}, ROAS {t['roas']}x, U={d['utilidad']['utilidad']}")
    if nombre in ("validar_restricciones", "validar_reparto_presupuesto"):
        if d.get("valido"):
            return "válido"
        return "INVÁLIDO: " + _limpio("; ".join(d.get("violaciones", [])), 160)
    if nombre == "calcular_utilidad":
        return f"U = {d.get('utilidad')}"
    return _limpio(salida, 120)


def evento_md(ev: dict) -> str:
    """Una línea Markdown por evento para el monitor en vivo."""
    tipo, ag = ev.get("tipo"), corto(ev.get("agente"))
    if tipo == "corrida_iniciada":
        return "▶️ **Corrida iniciada**" + (" · *modo respaldo (grabación de la Fase 3)*" if ev.get("modo") == "replay" else "")
    if tipo == "tarea_iniciada":
        return f"📋 **{ev.get('tarea')}** · {ag} recibe la tarea y el contexto"
    if tipo == "herramienta":
        icono = "🔧" if ev.get("ok", True) else "⚠️"
        quien = f"{ag} · " if ag else ""
        return f"{icono} {quien}`{ev.get('herramienta')}` → {resumen_salida_herramienta(ev.get('herramienta'), ev.get('salida'))}"
    if tipo == "paso":
        if ev.get("delegacion") and ev.get("clase") == "AgentAction":
            return f"🤝 **{ag} delega** una pregunta: {_limpio(ev.get('entrada'), 220)}"
        if ev.get("delegacion"):
            return f"↩️ **{ag} responde** al Broker: {_limpio(ev.get('salida'), 220)}"
        if ev.get("herramienta"):
            return f"💭 {ag} decide usar `{ev.get('herramienta')}`" + (
                f": {_limpio(ev.get('pensamiento'), 160)}" if ev.get("pensamiento") else "")
        if ev.get("clase") == "AgentFinish":
            return f"📝 **{ag}** entrega su respuesta final" + (
                f": {_limpio(ev.get('pensamiento'), 160)}" if ev.get("pensamiento") else "")
        if ev.get("pensamiento"):
            return f"💭 {ag}: {_limpio(ev.get('pensamiento'), 200)}"
        return f"💭 {ag} avanza ({ev.get('clase')})"
    if tipo == "guardrail":
        if ev.get("ok"):
            return f"🛡️ Guardrail `{ev.get('guardrail')}` **aprobó** la salida de {ag}"
        return f"⛔ Guardrail `{ev.get('guardrail')}` **rechazó** la salida de {ag}: {_limpio('; '.join(ev.get('errores', [])), 220)} → el agente reintenta"
    if tipo == "tarea_completada":
        return f"✅ **{ev.get('tarea') or ag}** completada · la salida pasa como contexto a la siguiente tarea"
    if tipo == "corrida_completada":
        return "🏁 **Corrida completada** · revisa la pestaña *Auditoría y decisión*"
    if tipo == "corrida_fallida":
        return f"❌ **Corrida fallida**: {_limpio(ev.get('error'), 300)}"
    return f"· {tipo}"
