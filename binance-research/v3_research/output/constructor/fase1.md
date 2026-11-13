# Constructor, fase 1: redes y árboles con datos de futuros

**Respuesta corta.** En el walk-forward de diseño, un ensamble de 3 LightGBM y 3 MLP **con datos de futuros**, sobre la geometría G3 (TP = 0.75·sd, SL = 1.5·sd, 48 h), logra **WR 72.0 % [63.8, 78.9], E +0.93 % por operación (+0.12 R) y b = 0.68**. Supera al azar de la misma moneda, mes y geometría por **+16.1 puntos de WR y +1.33 % de E** (t por día 3.42). Con costos de 0.30 % sigue en E +0.87 %. **No es significativo después de corregir por pruebas múltiples**: el DSR con todos los ensayos del equipo es 0.14 y el p de Bonferroni con mis 54 configuraciones es 0.20. El WR central (72 %) queda en el borde inferior de la meta. Veredicto: **WR 70–80 % con E > 0 es plausible, pero no está demostrado**. El candidato quedó congelado para el Verificador.

## 1. Datos

- **Spot 15 m** (ya disponibles): BTC, ETH, SOL y DOGE, del 2023-01 al 2025-06. Solo usé ese periodo; no miré nada del holdout ni otras monedas.
- **Futuros UM** (data.binance.vision, del 2023-01-01 al 2025-06-30, sin faltantes): `metrics` cada 5 min (OI, ratios top trader de cuentas y de posiciones, ratio global, taker ratio), `fundingRate`, `premiumIndexKlines` 15 m y klines UM 15 m. Guardados en `research/futures/{SYM}_*.npy` por `nn/nn_download_futures.py`.
- **Alineación sin fuga.** Comprobé que `create_time` marca el inicio de la ventana (la correlación con el desequilibrio taker de la vela es 0.84 para T ∈ {t_i, t_i+5, t_i+10}). Apliqué la regla del Verificador con margen: **T ≤ t_i + 5 min**, relleno hacia adelante de 30 min como máximo, indicador de faltante y filas ordenadas. Funding: solo `calc_time` ≤ cierre de la vela. Prima y klines UM: la vela con el mismo `open_time`.
- **Placebo de fuga:** con todos los futuros retrasados 1 h más, el ensamble da casi lo mismo (WR 72.6 %, E +0.88 %). La ventaja no sale de minutos solapados con la operación.

## 2. Variables y etiquetas

- **74 variables tabulares causales**, sin identificador de moneda (así el modelo puede aplicarse a monedas nuevas):
  - Retornos normalizados por σ en 1–672 velas, cocientes de volatilidad, z respecto de las SMA de 20, 96 y 672 velas, posición en el rango y caída desde el máximo, RSI.
  - Volumen relativo, desequilibrio taker y forma de la vela.
  - Hora y día de la semana.
  - Contexto de BTC: retornos, z, volatilidad, beta y retorno relativo.
  - Futuros (25 variables): cambio y z del OI, OI/volumen, nivel, cambio y z de los tres ratios long/short, taker ratio, funding y su z de 21 días, prima, base y desequilibrio taker de futuros.
- **10 canales de secuencia** (96 velas) para la CNN: 6 de spot y BTC, y 4 de futuros.
- **Etiqueta de triple barrera.** Entrada al cierre de la vela, TP = c(1 + a·sd), SL = c(1 − m·sd), barrera de tiempo de H velas, con sd = σ(log-ret 15 m, 672 velas)·√96 (volatilidad diaria). Clase positiva: neto > 0 con costos de 0.24 %. La etiqueta coincide exactamente con `harness.simulate` en 2 000 entradas de prueba (diferencia máxima 0).

**Geometrías (azar en diseño, 4 monedas).** p* = (1 + c/R)/(1 + b) con el R mediano:

