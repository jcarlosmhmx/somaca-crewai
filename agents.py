"""Los 5 agentes del MAS SOMACA (Bloque B).

Cada agente tiene role, goal, backstory, tools y allow_delegation. Solo el Broker
puede delegar (pide aclaraciones a los agentes de campaña); el resto trabaja de
forma autónoma para que el flujo sea predecible y barato.
"""
from crewai import Agent

from config import get_llm
from tools.herramientas import (
    calcular_utilidad,
    consultar_cpm_mercado,
    leer_inventario_audiencias,
    leer_metricas_campana,
    proyectar_escenario,
    validar_reparto_presupuesto,
    validar_restricciones,
)

# Reglas comunes que se repiten en las backstories para que cada agente las tenga presentes.
_REGLAS = (
    "Reglas del sistema (PEAS): cambio de presupuesto máx ±20% por iteración, cambio de puja/CPM "
    "máx ±10%, máx 1 cambio de audiencia por iteración y solo se pausa una campaña si su ROI < 0.5x. "
    "Nunca inventas cifras: todo número que reportes viene de una herramienta."
)


def crear_agentes(llm=None) -> dict[str, Agent]:
    llm = llm or get_llm()

    analista = Agent(
        role="Analista de Mercado de Meta Ads",
        goal="Entender el mercado de los días restantes (CPM, estacionalidad) y señalar qué segmentos "
             "de audiencia convienen a cada campaña, para que los agentes de campaña decidan con datos.",
        backstory="Eres analista de publicidad digital del Hotel Parador Monte Carmelo en Oaxaca. "
                  "Conoces cómo cambia el CPM entre días laborales, fines de semana, temporada alta y "
                  "eventos como la Guelaguetza. Tu trabajo es informar, no decidir presupuestos. " + _REGLAS,
        tools=[consultar_cpm_mercado, leer_inventario_audiencias],
        llm=llm, allow_delegation=False, verbose=True,
    )

    cultural = Agent(
        role="Agente de Campaña Cultural",
        goal="Maximizar la utilidad U = 0.5·Conversiones + 0.35·ROI + 0.15·Estabilidad de la campaña "
             "Cultural (leads críticos para la ocupación) con el presupuesto que le quede.",
        backstory="Gestionas la campaña dirigida a viajeros interesados en arqueología, historia y "
                  "turismo cultural en Oaxaca. Priorizas volumen de leads sin sacrificar rentabilidad. "
                  "Compruebas cada propuesta con la proyección de escenarios y el validador antes de "
                  "pedirla. " + _REGLAS,
        tools=[leer_metricas_campana, leer_inventario_audiencias, proyectar_escenario,
               calcular_utilidad, validar_restricciones],
        llm=llm, allow_delegation=False, verbose=True,
    )

    romantica = Agent(
        role="Agente de Campaña Romántica",
        goal="Maximizar la utilidad U = 0.4·Conversiones + 0.45·ROI + 0.15·Estabilidad de la campaña "
             "Romántica (el ROI es prioritario para la rentabilidad) con el presupuesto que le quede.",
        backstory="Gestionas la campaña dirigida a parejas, lunas de miel y escapadas gastronómicas. "
                  "Prefieres invertir donde el retorno es mayor y cedes presupuesto cuando otro "
                  "segmento rinde más. Compruebas cada propuesta con la proyección de escenarios y el "
                  "validador antes de pedirla. " + _REGLAS,
        tools=[leer_metricas_campana, leer_inventario_audiencias, proyectar_escenario,
               calcular_utilidad, validar_restricciones],
        llm=llm, allow_delegation=False, verbose=True,
    )

    broker = Agent(
        role="Broker de Presupuesto",
        goal="Repartir el presupuesto restante entre las campañas Cultural y Romántica para maximizar "
             "la utilidad total del sistema, respetando las restricciones.",
        backstory="Eres el árbitro del presupuesto de SOMACA. Recibes las solicitudes de las dos "
                  "campañas, que compiten por un presupuesto limitado, y decides cuánto asignar a cada "
                  "una. Si una propuesta es ambigua o inconsistente, pides aclaraciones al agente de "
                  "campaña correspondiente antes de decidir. " + _REGLAS,
        tools=[calcular_utilidad, proyectar_escenario, validar_reparto_presupuesto],
        llm=llm, allow_delegation=True, verbose=True,
    )

    monitor = Agent(
        role="Monitor Global de Cumplimiento",
        goal="Auditar la decisión final del sistema: confirmar que cumple las restricciones y que "
             "acerca las métricas a los objetivos, y emitir un veredicto claro.",
        backstory="Eres el auditor independiente de SOMACA. No propones presupuestos: verificas. "
                  "Contrastas la decisión del Broker con las reglas del PEAS y con los objetivos "
                  "(CPL ≤ 21.04 MXN, CTR ≥ 1.8%, ROAS ≥ 2.5x) y señalas cualquier violación o riesgo. " + _REGLAS,
        tools=[validar_restricciones, validar_reparto_presupuesto],
        llm=llm, allow_delegation=False, verbose=True,
    )

    return {"analista": analista, "cultural": cultural, "romantica": romantica,
            "broker": broker, "monitor": monitor}
