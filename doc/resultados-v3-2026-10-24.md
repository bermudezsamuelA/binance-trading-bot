# Resultados de la v3 al 2026-10-24

Todo con el modelo congelado (`spec_nn_v2.json`, hashes verificados), salida X5 con 384 velas, 15 USDT por operación y costo de 0.24 % ida y vuelta salvo que se indique. Salidas completas en `binance-research/v3_research/output/`.

## Respuesta corta

- **Lo único que gana dinero fuera de muestra es la v3**, y gana poco: con las monedas y el periodo nuevos a la vez (2025-07 a 2026-09), C0 en 19 monedas nunca usadas dio **E +0.41 % por operación, +95 USDT en 15 meses** (≈ +6 USDT/mes con 15 USDT por operación), con 14 de 19 monedas en positivo. **No es significativo** (t por día 1.08, p = 0.14) y solo **8 de 15 meses** fueron positivos.
- **En un mercado bajista pierde:** en 2022 (LUNA, FTX), S1 en 18 monedas perdió −44.49 USDT (6 de 18 monedas en positivo), aunque siguió ganándole al azar por +6 pt de WR.
- **Un PnL positivo todos los meses no está al alcance** con esta estrategia: en todos los periodos medidos hay entre un tercio y la mitad de meses negativos, con peores meses de −28 a −36 USDT.
- **Lo que se descartó con datos nuevos:** las 5 estrategias de Bollinger (pierden en 10-11 de cada 13 monedas nuevas) y el filtro de régimen "BTC > media de 30 días" (mejoraba 2025-26 pero empeoró 2022).

## Tablas

**C0 en 19 monedas nuevas** (`monedas_nuevas_20/`, pre-registrado; EOS quedó fuera por falta de datos antes de ver resultados):

| Periodo | Operaciones | WR | E | PnL | Monedas + | Meses + | p |
|---|---|---|---|---|---|---|---|
| 2023-03 a 2025-06 (años de entrenamiento del modelo, con otras monedas) | 3041 | 76.7 % | +0.85 % | +386 USDT | 19/19 | 25/28 | < 0.001 |
| **2025-07 a 2026-09 (nuevo en monedas y en tiempo)** | 1548 | 72.5 % | **+0.41 %** | **+95 USDT** | 14/19 | 8/15 | 0.14 |

La primera fila está inflada: el modelo aprendió el comportamiento del mercado en esos años, aunque fuera con otras monedas. La que cuenta es la segunda.

**Universo de 18 del pre-registro** (S1 = v2 + al menos 3 de las otras 17 monedas con señal en 12 h):

| Periodo | Operaciones | WR | E | PnL | Monedas + | Meses + | Peor mes | Caída máx. |
|---|---|---|---|---|---|---|---|---|
| 2022 (estrés, datos nuevos) | 1129 | 67.1 % | −0.26 % | −44.49 USDT | 6/18 | 5/12 | −34.2 | 102.0 |
| 2025-07 a 2026-09 (ya gastado, descriptivo) | 1051 | 72.1 % | +0.22 % | +34.13 USDT | 14/18 | 10/15 | −28.7 | 71.5 |
| 2026-10-01 a 2026-10-23 (prospectivo) | 33 | 72.7 % | +0.20 % | +0.99 USDT | 8/15 | — | — | — |

**Costos:** con BNB y el TP como orden límite (0.17 %), la E sube unos +0.065 puntos por operación en todos los brazos (S1 2025-26: +0.216 % → +0.281 %).

## Riesgo y tamaño

- Con 18-19 monedas puede haber **hasta 19 posiciones abiertas a la vez**: con 15 USDT por operación hacen falta ≈ 285 USDT.
- Caídas máximas de 70 a 102 USDT: entre el 25 % y el 36 % de ese capital.
- El PnL escala con el tamaño, pero la caída también, en la misma proporción. Con 30 USDT por operación (≈ 570 USDT de capital) la expectativa del periodo nuevo sería ≈ +12 USDT/mes, con meses de −70 USDT.
- **Recomendación:** dinero real en cero hasta que el canal sombra acumule 150-200 operaciones de S1 posteriores al 2026-10-01 (4-5 meses al ritmo actual) y la E siga positiva con t por día ≥ 1.645.

## Coinalyze (la v3 en vivo)

Coincide casi perfecto con Binance en *open interest*, ratio long/short global, flujo *taker*, velas del perpetuo y *funding* (correlaciones ≥ 0.999). No tiene los ratios de top traders ni la prima. La prueba de equivalencia del modelo **no es concluyente**: no hubo señales en los 5 días que cubre Coinalyze. La p del modelo correlaciona 0.94 en general y 0.73 cerca del umbral. La caché crece con cada corrida, así que la prueba se vuelve concluyente con el tiempo. `v3_live.py` genera las señales en vivo sin enviar órdenes.

## Qué falta

1. Acumular operaciones prospectivas (tarea semanal: `scripts/programar_tareas_v3.ps1`).
2. Que la equivalencia de Coinalyze dé "equivalente" con al menos 5 señales.
3. Solo entonces: órdenes de la v3 en la testnet (cierre a las 384 velas, tamaño por riesgo y topes de la sección 7.2 de la estrategia v3).
