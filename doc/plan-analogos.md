# Plan: predicción por análogos ("resorte")

Objetivo: buscar en el pasado los momentos más parecidos al actual y usar lo que pasó después para predecir. Son 5 sugerencias que se implementan en orden. Cada una se mide con el mismo marco (sección 0) y solo se adopta si mejora **en validación**, después de comisiones.

Es un proyecto aparte: **no usa ni modifica** las estrategias actuales del bot (Bollinger, v3). Solo reutiliza los datos ya descargados.

Referencia visual (datos de ejemplo): sugerencia 1 https://claude.ai/artifact/5NEAUa1jkipEJnoQZfxWP1 · sugerencia 2 https://claude.ai/artifact/4WpoerTozHbzYg3waiWJww · sugerencia 3 https://claude.ai/artifact/KvwQK6jngvg5bp9huJokYa

---

## 0. Marco común (implementar primero)

**Ubicación sugerida:** `binance-research/analogos/` con `common.py`, un archivo por sugerencia (`s1_knn.py`, `s2_dtw.py`, `s3_estado.py`, `s4_palabras.py`, `s5_multi.py`) y sus pruebas (`test_*.py`). Resultados en `binance-research/analogos/output/` (no versionar los pesados).

**Datos disponibles (ya en el repo local, formato `.npy`):**
- Velas spot de 15 min: `v3_research/klines/<SYM>_15m.npy` y, con más historia, `v3_research/tmp/data2022/klines/` (2021-10 a 2022-12) y `v3_research/tmp/new20/klines/` (2023-01 a 2026-10). Columnas: `t_ms, open, high, low, close, volume, taker_buy_volume`.
- Futuros: `v3_research/futures/<SYM>_funding.npy` (t, tasa), `<SYM>_metrics.npy` (t, interés abierto, valor del interés abierto, ratios long/short de top traders, ratio long/short global, ratio taker compra/venta), `<SYM>_premium15m.npy`, `<SYM>_fut15m.npy`.
- Si falta algo: `download_data.py` o data.binance.vision (con la VPN apagada).

**Preparación:**
- Pasar las velas de 15 min a 1 h (cierre = último cierre de la hora; volumen = suma) y rellenar huecos con el último valor.
- Monedas base: BTC, ETH, SOL y DOGE (las que tienen historia continua desde 2021-10). Temporalidad principal 1 h; 4 h como contexto; 15 min solo para afinar la entrada.

**Notación:** \(C_t\) es el precio de cierre de la vela \(t\). Retorno futuro a \(h\) velas: \(y_t = \ln(C_{t+h}/C_t)\).

**Periodos (fijos, no se cambian después de ver resultados):**
- Biblioteca: desde el inicio de los datos.
- Diseño: 2023-01 a 2024-12. Aquí se eligen todos los parámetros.
- Validación: 2025-01 a 2026-10. Se mira una vez al final, con la configuración ya elegida.

**Reglas que no se negocian:**
1. **Sin fuga de futuro:** para la consulta \(t\), los vecinos solo pueden ser \(s \le t - h_{\max}\) (24 h de margen), en todas las monedas. Así ningún vecino conoce el futuro de \(t\).
2. **Dato disponible en \(t\):** cada variable usa solo información publicada hasta \(t\). Si llega con retraso (funding, archivos mensuales), se desplaza ese retraso.
3. **Estandarizar con el pasado:** medias y desviaciones calculadas con datos \(< t\), nunca con todo el periodo.
4. **Un vecino por episodio:** dos vecinos de la misma moneda deben estar separados al menos \(L\) velas.

