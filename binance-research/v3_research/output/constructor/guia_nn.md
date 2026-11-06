# Guía técnica: modelo complejo con datos de futuros (meta-etiquetado con red neuronal y árboles)

Esta guía explica cómo construir, validar y poner en producción un modelo como el candidato **ENS6**: un ensamble de 3 LightGBM y 3 MLP sobre la geometría G3, con datos de futuros. Todo el código de referencia está en `binance-research/data/research/nn/`. Las cifras son del walk-forward de diseño (2024-01 a 2025-06, 4 monedas). El Verificador todavía está evaluando el candidato fuera de muestra.

---

## 1. Pipeline de datos

**Qué descargar.** Todo sale de `https://data.binance.vision`, porque `api.binance.com` y `fapi` están bloqueados para descargas históricas desde aquí:

| Fuente | Ruta | Resolución | Uso |
|---|---|---|---|
| Velas spot | `spot/monthly/klines/{SYM}/15m/` | 15 m | Precio, volumen, taker buy |
| Metrics | `futures/um/daily/metrics/{SYM}/` | 5 min | Open interest (OI), ratios long/short de top traders y global, taker ratio |
| Funding | `futures/um/monthly/fundingRate/{SYM}/` | 8 h | Tasa de financiamiento liquidada |
| Prima | `futures/um/monthly/premiumIndexKlines/{SYM}/15m/` | 15 m | Prima del perpetuo sobre el índice |
| Velas UM | `futures/um/monthly/klines/{SYM}/15m/` | 15 m | Base futuros/spot y taker de futuros |

- **Cómo descargar:** `nn_download_futures.py --symbols … --start … --end … --out …` baja los archivos en 32 hilos y los guarda como `.npy` por moneda: `{SYM}_metrics.npy`, `_funding.npy`, `_premium15m.npy` y `_fut15m.npy`.
- **Fusión:** si el archivo ya existe, une los datos nuevos por marca de tiempo. Así se puede ampliar un rango sin volver a bajar todo.
- **Tamaño:** 4 monedas y 2.5 años de diseño ocupan unos 90 MB y se bajan en menos de 3 min.

**Regla de alineación sin fuga (metrics).** La semántica de `create_time` cambió el 2024-03-04: antes marcaba el final de la ventana de 5 min y desde esa fecha marca el inicio. Para que la regla valga en los dos periodos, se supone que cada registro se conoce en T + 5 min:

$$\text{usar el registro en la vela } i \iff T + 5\,\text{min} \le t_i + 15\,\text{min} \iff T \le t_i + 10\,\text{min}$$

- $T$: `create_time` del registro.
- $t_i$: apertura de la vela de 15 m; la decisión se toma al cierre, en $t_i + 15$ min.

En el modelo se usa un margen de 5 min más para tolerar la latencia de publicación en vivo: **T ≤ t_i + 5 min**.

*Ejemplo:* para la vela de 12:00 a 12:15 se usan T = 11:55, 12:00 y 12:05. El registro de 12:10 está permitido por la regla, pero queda fuera por el margen. **El de 12:15 nunca se usa**: describe los primeros minutos de la operación, y usarlo sería fuga.

**Otras fuentes:**
- **Funding:** solo liquidaciones con `calc_time` ≤ cierre de la vela.
- **Prima y velas UM:** la vela con el mismo `open_time`, que cierra a la vez que la vela spot.

**Huecos:**
- Ordenar las filas, porque hay archivos diarios desordenados.
- Rellenar hacia adelante, por columna, desde el último valor válido con una antigüedad máxima de 30 min. Si no hay, dejar NaN y marcar `metrics_missing = 1`.
- Nunca rellenar hacia atrás.

**Control empírico.** La media del taker ratio con T ∈ {t_i, t_i+5, t_i+10} correlaciona 0.84 con el desequilibrio taker de la vela i. Si se corre la ventana 15 min hacia adelante, la correlación cae a 0.12–0.16. Este control detecta un desfase de una ventana entera.

---

## 2. Etiquetado

**Triple barrera.** Se entra al cierre de la vela $i$ con precio $c$ y se fijan tres barreras:

$$TP = c\,(1 + a\,s_d),\qquad SL = c\,(1 - m\,s_d),\qquad s_d = \sigma_{15}\sqrt{96}$$

