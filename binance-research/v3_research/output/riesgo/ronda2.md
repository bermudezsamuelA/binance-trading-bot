# Gestor de Riesgo — Ronda 2 (solo DISEÑO; holdout cerrado, 0 consultas)

## 1. Riesgo de C1 (2023-10 a 2025-06, operaciones del arnés)

- **Reproducción:** con `harness.simulate` y `build_scores` del Analista (h = 96, Q90) se obtienen las mismas N y E que en su ronda 1.
- **Criterio de elección de geometría:** lo declaré en el código antes de correr. Se elige la que maximiza **LCB95(E con costos 0.30 %) / CVaR95**, es decir, la ventaja mínima creible por unidad de pérdida de cola.
  - LCB95 = percentil 5 de un bootstrap por semanas.
  - CVaR95 = pérdida media del 5 % peor de las operaciones.
- **Variante nueva:** C48 (tiempo 48 velas + stop de catástrofe en c − 3R). Cuenta como +1 configuración.

| | T48 | G2H96 | G3H96 | C48 (nueva) |
|---|---|---|---|---|
| N (ops/año) | 459 (262) | 495 (283) | 467 (267) | 487 (278) |
| WR [IC 95 %] | 61.7 [57.1, 66.0] | 68.3 [64.1, 72.2] | **72.4 [68.2, 76.2]** | 60.4 [56.0, 64.6] |
| b_ef | 0.95 | 0.63 | 0.53 | 0.90 |
| E neta (t / t mensual) | **+0.73 % (3.27 / 3.18)** | +0.50 % (2.73 / 2.82) | +0.54 % (2.67 / 2.93) | +0.54 % (2.52 / 2.87) |
| E_R (R mediano) | +0.26 (2.7 %, distancia a la media) | +0.030 (5.9 %) | +0.034 (8.7 %) | +0.063 (8.4 %) |
| PF / meses con suma > 0 | 1.53 / 19 de 21 | 1.35 / 18 de 21 | 1.38 / 16 de 21 | 1.36 / 18 de 21 |
| E con costos 0.30 % (t) | +0.67 % (3.00) | +0.44 % (2.40) | +0.48 % (2.37) | +0.48 % (2.24) |
| LCB95 de E: 0.24 % / 0.30 % | +0.37 % / **+0.32 %** | +0.21 % / +0.14 % | +0.22 % / +0.16 % | +0.20 % / +0.14 % |
| Cola: peor 1 % / CVaR95 / peor operación | −14.8 / 10.7 / −21.8 % | −9.8 / 8.8 / −13.3 % | −13.2 / 11.9 / −19.8 % | −11.4 / 10.6 / −17.7 % |
| **Criterio** | **0.029** | 0.016 | 0.014 | 0.013 |
| Costo de equilibrio ida y vuelta | ≈ 0.97 % | ≈ 0.74 % | ≈ 0.78 % | ≈ 0.78 % |

**Concentración de pérdidas** (T48):

- El peor día (6 operaciones) suma −47.5 % de nocional, y los 10 peores días explican el 39 % de todas las pérdidas.
- Las operaciones solapadas tienen ρ = 0.54 (0.43–0.45 en las otras geometrías). P(ambas pierden) = 0.26, frente a 0.15 si fueran independientes.
- La excursión adversa intra-operación tiene p99 de −21 % y peor caso de −29.4 %.

**Hallazgo importante:** la E de C1 **sube** con el número de posiciones ya abiertas al entrar:

| Posiciones ya abiertas | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| E | +0.44 % | +0.67 % | +1.43 % | +2.23 % |
| N | 266 | 110 | 51 | 32 |

- Reducir el tamaño por correlación (f/(1 + k·0.5)) **empeora** todo: la E por nocional baja a 0.61 % y el MDD p95 sube de 6.3 a 7.5 %.
- Por eso, en C1 el riesgo de correlación se controla con un **tope de nocional total**, no reduciendo el tamaño de cada entrada.
- No propongo aprovecharlo agrandando el tamaño: es una observación dentro de la muestra y con N pequeñas.

**Kelly** (w = fracción del capital invertida en cada operación; el Kelly binario no aplica sin un stop fijo):

| | Kelly empírico w* | w con E en LCB95 al 0.30 % | ¼ de ese w |
|---|---|---|---|
| T48 | 2.77 | 1.35 | 0.34 |
| G2H96 | 2.78 | 0.81 | 0.20 |
| G3H96 | 2.37 | 0.83 | 0.21 |