| Geom. | a, m, H | b | WR del azar | E del azar | R mediano | p* |
|---|---|---|---|---|---|---|
| G1 | 0.5, 1.0, 96 | 0.50 | 58.0 % | −0.23 % | 3.3 % | 71.5 % |
| G2 | 0.4, 1.2, 96 | 0.33 | 64.4 % | −0.22 % | 4.0 % | 79.5 % |
| **G3** | 0.75, 1.5, 192 | 0.50 | 58.6 % | **−0.155 %** | **5.0 %** | **69.9 %** |
| G4 | 0.4, 1.2, 192 | 0.33 | **71.2 %** | −0.22 % | 4.0 % | 79.5 % |
| G5 | 0.6, 1.5, 192 | 0.40 | 63.7 % | −0.18 % | 5.0 % | 74.9 % |

- **G3** es la que menos sufre por los costos: tiene el R más grande y la operación dura más, así que una deriva pequeña rinde más por operación.
- **G4** ya da 70 % de WR al azar, pero necesita +8 puntos sobre el azar para que E > 0.
- Modelé G3 y G4. G5 la añadí por la advertencia del Verificador sobre el tamaño de muestra.

## 3. Modelos y entrenamiento

- **Meta-etiquetado sobre todas las velas** (sin señal primaria). Un único modelo para las 4 monedas.
- **LightGBM:** binario, lr 0.03, 15 hojas, `min_data_in_leaf` 1000, `feature_fraction` 0.7, bagging 0.5, L2 10. Parada temprana por AUC de validación, con un mínimo de 50 árboles.
- **MLP (torch):** 74 → 128 → 64 → 1, GELU y dropout 0.3. AdamW (lr 5e-4, wd 1e-3), parada por AUC de validación (paciencia 3).
- **CNN 1D dilatada:**
  - Entrada: 96 velas × 10 canales.
  - Convoluciones: 4 capas de 24 filtros, k = 5, dilataciones 1/2/4/8.
  - Salida: pooling medio, máximo y último paso, más una rama tabular 74 → 64 y una cabeza 136 → 64 → 1.
  - Regularización: dropout 0.1 y 0.3. Se entrenó con 1 de cada 4 velas.
- **Calibración:** Platt por modelo en validación. El ensamble promedia las probabilidades calibradas.
- **Walk-forward:**
  - Tests trimestrales del 2024Q1 al 2025Q2 (6 pliegues), con ventana expansiva desde 2023-01.
  - Validación: los 3 meses previos al test. Purga de H + 1 velas antes de la validación y antes del test.
- **Umbral (solo con la validación).** Entre los cuantiles 0.5–0.995 de p̂, el que maximiza la E de validación sujeto a:
  - WR ≥ 0.70 y E > 0;
  - ≥ 150 velas y ≥ 15 días distintos.

  Si ninguno cumple, ese trimestre no opera.
- **Simulación:** `harness.simulate`, una posición por moneda, empate TP/SL = SL, hueco = apertura, costo de 0.24 % y estrés a 0.30 %.

## 4. Resultados del walk-forward (OOS concatenado 2024-01 a 2025-06; 4 monedas)

La columna "Azar" es la media de todas las velas de la misma moneda y mes con la misma geometría. MDD con el 100 % del capital por operación.