- $a, m$: múltiplos de la volatilidad para el TP y el SL; $b = a/m$.
- $\sigma_{15}$: desviación de los log-retornos de 15 m en las últimas 672 velas (7 días).
- $s_d$: volatilidad diaria.
- $H$: barrera de tiempo en velas. Si no se toca ninguna barrera, se sale al cierre de la vela $i + H$.

*Ejemplo (G3: a = 0.75, m = 1.5, H = 192):* con $c$ = 100 y $s_d$ = 4 %, TP = 103, SL = 94, R = 6 % y b = 0.5.

Las reglas de llenado son las del arnés: high/low, empate TP/SL = SL y hueco = apertura. La etiqueta es $y = \mathbb{1}[\text{neto} > 0]$, con 0.24 % de costos. Se comprobó que coincide con `harness.simulate` en 2 000 entradas de prueba.

**Por qué G3 y no b = 0.33.** Sin ventaja, el WR lo fija la geometría. El WR mínimo para que E > 0 es:

$$p^* = \frac{1 + c/R}{1 + b}$$

- $c$: costo de ida y vuelta (0.24 %).
- $R$: distancia al stop en fracción del precio.
- $b$: recompensa/riesgo.

| Geometría | b | R mediano | p* | WR del azar (medido) |
|---|---|---|---|---|
| G4 (0.4, 1.2, 192) | 0.33 | 3.98 % | (1 + 0.060)/1.33 = **79.5 %** | 71.2 % |
| G3 (0.75, 1.5, 192) | 0.50 | 4.97 % | (1 + 0.048)/1.5 = **69.9 %** | 58.6 % |

En las dos hace falta subir la E bruta en ≈ c. La diferencia está en cuánto rinde la misma capacidad de predicción. Si el modelo detecta una deriva $\mu$ por día, la ganancia bruta es aproximadamente $\mu$ por la duración esperada de la operación, y esa duración crece con las distancias a las barreras:

$$E_{\text{bruta}} \approx \mu\,\mathbb{E}[\tau],\qquad \mathbb{E}[\tau] \approx \frac{a\,m\,s_d^2}{s_d^2} = a\,m\ \text{días}$$

- $\mathbb{E}[\tau]$: duración esperada de la operación sin barrera de tiempo (movimiento browniano).

*Ejemplo:* con μ = 0.5 % por día, G3 (a·m = 1.125 días) gana ≈ 0.56 % bruto, más del doble de c. G4 (a·m = 0.48 días) gana ≈ 0.24 %, que es justo c.

Así salió en la práctica: en G4 todos los modelos dieron WR de 70–74 % y E < 0. En G3, con futuros, la E fue positiva.

**Meta-etiquetado.** El modelo estima $\hat p = P(y = 1 \mid x_i)$ en **todas** las velas, sin señal primaria. Se opera solo en el 1–3 % superior de $\hat p$.

---

## 3. Variables (74, sin identificador de moneda)

Todas son causales: el valor en $i$ usa solo datos ≤ cierre de $i$. Se normalizan por la volatilidad propia, así sirven para monedas que el modelo no vio.

| Familia | Ejemplos | Fórmula típica |
|---|---|---|
| Precio | `ret_k` (k = 1, 4, 16, 48, 96, 288, 672), `z_20`, `z_96`, `z_672`, `rngpos_96`, `dd_672`, `rsi14` | $\text{ret}_k = \ln(c_t/c_{t-k})/(\sigma_{15}\sqrt{k})$ |
| Volatilidad | `vol_ratio_16_96`, `vol_ratio_96_672`, `atr_rel`, `bar_range`, `vol_level` = ln(s_d/c) | Cocientes de σ en distintas ventanas |
| Volumen y flujo | `vol_rel_1/16/96` (log del volumen frente a su media de 7 d), `taker_imb_1/4/16/96`, `bar_body`, `bar_upwick` | $\text{imb} = v_{\text{taker}}/v - 0.5$ |
| Futuros (25) | `oi_chg_1/4/16/96`, `oi_z_672`, `oi_to_vol`, `top_acc_*`, `top_pos_*`, `glob_acc_*` (nivel, cambio y z), `fut_taker_*`, `funding`, `funding_z_2016`, `premium*`, `basis*`, `fut_imb_*`, `fut_spot_vol`, `metrics_missing` | $\text{oi\_chg}_k = \ln(OI_t/OI_{t-k})$ |
| Contexto BTC | `btc_ret_4/16/96/672`, `btc_z_672`, `btc_vol_ratio`, `rel_btc_96/672`, `beta_btc` | $\beta = \text{cov}(r, r_{BTC})/\text{var}(r_{BTC})$, 672 velas |
| Tiempo | `hour_sin/cos`, `wd_sin/cos` | $\sin(2\pi h/24)$ |