Con la E rebajada al umbral de Bonferroni (z ≈ 4, t mensual de 3.18 < 3.96–4.46), w = 0.

**Monte Carlo a 1 año:** 52 semanas remuestreadas; dentro de cada semana las pérdidas simultáneas se suman.

| | MDD med / p95 / p99 | P(MDD > 20 %) | Ruina (< 50 %) | Retorno mediano [p5] |
|---|---|---|---|---|
| T48, w = 0.10 | 3.0 / 6.2 / 8.3 % | 0 | 0 | +20 % [+5.6 %] |
| T48, w = 0.25 | 7.3 / 15.1 % | 0.95 % | 0 | +57 % [+14 %] |
| T48, w = 0.34 (¼ Kelly-LCB) | 10.1 / 20.5 % | 5.7 % | 0 | +81 % |
| T48, w = 1.39 (½ Kelly) | 41 / 67 % | 87 % | 5.5 % | — |
| G3H96, w = 0.10 | 3.3 / 6.7 % | 0 | 0 | +15 % |

**Rachas** (cadena de Markov exacta, 1 año):

| | P(≥ 5) | P(≥ 8) | Racha con P < 1 % | Racha máxima observada |
|---|---|---|---|---|
| T48 | 0.74 | 0.071 | 11 | 7 |
| G2H96 | 0.46 | 0.019 | 9 | 6 |
| G3H96 | 0.27 | 0.006 | 8 | 6 |

**Respuesta.** Sí: en DISEÑO, E > 0 neta en las 4 geometrías, incluso con costos de 0.30 % (LCB95 > 0). El capital sobrevive con un nocional por operación ≤ 0.25 (ruina 0, P(MDD > 20 %) ≤ 2 %). Tres reservas:

- No pasa Bonferroni. El conteo del equipo va en 12 105 configuraciones; mi parte quedó registrada y corregida con `log_trials`.
- El periodo es alcista: comprar la caída tiene riesgo de régimen.
- La cola es correlacionada. Con w = 0.10, el peor día habría costado **−4.75 % del capital**. Si 4 posiciones tocaran el stop de catástrofe a la vez, la pérdida teórica máxima sería del 14 %.

**Tamaño propuesto para C1:**

- **Testnet:** w = 0.10 de nocional por operación y ≤ 0.40 en total (4 monedas). Es ≈ 1/13 del Kelly-LCB. Elijo este nivel porque no supera Bonferroni y porque fija la pérdida del peor día en < 5 %.
- **Dinero real:** solo si el holdout pasa. Empezar con w = 0.05 durante 100 operaciones, luego 0.10, y nunca superar 0.25 ni ¼ del Kelly-LCB recalculado con datos en vivo.

## 2. Qué geometría prefiero

- **Elijo T48 por el criterio declarado** (0.029 frente a 0.016, 0.014 y 0.013). Tiene:
  - el doble de E mínima creíble con costos de 0.30 % (+0.32 % frente a +0.14–0.16 %);
  - el mejor t mensual (3.18) y 19 de 21 meses positivos;
  - el costo de equilibrio más alto (0.97 %).
- **El SL no reduce la cola.** Ni el de c − 3R (G3: CVaR95 de 11.9 % frente a 10.7 % en T48) ni el de catástrofe (C48: le quita 0.19 pp de E a T48 y no mejora el CVaR, 10.6 %). Las pérdidas grandes vienen de caídas de todo el mercado; el stop vende en el fondo, antes del rebote.
- **G3H96 es la única con WR de 70–80 %** (72.4 %). Para lograrlo cede la mitad de la ventaja creíble (LCB95 de +0.16 % frente a +0.32 %), y su cola es igual o peor. No la vetaría (E > 0 y sobrevive), pero **el WR realista con E máxima es ≈ 62 %**.
- **Al holdout debe ir una sola geometría**, declarada de antemano.

## 3. Mi candidato BO 1h: lo retiro

Le apliqué el walk-forward 12/3/3 del Validador a mi familia 1h, con la regla «máxima E_R en el entrenamiento» y purga:

- **OOS concatenado:** N = 210, E_R = +0.234, t = 2.21. Solo **3 de 6 pliegues** son positivos.
- **La selección es inestable:** alterna entre BOT_BO y CHAN.
- **El candidato fijo** (BO 96/2.5 con chandelier 3) da t = 2.42 en esos meses, pero eso es dentro de la muestra.
- **No cumple el protocolo:** falla P4(a) (Bonferroni 4.18 o más), P4(c) (N mínimo) y P4(d) (≥ 4 de 6 pliegues).
- **Además es momentum de un mercado alcista** y su WR es del 42 %.

## 4. Paquete de riesgo (independiente de la señal)

**Tamaño en Node, en `evaluateNewTrade`.** P = precio medio de llenado y s = 0.0012.

```
lossU = SL ? (P−SL) + s·(P+SL) : Q_TAIL·P          // Q_TAIL = 0.15 (peor 1 % de C1)
gainU = TP ? (TP−P) − s·(P+TP) : +inf ;  si gainU <= 0 -> no operar
qRisk = F_RISK·equity / lossU                       // F_RISK = 1.5 % con Q_TAIL => nocional 10 %
qCap  = min(W_MAX·equity, NOT_TOT·equity − Σ nocional_abierto, 0.99·USDT_libre) / (P·(1+s))
q = floor(min(qRisk,qCap)/stepSize)·stepSize ;  exigir q ≥ minQty y q·P ≥ minNotional
```

**Parámetros:**

- W_MAX = 0.10 y NOT_TOT = 0.40.
- Calor de cola total: Σ w·Q_TAIL ≤ 6 %.
- Precios redondeados al `tickSize`.

**Costos:**

- Solo se opera si la E bruta esperada es ≥ 3c.
- Para TP/SL fijos, se exige R ≥ 10c.
- Hay que medir el deslizamiento real. **Si supera 0.10 % por lado en 50 operaciones, se detiene el bot.**

**Barrera de tiempo:**

- `time_stop_ts = entrada + 48×15 min`, guardado en el ledger para que sobreviva a los reinicios.
- Al vencer, se cierra con orden de mercado.

**En el exchange:**

- Justo después del llenado se coloca un **STOP_LOSS_LIMIT de catástrofe a −35 %**. En DISEÑO nunca se habría activado (peor excursión −29.4 %), así que no cambia la estrategia; protege si Node se cae.
- En geometrías con TP: OCO (TP + SL).
- Se confirma `executedQty` antes de registrar la posición.

**Interruptores** (C1-T48, w = 0.10):

1. Drawdown ≥ 10 % del pico (p99 del Monte Carlo = 8.3 %): parar y revisar.
2. Pérdida del día UTC ≥ 6 %, contando abiertas y cerradas (peor caso en diseño: 4.75 %): sin entradas durante 24 h.
3. Racha de 11 pérdidas o más (P < 1 % al año): parar.
4. CUSUM tras n ≥ 30 operaciones: parar si Σr < n·0.0032 − 2·0.048·√n.
5. Fallo operativo: datos atrasados más de 2 velas, modelo sin reentrenar en más de 35 días, o frecuencia de señales fuera de ±3σ de 22 al mes.

## 5. Voto provisional

| Punto | Voto | Razón |
|---|---|---|
| (a) C1 | **CONDICIONO, con T48** | E +0.73 %, LCB95 de +0.32 % con costos de 0.30 % y supervivencia con w ≤ 0.25. Condiciones: pre-registro y una sola prueba en el holdout (E > 0, p < 0.05), PBO ≤ 0.2 y velas cerradas. No vetaría G3H96 si el equipo prioriza el WR. |
| (b) BO 1h | **RETIRO** | 3 de 6 pliegues positivos y no pasa Bonferroni. |
| (c) Infraestructura | **ACEPTO** | Es requisito para que cualquier E medida exista en vivo. |
| (d) Dimensionamiento | **ACEPTO** | w = 0.10 con tope total de 0.40 e interruptores: ruina 0 y MDD p99 de 8.3 %. Con dinero real, w = 0 hasta que el holdout pase. |

## Archivos

Scripts:

- `riesgo_r2_c1.py`
- `riesgo_r2_extra.py`
- `riesgo_r2_wf_bo.py`
- `riesgo_log_trials.py`
- `riesgo_log_fix.py`

Resultados en `output/riesgo/`:

- `r2_c1.json`
- `r2_c1_log.txt`
- `r2_extra_log.txt`
- `r2_wf_bo_log.txt`
