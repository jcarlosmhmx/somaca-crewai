"""Dashboard B2B Human-in-the-Loop de SOMACA (Streamlit).

Arranque (con la API ya corriendo en el puerto 8000):
    streamlit run ui/app.py

Cuatro pestañas, en el mismo orden del flujo de usuario de la Fase 4:
    1. Resumen               → sensores del PEAS al corte (datos sintéticos)
    2. Flujo de agentes      → lanzar la corrida y ver en vivo (SSE) herramientas, delegación y guardrails
    3. Auditoría y decisión  → veredicto, verificación determinista, evaluación PEAS y decisión humana
    4. Historial             → corridas anteriores y sus decisiones

La GUI no calcula ni valida nada por su cuenta: todo viene de la API, que es la única fuente de verdad.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from ui.cliente import ApiError, Cliente  # noqa: E402
from ui.formato import ESTADO_ETAPA, VEREDICTO, corto, evento_md, mxn, pct  # noqa: E402

st.set_page_config(page_title="SOMACA · Meta Ads", page_icon="🏨", layout="wide")

st.markdown("""
<style>
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
.ok{background:#E2F1E8;color:#1F7A4D}.warn{background:#FBEED6;color:#8F5400}.bad{background:#F7E2DE;color:#A63A2B}
.mute{background:#ECEAE4;color:#5E6E6C}.info{background:#E3ECE9;color:#173A3A}
.etapa{border:1px solid #E3DED3;border-radius:12px;padding:12px 14px;background:#FFFFFF;min-height:150px}
.etapa h4{margin:0 0 4px 0;font-size:15px}.etapa small{color:#55706E}
.num{font-variant-numeric:tabular-nums}
</style>""", unsafe_allow_html=True)


def chip(texto: str, clase: str) -> str:
    return f'<span class="chip {clase}">{texto}</span>'


ss = st.session_state
ss.setdefault("eid", None)
ss.setdefault("eventos", {})
ss.setdefault("seguir", False)

# --------------------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown("### 🏨 SOMACA")
    st.caption("Hotel Parador Monte Carmelo · Meta Ads")
    url = st.text_input("URL de la API", value=os.getenv("SOMACA_API", "http://localhost:8000"))
    c = Cliente(url)
    try:
        salud = c.salud()
        st.success(f"API conectada · `{salud['modelo']}`")
        if not salud["llave_configurada"]:
            st.warning("Sin llave de API en .env: solo funciona el modo respaldo.")
    except ApiError as e:
        st.error(str(e))
        st.info("Arranca la API con:\n\n`uvicorn api.main:app --port 8000`")
        st.stop()

    st.divider()
    modo_txt = st.radio("Modo de ejecución", ["CrewAI en vivo", "Respaldo grabado (Fase 3)"],
                        index=0 if salud["llave_configurada"] else 1,
                        help="El respaldo reproduce la corrida real del 30-oct-2026 por si falla la red o la API del LLM.")
    modo = "crewai" if modo_txt.startswith("CrewAI") else "replay"
    velocidad = st.slider("Velocidad del respaldo", 0.5, 4.0, 1.0, 0.5) if modo == "replay" else None

    st.divider()
    corridas = c.listar()
    if corridas:
        ids = [r["id"] for r in corridas]
        etiqueta = {r["id"]: f"{r['id']} · {r['modo']} · {r['estado']}" + (f" · {r['decision']}" if r.get("decision") else "")
                    for r in corridas}
        if ss.eid not in ids:
            ss.eid = ids[0]
        sel = st.selectbox("Ejecución seleccionada", ids, index=ids.index(ss.eid), format_func=etiqueta.get)
        if sel != ss.eid:
            ss.eid, ss.seguir = sel, False
    st.caption("Datos sintéticos (simulador, semilla 13). SOMACA recomienda; la persona decide.")

st.title("SOMACA · Reparto del presupuesto de Meta Ads")
st.markdown(chip("Datos sintéticos", "info") + " " + chip("Human-in-the-Loop", "ok"), unsafe_allow_html=True)

tab_res, tab_flujo, tab_aud, tab_hist = st.tabs(["📊 Resumen", "🤖 Flujo de agentes", "🧾 Auditoría y decisión", "🗂️ Historial"])

# --------------------------------------------------------------------------- 1. Resumen
with tab_res:
    esc = c.escenario()
    e = esc["entradas"]
    k = st.columns(4)
    k[0].metric("Corte", f"Iteración {e['iteracion_corte']} de 48", e["fecha_corte"])
    k[1].metric("Periodo restante", f"{e['primer_dia_restante'][5:]} → {e['ultimo_dia'][5:]}")
    k[2].metric("Presupuesto restante", mxn(e["presupuesto_restante"]))
    k[3].metric("Presupuesto total", mxn(esc["presupuesto_total_mxn"]))

    cols = st.columns(2)
    for col, (nombre, camp) in zip(cols, esc["campanas"].items()):
        a = camp["acumulado"]
        w = esc["pesos"][nombre]
        with col:
            st.subheader("Campaña " + ("Romántica" if nombre == "Romantica" else nombre))
            st.caption(f"Segmento actual: {camp['segmento_actual']['segment_id']} · {camp['segmento_actual']['nombre']} · "
                       f"U = {w['w1_conversiones']}·Conv + {w['w2_roi']}·ROI + {w['w3_estabilidad']}·Estab.")
            m = st.columns(3)
            m[0].metric("Gasto al corte", mxn(a["gasto"]))
            m[1].metric("Leads", a["leads"])
            m[2].metric("Saldo", mxn(camp["presupuesto_disponible"]))
            m = st.columns(3)
            ob = esc["objetivos"]
            m[0].metric("CPL", mxn(a["cpl"]), f"meta ≤ {ob['cpl_max_mxn']}", delta_color="off")
            m[1].metric("CTR", pct(a["ctr"]), f"meta ≥ {ob['ctr_min'] * 100:.1f} %", delta_color="off")
            m[2].metric("ROAS", f"{a['roas']}x", f"meta ≥ {ob['roas_min']}x", delta_color="off")

    serie = pd.DataFrame(c.serie())
    if not serie.empty:
        st.markdown("**Leads acumulados por iteración (6 h) hasta el corte**")
        piv = serie.pivot_table(index="iteracion", columns="campana", values="leads_acum")
        st.line_chart(piv, height=220)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Objetivos de desempeño (P del PEAS)**")
        ob = esc["objetivos"]
        st.dataframe(pd.DataFrame([
            ["Leads en 12 días", f"{ob['leads_min']}–{ob['leads_max']}"], ["CPL", f"≤ {ob['cpl_max_mxn']} MXN"],
            ["CTR", f"≥ {ob['ctr_min'] * 100:.1f} %"], ["Impresiones", f"≥ {ob['impresiones_min']:,}"],
            ["ROAS", f"≥ {ob['roas_min']}x"], ["Lead → reserva", f"≥ {ob['conv_lead_a_reserva_min'] * 100:.0f} %"],
        ], columns=["Métrica", "Meta"]), hide_index=True, width="stretch")
    with c2:
        st.markdown("**Restricciones de los actuadores (A del PEAS)**")
        r = esc["restricciones"]
        st.dataframe(pd.DataFrame([
            ["adjust_budget()", f"±{r['max_cambio_presupuesto']:.0%} por iteración"],
            ["modify_bid()", f"±{r['max_cambio_puja']:.0%}"],
            ["change_audience()", f"máx. {r['max_cambios_audiencia_por_iteracion']} por iteración"],
            ["toggle_campaign()", f"pausar solo si ROI < {r['roi_minimo_para_operar']}x"],
            ["Reparto (Broker)", "conserva el total restante"],
        ], columns=["Actuador", "Regla"]), hide_index=True, width="stretch")

# --------------------------------------------------------------------------- 2. Flujo de agentes
with tab_flujo:
    izq, der = st.columns([1, 3])
    with izq:
        activa = salud.get("ejecucion_activa")
        if st.button("▶ Ejecutar SOMACA", type="primary", width="stretch", disabled=bool(activa)):
            try:
                r = c.iniciar(modo, velocidad)
                ss.eid, ss.seguir = r["id"], True
                ss.eventos[r["id"]] = []
                st.rerun()
            except ApiError as err:
                st.error(str(err))
        if activa:
            st.info(f"Corrida en curso: {activa}")
            if activa != ss.eid and st.button("Seguir corrida en curso", width="stretch"):
                ss.eid, ss.seguir = activa, True
                st.rerun()
    with der:
        st.markdown("Analista → **[Cultural ∥ Romántica]** → Broker → Monitor · `Process.sequential`, "
                    "T2 y T3 con `async_execution`, solo el Broker con `allow_delegation`.")

    etapas_ph = st.empty()
    st.markdown("**Registro en vivo** (lo más reciente arriba: herramientas, delegaciones, guardrails y paso de contexto)")
    log_ph = st.container(height=460).empty()


def pintar_etapas(ph, ej: dict | None) -> None:
    if not ej:
        ph.info("Aún no hay corridas. Pulsa **Ejecutar SOMACA**.")
        return
    with ph.container():
        st.caption(f"Ejecución `{ej['id']}` · modo **{ej['modo']}** · modelo `{ej['modelo']}` · estado **{ej['estado']}**")
        cols = st.columns(5)
        for col, et in zip(cols, ej["etapas"]):
            txt, cls = ESTADO_ETAPA.get(et["estado"], (et["estado"], "mute"))
            gr = {"aprobado": chip("🛡️ guardrail OK", "ok"), "rechazado": chip("🛡️ reintento", "warn")}.get(et["guardrail"] or "", "")
            dele = f"<br><small>🤝 {et['delegaciones']} delegaciones</small>" if et["delegaciones"] else ""
            col.markdown(f'<div class="etapa"><small>{et["tarea"].split(" ")[0]}</small><h4>{corto(et["agente"])}</h4>'
                         f'{chip(txt, cls)}<br><small>🔧 {et["herramientas"]} herramientas</small>{dele}<br>{gr}</div>',
                         unsafe_allow_html=True)


def pintar_log(ph, evs: list[dict]) -> None:
    if not evs:
        ph.caption("Sin eventos todavía.")
        return
    # Lo más reciente arriba: durante la corrida se ve el último paso sin desplazarse.
    ph.markdown("\n\n".join(evento_md(ev) for ev in reversed(evs)))


ej_actual = None
if ss.eid:
    try:
        ej_actual = c.obtener(ss.eid)
    except ApiError:
        ss.eid = None
if ss.eid and not ss.eventos.get(ss.eid):
    ss.eventos[ss.eid] = c.eventos_json(ss.eid)
pintar_etapas(etapas_ph, ej_actual)
pintar_log(log_ph, ss.eventos.get(ss.eid, []))

# --------------------------------------------------------------------------- 3. Auditoría y decisión
with tab_aud:
    if not ej_actual:
        st.info("Ejecuta SOMACA para obtener una recomendación.")
    elif ej_actual["estado"] != "completada":
        st.info(f"La ejecución está **{ej_actual['estado']}**. La auditoría aparece cuando el Monitor emite su veredicto.")
        if ej_actual.get("error"):
            st.error(ej_actual["error"])
    else:
        a = c.auditoria(ss.eid)
        sal = a["salidas"]
        asig = (sal.get("asignacion") or {}).get("json") or {}
        aud = (sal.get("auditoria") or {}).get("json") or {}

        for al in a["alertas"]:
            {"veto": st.error, "observacion": st.warning, "info": st.info}[al["nivel"]](
                ("⛔ VETO · " if al["nivel"] == "veto" else "") + al["texto"])

        v_txt, v_cls = VEREDICTO.get(a["veredicto_monitor"] or "", ("Sin veredicto", "mute"))
        st.markdown(f"### Veredicto del Monitor Global: {chip(v_txt, v_cls)}", unsafe_allow_html=True)
        resumen = aud.get("resumen_ejecutivo")
        if resumen:
            st.markdown("\n".join(f"- {x}" for x in (resumen if isinstance(resumen, list) else [resumen])))

        st.markdown("#### Recomendación del Broker")
        val = a["validacion_reparto"] or {}
        m = st.columns(4)
        m[0].metric("Cultural", mxn(asig.get("presupuesto_cultural_mxn")),
                    pct((val.get("cambio_pct") or {}).get("Cultural"), 1) + " vs saldo" if val.get("cambio_pct") else None)
        m[1].metric("Romántica", mxn(asig.get("presupuesto_romantica_mxn")),
                    pct((val.get("cambio_pct") or {}).get("Romantica"), 1) + " vs saldo" if val.get("cambio_pct") else None)
        segf = asig.get("segmento_final") or {}
        segf_txt = (" / ".join(f"{corto(k) or k}: {v}" for k, v in segf.items()) if isinstance(segf, dict)
                    else str(segf))
        m[2].metric("Segmentos finales", segf_txt or "—")
        m[3].markdown("**Validación determinista**<br>" + (chip("Conserva total y ±20 %", "ok") if val.get("valido")
                      else chip("Viola restricciones", "bad")), unsafe_allow_html=True)
        with st.expander("Justificación del Broker y aclaraciones (delegación)"):
            st.write(asig.get("justificacion", ""))
            for acl in asig.get("aclaraciones_solicitadas") or []:
                # El LLM puede devolver cada aclaración como objeto o como frase: se aceptan ambos.
                if isinstance(acl, dict):
                    st.markdown(f"**🤝 Pregunta a {corto(acl.get('destinatario'))}:** {acl.get('pregunta')}\n\n"
                                f"**↩️ Respuesta:** {acl.get('respuesta')}")
                else:
                    st.markdown(f"🤝 {acl}")

        peas = a["evaluacion_peas"]
        if peas:
            st.markdown("#### Evaluación frente a las métricas PEAS (calculada en Python, no por el LLM)")
            filas = []
            for mt in peas["metricas"]:
                fmt = (lambda x: "—" if x is None else (f"{x * 100:.2f} %" if "CTR" in mt["metrica"] else f"{x:,}"))
                filas.append({"Métrica": mt["metrica"], "Meta": mt["meta"], "Recomendación": fmt(mt["proyectado"]),
                              "Sin optimizar": fmt(mt["linea_base"]),
                              "Cumple": {True: "✅", False: "❌", None: "—"}[mt["cumple"]], "Nota": mt["nota"]})
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
            mj = peas["mejora_vs_base"]
            st.caption(f"Frente a no optimizar: {mj['leads']:+} leads · CPL {mj['cpl']:+} MXN · "
                       f"utilidad del sistema {mj['utilidad_sistema']:+}. Proyecciones con valores esperados del simulador.")

        with st.expander("Guardrails re-ejecutados sobre las salidas guardadas"):
            st.dataframe(pd.DataFrame([{"Tarea": g["tarea"], "Agente": corto(g["agente"]),
                                        "Resultado": {True: "✅ OK", False: "⛔ Falla", None: "—"}[g["ok"]],
                                        "Detalle": g["detalle"]} for g in a["guardrails"]]),
                         hide_index=True, width="stretch")
        with st.expander("Riesgos y objetivos según el Monitor"):
            for r_ in aud.get("riesgos") or []:
                st.markdown(f"- {r_}")
            if aud.get("objetivos"):
                st.json(aud["objetivos"], expanded=False)
        with st.expander("Salidas completas por agente (JSON)"):
            for clave, s_ in sal.items():
                st.markdown(f"**{s_['tarea']}** · {corto(s_['agente'])}")
                st.json(s_["json"] if s_["json"] else {"error": s_["error_json"]}, expanded=False)

        st.divider()
        st.markdown("### 👤 Decisión humana")
        d = a["decision"]
        if d:
            st.success(f"**{d['accion'].upper()}** por {d['responsable']}: Cultural {mxn(d['cultural_mxn'])}, "
                       f"Romántica {mxn(d['romantica_mxn'])}. Comentario: {d['comentario']}")
        else:
            veto = any(al["nivel"] == "veto" for al in a["alertas"])
            opciones = (["ajustar", "rechazar"] if veto else ["aprobar", "ajustar", "rechazar"])
            nombres = {"aprobar": "✅ Aprobar recomendación", "ajustar": "✏️ Ajustar montos", "rechazar": "✖️ Rechazar"}
            accion = st.radio("¿Qué haces con la recomendación?", opciones, format_func=nombres.get, horizontal=True)
            responsable = st.text_input("Responsable", placeholder="Nombre de quien decide")
            datos = {"accion": accion, "responsable": responsable}
            restante = float(ej_actual["entradas"]["presupuesto_restante"])
            if accion == "ajustar":
                base_c = float(asig.get("presupuesto_cultural_mxn") or restante / 2)
                cult = st.slider("Cultural (MXN) · Romántica recibe el resto", 0.0, restante, base_c, 5.0)
                rom = round(restante - cult, 2)
                prev = c.validar_reparto(cult, rom)
                st.markdown(f"Romántica: **{mxn(rom)}** · " + (chip("Reparto válido", "ok") if prev["valido"] else
                            chip("Inválido: " + "; ".join(prev["violaciones"]), "bad")), unsafe_allow_html=True)
                datos.update(cultural_mxn=cult, romantica_mxn=rom)
            if accion == "aprobar" and a["veredicto_monitor"] == "aprobado_con_observaciones":
                datos["acepta_observaciones"] = st.checkbox("Revisé las observaciones del Monitor y las metas no alcanzadas")
            datos["comentario"] = st.text_area("Comentario (obligatorio salvo aprobación limpia)", max_chars=2000)
            if st.button("Registrar decisión", type="primary"):
                try:
                    c.decidir(ss.eid, **datos)
                    st.toast("Decisión registrada en la bitácora.")
                    st.rerun()
                except ApiError as err:
                    det = err.detalle if isinstance(err.detalle, dict) else {"motivo": str(err.detalle)}
                    st.error(("⛔ " if det.get("veto") else "") + str(det.get("motivo")))
                    for vi in det.get("violaciones", []):
                        st.markdown(f"- {vi}")
        st.download_button("⬇️ Descargar reporte (.md)", data=c.reporte(ss.eid), file_name=f"somaca_{ss.eid}.md",
                           mime="text/markdown")
        st.caption("SOMACA no ejecuta cambios en Meta Ads: la decisión queda registrada para que el equipo la aplique.")

# --------------------------------------------------------------------------- 4. Historial
with tab_hist:
    if corridas:
        st.dataframe(pd.DataFrame([{
            "Ejecución": r["id"], "Modo": r["modo"], "Modelo": r["modelo"], "Estado": r["estado"],
            "Decisión": r.get("decision") or "pendiente",
            "Duración (s)": round(r["terminada"] - r["creada"]) if r.get("terminada") else None,
        } for r in corridas]), hide_index=True, width="stretch")
        st.caption("Selecciona una ejecución en la barra lateral para ver su flujo y su auditoría.")
    else:
        st.info("Sin corridas registradas.")

# --------------------------------------------------------------------------- monitor en vivo (SSE)
# Va al final para que las demás pestañas ya estén dibujadas mientras se reciben eventos.
if ss.seguir and ej_actual and ej_actual["estado"] not in ("completada", "fallida"):
    evs = ss.eventos.setdefault(ss.eid, [])
    desde = evs[-1]["seq"] if evs else 0
    try:
        for ev in c.eventos(ss.eid, desde=desde):
            evs.append(ev)
            pintar_log(log_ph, evs)
            if ev["tipo"] in ("tarea_iniciada", "guardrail", "tarea_completada", "corrida_completada", "corrida_fallida"):
                pintar_etapas(etapas_ph, c.obtener(ss.eid))
    except ApiError as err:
        st.toast(f"Se perdió el flujo de eventos: {err}")
    ss.seguir = False
    st.rerun()