*Ejemplo de normalización:* ETH sube 1.5 % en 4 h con $\sigma_{15}$ = 0.4 %. Entonces $\text{ret}_{16} = \ln(1.015)/(0.004\cdot 4) = 0.93$: un movimiento de 0.93 desviaciones, comparable entre monedas.

**Normalización para la red:**

$$z = \text{clip}\big((x - \mu_{\text{ajuste}})/s_{\text{ajuste}},\ -5,\ 5\big)$$

- $\mu_{\text{ajuste}}, s_{\text{ajuste}}$: media y desviación calculadas solo con el tramo de ajuste del pliegue.
- Los NaN pasan a 0. LightGBM usa los NaN directamente.

**Canales para la CNN (10 por vela):** retorno/σ, rango/σ, cuerpo, volumen relativo, desequilibrio taker, retorno de BTC/σ, ΔOI normalizado, taker ratio de futuros, z de la prima y desequilibrio de futuros.

---

## 4. Arquitecturas y regularización

**LightGBM:**
- Configuración: binario, `learning_rate` 0.03, `num_leaves` 15, `min_data_in_leaf` 1000, `feature_fraction` 0.7, `bagging_fraction` 0.5, `lambda_l2` 10 y `max_bin` 63.
- Parada temprana por AUC de validación, con paciencia de 150 árboles y un mínimo de 50.
- `min_data_in_leaf` = 1000 obliga a que cada hoja agrupe unos 10 días de una moneda. Es el freno principal contra memorizar episodios.

**MLP (torch):**
- Capas: 74 → Linear(128) → GELU → Dropout(0.3) → Linear(64) → GELU → Dropout(0.3) → Linear(1). Son unos 18 000 parámetros.
- Entrenamiento: AdamW con lr 5e-4, weight decay 1e-3 y lote de 512. Parada por AUC de validación, con paciencia de 3 épocas y un máximo de 12.

**CNN 1D dilatada:**
- Entrada: (lote, 10 canales, 96 velas), con Dropout(0.1).
- Convoluciones: 4 capas Conv1d de 24 filtros, k = 5, dilataciones 1, 2, 4 y 8, con *padding* "same" y GELU. El campo receptivo es 1 + 4·(1+2+4+8) = 61 velas.
- Pooling: media, máximo y último paso, que dan un vector de 72.
- Rama tabular: 74 → Linear(64) → GELU → Dropout(0.3).
- Cabeza: concatenación de 136 → Linear(64) → GELU → Dropout(0.3) → Linear(1).
- Para ahorrar cómputo se entrenó con 1 de cada 4 velas.

**Por qué un ensamble.** Con una AUC de 0.50–0.59, cada modelo tiene mucho ruido de estimación. Promediar las probabilidades calibradas de 6 modelos con semillas y sesgos inductivos distintos reduce la varianza del 1–3 % superior, que es donde se opera. En el walk-forward, el ensamble tuvo la mejor E (+0.93 %) y el mejor PF (1.74), aunque menos operaciones que LGB s0.

**Cuándo tiene sentido una red más grande (LSTM o Transformer):**
- **Tiene sentido** con mucha información independiente y microestructura fina: velas de 1 s, libro de órdenes, flujo de operaciones. Ahí el orden temporal dentro de la ventana importa, y hay millones de eventos poco correlacionados.
- **Aquí sobreajusta.** La parada temprana se detuvo en la época 1–3 en casi todos los pliegues. La CNN sola fue el modelo más débil (E +0.37 %). Las variables que más pesan son lentas: z del funding a 21 días, BTC a 7 días y ratios de top traders.
- **Regla práctica:** la red debe tener muchos menos parámetros que eventos independientes (≈ días × monedas ≈ 3 000 en diseño). Si la AUC de validación no supera la del árbol en al menos 2–3 de cada 6 pliegues, no hay que agrandar la red.

