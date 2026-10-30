"""Las 5 tareas del MAS (Bloque C): description, expected_output, agent y context.

Las descripciones usan las variables {iteracion_corte}, {fecha_corte}, {primer_dia_restante},
{ultimo_dia} y {presupuesto_restante}, que main.py pasa en kickoff(inputs=...).
(No se usan llaves en los ejemplos de JSON para no chocar con la interpolación.)
"""
from crewai import Task


def crear_tareas(a: dict) -> list[Task]:
    analisis = Task(
        description=(
            "Estamos en la iteración {iteracion_corte} de 48 (fecha de corte: {fecha_corte}). Quedan "
            "los días del {primer_dia_restante} al {ultimo_dia}. 1) Consulta el CPM de mercado de cada "
            "día restante con consultar_cpm_mercado. 2) Lee el inventario de audiencias de las campañas "
            "Cultural y Romantica. 3) Para cada campaña identifica los 2 segmentos más atractivos "
            "según tasa de conversión y CPM esperado, explicando por qué."
        ),
        expected_output=(
            "Un objeto JSON con las claves: resumen_cpm (lista de períodos restantes con su rango de "
            "CPM y los días que cubre), cultural y romantica (cada una con segmentos_recomendados: "
            "lista de 2 elementos con segment_id, nombre y justificacion) y observaciones (texto breve)."
        ),
        agent=a["analista"],
    )

    def propuesta_campana(nombre: str, clave: str) -> Task:
        return Task(
            description=(
                f"Eres responsable de la campaña {nombre}. Estamos en la iteración {{iteracion_corte}} de 48 "
                "y el presupuesto restante total del sistema es {presupuesto_restante} MXN. 1) Lee tus "
                f"métricas con leer_metricas_campana (campana='{nombre.replace('ó', 'o')}', "
                "hasta_iteracion={iteracion_corte}) y diagnostica el desempeño frente a los objetivos. "
                "2) Usa proyectar_escenario para comparar al menos 3 alternativas (mantener segmento y "
                "presupuesto, cambiar de segmento, subir o bajar presupuesto). 3) Elige la mejor por "
                "utilidad (calcular_utilidad) y valídala con validar_restricciones. 4) Declara cuánto "
                "presupuesto necesitas para lo que queda y si pides o cedes presupuesto al Broker."
            ),
            expected_output=(
                "Un objeto JSON con las claves: campana, diagnostico (texto breve con cifras), "
                "alternativas_evaluadas (lista con segment_id, presupuesto, leads, roi y utilidad), "
                "propuesta (segment_id, presupuesto_restante_mxn, cambio_puja_pct, cambio_audiencia: "
                "true o false), utilidad_esperada, solicitud_al_broker (tipo: pedir, ceder o mantener; "
                "monto_mxn; razon) y validacion (resultado de validar_restricciones)."
            ),
            agent=a[clave],
            context=[analisis],
            async_execution=True,  # las dos campañas se evalúan en paralelo
        )

    cultural = propuesta_campana("Cultural", "cultural")
    romantica = propuesta_campana("Romántica", "romantica")

    asignacion = Task(
        description=(
            "Recibes las propuestas de las campañas Cultural y Romántica. Decide el reparto del "
            "presupuesto restante ({presupuesto_restante} MXN) para maximizar la utilidad total del "
            "sistema. 1) Compara ambas propuestas y sus solicitudes (pedir/ceder). 2) Si algo es "
            "ambiguo o inconsistente, delega una pregunta de aclaración al agente de campaña "
            "correspondiente. 3) Propón el reparto final y valídalo con validar_reparto_presupuesto; si "
            "viola alguna restricción, ajústalo hasta que sea válido. 4) Justifica la decisión."
        ),
        expected_output=(
            "Un objeto JSON con las claves: presupuesto_cultural_mxn, presupuesto_romantica_mxn, "
            "cambio_pct (por campaña), segmento_final (por campaña), justificacion, "
            "aclaraciones_solicitadas (lista, vacía si no hubo) y validacion (resultado de "
            "validar_reparto_presupuesto)."
        ),
        agent=a["broker"],
        context=[cultural, romantica],
    )

    auditoria = Task(
        description=(
            "Audita la decisión final del sistema. 1) Verifica el reparto con "
            "validar_reparto_presupuesto. 2) Verifica cada campaña con validar_restricciones usando los "
            "cambios de presupuesto, de puja y de audiencia propuestos. 3) Contrasta lo proyectado con "
            "los objetivos (CPL ≤ 21.04 MXN, CTR ≥ 1.8%, ROAS ≥ 2.5x, 45-48 leads) y señala qué se "
            "cumple y qué no. 4) Emite un veredicto: aprobado, aprobado_con_observaciones o rechazado."
        ),
        expected_output=(
            "Un objeto JSON con las claves: veredicto, restricciones_cumplidas (true o false), "
            "violaciones (lista), objetivos (por métrica: meta, proyectado y cumple), riesgos (lista) "
            "y resumen_ejecutivo (máximo 5 líneas para el hotel)."
        ),
        agent=a["monitor"],
        context=[analisis, cultural, romantica, asignacion],
    )

    return [analisis, cultural, romantica, asignacion, auditoria]
