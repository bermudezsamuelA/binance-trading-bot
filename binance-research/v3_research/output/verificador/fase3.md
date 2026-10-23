# Verificador, fase 3: auditoría y prueba única de la v2 (2026-10-14, 07:10 VST)

**Veredicto pre-registrado: RECHAZA.**

| Criterio | Resultado |
|---|---|
| (a) E > 0 con t por día > 1.645, y E > 0 con costos de 0.30 % | No cumple |
| (b) Límite inferior de Wilson ≥ 0.70 | No cumple |
| (c) ΔE frente al azar con significancia | Cumple |
| (d) Sin fugas | Cumple |

Pasa lo mismo que con la v1: hay una ventaja relativa clara frente al azar de la misma geometría, pero ni la E absoluta ni un WR ≥ 70 % quedan demostrados. El WR de 81 % del diseño bajó a 69 %.

## 1. Auditoría (antes de ejecutar; detalle en `auditoria_nn_v2.md`)

- **Hashes.** Los 8 scripts y los 20 archivos de modelo coinciden con `spec_nn_v2.json`.
- **Lista blanca de monedas y fechas.**
  - `H.SYMBOLS` contiene solo BTC, ETH, SOL y DOGE.
  - Los caches de entrenamiento (`tmp/nn_cache` y `tmp/nn_cache_v2`) solo tienen esas 4 monedas, con la última fecha en 2025-06-30 23:45. `research/futures` tampoco llega más allá del 2025-06-30.
  - Fuera de `verificador/` no hay ningún archivo de las 14 monedas reservadas o gastadas.
  - El Constructor no tiene ninguna entrada en `holdout_log`.
- **Perturbación del futuro.** Hice 12 cortes en DOGE y BTC, incluido el 2024-03-04. Las 74 variables y los 10 canales de secuencia de la CNN quedaron idénticos antes de cada corte (diferencia 0.0) y cambiaron en un 90 % después.
- **Umbral.** Lo recalculé con los 13 modelos congelados sobre la validación [2025-04-01, 2025-07-01 − 289 velas), que son 33 788 velas con etiquetas X5. El cuantil 0.98 da 0.714268362561, idéntico al de la especificación (WR_val 0.987, 676 velas).
- **La "fuga leve" es real y quedó corregida.**
  - En el walk-forward, la validación terminaba 193 velas antes del test (el horizonte de G3), pero el umbral se elige con etiquetas X5, que miran 288 velas adelante. Las últimas ~95 velas de validación veían hasta ~1 día del test.
  - Ahora la purga es de 289 velas, tanto en el walk-forward (`okv`) como en el entrenamiento final.
  - Lo comprobé: la última vela de validación es del 2025-06-27 23:30 y la última salida X5 que se usa es del 2025-06-30 16:45, antes del 2025-07-01.
- **Prueba de humo reproducida** (dentro de muestra): n 228, WR 84.6 %, E +1.615 %, idéntica a la del Constructor.
- **Conclusión: sin fugas.** Sí hay sesgo de selección: X5, el umbral con WR_val ≥ 0.75 y el ensamble de 13 se eligieron mirando el walk-forward.

## 2. Prueba primaria (ejecución única, `ejecuciones_log.csv`: `primaria_v2`)

- El modelo se ejecutó una sola vez.
- `verify.py` falló en su primer intento porque no encontraba los datos nuevos, antes de calcular nada. Copié las velas a `verificador/data/` y lo ejecuté sin modificar su código (hash `0aeb8099…`). Ese hecho quedó anotado en el registro.
- `verify.py` reproduce las 621 operaciones sin discrepancias.
- N = 12 342 configuraciones (las 74 del Constructor ya están incluidas en el registro).

| | Diseño WF v2 | **Primaria: 8 nuevas** | Desc.: 6 de la fase 2 | Desc.: 4 originales |
|---|---|---|---|---|
| n (op./moneda/año) | 188 (31) | **621 (62)** | 397 (53) | 203 (41) |
| WR [Wilson 95 %] | 81.4 [75.2, 86.3] | **69.4 [65.7, 72.9]** | 71.5 [66.9, 75.8] | 72.9 [66.4, 78.6] |
| Límite inferior con n_ef (DEFF) | — | 63.4 (2.44) | 63.3 (3.18) | 64.5 (1.71) |
| b efectivo / WR de equilibrio | 0.53 / — | 0.54 / 65.1 | 0.46 / 68.7 | 0.40 / 71.4 |
| E neta (en R) | +1.41 % (+0.145) | **+0.32 % (+0.002)** | +0.22 % (+0.03) | +0.12 % (+0.02) |
| t por día (días) | 4.80 | **1.02 (186)** | 0.65 (104) | 0.31 (67) |
| E con costos de 0.30 % (t) | +1.35 % | +0.26 % (0.83) | +0.16 % | +0.06 % |
| Azar: WR / E | 62.0 / −0.44 % | 60.0 / −0.75 % | 57.2 / −0.89 % | 58.3 / −0.82 % |
| **ΔWR** (t por día) | +19.4 | **+9.4 (3.29)** | +14.4 (4.03) | +14.6 (4.29) |
| **ΔE** (t por día; p por día; p de repeticiones) | +1.85 % (5.98) | **+1.07 % (3.03; 0.001; 0.005)** | +1.11 % (3.16) | +0.94 % (2.38) |
| DSR | 0.755 | 0.02 | 0.003 | 0.00 |