| G3 | Fut. | n | WR [IC 95 %] | b | E % (R) | PF | MDD % | t día | Azar WR / E % | ΔWR | ΔE % (t día) | E a 0.30 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LGB s0 | sí | 194 | 72.2 [65.5, 78.0] | 0.59 | +0.71 (+0.09) | 1.53 | 48 | 2.22 | 55.8 / −0.41 | +16.3 | +1.12 (3.54) | +0.65 |
| LGB ×3 | sí | 264 | 67.4 [61.6, 72.8] | 0.63 | +0.47 (+0.04) | 1.31 | 51 | 1.54 | 56.8 / −0.36 | +10.6 | +0.82 (2.76) | +0.40 |
| MLP s0 | sí | 125 | 69.6 [61.1, 77.0] | 0.66 | +0.83 (+0.07) | 1.51 | 28 | 1.98 | 57.8 / −0.29 | +11.8 | +1.11 (2.66) | +0.77 |
| MLP ×3 | sí | 87 | 70.1 [59.8, 78.7] | 0.66 | +0.88 (+0.10) | 1.54 | 29 | 1.64 | 56.5 / −0.35 | +13.6 | +1.23 (2.16) | +0.82 |
| CNN | sí | 127 | 72.4 [64.1, 79.5] | 0.47 | +0.37 (+0.06) | 1.24 | 45 | 0.76 | 57.7 / −0.30 | +14.7 | +0.67 (1.34) | +0.31 |
| **ENS6 = LGB×3 + MLP×3 (congelado)** | sí | **132** | **72.0 [63.8, 78.9]** | 0.68 | **+0.93 (+0.12)** | 1.74 | 51 | 2.33 | 55.8 / −0.41 | **+16.1** | **+1.33 (3.42)** | **+0.87** |
| ENS6 + CNN | sí | 166 | 73.5 [66.3, 79.6] | 0.63 | +0.99 (+0.11) | 1.73 | 58 | 2.23 | 56.4 / −0.38 | +17.1 | +1.36 (2.98) | +0.93 |
| Placebo ENS6, futuros +1 h | sí | 146 | 72.6 [64.9, 79.2] | 0.62 | +0.88 (+0.11) | 1.65 | 54 | 2.37 | 56.1 / −0.37 | +16.5 | +1.25 (3.45) | +0.82 |
| LGB | no | 78 | 62.8 [51.7, 72.7] | 0.61 | +0.04 (−0.03) | 1.02 | 33 | 0.07 | 57.4 / −0.36 | +5.4 | +0.39 (0.68) | −0.02 |
| MLP | no | 196 | 64.8 [57.9, 71.1] | 0.61 | +0.20 (+0.01) | 1.12 | 61 | 0.53 | 61.0 / −0.02 | +3.8 | +0.22 (0.59) | +0.14 |
| CNN | no | 584 | 65.8 [61.8, 69.5] | 0.58 | +0.19 (−0.01) | 1.10 | 82 | 0.76 | 57.0 / −0.41 | +8.8 | +0.60 (2.44) | +0.12 |
| LGB + MLP | no | 402 | 63.4 [58.6, 68.0] | 0.58 | +0.01 (−0.03) | 1.01 | 69 | 0.05 | 55.9 / −0.47 | +7.5 | +0.48 (1.89) | −0.05 |

**Otras geometrías:**

- **G4 (b = 0.33):** WR de 70–74 % en todos los modelos, pero E < 0 siempre.
  - Con futuros: LGB −0.32 %, MLP −0.18 %, ensamble −0.31 %.
  - Sin futuros: de −0.06 % a −0.46 %.
  - ΔWR de +0.6 a +3.8 puntos: es el WR que ya da la geometría.
- **G5 (b = 0.4):**
  - Ensamble con futuros: WR 67.7 %, E +0.10 % (t 0.47).
  - MLP con futuros: WR 71.6 %, E +0.42 % (t 1.31).
  - Sin futuros: E +0.07 %.

**Qué aporta cada pieza:**

- **AUC de test por pliegue:** 0.50–0.59 en todos los modelos, igual que la logística del equipo anterior. Ningún modelo predice bien en general; la ganancia sale solo del 1–3 % superior de p̂.
- **Futuros:** con el mismo modelo, la E pasa de ≈ 0 a +0.4/+0.9 % en LGB, MLP y CNN, en todas las semillas y también con el retraso de 1 h. En LightGBM, los futuros explican ≈ 30 % de la ganancia de información (medido en v3): z del funding a 21 días, z del ratio de cuentas top, nivel de posiciones top y OI/volumen.
- **Qué compra el modelo:** velas de capitulación. Frente a la media, las operaciones elegidas tienen rango +2.3 σ, volumen +1.4 σ, retorno de 1 h −1.0 σ y OI/volumen −0.9 σ (volumen de liquidación). Además caen en meses malos para el azar (E del azar −0.41 %).
- **Red de secuencias:** sola es la más débil (E +0.37 %). Sumada al ensamble aporta +0.06 % de E y +34 operaciones, dentro del ruido. No la incluí en la especificación congelada: duplicaría la complejidad de la evaluación por una mejora que no es significativa.