**Predicción y regla de operación (igual para las 5):**
- \(\hat y_t = \frac{\sum_i w_i\, y_{s_i}}{\sum_i w_i}\) y consenso \(\pi_t = \frac{\#\{y_{s_i} > 0\}}{k}\).
- Compra si \(\hat y_t > c\) con \(c = 0.24\,\%\) y \(\pi_t \ge q\). Venta a las \(h\) velas. Sin solapar operaciones en la misma moneda.
- Neto por operación: \(g = e^{y_t} - 1 - c\). Tamaño: 15 USDT.

**Métricas (diseño y validación por separado):**
- IC: correlación de Spearman entre \(\hat y\) y \(y\).
- Acierto de dirección (%).
- Operaciones, WR, E neta por operación, PnL, meses positivos.
- \(t = \bar g / (s_g/\sqrt n)\).
- Comparar siempre contra: "comprar siempre cada \(h\) velas" y \(k\) vecinos al azar del mismo periodo.

**Criterio para adoptar:** E neta > 0 en validación con \(t \ge 2\) y al menos 100 operaciones. Si no se cumple, se documenta y no se usa.

**Salida de cada sugerencia:** un CSV con la rejilla de parámetros y sus métricas, un CSV de operaciones y un resumen en `doc/` con la tabla diseño frente a validación.

---

## 1. Vecinos más cercanos sobre la forma del precio (k-NN)

**Idea:** comparar la ventana de las últimas \(L\) velas con todas las ventanas del pasado y promediar lo que pasó después de las \(k\) más parecidas.

**Matemática:**
- Ventana de log precios \(\ell = (\ln C_{t-L+1}, \dots, \ln C_t)\), z-normalizada: \(\tilde x_t = (\ell - \bar\ell)/\sigma_\ell\).
- Distancia euclidiana \(d(t,s) = \lVert \tilde x_t - \tilde x_s \rVert\). Con z-normalización se cumple \(d^2 = 2L(1-\rho)\), donde \(\rho\) es la correlación.
- Peso opcional \(w_i = 1/(d_i + \varepsilon)\).

**Implementación:**
- Distancias por bloques con álgebra matricial: \(\lVert a-b\rVert^2 = \lVert a\rVert^2 + \lVert b\rVert^2 - 2a\cdot b\), en float32. Para cada bloque se enmascaran las posiciones no permitidas y se usa `argpartition` para los \(k\) mejores.
- Alternativa: la librería `stumpy` (matrix profile).

**Rejilla:** \(L \in \{12, 24, 48, 96\}\), \(k \in \{10, 30, 100\}\), \(h \in \{4, 12, 24\}\), peso sí/no, \(q \in \{0.50, 0.55, 0.60, 0.65, 0.70\}\), biblioteca de 1 o 4 monedas. Comparar también "precio crudo" y "retornos" frente a "forma z" para mostrar por qué se normaliza.

**Ya medido (parcial, datos reales, 1 h):** con \(L = 12\) y \(24\), una moneda, el IC de validación fue ≈ 0 y la E neta negativa (−0.2 a −0.3 % por operación). Hay que completar la rejilla, pero la expectativa es baja: la forma sola casi no predice.

**Costo:** con 4 monedas y una biblioteca de 4 monedas, unos 5 minutos por configuración en 4 núcleos. Guardar los índices de los 100 vecinos por configuración y calcular las métricas después.

---

## 2. DTW (alineamiento temporal dinámico)

**Idea:** el mismo patrón puede durar 20 velas una vez y 30 la siguiente. DTW empareja cada vela con la que de verdad le corresponde.

**Aclaración:** "vela \(i\)" es una posición dentro de la ventana, no una fecha. \(a_i = \ln C_{t-L+i}\) es la ventana de ahora y \(b^{(s)}_j = \ln C_{s-L+j}\) es una ventana del pasado que termina en \(s\). Se recorre todo \(s \le t - 24\).

**Matemática:**
- Recurrencia: \(D(i,j) = (a_i - b_j)^2 + \min\{D(i-1,j),\ D(i,j-1),\ D(i-1,j-1)\}\), con \(D(0,0) = 0\). Distancia: \(d_{DTW} = \sqrt{D(L,L)}\).
- Banda de Sakoe–Chiba: \(|i - j| \le R = \lceil rL \rceil\).
- Cota inferior LB_Keogh, con la envolvente \(U_i = \max b_{i-R..i+R}\) y \(L_i = \min b_{i-R..i+R}\): \(LB_K = \sqrt{\sum (a_i - U_i)^2_{[a_i > U_i]} + (a_i - L_i)^2_{[a_i < L_i]}} \le d_{DTW}\).
- Velocidad del patrón: \(s = \Delta j / \Delta i\) en el último 30 % del camino. Horizonte escalado \(h' = \operatorname{round}(h \cdot s)\).

**Implementación (pasos, cada uno medido por separado):**
1. Preseleccionar \(M = 500\) candidatos con la distancia euclidiana de la sugerencia 1.
2. Descartar con LB_Keogh los que no pueden entrar entre los \(k\) mejores.
3. Calcular DTW con banda solo para los restantes. Usar `numba` o la librería `dtaidistance` (en C).
4. Opcional: medir el futuro del vecino en \(h'\) velas en lugar de \(h\).

**Rejilla:** \(r \in \{0, 0.05, 0.10, 0.15, 0.20, 0.30\}\) (con \(r = 0\), DTW es igual a la euclidiana), \(M \in \{200, 500, 1000\}\), horizonte escalado sí/no. El resto, la mejor configuración de diseño de la sugerencia 1.

**Comprobar:** que la versión con preselección y LB_Keogh da los mismos vecinos que DTW sin atajos en una muestra (recall ≥ 97 %).

---

## 3. Comparar el estado del mercado (forma + contexto)

**Idea:** dos gráficos con la misma forma pueden venir de un mercado en calma o en pánico. Cada hora se describe con un vector de variables y se buscan los vecinos en ese espacio.

**Variables (10, todas calculadas con datos hasta \(t\)):**

| Grupo | Variable | Fórmula |
|---|---|---|
| Forma | Retorno de 24 h | \(\ln(C_t/C_{t-24}) / (\sigma_{30d}\sqrt{24})\) |
| Forma | Curvatura | \((\ln C_t - 2\ln C_{t-12} + \ln C_{t-24}) / (\sigma_{30d}\sqrt{12})\) |
| Forma | Retorno de 6 h | \(\ln(C_t/C_{t-6}) / (\sigma_{30d}\sqrt{6})\) |
| Contexto | Volatilidad relativa | \(\sigma_{24h} / \sigma_{30d}\) |
| Contexto | Volumen relativo | \(\bar V_{24h} / \bar V_{30d}\) |
| Contexto | Compras agresivas | \((B - S)/(B + S)\) en 24 h, con el volumen taker de las velas spot |
| Contexto | Posición en el rango de 7 días | \((C_t - \min_{7d}) / (\max_{7d} - \min_{7d})\) |
| Contexto | Tendencia de BTC | \(\ln(C^{BTC}_t / \mathrm{SMA}_{30d})\) |
| Contexto | Funding | última tasa publicada hasta \(t\) |
| Contexto | Cambio del interés abierto | \(\ln(OI_t / OI_{t-24})\) (de `metrics.npy`) |

**Matemática:**
- Estandarizar: \(z_{t,f} = (x_{t,f} - \mu_{f,<t}) / \sigma_{f,<t}\).
- Distancia: \(d^2(t,s) = \sum_f w_f (z_{t,f} - z_{s,f})^2\). Al usar la misma transformación para las dos horas, la media se cancela y solo importa \(\sigma_{f,<t}\).
- Pesos:
  - iguales;
  - forma frente a contexto: \(w_f = 2(1-\alpha)\) para forma y \(2\alpha\) para contexto;
  - aprendidos: \(w_f \propto |\mathrm{IC}_f|\), medido solo **antes** del periodo de diseño.
- PCA opcional: \(\Sigma = V\Lambda V^\top\) y \(u_t = V_{1:m}^\top \tilde z_t\), ajustado solo con datos anteriores al diseño.

**Camino de mejoras a medir (cada paso sobre el anterior):**
1. Solo forma.
2. \+ Contexto sin estandarizar.
3. \+ Estandarizar.
4. \+ Pesos aprendidos.
5. \+ PCA (\(m \in \{2, 3, 4, 6\}\)).
6. Control: la versión con biblioteca sin margen (\(s \le t-1\)), para ver cuánto infla la fuga. Este paso no se adopta nunca.

**Búsqueda:** con unas 176 000 horas (4 monedas × 5 años) y 10 variables, la fuerza bruta en numpy alcanza para el bot en vivo (~2 ms por consulta). Para el backtest conviene FAISS (`IndexFlatL2` exacto, o `IndexIVFFlat` si hace falta velocidad).

**Cuidado:** el funding y el interés abierto mensuales llegan con días de retraso (ya nos pasó con la v3). Para el día en curso hay que usar la misma fuente que se usaría en vivo.

---

## 4. Patrones como "palabras" (SAX / patrones ordinales)

**Idea:** convertir cada ventana en una palabra corta y contar qué pasó después de cada palabra. Es más simple y fácil de auditar que una caja negra.

**Matemática:**
- Cada vela se traduce a un símbolo según su retorno estandarizado \(r_t/\sigma_{30d}\), con cortes en cuantiles del periodo de entrenamiento. Por ejemplo, 4 niveles: B (baja fuerte), b, s, S (sube fuerte).
- Una ventana de \(n\) velas es una palabra, por ejemplo `BbsSSs`. Hay \(4^n\) palabras posibles.
- Variante ordinal: el orden relativo de los \(n\) cierres (\(n!\) patrones).
- Estimador para cada palabra \(w\): \(\hat P(\text{sube} \mid w) = \frac{\#\{\text{subió después de } w\}}{\#\{w\}}\) y retorno medio \(\bar y_w\).
- Intervalo de Wilson para \(\hat P\). Una palabra solo se usa si tiene al menos 30 apariciones y su intervalo no incluye la tasa base.

**Implementación:**
- Contar con las apariciones anteriores a \(t - h\) (el conteo crece en el tiempo, sin mirar el futuro).
- Corrección por comparaciones múltiples: con cientos de palabras, alguna parece significativa por azar. Usar Bonferroni o un control de falsos descubrimientos (FDR) de Benjamini–Hochberg.

**Rejilla:** \(n \in \{3, 4, 5, 6\}\), niveles \(\in \{3, 4, 5\}\), \(h \in \{4, 12, 24\}\), mínimo de apariciones \(\in \{30, 100\}\).

**Salida extra:** tabla de las palabras que pasan el filtro en diseño y cómo les fue en validación.

---

## 5. Todas las monedas y varias temporalidades

**Idea:** una sola moneda tiene pocos análogos buenos. Con una biblioteca de todas las monedas los vecinos se multiplican, y se pide acuerdo entre temporalidades.

**Matemática:**
- Biblioteca conjunta \(\mathcal{B}_t = \{(m, s) : m \in \text{monedas},\ s \le t - 24\}\). Las ventanas se normalizan (forma z o estado estandarizado), así que se comparan entre monedas.
- Excluir "gemelos": ventanas de otra moneda muy correlacionada en la misma hora. Basta el margen de 24 h para todas.
- Acuerdo entre temporalidades: \(\hat y^{(1h)}_t > c\) y \(\hat y^{(4h)}_t \ge 0\); la de 15 min solo para elegir el momento de entrada dentro de la hora.
- Combinación opcional: \(\hat y_t = \sum_\tau \beta_\tau \hat y^{(\tau)}_t\), con \(\beta\) ajustado solo en diseño.

**Implementación:**
- Reutilizar el motor de la sugerencia 1 o 3 con la biblioteca ampliada. Probar con 4 monedas y luego con las 18–23 disponibles desde 2023 (`tmp/new20`, `tmp/new15`).
- Medir si los vecinos de otras monedas ayudan o estorban: proporción de vecinos de la misma moneda frente a IC.

**Rejilla:** biblioteca \(\in \{\)misma moneda, 4 monedas, todas\(\}\), con o sin filtro de 4 h, y la mejor configuración de diseño de la sugerencia 1 o 3.

---

## Orden de trabajo y entregables

1. `common.py` (datos, periodos, regla de operación, métricas, pruebas de la regla sin fuga). Incluir una prueba que verifique que ningún vecino tiene \(s > t - 24\).
2. Sugerencia 1 completa: rejilla, resultados y resumen.
3. Sugerencia 3. Es la más prometedora, porque agrega información que la forma no tiene.
4. Sugerencias 2, 4 y 5, según cómo salgan la 1 y la 3.
5. Un documento final `doc/resultados-analogos.md` con la tabla de todas las sugerencias (diseño frente a validación) y la decisión: adoptar o descartar.

**Cuidado general:**
- Elegir parámetros solo con diseño.
- Validación se mira una vez.
- Toda mejora se compara contra "comprar siempre" y contra vecinos al azar.
- Si nada pasa el criterio, se documenta como resultado negativo. También es información útil.
