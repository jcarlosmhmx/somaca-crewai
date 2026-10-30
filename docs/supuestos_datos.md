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
| Reparto inicial 500/500, segmentos iniciales (1 y 3), inicio 9-nov-2026, semilla 13 | **Supuesto** del prototipo |

## Hallazgos: inconsistencias del PEAS

1. **CPC [5, 100] MXN vs. CPM y CTR.** Con CPM de 20-38 MXN y CTR ≥ 1.8 %, el CPC sale de CPM / (1000 × CTR) ≈ 1-2 MXN, no 5-100. El simulador **deriva** el CPC (rango observado ≈ 0.6-5.2 MXN) en lugar de forzar el rango del PEAS.
2. **Presupuesto.** La Ficha dice 1,000 MXN/mes y el PEAS 1,000 MXN en 12 días; se usa el PEAS.
3. **Segmentos.** La Ficha habla de 120 combinaciones (5 audiencias) y el PEAS de 40+ segmentos; se usan 10.

*Corrección:* una versión anterior de este documento decía que la meta de 45-48 leads quedaba "al límite de lo posible". Con 500 semillas la línea base sin optimizar promedia 41.7 leads (desviación 6.3; mínimo 26, máximo 66), así que la meta es alcanzable y está ligeramente por encima de lo típico.

## Elección de la semilla (13)

La semilla 42 produjo un empate accidental: a la iteración 24 ambas campañas acumulaban 8 leads y 720 MXN de ingresos, aunque sus filas son distintas (0 de 48 iguales). Un agente auditor lo interpretó como posible duplicación de datos y bloqueó la transferencia de presupuesto, por lo que la demo no mostraba la negociación.

Se escogió otra semilla con un criterio fijado antes de mirar los resultados: de las 500 primeras semillas (1 a 500), la **más pequeña** que cumple las tres condiciones siguientes. Salieron 12 y la menor es la 13.

1. A la iteración 24 las campañas no coinciden en leads ni en ingresos.
2. El total de leads de los 12 días está a ≤ 0.5 desviaciones de la media (41.7), es decir, una línea base típica.
3. Una campaña queda bajo el ROAS objetivo de 2.5x y la otra sobre él, para que haya algo que reasignar.

Esto es un artificio de la demo: la semilla se eligió para que el caso de prueba fuera informativo, y así debe declararse.

## Línea base (semilla 13, sin optimizar)

| Campaña | Gasto | Leads | CPL | ROAS |
|---|---|---|---|---|
| Cultural (seg. 1) | 500 | 13 | 38.46 | 2.34 |
| Romántica (seg. 3) | 500 | 26 | 19.23 | 4.68 |
| **Total** | **1,000** | **39** | **25.64** | |

A la iteración 24: Cultural 8 leads (ingresos 720) y Romántica 12 leads (ingresos 1,080). La Cultural queda bajo el ROAS objetivo (2.34x contra 2.5x) y la Romántica muy por encima, lo que da a los agentes una reasignación de presupuesto real que evaluar.