**Primaria por moneda (n, WR, E):**

| Moneda | n | WR | E |
|---|---|---|---|
| FIL | 66 | 73 % | +1.71 % |
| NEAR | 80 | 71 % | +0.62 % |
| ETC | 63 | 68 % | +0.48 % |
| UNI | 55 | 67 % | +0.34 % |
| ATOM | 80 | 69 % | +0.25 % |
| DOT | 66 | 70 % | +0.16 % |
| TRX | 117 | 71 % | −0.16 % |
| BCH | 94 | 66 % | −0.25 % |

Ninguna moneda tiene un límite inferior de Wilson ≥ 0.70; el máximo es 0.62.

**Primaria por trimestre (WR, E):**

| Trimestre | WR | E |
|---|---|---|
| 2025T3 | 78 % | +0.73 % |
| 2025T4 | 71 % | +1.24 % |
| 2026T1 | 63 % | −0.20 % |
| 2026T2 | 60 % | −0.72 % |
| 2026T3 | 78 % | +0.56 % |

**Concentración.** Los 10 días con más entradas reúnen 168 operaciones, con E +1.18 %. El resto tiene E 0.00 %.

**Composición de los resultados.**
- 68 % de las operaciones salen por TP, 19 % por SL y 13 % por tiempo.
- La ganancia media es 2.61 % y la pérdida media 4.88 %, con un R mediano de 6.4 %.

## 3. Respuestas separadas

**(A) ¿Hay ventaja? Relativa sí; absoluta no demostrada.**
- **(c) y (d) se cumplen.** Frente al azar de la misma moneda, mes y geometría, la v2 gana +1.07 % de E y +9.4 puntos de WR (p = 0.001). Lo mismo se repite en los dos conjuntos descriptivos (ΔE de +0.9 a +1.1 %).
- **(a) no se cumple.** La E es +0.32 % (+0.26 % con costos de 0.30 %), con t por día de 1.02. En R la E es ≈ 0. La E cayó un 77 % frente al diseño.
- **Cuánta muestra haría falta.** Con estos valores, (a) necesitaría ≈ 1 600 operaciones para llegar a t = 1.645, y ≈ 3 700 para tener una potencia del 80 %.

**(B) ¿Se demuestra WR ≥ 70 %? No.**
- **El WR observado está por debajo de la meta.** Es 69.4 %, con IC [65.7, 72.9]: excluye el 75 % y el 80 %. Corregido por la correlación diaria, el límite inferior es 63.4 %.
- **Ningún tamaño de muestra alcanzaría con este WR.** Con un WR observado inferior a 0.70, el límite inferior no puede superar 0.70.
- **Los conjuntos descriptivos tampoco lo alcanzan.** Rozan el 70 % (71.5 % y 72.9 %), pero sus límites inferiores (66.9 % y 66.4 %) se quedan por debajo.
- **La geometría pone casi todo el WR.** Con b = 0.4–0.54, el azar ya da un WR del 57–62 %.

## 4. Lectura

1. **El salto del WR en diseño era selección.** El WR pasó de 72 % (v1) a 81 % (v2) en diseño, pero en datos nuevos volvió a ≈ 69 %, igual que la v1 (68.7 %). Elegir la salida, el umbral y el ensamble mirando el walk-forward infló el diseño: el DSR bajó de 0.755 a 0.02.
2. **La señal real es estable.** Comprar capitulaciones supera al azar del mismo mes por ≈ +1 % de E en 18 monedas, pero esa ventaja no alcanza para superar la deriva negativa del periodo. La E se concentra en unos pocos días de pánico.
3. **La frecuencia vuelve a duplicar lo previsto.** Fueron 62 operaciones por moneda y año, cuando se esperaban 20–40. En TRX, p supera el umbral en el 11 % de las velas.
4. **No recomiendo una v3 con las mismas variables.** Dos intentos fallaron de la misma forma. Si se sigue, lo honesto es una prueba prospectiva desde 2026-10, con el criterio (a) y tamaño por riesgo.

**Archivos:**
- `research/verificador/runs/{primaria_v2, desc_v2_fase2coins, desc_v2_originales}/`
- `research/verificador/audit_v2.py`
- `research/output/verificador/auditoria_nn_v2.md`

No compartí nada con el Constructor. La lista de monedas del anexo reservado (`e2db3a07…`) se puede revelar ahora, a criterio del coordinador.
