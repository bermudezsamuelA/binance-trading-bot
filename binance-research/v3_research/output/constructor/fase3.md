# Constructor, fase 3: candidato v2 (meta: WR ≥ 0.75 con E > 0)

**Respuesta corta.** La v2 usa las mismas entradas que la v1 (capitulaciones detectadas con datos de futuros), con tres cambios:

1. Se sale con una geometría **más ancha y más larga**: X5, con TP = 0.7·sd, SL = 1.75·sd, b = 0.4 y 72 h.
2. El umbral se elige en validación con **WR_val ≥ 0.75**.
3. El ensamble pasa a **13 modelos**: 6 LightGBM, 6 MLP y 1 CNN.

En el walk-forward de diseño (2024-01 a 2025-06, 4 monedas):

| n | WR [IC 95 %] | E neta | t por día | Contra el azar | Op./moneda/año |
|---|---|---|---|---|---|
| 188 | **81.4 % [75.2, 86.3]** | **+1.41 % (+0.145 R)** | 4.80 | ΔWR +19.7 pt, ΔE +1.83 % | 31 |

- E es positiva en 6 de 6 pliegues, en 17 de 18 meses y en las 4 monedas.
- La sospecha principal no cambia: **la v1 tiene las mismas variables y el mismo modelo base, y no aprobó**. Si falló porque la señal no se traslada, la v2 probablemente también fallará.

## 1. Qué cambié y por qué (solo con lo medido en diseño)

1. **Geometría de salida.** El modelo no cambia: se entrena con la etiqueta G3, que tiene clases más balanceadas, y solo cambia la salida.
   - En la fase 1 vi que las entradas son velas de capitulación: rango +2.3 σ, volumen +1.4 σ y OI/volumen bajo. El rebote necesita tiempo y margen, porque con SL a 1.5·sd y 48 h, el 17 % salía por tiempo.
   - Probé 5 salidas con b entre 0.4 y 0.5, **sin reentrenar**. Las 5 mejoraron a G3 (tabla 3).
   - Elegí X5 porque tuvo el mayor n y el mayor t; no es la de mayor E.
2. **Umbral con WR_val ≥ 0.75.** Maximiza la E de validación sujeto a WR_val ≥ 0.75, ≥ 150 velas y ≥ 15 días.
   - La validación usa las etiquetas X5, con purga de 289 velas para que ninguna etiqueta de validación entre al test.
   - Con WR_val ≥ 0.80 el resultado fue casi igual pero con menos operaciones. Con el criterio "máximo n" el WR cayó a 74 %, así que lo descarté.
3. **Más semillas y la CNN.** Promediar 12 modelos (6 LGB y 6 MLP) bajó el MDD y subió la moneda más floja: BTC pasó de +0.43 % a +0.75 % (ETH, de +0.69 % a +1.18 %). La CNN aportó n y WR, y el ensamble de 13 fue el mejor en todas las métricas de robustez.
4. **Descartado: filtro de régimen** (BTC sobre su SMA de 30 días). Empeoró: WR 74.0 %, E +0.60 %. Quita justo las capitulaciones de los mercados bajistas.

## 2. Candidato v2: walk-forward de diseño

Tests trimestrales del 2024Q1 al 2025Q2, con reentreno trimestral y ventana expansiva. Calibración Platt y umbral solo con la validación. Simulación con `harness.simulate`: una posición por moneda, empate TP/SL = SL y hueco = apertura.

| Métrica | Valor |
|---|---|
| n | 188 (**31.3 por moneda y año**) |
| WR [Wilson 95 %] | **81.4 % [75.2, 86.3]** |
| b efectivo | 0.53 (TP 79 %, SL 12 %, tiempo 8.5 %) |
| E neta | **+1.41 % (+0.145 R)**; a 0.30 % de costo, +1.35 % |
| PF / MDD | 2.31 / 41 % con el 100 % del capital por operación; 4 pérdidas seguidas como máximo |
| t agrupado | 4.80 por día, 5.15 por semana, 5.79 por mes |
| Azar (misma moneda, mes y geometría) | WR 61.7 %, E −0.43 % → **ΔWR +19.7 pt, ΔE +1.83 % (t por día del ΔE 5.78)** |
| Por pliegue (n, WR, E %) | (19, 84 %, +2.59), (24, 75 %, +1.14), (37, 78 %, +0.93), (35, 86 %, +1.89), (34, 74 %, +0.62), (39, 90 %, +1.69) |
| Por moneda (n, WR, E %) | BTC (47, 81 %, +0.74), ETH (31, 87 %, +1.67), SOL (55, 80 %, +1.30), DOGE (55, 80 %, +1.94) |
| Significancia | p = 1.5·10⁻⁶; Bonferroni con mis 74 configuraciones: 1·10⁻⁴. DSR 0.755 con los ≈ 12 396 ensayos del equipo (0.967 con los míos) |
| R mediano | 7.5 % del precio; duración mediana 45 velas (11 h) |

