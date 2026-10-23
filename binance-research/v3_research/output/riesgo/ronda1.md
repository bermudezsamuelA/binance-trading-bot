# Gestor de Riesgo — Ronda 1

## 0. Veredicto

- **En 15m no hay E neta positiva en ninguna configuración.**
  - E_R > 0 en 0 de 3 447 configuraciones.
  - Solo una tiene E_% > 0: +0.022 %, sin significancia.
  - El borde **bruto** tampoco se separa de cero: entre −0.11 y +0.02 R (percentiles 5–95), con máximo de +0.07 R.
- **El WR de 70–80 % sale de la geometría, no de la señal.** Se logra con TP/SL ≈ 1/4–1/3 y siempre da E < 0. Las entradas aleatorias dan el mismo WR.
- **En 1h**, 45 de 3 447 configuraciones tienen E_R > 0. Todas son rupturas BO(n=96) en un diseño alcista. La mejor tiene t_mes = 2.05, por debajo del umbral de Bonferroni (4.18).
- **WR realista con E > 0: 40–60 %** (tendencia, b ≈ 0.8–1.9). Un WR de 70–80 % con E > 0 exige un borde bruto de ≥ 0.125 R y R ≥ 8c. Lo medido va de ≈ 0 a 0.08 R.
- **Riesgo recomendado:** f = 0 con dinero real. En testnet, 0.25 % por operación con topes, después de corregir los defectos de la §5.

## 1. Método

- **Partición:** DISEÑO 2023-01 a 2025-06, las 4 monedas juntas, una posición por moneda.
- **Ejecución simulada:** entrada al cierre de la vela de señal, igual que `entry_mode="close"` del arnés. TP/SL con high/low de las velas siguientes. Si TP y SL caen en la misma vela, cuenta como SL. Un hueco bajo el SL se llena a la apertura.
- **Costos:** s = 0.12 % por lado, c ≈ 0.24 %.
- **Validación del simulador:** reproduce `harness.py`. En BTC, MR 20/2 con salida 1/2 ATR y H 48: N = 2 446 en ambos y E de −0.2412 % frente a −0.2414 %.
- **Entradas:**
  - MR (z < −k).
  - BO (z > k).
  - n ∈ {20, 48, 96} y k ∈ {1.5, 2, 2.5}.
  - Control aleatorio (RND).
- **Salidas:**
  - TP = a·ATR14 y SL = m·ATR.
  - TP a una fracción del camino a la media.
  - Salida en la SMA móvil.
  - Chandelier.
  - Toma parcial del 50 % con stop a break-even.
  - Barrera de tiempo H.
  - Las geometrías actuales del bot.
- **Configuraciones probadas:** 3 447 en 15m + 3 447 en 1h (agregadas desde 15m) = **6 894**, más 294 de control. **Holdout: 0 consultas.**
- **Definiciones:**
  - WR = fracción con PnL neto > 0.
  - E_R = media de r_neto/R, lo que rinde el riesgo fijo.
  - E_% = lo que rinde el nocional fijo.
  - MDD en R.
  - t_mes = t de la suma mensual de R. Considera la correlación entre monedas.

## 2. Frontera WR–b–E (diseño)

| Caso | N | WR [IC 95 %] | b_ef | E % | E R | PF | MDD | t_mes |
|---|---|---|---|---|---|---|---|---|
| 15m bot MR (20,2) TP=μ, SL simétrico | 5 730 | 48.6 [47.3, 49.9] | 0.77 | −0.232 | −0.260 | 0.73 | 1 492 R | −11.1 |
| 15m bot BO (96,2.5) TP=2R (mejor del bot) | 1 220 | 35.7 [33.0, 38.4] | 1.73 | −0.077 | −0.092 | 0.96 | 144 R | −1.2 |
| 15m MR (48,2) 1/3 ATR, H 96 | 6 965 | 63.8 [62.7, 64.9] | 0.30 | −0.240 | −0.223 | 0.52 | 1 553 R | −12.1 |
| 15m RND, misma geometría | 31 751 | 62.8 [62.3, 63.3] | 0.29 | −0.243 | −0.233 | 0.50 | — | −12.8 |
| 15m, la mejor con WR 70–80 %: BO (96,2.5) 1.5/4 ATR | 3 320 | 70.7 [69.1, 72.2] | 0.31 | −0.169 | −0.120 | 0.75 | 410 R | −6.3 |
| 1h MR (48,2) 1/3 ATR, H 96 | 1 580 | 73.2 [70.9, 75.3] | 0.28 | −0.211 | −0.110 | 0.77 | 184 R | −4.4 |
| 1h, la mejor con WR 70–80 %: BO (96,2.5) 1.5/4 ATR, H 48 | 876 | 74.7 [71.7, 77.4] | 0.38 | +0.140 | +0.016 | 1.13 | 23 R | +0.56 |
| 1h, la mejor en general: BO (96,2.5) chandelier 3 ATR | 486 | 42.0 [37.7, 46.4] | 1.87 | +0.446 | +0.130 | 1.35 | 22 R | +2.05 |

