# Verificador, fase 2: auditoría y prueba única de ENS6 (2026-10-14, 06:50 VST)

**Veredicto pre-registrado: RECHAZA.**

| Criterio | Resultado |
|---|---|
| (a) E > 0 con t por día > 1.645 y E > 0 con costos de 0.30 % | No cumple |
| (b) Límite inferior de Wilson del WR ≥ 0.70 | No cumple |
| (c) ΔE frente al azar > 0 con p < 0.05 en las dos pruebas | Cumple |
| (d) Auditoría sin fugas | Cumple |

La red elige entradas mucho mejores que el azar de la misma geometría, también en monedas que nunca vio. Pero en la prueba primaria ni la esperanza absoluta ni el WR ≥ 70 % quedan demostrados, y en la secundaria la E es negativa.

## 1. Auditoría (terminada antes de ejecutar; `auditoria_nn.md`)

- **Hashes.** Los 7 scripts y los 9 archivos de modelo coinciden con `spec_nn.json`.
- **Perturbación del futuro** (`verificador/audit_nn.py`).
  - Hice 16 cortes en SOL y ETH, incluidos 2023, el cambio de convención del 2024-03-03/04 y 2025.
  - En cada corte alteré todo lo que no se conoce al cierre de la vela: spot, BTC, metrics con T > t+5 y con T > t+10 min, funding, prima y velas UM.
  - Las 74 variables de todas las velas anteriores al corte quedaron **idénticas** (diferencia 0.0). Después del corte cambió el 90 %.
- **Alineación de cada fuente.**
  - Velas UM: correlación 0.998 con spot sin desfase, ≈ 0 con ±1 vela.
  - Extremos de premiumIndex: caen en la vela de la divergencia entre futuros y spot o en la siguiente, nunca antes.
  - Metrics: usa T ≤ t_i + 5 min, más estricto que mi regla.
  - Funding: usa calc_time ≤ cierre.
- **Umbral.** Lo recalculé con los modelos congelados: el cuantil 0.98 de p en la validación 2025-04..06 (34 172 velas) da 0.713364215387, **idéntico** al congelado. Platt y la parada temprana también se ajustaron solo en esa validación.
- **Resto del proceso.**
  - Hay purga de 193 velas (H + 1) antes de la validación y del test.
  - La etiqueta no está entre las variables.
  - El escalador del MLP se ajustó solo con los datos de ajuste.
  - BTC se alinea por `open_time` y se rellena solo hacia adelante.
  - Los datos de futuros del Constructor llegan hasta 2025-06-30, y no tocó el holdout.
- **Prueba de humo reproducida.** En 2025-04..06 da n = 51, WR 86.3 % y E +1.72 %, exactamente lo reportado. `verify.py` replica las 51 salidas.
- **Conclusión: no encontré fugas.**

## 2. Resultados (ejecución única, registrada en `ejecuciones_log.csv` con hashes)

`verify.py` replica las 587 operaciones sin ninguna discrepancia y sin solapamientos. El control aleatorio es emparejado (200 repeticiones) y N = 12 322 configuraciones.

| | Diseño WF (4 monedas) | **Primaria** (6 reservadas) | Secundaria (4 originales) |
|---|---|---|---|
| n (ops/moneda/año) | 132 (22) | **383 (51)** | 204 (41) |
| WR [Wilson 95 %] | 72.0 [63.8, 78.9] | **68.7 [63.9, 73.1]** | 60.8 [53.9, 67.2] |
| Wilson con n_ef (DEFF) | — | 59.9 (3.08) | 49.8 (2.30) |
| b efectivo / WR de equilibrio | 0.68 / — | 0.59 / 63.0 | 0.57 / 63.9 |
| E neta (en R) | +0.93 % (+0.12) | **+0.41 % (+0.06)** | −0.22 % (−0.04) |
| t por día (días) | 2.33 | **1.08 (102)** | −0.47 (76) |
| E con costos de 0.30 % (t) | +0.87 % | +0.35 % (0.92) | −0.28 % (−0.61) |
| PF / MDD (100 % del capital) | 1.74 / 51 % | 1.29 / 73 % | 0.88 / 73 % |
| Azar: WR / E | 55.2 / −0.49 % | 51.7 / −0.73 % | 52.3 / −0.73 % |
| **ΔWR** (p) | +16.7 | **+16.9 (p < 0.001)** | +8.5 (p 0.04) |
| **ΔE** (t por día; p de repeticiones) | +1.41 % (3.54) | **+1.13 % (2.94; 0.005)** | +0.51 % (1.09; 0.02) |
| DSR | 0.14 | 0.04 | 0.00 |