**Tamaño de la prueba (límite inferior de Wilson con WR 0.814):**

| n | 150 | 230 | 300 | 500 |
|---|---|---|---|---|
| Límite inferior | 0.743 | 0.758 | 0.765 | 0.778 |

Si el WR real fuera 0.76, el límite superaría 0.70 recién con unas 230 operaciones. Para E > 0 bastan unas 75 operaciones (α = 0.05, potencia 0.8, DEFF 1.5).

**Frecuencia esperada:**
- El umbral congelado (**0.714**, cuantil 0.98 de la validación 2025Q2) es más alto que los del walk-forward (0.59–0.705).
- Dentro de muestra (2024-01 a 2025-03) da 45 operaciones por moneda y año, pero esa cifra está inflada.
- Fuera de muestra espero **≈ 20–40 por moneda y año**. Con 6 monedas y 457 días, unas 150–300 operaciones.

## 3. Lo que aportó cada pieza (walk-forward, c = 0.24 %)

| Configuración | n | WR [IC 95 %] | E % (t por día) | ΔWR / ΔE contra el azar |
|---|---|---|---|---|
| v1: ENS6, salida G3 (0.75, 1.5, 192) | 132 | 72.0 [63.8, 78.9] | +0.93 (2.33) | +16.1 / +1.33 |
| ENS6, salida X1 (0.6, 1.5, 192), b = 0.40 | 160 | 78.8 [71.8, 84.4] | +1.05 (3.46) | +18.2 / +1.48 |
| ENS6, salida X2 (0.8, 2.0, 288), b = 0.40 | 133 | 80.5 [72.9, 86.3] | +1.32 (2.84) | +21.4 / +1.85 |
| ENS6, salida X3 (0.75, 1.5, 288), b = 0.50 | 129 | 76.7 [68.7, 83.2] | +1.17 (2.77) | +18.6 / +1.62 |
| ENS6, salida X4 (1.0, 2.0, 288), b = 0.50 | 93 | 76.3 [66.8, 83.8] | +1.59 (2.71) | +22.4 / +2.04 |
| ENS6, salida X5 (0.7, 1.75, 288), b = 0.40 | 186 | 80.6 [74.4, 85.7] | +1.25 (3.86) | +17.1 / +1.53 |
| ENS6 X5, WR_val ≥ 0.80 (*) | 145 | 81.4 [74.3, 86.9] | +1.18 (3.10) | +19.6 / +1.63 |
| ENS6 X5, WR_val ≥ 0.80, máximo n | 332 | 74.4 [69.4, 78.8] | +0.51 (1.74) | +11.0 / +0.83 |
| ENS6 X5 con BTC > SMA de 30 días (*) | 154 | 74.0 [66.6, 80.3] | +0.60 (1.62) | +4.7 / +0.43 |
| ENS12 X5 | 177 | 79.1 [72.5, 84.4] | +1.25 (4.00) | +17.3 / +1.66 |
| ENS6 + CNN, X5 | 209 | 81.3 [75.5, 86.0] | +1.31 (4.51) | +18.3 / +1.62 |
| **ENS12 + CNN, X5 (v2 congelada)** | **188** | **81.4 [75.2, 86.3]** | **+1.41 (4.80)** | **+19.7 / +1.83** |
| Sin futuros: LGB + MLP + CNN, X5 | 318 | 74.5 [69.5, 79.0] | +0.61 (1.96) | +11.6 / +1.01 |
| Placebo: futuros retrasados 1 h, ENS6 X5 | 171 | 80.7 [74.1, 85.9] | +1.18 (3.31) | +17.7 / +1.48 |

(*) Medidas antes de corregir la purga de la geometría de salida en la validación. Al corregirla, las demás filas cambiaron en ≤ 2 operaciones.

**Azar de cada geometría de salida (todas las velas):**

| Geometría | WR | E |
|---|---|---|
| X1 | 63.7 % | −0.18 % |
| X2 | 62.7 % | −0.11 % |
| X3 | 62.0 % | −0.15 % |
| X4 | 58.0 % | −0.07 % |
| X5 | 65.0 % | −0.13 % |