**Robustez del candidato (ENS6):**

- **Significancia:**
  - t agrupado: 2.33 por día, 1.86 por semana y 2.07 por mes.
  - p por operación 0.0037; con Bonferroni sobre 54 configuraciones, 0.20.
  - DSR 0.14 con los ≈ 12 322 ensayos del equipo (0.61 solo con los míos).
- **Por pliegue:** 5 de 5 pliegues con operaciones tienen E > 0; el 2024Q4 no operó.
- **Por mes:** 10 de 14 meses con E > 0. El peor es 2024-08: n = 29, E −0.8 %.
- **Por moneda (n, WR, E):** BTC (37, 67.6 %, +0.13 %), ETH (24, 70.8 %, +0.77 %), SOL (41, 80.5 %, +1.86 %) y DOGE (30, 66.7 %, +0.75 %): las cuatro con E > 0.
- **Riesgo:** desviación por operación 3.9 %, racha máxima de 5 pérdidas y duración mediana de 44 velas (11 h).

## 5. Configuraciones probadas

Probé **54** configuraciones, registradas con `harness.log_trials("constructor", …)` en 9 entradas: geometrías, versiones v1–v4 de alineación y parada, modelos, semillas, ensambles, CNN y placebo. Corregí la alineación dos veces antes de los resultados finales (v3: retraso de 5 min; v4: la regla de huecos del Verificador). Las tablas usan solo v4. Los resultados de v1–v3 fueron del mismo orden.

## 6. Especificación congelada (para el Verificador)

- **Archivos:**
  - `output/constructor/spec_nn.json`: variables, geometría, hiperparámetros, Platt de cada modelo y umbral, hashes SHA-256 de 7 scripts y de los 9 archivos de modelo, entorno, instrucciones y advertencias.
  - Modelos: `nn/models/` (3 `lgb_G3_f1_s*.txt`, 3 `mlp_G3_f1_s*.pt` y sus escaladores).
- **Entrenamiento final:** la misma receta del walk-forward, aplicada una vez más:
  - Ajuste: 2023-01 al 2025-03, con purga.
  - Validación: 2025-04 al 2025-06.
  - Umbral **p ≥ 0.7134** (cuantil 0.98 de la validación).
- **Script:** `nn/nn_eval.py --symbols … --start … --end … --data-dir … [--reason …]`.
  - Verifica los hashes, construye las variables y opera con una posición por moneda.
  - Devuelve `trades_{SYM}.csv` y `metrics.json`: n, WR con Wilson, b, E en % y en R, PF, MDD, t por día, azar de la misma moneda, mes y geometría, ΔWR y ΔE, estrés a 0.30 % y operaciones por moneda y año.
  - Sin parámetros libres. Si el rango toca el holdout, exige `--reason` (`harness.bounds` lo registra).
- **Datos que necesita, para cada moneda y desde ≥ 35 días antes de `--start`:**
  - Spot: `klines/{SYM}_15m.npy` y `klines/BTCUSDT_15m.npy`, en el formato de `download_klines.py`.
  - Futuros: se bajan con `python -I nn/nn_download_futures.py --symbols SYM1,SYM2 --start <inicio−35 d> --end <fin> --out <data-dir>/futures`.
  - Para el holdout de las 4 monedas hay que bajar los futuros del 2025-05-27 al 2026-09-30 (el script fusiona con lo que ya existe).