**Primaria por moneda (E, WR):**

| Moneda | E | WR | t por día |
|---|---|---|---|
| XRP | +0.87 % | 74 % | 2.28 |
| LINK | +0.70 % | 71 % | — |
| AVAX | +0.52 % | 71 % | — |
| ADA | +0.35 % | 63 % | — |
| LTC | +0.14 % | 64 % | — |
| BNB | −0.32 % | 67 % | — |

**Primaria por trimestre (WR, E):**

| Trimestre | WR | E |
|---|---|---|
| 2025T3 | 92 % | +1.77 % |
| 2025T4 | 69 % | +0.66 % |
| 2026T1 | 60 % | +0.03 % |
| 2026T2 | 53 % | −0.76 % |
| 2026T3 | 81 % | +0.98 % |

**Concentración.** Hay 383 operaciones en solo 102 días. Los 10 días con más entradas reúnen 136 operaciones, con E de +1.23 %; el resto tiene E de −0.05 %. Las entradas son capitulaciones simultáneas en varias monedas, de ahí el DEFF de 3.1 y la t baja.

## 3. Respuestas separadas

**(A) ¿Hay ventaja? Relativa sí; absoluta no demostrada.**

- **(c) y (d) se cumplen.** Dentro de la misma moneda, el mismo mes y la misma geometría, la red supera al azar por +16.9 puntos de WR y +1.13 % de E, prácticamente lo mismo que en diseño (+16.7 y +1.41 %), y en monedas nunca vistas. Superó a las 200 repeticiones aleatorias. La auditoría descarta que esto venga de una fuga.
- **(a) no se cumple.** La E absoluta es +0.41 % (+0.35 % con costos de 0.30 %), con t por día de 1.08 (p ≈ 0.14). Se redujo un 56 % frente al diseño, en línea con la maldición del ganador que se esperaba.
- **Por qué la ventaja relativa no basta.** El periodo fue bajista para estas monedas (el azar dio E −0.73 %), y la ventaja relativa apenas compensa esa deriva.
- **La secundaria no la respalda.** La E es −0.22 % y ΔE +0.51 % no es significativo por día (p 0.14).
- **Cuánta muestra haría falta.** Con la E y la agrupación observadas, (a) necesitaría unas 890 operaciones para t = 1.645 y unas 2 000 para una potencia del 80 %. A esta frecuencia, con las 6 monedas, eso son unos 3 y unos 6.5 años de datos.

**(B) ¿Se demuestra WR ≥ 70 %? No.**

- **Primaria.** El WR puntual es 68.7 %, por debajo de la meta. Su IC 95 % es [63.9, 73.1]: excluye el 80 % y contiene el 70 %, pero el límite inferior (63.9 %) queda lejos de 0.70. Corregido por agrupación diaria, el límite inferior baja a 59.9 %.
- **Secundaria.** WR 60.8 % [53.9, 67.2], que excluye el 70 %.
- **La muestra no era el problema.** Hubo 383 operaciones, más de las 324 que el pre-registro pedía para un WR de 0.75. Con un WR observado inferior a 0.70, ningún n habría bastado.

## 4. Observaciones

1. **Frecuencia.** Fueron 51 operaciones por moneda y año en lugar de 15–30: en las monedas nuevas p supera el umbral en el 3–5.6 % de las velas, frente al 2 % de la validación. El umbral no se traslada bien entre monedas.
2. **Bloque de riesgo.** El modelo compra capitulaciones correlacionadas entre monedas. Las pérdidas llegan en bloque (2026T2: WR 53 %) y un MDD del 73 % con el capital completo exige dimensionar por riesgo.
3. **Lo que queda.** La única evidencia sólida es la ventaja relativa sobre el azar de la misma geometría. Si se sigue, recomiendo una prueba prospectiva (datos desde 2026-10) con tamaño por riesgo y el criterio (a) pre-registrado, sin reajustar nada.
4. **Lo que no se cambió.** Los criterios no se modificaron. La propuesta del Constructor de evaluar solo E > 0 y ΔE tampoco lleva a aceptar: falla (a).

**Archivos:**

- `research/verificador/runs/{primaria,secundaria}/`: operaciones, `all.csv` y `verify.json`.
- `research/verificador/audit_nn.py`, `audit_thr.py` y `convert_trades.py`.
- `research/output/verificador/auditoria_nn.md` y `ejecuciones_log.csv`.
- `harness.bounds` dejó 2 líneas en `output/validador/holdout_log.csv`, solo con los nombres de las monedas, sin resultados.