**Configuraciones con E_R > 0 en la banda de WR 70–80 %** (N ≥ 200):

- 15m: 0 de 4.
- 1h: 3 de 401, la mejor con +0.016 R.

**Walk-forward anual dentro del diseño:**

- **15m:** ninguna configuración es positiva en ningún año.
- **1h:** el top-10 elegido en 2023 rinde +0.121 R en 2024, y el elegido en 2024 rinde +0.084 R en 2025S1. Las 14 configuraciones positivas los 3 años son BO(96, k ≥ 2), es decir, momentum en un mercado alcista. Hay riesgo de que dependa del régimen.

## 3. Primer paso, p* y costos

- **Teorema base:** si el precio es una martingala, P(TP primero) = m/(a+m) = 1/(1+b). Entonces p(1+b) = 1 y **E = −c para cualquier geometría**. La geometría solo elige un punto de la curva WR ↔ b.
- **Lo medido** (H = 96, a ≥ 0.5): en RND, P(TP primero) queda 0–2 puntos bajo m/(a+m). Con 1/3 ATR: 0.739 frente a 0.750 en 15m.
- **MR no lo mejora:** 0.740 en 15m y 0.737 en 1h.
- **Solo BO(96,2.5) en 1h lo sube 2–4 puntos:** 0.825 frente a 0.800 con 0.5/2.

**Margen p − p\*** (p* = (1 + c/R)/(1 + b)) en geometrías con WR teórico entre 70 y 80 %:

| Caso | c/R | p* | Margen | z |
|---|---|---|---|---|
| 15m | 0.11–0.56 | 0.81–1.25 | −0.08 a −0.50 | −11 a −431 |
| 1h MR | — | — | −0.06 a −0.28 | — |
| 1h BO 1.5/4 | 0.06 | 0.767 | 0.000 | 0.0 |

**R/c mínimo para E > 0** (de E/R = p(1+b) − 1 − c/R, despejando R/c > 1/(p(1+b) − 1)):

| p \ b | 0.33 | 0.43 | 0.50 | 0.75 | 1.0 |
|---|---|---|---|---|---|
| 0.70 | ∞ | 1000 | 20 | 4.4 | 2.5 |
| 0.75 | ∞ | 13.8 | 8.0 | 3.2 | 2.0 |
| 0.80 | 15 | 6.9 | 5.0 | 2.5 | 1.7 |

- **En precio:** R/c = 8 equivale a R ≥ 1.92 %.
- **ATR14 de 15m** (mediana): BTC 0.27 %, ETH 0.35 %, SOL 0.60 %, DOGE 0.53 %. Así que c ≈ 1 ATR de BTC.
- **Un TP de 0.25 ATR toca el 75 % de las veces**, pero el WR neto es del 7 %.
- **Por quintil de c/R**, la E bruta sigue en ≈ 0 (±0.05 R). Filtrar R grande baja la pérdida (de −0.47 a −0.05 R) pero no la vuelve positiva.
- **Un sistema real con WR 75 % y E = +0.05 R** (b neto 0.40, σ_X = 0.61) necesita 588 operaciones para t = 2 y 2 568 para el umbral de Bonferroni.

## 4. Tamaño y supervivencia

**Kelly:**

- Fórmulas: f* = p − (1−p)/b (fracción del capital arriesgada hasta el SL). La versión empírica es argmax E[ln(1 + fX)], y g(f) = E[ln(1 + fX)].
- Monte Carlo: bootstrap por semanas (conserva la correlación entre monedas), 4 000 años simulados.

| Caso | f* empírico | f con E − 1.645 EE | f = 1 %: MDD mediano / p95 / ruina (< 50 %) | ½ Kelly: MDD / ruina | Kelly: MDD / ruina |
|---|---|---|---|---|---|
| 15m bot MR | 0 | < 0 | con f = 0.5 %: 95 % / 97 % / 100 % | — | — |
| 1h WR 74.7 % | 0.055 | < 0 | 13 % / 25 % / 0 (ret. +5.4 % [−18, +37]) | 33 % / 4 % | 56 % / 31 % |
| 1h chandelier | 0.107 | 0.025 (con Bonferroni < 0) | 13 % / 24 % / 0 (ret. +25 % [−11, +91]) | 54 % / 22 % | 82 % / 55 % |

