# Datos sintéticos: fuentes, supuestos y hallazgos

## Qué viene del PEAS (Fase 2) y qué es supuesto

| Dato | Origen |
|---|---|
| Pesos de utilidad por campaña | PEAS C.1 |
| Objetivos (leads, CPL, CTR, impresiones, ROAS, lead→reserva) | PEAS C.1 |
| Segmentos 1-4 (conv. rate y CPM) | PEAS C.2, tabla 1 |
| CPM por período y variación | PEAS C.2, tabla 2 |
| Restricciones (±20 % presupuesto, ±10 % puja, 1 cambio de audiencia, pausa si ROI < 0.5x) | PEAS C.3 |
| Iteraciones de 6 h, 12 días | PEAS C.4 / C.1 |
| **Segmentos 5-10** | **Supuesto** (el PEAS habla de 40+; el prototipo usa 10) |
| **`ctr_base` de cada segmento** | **Supuesto** (el PEAS solo fija CTR ≥ 1.8 %) |
| **Ingreso por reserva = 900 MXN, lead→reserva = 10 %** | **Supuesto** (el PEAS solo fija ROAS ≥ 2.5x y lead→reserva ≥ 10 %) |
| Reparto inicial 500/500, segmentos iniciales (1 y 3), inicio 9-nov-2026 | **Supuesto** del prototipo |

## Hallazgos: inconsistencias numéricas del PEAS

1. **CPC [5, 100] MXN vs. CPM y CTR.** Con CPM de 20-38 MXN y CTR ≥ 1.8 %, el CPC sale de CPM / (1000 × CTR) ≈ 1-2 MXN, no 5-100. El simulador **deriva** el CPC (rango observado ≈ 0.6-5.2 MXN) en lugar de forzar el rango del PEAS.
2. **Leads 45-48 vs. tasas de conversión de 2.5-5 %.** Con 1,000 MXN, esas tasas y los CPM del PEAS, el máximo realista ronda 44-49 leads (mejores segmentos); el reparto inicial da ≈ 40 esperados (32 con semilla 42).
3. **Presupuesto.** La Ficha dice 1,000 MXN/mes y el PEAS 1,000 MXN en 12 días; se usa el PEAS.
4. **Segmentos.** La Ficha habla de 120 combinaciones (5 audiencias) y el PEAS de 40+ segmentos; se usan 10.

## Línea base (semilla 42, sin optimizar)

| Campaña | Gasto | Leads | CPL | ROAS |
|---|---|---|---|---|
| Cultural (seg. 1) | 500 | 12 | 41.67 | 2.16 |
| Romántica (seg. 3) | 500 | 20 | 25.00 | 3.60 |
| **Total** | **1,000** | **32** | **31.25** | |

La campaña Cultural queda bajo el ROAS objetivo (2.5x), lo que da a los agentes algo real que optimizar.