**Qué se lee en las tablas:**
- **La salida explica parte de la mejora:** sin futuros, X5 da E +0.61 %, contra ≈ 0 % con G3.
- **Los futuros siguen sumando** unos +0.8 % de E y +7 puntos de WR.
- **No hay fuga de minutos:** el placebo con 1 h de retraso no cambia nada.

## 4. Especificación congelada v2

- **Archivos:**
  - `output/constructor/spec_nn_v2.json`: variables, etiqueta G3, salida X5, hiperparámetros, Platt de cada modelo, umbral 0.71427, hashes SHA-256 de 8 scripts y de los 20 archivos de modelo, entorno, datos necesarios, resumen del walk-forward y advertencias.
  - Modelos: `nn/models_v2/` (6 `lgb_G3_s*.txt`, 6 `mlp_G3_s*.pt`, `cnn_G3_s0.pt` y escaladores; 0.8 MB).
- **Entrenamiento:** ajuste de 2023-01 a 2025-03, con purga; validación 2025-04 a 2025-06.
- **Evaluación:** `nn/nn_v2_eval.py --symbols … --start … --end … --data-dir … [--reason …]`.
  - Mismas entradas y salidas que `nn_eval.py`, más el campo `wilson_lo_supera_070`.
  - Verifica los hashes y no tiene parámetros libres.
  - Necesita los mismos datos que la v1: velas spot de la moneda y de BTCUSDT, y los 4 archivos de futuros de `nn_download_futures.py`, desde ≥ 35 días antes de `--start`.
  - Tarda ≈ 25 s para 4 monedas y 15 meses.
- **Prueba de humo:** solo comprueba que el script corre, sobre 2024-01..2025-03, que es dentro de muestra (WR 84.6 %, n = 228). **No es evidencia.**
- **La v1 sigue intacta:** `spec_nn.json`, `nn_eval.py` y `models/` no se modificaron, y sus hashes se verificaron.

## 5. Configuraciones y advertencias

- **Configuraciones:** 20 nuevas, registradas con `harness.log_trials` (`nn_v2_log_trials.py`). Son 74 en total para el Constructor.
- **Sesgo de selección:** X5, el umbral ≥ 0.75 y el ensamble de 13 se eligieron mirando el walk-forward de diseño. El DSR (0.755 con todos los ensayos del equipo) no llega a 0.95.
- **Misma base que la v1:** variables, etiqueta y familia de modelos son las de la v1, que no aprobó la prueba independiente. **La v2 no agrega información nueva**: cambia cómo se sale y cuán estricto es el umbral.
- **Riesgo por operación:** el SL a 1.75·sd (R ≈ 7.5 %) y hasta 3 días en posición hacen que cada pérdida sea grande. Hay que dimensionar por riesgo: con 1 % de riesgo por operación, el nocional es ≈ 13 % del capital.

## Nota de corrección (2026-10-19)

Se corrigieron las cifras del azar y del desglose por moneda, recalculadas con el código vigente (`nn_v2_report.run` y `nn_report.run`, sin escribir en los `.jsonl`):

- **2026-10-18:** `nn_report.summarize` asignaba cada operación a la moneda equivocada (afectaba el desglose por moneda y el azar de la misma moneda y mes).
- **2026-10-19:** `nn_report.random_baseline` asignaba el mes por bloques de 96 velas; con el hueco de 5 velas del 2023-03-24, 135 velas por moneda caían en el mes equivocado. Ahora se calcula vela por vela.
- **v2 congelada:** azar 62.0 % / −0.44 % → **61.7 % / −0.426 %**, ΔWR +19.4 → **+19.7** pt, ΔE +1.85 % → **+1.83 %**. El "t por día 5.98" era el t del **ΔE** contra el azar: ahora es **5.78**. El t por día de E (4.80) no cambia.
- **v1 en la tabla 3:** ΔWR / ΔE +16.7 / +1.41 → **+16.1 / +1.33** (azar 55.8 % / −0.41 %).
- **Por moneda (v2):** se reescribió con la asignación correcta; las cuatro siguen con E > 0. La frase sobre ETH (−0.78 % → +0.68 %) también venía del error de asignación.
- En la tabla 3 se recalcularon las columnas ΔWR / ΔE de todas las filas sin (*); n, WR, E y su t coinciden con las originales. Las dos filas con (*) se midieron antes de corregir la purga y no se pueden reproducir con el código actual: conservan sus cifras viejas.
- **Qué no cambió:** las señales, las operaciones, n, WR, E, PF, MDD ni las significancias de E. El veredicto tampoco.