- **Con los 15 USDT fijos actuales**, el bot MR pierde unas 2 292 ops/año × 0.232 % × 15 ≈ **80 USDT al año**.

**Rachas** (cadena de Markov exacta; el umbral es la racha con P < 1 % en un año):

| Caso | Operaciones/año | Probabilidades de racha | Racha máx. en diseño | Umbral 1 % |
|---|---|---|---|---|
| WR 74.7 % | 350 | P(≥ 5) = 0.24, P(≥ 8) = 0.004 | 4 | 8 |
| WR 42 % | 194 | P(≥ 8) = 0.66 | 11 | 17 |

**Correlación y exposición:**

- **Retornos:** ρ = 0.70 de media, tanto en 15m (de 0.64 a 0.81) como en diario.
- **Operaciones solapadas:** ρ de 0.30 a 0.40. P(ambas pierden) = 0.405, frente a 0.264 si fueran independientes.
- **Concurrencia en 15m MR:** 2 o más posiciones abiertas el 47 % del tiempo y las 4 el 10 %.
- **Equivalencia:** N_ef = 4/(1 + 3ρ) = 1.3–1.8 apuestas independientes.
- **Regla de tamaño:** f_nueva = f_base/(1 + k_abiertas·0.4), con calor total ≤ 2·f_base.
- **Tope de nocional en spot:** f_max = 0.25·R. En 15m (R ≈ 1.1 %), el riesgo máximo es 0.28 %.

## 5. Cambios propuestos

**Python:** usar velas **cerradas** de la temporalidad del backtest.

- **Niveles:**
  - ATR = media de 14 TR.
  - R = m·ATR, SL = P − R y TP = P + a·ATR.
  - Trailing: SL_j = max(SL_{j−1}, máx H desde la entrada − m·ATR_e).
  - Barrera de tiempo t + H·Δt.
- **Filtros:**
  - R/P ≥ 10c (R ≥ 2.4 %).
  - a·ATR/P ≥ 2c.
- **Se envía:** `time_stop_ts` y `risk_per_unit = (P−SL) + s(P+SL)`.
- **Hay que quitar `round(x, 2)` y redondear al `tickSize`.** En DOGE (TrendFollowing 24/0.8), el **59.6 %** de las señales del diseño quedan con TP ≤ entrada o SL ≥ entrada. R pasa de 0.80 % a 3.02 % y b baja de 2 a 1.45.

**Node (`evaluateNewTrade`):**

```
s = 0.0012
lossU = (P - SL) + s*(P + SL);  gainU = (TP - P) - s*(P + TP);  si gainU <= 0 -> no operar
equity = USDT_libre + Σ q_j·P_actual_j
riesgo = equity · F_BASE / (1 + k_abiertas·0.4)                 // F_BASE = 0.0025 en testnet
riesgo = min(riesgo, 2·F_BASE·equity − Σ q_j·lossU_j)            // calor total
q = floor_step( min(riesgo/lossU, min(0.25·equity, 0.99·USDT_libre)/(P(1+s))), stepSize )
si q < minQty o q·P < minNotional -> no operar
```

**Otros defectos de ejecución:**

- `toFixed(2)` en el precio de la orden.
- La posición se registra sin confirmar el llenado. Hay que usar `executedQty` y el precio medio.
- El SL vive solo en memoria. Conviene una OCO en el exchange.
- No existe la barrera de tiempo.

**Interruptores:**

- Detener si la racha supera el umbral del 1 %.
- Detener si ΣR_vivo < n·E_diseño − 2σ_X·√n.

## 6. Condiciones de aceptación (Riesgo)

1. E_R > 0 en walk-forward, con t_mes por encima del umbral corregido por todas las configuraciones (6 894 hasta ahora, más las del Analista). Además, E_R > 0 en holdout.
2. Mediana de c/R ≤ 0.10.
3. f = min(¼·Kelly con la E en su cota inferior del 95 %, 0.25·R, 1 %).
4. Si se exige WR de 70–80 %: p − p* > 0 con z > 2 fuera de muestra **y** mejor que el control aleatorio de la misma geometría.

## Archivos

Scripts en `binance-research/data/research/scripts/`:

- `riesgo_sim.py`
- `riesgo_frontera.py` (argumento 1 = 15m, 4 = 1h)
- `riesgo_resumen.py`
- `riesgo_tabla_p.py`
- `riesgo_wf.py`
- `riesgo_sizing.py`
- `riesgo_extra.py`
- `riesgo_test_sim.py`
- `riesgo_check_harness.py`

Resultados en `output/riesgo/`:

- `frontera_15m.csv`
- `frontera_1h.csv`
- `sizing_log.txt`
- `tabla_p_log.txt`
- `wf_log.txt`
- `extra_log.txt`