- **Entorno:** `.venv` con torch 2.14.1+cpu, lightgbm 4.7.0, numpy 2.4.6 y scipy 1.17.1; ejecutar con `PYTHONIOENCODING=utf-8 … python.exe -I`.
- **Prueba de humo:** solo comprobé que el script funciona, sobre la validación 2025-04..06, que es dentro de muestra para el umbral (n = 51, WR 86 %). **No es evidencia.**

## 7. ¿Es factible WR 70–80 % con E > 0?

1. **Con geometrías de b ≈ 0.33 (G2, G4), no.** El WR de 70–74 % lo pone la geometría y ningún modelo mejora la E lo suficiente (E de −0.06 % a −0.46 %).
2. **Con G3 y datos de futuros, posiblemente**, con un WR de **≈ 70–73 %**, no de 80 %. Es la primera vez que el equipo ve, en walk-forward y con el azar como control, que la E sube +0.5/+0.9 % al añadir una fuente de información. Pero la significancia corregida es insuficiente (DSR 0.14) y el antecedente de C1 obliga a ser prudentes.
3. **Frecuencia y tamaño de la prueba:**
   - El walk-forward hizo **22 operaciones por moneda y año**. El umbral congelado (0.713) es más alto que todos los del walk-forward (0.59–0.70), así que espero **≈ 15–30 por moneda y año**: unas 110–230 operaciones en la prueba de 6 monedas × 457 días.
   - Con WR 0.72, el límite inferior de Wilson llega a 0.70 solo con unas 2 000 operaciones: **esa prueba no se puede pasar**.
   - La prueba de E > 0 sí tiene potencia si la E se mantiene: n mínimo ≈ 166 (α = 0.05, potencia 0.8, DEFF 1.5).
   - **Propongo como prueba primaria E > 0 con t agrupado por día, y ΔE contra el azar.** El WR y su IC se reportan, pero no como criterio.
4. **Riesgos de implementación:**
   - Las entradas caen en velas de capitulación, donde el deslizamiento real puede superar 0.02 % por lado (a 0.30 % de costo, la E sigue en +0.87 %).
   - R mediano ≈ 6 % del precio: con 100 % del capital por operación el MDD es de ~51 %, así que hay que dimensionar por riesgo.

Archivos: código en `research/nn/` (`nn_common`, `nn_build`, `nn_wf`, `nn_report`, `nn_final`, `nn_eval`, `nn_stats`, `nn_download_futures`, `nn_log_trials`), predicciones del walk-forward en `research/tmp/nn_preds/` y resultados en `research/output/constructor/wf_results.jsonl`.

## Nota de corrección (2026-10-19)

Se corrigieron las cifras del azar y del desglose por moneda, recalculadas con el código vigente (`nn_report.run`, sin escribir en `wf_results.jsonl`):

- **2026-10-18:** `nn_report.summarize` asignaba cada operación a la moneda equivocada. Cambiaban el desglose por moneda y el azar de la misma moneda y mes.
- **2026-10-19:** `nn_report.random_baseline` asignaba el mes por bloques de 96 velas; con el hueco de 5 velas del 2023-03-24, 135 velas por moneda caían en el mes equivocado. Ahora el mes se calcula vela por vela.
- **Qué cambió en ENS6 (congelado):** azar 55.2 % / −0.49 % → **55.8 % / −0.41 %**, ΔWR +16.7 → **+16.1** pt, ΔE +1.41 % → **+1.33 %** (t por día del ΔE 3.54 → **3.42**). Por moneda, ETH no pierde: el −2.29 % salía de operaciones asignadas a la moneda equivocada. ETH queda en **70.8 % / +0.77 %** y BTC en **67.6 % / +0.13 %**.
- **Qué no cambió:** las señales, las operaciones, n, WR, E, PF, MDD, el t por día de E (2.33) y la E a 0.30 %. En la tabla de la sección 4 se recalcularon las columnas del azar, ΔWR y ΔE de todas las filas; n, WR y E coinciden con las originales.
- El veredicto no cambia: ΔE sigue siendo positivo y la significancia corregida sigue siendo insuficiente.