---

## 5. Entrenamiento y validación

**Walk-forward con ventana expansiva.** El test es cada trimestre del 2024Q1 al 2025Q2 (6 pliegues) y el modelo se reentrena cada trimestre:
- **Ajuste:** desde 2023-01, más 800 velas de calentamiento, hasta el inicio de la validación, con purga.
- **Validación:** los 3 meses previos al test.
- **Test:** el trimestre.

**Purga y embargo.** La etiqueta de la vela $i$ depende de las velas $i+1 \ldots i+H$. Para que ninguna etiqueta de entrenamiento vea el periodo siguiente:

$$t_i + (H + 1)\,\Delta \le t_{\text{inicio}}\quad\Longrightarrow\quad i_{\max} = i_{\text{inicio}} - H - 1$$

- $\Delta$: 15 min.
- $t_{\text{inicio}}$: inicio de la validación (para el ajuste) o del test (para la validación).

*Ejemplo:* con H = 192, se descartan las últimas 193 velas (48 h 15 min) antes de cada corte. Como todas las variables son causales, no hace falta embargo después del test.

**Calibración de Platt** (con la validación):

$$\hat p = \frac{1}{1 + e^{-(A s + B)}},\qquad (A, B) = \arg\min_{A,B}\ \sum_{j \in \text{val}} \big[\ln(1 + e^{A s_j + B}) - y_j\,(A s_j + B)\big]$$

- $s$: puntuación cruda del modelo (logit de LightGBM o salida de la red).
- $y_j$: etiqueta en la validación.

*Ejemplo:* con A = 2.38 y B = −0.35 (LGB s0 final), una puntuación s = 0.5 da $\hat p = 1/(1+e^{-0.84}) = 0.70$.

**Umbral, elegido solo con la validación:**

$$\theta^* = \arg\max_{\theta \in Q}\ \bar E_{\text{val}}(\theta)\quad \text{s.a.}\quad WR_{\text{val}}(\theta) \ge 0.70,\ \bar E_{\text{val}} > 0,\ n \ge 150,\ \text{días} \ge 15$$

- $Q$: cuantiles {0.5, 0.7, …, 0.99, 0.995} de $\hat p$ en la validación.
- $\bar E_{\text{val}}(\theta)$: neto medio de las velas con $\hat p \ge \theta$.
- Si ningún θ cumple, ese trimestre no se opera.

Elegir θ con el test sería ajustar al resultado que se quiere medir. Por eso el test solo se usa una vez, para medir. En el walk-forward, θ quedó entre 0.59 y 0.70; en el modelo congelado, 0.713.

**Registro de pruebas.** Cada variante (geometría, versión de variables, modelo, semilla, ensamble o placebo) se registra con `harness.log_trials`. Fueron 54 en esta fase, y entran en la corrección: con ellas, el p de Bonferroni es 0.20 y el DSR con los ≈ 12 300 ensayos del equipo, 0.14.

---

## 6. Puesta en producción en este bot

Solo después de que el Verificador apruebe, y respetando S1–S7 de `doc/matematica-aplicativa.md`.

**Python (`binance-research/`):**
- Crear `nn_strategy/` con:
  - `features.py`: copia de `nn_common.py` (variables y alineación).
  - `model.py`: carga los 6 modelos, aplica Platt y el umbral, y verifica los SHA-256 de `spec_nn.json`.
  - `models/`: los archivos congelados.
- `strategy_engine.py`: registrar `NNMetaStrategy`, que mantiene por moneda y para BTC un búfer de ≥ 3 360 velas de 15 m **cerradas** (35 días) y las series de futuros. Su `evaluate(bar)` devuelve `{"action": "BUY", "entry_price", "take_profit", "stop_loss", "max_hold_bars": 192}`.
- `server.py`: nuevo tipo `evaluate_bar` con la vela cerrada completa (open_time, o, h, l, c, v, taker_buy_base).
  - Hoy recibe velas de 1 m y solo usa close y volume. Así no se puede calcular el modelo.
  - Al arrancar, debe cargar el historial desde los archivos `.npy`, no con 100 velas de 1 m.
