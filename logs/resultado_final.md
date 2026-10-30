```json
{
  "veredicto": "aprobado_con_observaciones",
  "restricciones_cumplidas": true,
  "violaciones": [],
  "objetivos": {
    "CPL": {
      "meta": "≤ 21.04 MXN",
      "proyectado": "Cultural (segmento 5, 250 MXN): 26.50 MXN. Romántica (segmento 3, 250 MXN): 21.27 MXN.",
      "cumple": "No. Cultural excede la meta por 5.46 MXN. Romántica queda 0.23 MXN por encima. Acumulado Romántica: 20.83 MXN (sí cumple)."
    },
    "CTR": {
      "meta": "≥ 1.8%",
      "proyectado": "No reportado por la herramienta para la propuesta final. Acumulado: Cultural 3.48%, Romántica 3.47%.",
      "cumple": "Sí en el acumulado de ambas campañas. No verificable en la proyección."
    },
    "ROAS": {
      "meta": "≥ 2.5x (ROI ≥ 1.5)",
      "proyectado": "Cultural (segmento 5, 250 MXN): 3.40x (ROI 2.40). Romántica (segmento 3, 250 MXN): 4.23x (ROI 3.23).",
      "cumple": "Sí en ambas campañas, con margen."
    },
    "leads": {
      "meta": "45-48 leads",
      "proyectado": "18.9 (Cultural) + 23.5 (Romántica) = 42.4 leads en la proyección. Acumulado previo: 8 + 12 = 20 leads.",
      "cumple": "No, según la proyección (42.4 < 45). Si la meta se interpreta como total acumulado más proyección (62.4), se superaría. La base de la meta debe aclararse."
    }
  },
  "riesgos": [
    "Cultural (segmento 5) tiene fuente 'sintetico'. Su utilidad de 0.7694 con 250 MXN no tiene respaldo real. El CPL proyectado de 26.50 MXN queda lejos de la meta. Se trata como prueba condicionada.",
    "Cultural arrastra un CPM efectivo de 37-39 MXN con el segmento 1. El cambio a segmento 5 es una hipótesis por validar. Criterio de reversión: CPM real > 26 MXN o conversión < 3% durante 4 iteraciones seguidas.",
    "Romántica registró un CPM efectivo de 36-43 MXN en las iteraciones 21-24, por encima de su inventario (28-38 MXN). La herramienta no permite ingresar ese CPM, por lo que las proyecciones pueden ser optimistas.",
    "Las iteraciones 21-24 de Romántica están fechadas 2026-11-14. El agente confirma fechas consecutivas y sin duplicados, pero la trazabilidad debe revisarse.",
    "Las dos solicitudes de 50 MXN (Cultural y Romántica) eran incompatibles con el total fijo de 500 MXN. La decisión final las resuelve en 250/250 y no requiere cambio de presupuesto. Las alternativas de 300 MXN no están aprobadas.",
    "Riesgo de meta de leads: la proyección (42.4) queda por debajo de 45 leads. Sin más presupuesto o una mejora de CPL, no se alcanzará el rango objetivo.",
    "Restricción de audiencia: Cultural usa su único cambio de audiencia de la iteración (1 → 5). Romántica no cambia audiencia."
  ],
  "resumen_ejecutivo": [
    "Decisión auditada: reparto 250/250 MXN, sin cambios de presupuesto ni de puja; cumple todas las reglas del PEAS (validación verificada).",
    "ROAS proyectado: Cultural 3.40x y Romántica 4.23x, ambos por encima de la meta de 2.5x.",
    "CPL: Romántica 21.27 MXN (≈ meta de 21.04, por poco); Cultural 26.50 MXN (no cumple).",
    "Leads proyectados 42.4, por debajo del rango de 45-48; se requiere aclarar la base de la meta.",
    "Cultural (segmento 5) es una prueba condicionada con datos sintéticos; Romántica mantiene su segmento con datos reales. Vigilar CPM y fechas."
  ]
}
```