- Datos de futuros en vivo: `/futures/data/openInterestHist`, `topLongShortAccountRatio`, `topLongShortPositionRatio`, `globalLongShortAccountRatio` y `takerlongshortRatio` (period = 5m), además de `/fapi/v1/fundingRate`, `/fapi/v1/premiumIndexKlines` y `/fapi/v1/klines`.
  - Se consultan cada 5 min y se aplica T ≤ t_i + 5 min.
  - Si falta un dato por más de 30 min, **no se opera esa vela**.

**Node (`src/`):**
- `ws-client.ts`: suscribirse a `kline_15m` y enviar solo velas cerradas (`k.x == true`), con `k.V` (taker buy).
- `index.ts` y `zmq-client.ts`:
  - Abrir con orden de mercado y OCO TP/SL.
  - Registrar la hora de entrada y cerrar a mercado a las 192 velas (48 h).
  - Tamaño por riesgo, porque R ≈ 6 % del precio: arriesgar 0.5–1 % del capital implica un nocional de 8–16 % del capital.

**Reentrenamiento.** Cada trimestre, con la misma receta: ajuste expansivo, 3 meses de validación, purga de 193 velas, Platt y θ elegidos en la validación. Antes de reemplazar el modelo:
- Congelar y calcular los hashes.
- Correr 2–4 semanas en sombra.
- Registrar la variante con `log_trials`.

**Cómputo medido en esta máquina (6 hilos de CPU):**
- **Walk-forward completo (6 pliegues):** LightGBM 13–35 s, MLP 40–103 s y CNN ≈ 6 min con 1 de cada 4 velas.
- **Entrenamiento final de los 6 modelos:** ≈ 1 min.
- **Inferencia:**
  - Arranque: importar torch y LightGBM tarda 3.1 s y cargar los modelos, 0.03 s.
  - Por vela: las variables de 2.5 años de una moneda se calculan en 1.1 s, y la predicción de los 6 modelos para una vela tarda 1.2 ms.
- **Tamaño:** modelos 348 KB. Con torch CPU, unos 300 MB de RAM (estimado, no medido).

**Monitoreo de deriva:**
- **Frecuencia de señales:** se esperan ≈ 15–30 operaciones por moneda y año (≈ 1–3 % de las velas con $\hat p \ge \theta$). Alertar si en 3 meses sale menos de la mitad o más del doble.
- **Calibración:** WR realizado frente a $\hat p$ medio, por tramos, cada 30 operaciones. Alertar si la diferencia supera 10 puntos.
- **Deriva de variables:** PSI de `funding_z_2016`, `oi_to_vol`, `top_acc_z_672` y `btc_ret_672` frente al ajuste. Alertar si PSI > 0.25.
- **Datos:** fracción de `metrics_missing`.
- **Interruptor:** con ≥ 30 operaciones y E < 0 con t < −2, o WR < 55 %, pasar a HOLD.

---

## 7. Factibilidad honesta

- **WR alcanzable:** en el walk-forward, **72 % [63.8, 78.9]** con b = 0.68 y E +0.93 % por operación. Lo realista es 68–73 %, no 80 %.
- **Por qué 80 % no:**
  - Con b ≈ 0.33 hace falta Δp ≈ 8 puntos sobre el azar (p* = 79.5 % frente a 71.2 %). Los modelos lograron +0.6 a +3.8 puntos en G4.
  - En G3, un 80 % solo aparece en pliegues sueltos con pocas operaciones.
- **Operaciones por año:** 22 por moneda en el walk-forward; el umbral congelado, más alto, apunta a 15–30.
- **Muestra para validar E > 0:**

$$n = \Big(\frac{(z_{1-\alpha} + z_{\text{pot}})\,\sigma}{\mu}\Big)^2\cdot \text{DEFF}$$

- $z_{1-\alpha}$: 1.645; $z_{\text{pot}}$: 0.84 (potencia de 0.8).
- $\sigma$: 3.92 % (desviación por operación).
- $\mu$: 0.93 % (E por operación).
- DEFF: 1.5 (efecto de diseño por agrupamiento).

*Ejemplo:* n = (2.485 · 3.92/0.93)² · 1.5 ≈ **166 operaciones**. Eso son ≈ 1.9 años con 4 monedas (88 por año) o ≈ 1.3 años con 6. Si la E real fuera la mitad, harían falta 4 veces más.

- **Muestra para el WR:** que el límite inferior de Wilson supere 70 % con un WR de 72 % exige ≈ 2 000 operaciones (≈ 20 años con 4 monedas). Ese WR **no se puede demostrar** en un plazo razonable; lo que sí se puede demostrar es E > 0.

**Datos que podrían subir la señal y cómo integrarlos.** Cada uno entra como columnas nuevas en la misma tabla, con su regla de "cuándo se conoce", una ablación con y sin la fuente, y su registro en `log_trials`:

| Fuente | Variables propuestas | Cómo obtenerla |
|---|---|---|
| Libro de órdenes | Desequilibrio de profundidad a ±1, 2 y 5 % y su cambio en 1 h | `futures/um/daily/bookDepth` (data.binance.vision); en vivo, `depth@100ms` agregado a 15 m |
| Liquidaciones | Volumen liquidado de largos y de cortos en 15 m y 1 h, y su z | Coinalyze (API con clave; histórico limitado). En Binance no hay histórico: grabar `!forceOrder@arr` desde ahora |
| On-chain | Flujos netos de stablecoins y de BTC/ETH hacia exchanges (diarios) | CryptoQuant o Glassnode (de pago). Por su baja resolución, usar solo como régimen |
| Opciones | DVOL, *skew* 25Δ | Deribit (API pública) |

Lo que el modelo ya explota (compras en capitulación con OI/volumen bajo y funding extremo) es justo lo que las liquidaciones medirían directamente. Es la fuente más prometedora.

---

## 8. Qué aportó cada pieza (walk-forward G3, OOS 2024-01 a 2025-06, c = 0.24 %)

| Pieza | n | WR [IC 95 %] | E % (t día) | ΔWR / ΔE contra el azar | Lectura |
|---|---|---|---|---|---|
| LGB sin futuros | 78 | 62.8 [51.7, 72.7] | +0.04 (0.07) | +2.3 / +0.31 | Spot solo ≈ azar |
| MLP sin futuros | 196 | 64.8 [57.9, 71.1] | +0.20 (0.53) | +2.8 / +0.19 | Igual |
| CNN sin futuros | 584 | 65.8 [61.8, 69.5] | +0.19 (0.76) | +9.0 / +0.69 | La secuencia sola no basta |
| **LGB con futuros** | 194 | 72.2 [65.5, 78.0] | +0.71 (2.22) | +17.0 / +1.21 | **Los futuros suben E en +0.67** |
| MLP con futuros | 125 | 69.6 [61.1, 77.0] | +0.83 (1.98) | +11.9 / +1.25 | +0.62 frente a sin futuros |
| CNN con futuros | 127 | 72.4 [64.1, 79.5] | +0.37 (0.76) | +14.4 / +0.65 | La más débil con futuros |
| LGB ×3 semillas | 264 | 67.4 [61.6, 72.8] | +0.47 (1.54) | +11.3 / +0.91 | 0.24 menos que LGB s0: la semilla pesa |
| **ENS6 (congelado)** | 132 | **72.0 [63.8, 78.9]** | **+0.93 (2.33)** | +16.7 / +1.41 | Mejor E y PF (1.74) |
| ENS6 + CNN | 166 | 73.5 [66.3, 79.6] | +0.99 (2.23) | +18.0 / +1.47 | +0.06 de E: ruido |
| Placebo: futuros +1 h | 146 | 72.6 [64.9, 79.2] | +0.88 (2.37) | +17.2 / +1.35 | Sin fuga de minutos |
| G4 (b = 0.33), ensamble con futuros | 182 | 72.0 [65.1, 78.0] | −0.31 (−1.65) | +0.6 / −0.12 | WR alto, E < 0 |

**Lectura de la tabla:**
- **Futuros:** la información de futuros es lo único que movió la E en todas las arquitecturas.
- **Arquitecturas:** aportan poco, del orden de la variabilidad entre semillas.
- **Prueba pendiente:** nada de esto es significativo después de la corrección por pruebas múltiples (DSR 0.14). La prueba real es la del Verificador sobre monedas y periodos no vistos.
