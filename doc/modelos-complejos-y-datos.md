# Modelos complejos y mejores datos: hasta dónde se puede llegar

Este documento continúa [matematica-aplicativa.md](matematica-aplicativa.md). Allí se concluyó que, con velas de precio y modelos simples, ninguna estrategia logra un *win rate* de 70–80 % con esperanza positiva fuera de muestra. Aquí se responden tres preguntas:

1. **¿Qué datos con más información existen y dónde se consiguen?** (sección 1, corta)
2. **¿Sirven otras temporalidades u otros activos?** (sección 2, corta)
3. **¿Cómo se construye un modelo más complejo (redes neuronales) que intente el 70–80 %, y qué tan factible es?** (sección 3, detallada, con dos intentos reales verificados por un segundo agente sobre 14 monedas que el modelo nunca vio)

## Respuesta corta

> **No se pudo lograr un win rate de 70–80 % con esperanza positiva, ni siquiera con redes neuronales y datos de futuros.** Se intentó dos veces, con verificación independiente sobre monedas que el modelo nunca vio, y las dos versiones quedaron en **≈ 69 %** de win rate y sin ganancia demostrada.

- **Lo que sí funcionó:** al añadir datos de futuros (open interest, ratios long/short, *funding*, prima), un ensamble de redes neuronales y árboles aprendió a comprar **velas de capitulación** (ventas forzadas que rebotan). En **18 monedas que no vio**, eligió entradas **9–17 puntos de win rate mejores que el azar** con la misma geometría, y con ≈ +1 % más de esperanza por operación ($p \approx 0.001$). Es la primera ventaja de todo el proyecto que se replica fuera de muestra.
- **Lo que no alcanzó:**
  - **El win rate:** 68.7 % (v1) y 69.4 % (v2) en monedas nuevas. Su intervalo de confianza **descarta el 75 % y el 80 %** y no permite afirmar el 70 %. La v2 llegó a 81 % en diseño, pero ese salto fue producto de la selección y desapareció en datos nuevos.
  - **La ganancia absoluta:** +0.32 % a +0.41 % por operación, no significativa. El periodo de prueba (2025-07 a 2026-09) fue bajista: entrar al azar perdía ≈ −0.75 % por operación, y la ventaja del modelo apenas compensó esa caída.
- **La complejidad del modelo importó poco; la información, mucho.** Sin datos de futuros, ninguna arquitectura superó al azar de forma útil. Con ellos, todas mejoraron. Una red más grande (LSTM, Transformer) solo agrega sobreajuste con estos datos.
- **"Sí o sí" no es honesto:** un win rate de 70–80 % se puede fabricar siempre con un TP corto y un SL largo, pero entonces la esperanza es negativa. Con ventaja real, lo que se midió en datos nuevos es **≈ 69 %**. Para acercarse al 70–80 % con ganancia haría falta información nueva (sobre todo liquidaciones y libro de órdenes, sección 1) y una prueba prospectiva con datos posteriores a 2026-10.

## Tabla de contenido

- [Respuesta corta](#respuesta-corta)
- [1. Datos con más información que las velas de precio](#1-datos-con-más-información-que-las-velas-de-precio)
- [2. Otras temporalidades u otros activos](#2-otras-temporalidades-u-otros-activos)
- [3. Modelos más complejos: cómo construirlos y qué tan factibles son](#3-modelos-más-complejos-cómo-construirlos-y-qué-tan-factibles-son)

---

## 1. Datos con más información que las velas de precio

Las velas solo dicen a qué precio se negoció. Los datos de esta sección dicen **quién** está posicionado, **cuánto** apalancamiento hay y **qué tan fácil** es mover el precio. Ninguno garantiza una ventaja, pero son la única fuente de información nueva que un modelo podría aprovechar.

### 1.1 Libro de órdenes

**Qué es.** Las órdenes pendientes de compra y venta en cada nivel de precio. Un libro "delgado" del lado vendedor anticipa subidas fáciles; un muro de órdenes grandes puede frenar el precio.

| Fuente | Qué da | Costo | Acceso desde tu ubicación |
|---|---|---|---|
| `data.binance.vision` → `futures/um/daily/bookDepth/{SYM}/` | Profundidad agregada del libro de futuros (cantidad acumulada a ±1 %, ±2 %… del precio), en archivos diarios | Gratis | **Sí** (verificado) |
| `data.binance.vision` → `spot/daily/aggTrades`, `futures/um/daily/aggTrades`, `bookTicker` | Cada operación agregada; mejor compra y venta | Gratis | Sí |
| WebSocket de Binance `<symbol>@depth@100ms` | Libro completo en tiempo real (para grabarlo uno mismo hacia adelante) | Gratis | Desde testnet sí; el mercado real puede estar bloqueado |
| [Tardis.dev](https://tardis.dev/) | Libro completo tick a tick de muchos exchanges | El primer día de cada mes es gratis; el resto, planes de 350–6 000 USD/mes | Sí (descarga por HTTP) |

**Recomendación:** empezar con `bookDepth` de `data.binance.vision`, que es gratis y cubre 2023 en adelante. Si un modelo encuentra algo, recién ahí pagar datos tick a tick.

### 1.2 Funding y open interest de futuros

**Qué son.** El *funding* es el pago periódico entre largos y cortos de los futuros perpetuos: si es muy positivo, hay exceso de compradores apalancados. El *open interest* es la cantidad de contratos abiertos: si sube con el precio, entra dinero nuevo; si sube mientras el precio cae, se acumulan cortos.

| Fuente | Qué da | Costo | Acceso |
|---|---|---|---|
| `data.binance.vision` → `futures/um/daily/metrics/{SYM}/` | Cada 5 min: open interest, ratios long/short de los *top traders* y de todas las cuentas, ratio de volumen comprador/vendedor agresivo. Desde 2023 | Gratis | **Sí** (verificado) |
| `data.binance.vision` → `futures/um/monthly/fundingRate/{SYM}/` | Historial de *funding* (cada 8 h) | Gratis | **Sí** (verificado) |
| `data.binance.vision` → `futures/um/monthly/premiumIndexKlines/{SYM}/15m/` | Prima del futuro sobre el índice (*basis*) en velas de 15 min | Gratis | **Sí** (verificado) |
| API de futuros `fapi.binance.com` | Lo mismo en tiempo real | Gratis | **No**: bloqueada desde tu ubicación (HTTP 451) |
| [Coinalyze](https://dlthub.com/context/source/coinalyze) | Open interest, *funding* y liquidaciones agregados de ~25 exchanges | API gratis con clave, 40 llamadas/min | Sí |

### 1.3 Liquidaciones

**Qué son.** Cierres forzados de posiciones apalancadas. Las cascadas de liquidaciones producen las caídas y subidas más violentas, que es justo donde un modelo de reversión podría encontrar ventaja.

| Fuente | Qué da | Costo |
|---|---|---|
| `data.binance.vision` | El conjunto `liquidationSnapshot` **ya no está disponible** (404 verificado para 2023) | — |
| WebSocket de Binance `!forceOrder@arr` | Liquidaciones en tiempo real (hay que grabarlas uno mismo; solo sirve hacia adelante) | Gratis |
| [Coinalyze](https://dlthub.com/context/source/coinalyze) | Historial de liquidaciones de largos y cortos por símbolo | Gratis con límite de llamadas |
| [CoinGlass](https://nexusfi.com/d/data-providers/coinglass/) | Liquidaciones, mapas de calor y open interest agregado | API de pago desde ~29 USD/mes; los mapas de calor, en planes superiores |

**Recomendación:** Coinalyze para el historial y grabar `!forceOrder@arr` desde ahora para tener datos propios a futuro.

### 1.4 Datos on-chain

**Qué son.** Movimientos en la propia blockchain: monedas que entran a los exchanges (posible presión vendedora), que salen (acumulación), reservas de las plataformas, actividad de grandes billeteras. Son lentos (horas o días), así que sirven más como **contexto de régimen** que como señal para velas de 15 min.

| Fuente | Qué da | Costo |
|---|---|---|
| [BGeometrics](https://bgeometrics.com/2023/10/16/bitcoin-api-free-with-on-chain-data/amp/) | Flujos de BTC hacia y desde exchanges (entradas, salidas, reservas, neto), últimos 4 años | Gratis, 8 llamadas/hora y 200/día |
| CoinMetrics Community API | Métricas on-chain básicas de varias redes | Gratis |
| [CryptoQuant](https://cryptoquant.com/apis) | Flujos de exchanges, reservas, mineros | API on-chain desde ~109 USD/mes |
| Glassnode, Dune Analytics | Métricas on-chain avanzadas; Dune permite consultas SQL propias | Planes gratuitos limitados; verificar condiciones vigentes |

**Advertencia común a toda la sección.** Las fuentes de terceros cambian precios y límites con frecuencia: verificar en su página antes de depender de ellas. Y cualquier dato nuevo debe alinearse en el tiempo sin fugas: un valor publicado a las 10:05 solo puede usarse en una vela que **cierra** a las 10:05 o después.

---

## 2. Otras temporalidades u otros activos

### 2.1 Temporalidades

`data.binance.vision` tiene velas de 1 s, 1 m, 3 m, 5 m, 15 m, 30 m, 1 h, 2 h, 4 h, 6 h, 8 h, 12 h y 1 d, en `spot/monthly/klines/{SYM}/{intervalo}/`. Lo que importa al elegir:

| Temporalidad | A favor | En contra |
|---|---|---|
| 1 s – 5 m | Muchas operaciones (muestra grande para validar) | Los costos (0.24 %) son varias veces el movimiento típico de una vela: casi imposible ganar sin ser *maker* |
| 15 m – 1 h | Equilibrio entre costos y número de operaciones | Es lo que ya se probó: sin ventaja fuera de muestra |
| 4 h – 1 d | Los costos pesan poco frente al movimiento; patrones de *momentum* documentados en la literatura | Pocas operaciones por año: validar una ventaja puede llevar años |

**Regla práctica.** Con $c = 0.24\,\%$, el riesgo por operación debería ser al menos 8–10 veces los costos (≈ 2–2.5 %) para que un win rate alto deje ganancia (fórmula 3 de [matematica-aplicativa.md](matematica-aplicativa.md)). Eso empuja hacia velas de 1 h o más.

### 2.2 Otros activos

| Opción | Dónde | Para qué sirve |
|---|---|---|
| Más pares USDT de Binance (XRP, BNB, ADA, LINK, AVAX, LTC, etc.) | `data.binance.vision/data/spot/...` | **Validación**: una regla que funciona en 4 monedas debería funcionar en otras que no se usaron para diseñarla. Es lo que hace la sección 3. |
| Futuros perpetuos de Binance | `data.binance.vision/data/futures/um/...` | Permiten operar en corto (el bot spot no puede) y aportan *funding*/open interest |
| Otros exchanges (OKX, Bybit, Coinbase, Kraken) | Sus archivos públicos o la librería CCXT | Comparar precios entre exchanges; diferencias persistentes pueden ser señal |
| Mercados tradicionales (índice S&P 500, dólar, oro) | Proveedores como Yahoo Finance o Stooq | Contexto de régimen (las cripto suelen caer cuando cae el apetito de riesgo); no operan 24/7 |

**Cuidado con la selección.** Elegir las monedas "que mejor funcionan" en el pasado es otra forma de sobreajuste. Las monedas de validación se fijan **antes** de mirar resultados.

---

## 3. Modelos más complejos: cómo construirlos y qué tan factibles son

Esta sección no es teórica: dos agentes construyeron y probaron un modelo real.

- **Constructor:** diseñó y entrenó el modelo usando **solo** datos de BTC, ETH, SOL y DOGE de 2023-01 a 2025-06.
- **Verificador:** auditó el código en busca de fugas de información y ejecutó **una sola vez** la prueba final sobre **monedas que el Constructor nunca vio**, con criterios de aprobación escritos antes de la prueba.

Todo el código está en `binance-research/data/research/nn/`, los modelos entrenados en `nn/models/` y los informes en `output/constructor/` y `output/verificador/`.

### 3.1 La idea central: la información manda, no el algoritmo

Una red neuronal no inventa información: encuentra patrones que ya están en los datos. Por eso el primer experimento fue medir qué aporta cada pieza por separado, con la misma geometría de salida y el mismo walk-forward (diseño, 2024-01 a 2025-06):

| Modelo | Solo velas de precio: E por operación | Con datos de futuros: E por operación |
|---|---|---|
| LightGBM (árboles) | +0.04 % | +0.71 % |
| MLP (red densa) | +0.20 % | +0.83 % |
| CNN 1D (red de secuencias) | +0.19 % | +0.37 % |

> **Lectura:** con solo velas, ninguna arquitectura, ni la red de secuencias, supera al azar de forma útil. Al añadir open interest, ratios long/short, *funding* y prima de futuros, la esperanza sube en **todas** las arquitecturas. Cambiar de árbol a red o de red densa a red de secuencias mueve la esperanza mucho menos que añadir una fuente de datos.

Esto confirma la advertencia: **con los mismos datos de velas, un modelo más complejo solo aumenta el riesgo de sobreajuste**. La complejidad tiene sentido **después** de conseguir datos con más información (sección 1).

### 3.2 Paso 1 — Datos y alineación sin fuga

**Qué se descargó** (todo gratis desde `data.binance.vision`; ~90 MB para 4 monedas y 2.5 años, en menos de 3 minutos con 32 hilos):

| Fuente | Ruta | Resolución |
|---|---|---|
| Velas spot | `spot/monthly/klines/{SYM}/15m/` | 15 min |
| Open interest y ratios long/short | `futures/um/daily/metrics/{SYM}/` | 5 min |
| *Funding* | `futures/um/monthly/fundingRate/{SYM}/` | 8 h |
| Prima del perpetuo | `futures/um/monthly/premiumIndexKlines/{SYM}/15m/` | 15 min |
| Velas de futuros | `futures/um/monthly/klines/{SYM}/15m/` | 15 min |

**La trampa de las marcas de tiempo.** El Verificador descubrió que el campo `create_time` de los datos de futuros **cambia de significado el 2024-03-04**: antes marcaba el final del intervalo de 5 minutos y desde esa fecha marca el inicio. Si no se tiene en cuenta, el modelo ve datos de los primeros minutos de la operación, es decir, del futuro. La regla segura es:

$$
\text{usar el registro en la vela } i \iff T + 5\ \text{min} \le t_i + 15\ \text{min} \iff T \le t_i + 10\ \text{min}
$$

**Qué es cada símbolo:**

- $T$: marca de tiempo (`create_time`) del registro de futuros.
- $t_i$: apertura de la vela de 15 min; la decisión se toma al cierre, en $t_i + 15$ min.
- $+5$ min: se asume que cada registro solo se conoce 5 minutos después de su marca, para que la regla valga antes y después del cambio.

> **Ejemplo:** para la vela de 12:00 a 12:15 se pueden usar los registros de 11:55, 12:00, 12:05 y 12:10. El modelo usó un margen extra (hasta 12:05) para tolerar demoras en vivo. El registro de 12:15 **nunca** se usa: describe lo que pasó después de entrar.

**Huecos:** ordenar las filas (hay archivos diarios desordenados), rellenar hacia adelante con un máximo de 30 minutos, marcar el dato faltante con una columna `metrics_missing` y **nunca** rellenar hacia atrás.

**Control empírico de la alineación:** el ratio de compradores agresivos de futuros alineado con la regla correlaciona 0.84 con el desequilibrio de la vela spot; corrido 15 minutos hacia adelante, cae a 0.12–0.16. Si la alineación estuviera mal, esta prueba lo delataría.

### 3.3 Paso 2 — Etiqueta: qué aprende el modelo

El modelo no predice el precio: predice si una operación con una geometría fija terminará ganando. Es el **meta-etiquetado con triple barrera**:

$$
TP = c\,(1 + a\,s_d),\qquad SL = c\,(1 - m\,s_d),\qquad s_d = \sigma_{15}\sqrt{96},\qquad y = \mathbb{1}[\text{retorno neto} > 0]
$$

**Qué es cada símbolo:**

- $c$: precio de entrada (cierre de la vela).
- $a$, $m$: múltiplos de la volatilidad diaria para el TP y el SL; $b = a/m$.
- $\sigma_{15}$: desviación de los retornos de 15 min en los últimos 7 días (672 velas); $s_d$: volatilidad diaria.
- $H$: barrera de tiempo en velas; si no se toca ninguna barrera, se sale al cierre de la vela $i + H$.
- $y$: etiqueta, 1 si la operación gana después de costos (0.24 %).

> **Ejemplo (geometría G3: $a = 0.75$, $m = 1.5$, $H = 192$ velas = 48 h):** con $c = 100$ y $s_d = 4\,\%$: TP = 103, SL = 94, riesgo $R = 6\,\%$, $b = 0.5$.

**Por qué G3 ($b = 0.5$) y no una geometría de win rate más alto como G4 ($b = 0.33$).** Sin ventaja, el win rate lo fija la geometría, y el mínimo para ganar es $p^{*} = (1 + c/R)/(1 + b)$:

| Geometría | $b$ | $R$ mediano | $p^{*}$ | WR del azar (medido) |
|---|---|---|---|---|
| G4 (0.4, 1.2, 192) | 0.33 | 3.98 % | 79.5 % | 71.2 % |
| G3 (0.75, 1.5, 192) | 0.50 | 4.97 % | 69.9 % | 58.6 % |

En las dos, la señal debe aportar lo mismo en términos brutos. La diferencia está en **cuánto rinde** una misma capacidad de predicción. Si el modelo detecta una deriva $\mu$ por día, la ganancia bruta crece con la duración esperada de la operación:

$$
E_{\text{bruta}} \approx \mu \cdot \mathbb{E}[\tau],\qquad \mathbb{E}[\tau] \approx a \cdot m \ \text{días}
$$

**Qué es cada símbolo:** $\mu$ es la deriva favorable que detecta el modelo (por día); $\mathbb{E}[\tau]$ es la duración media de la operación cuando el precio se mueve al azar entre dos barreras a $a$ y $m$ volatilidades diarias.

> **Ejemplo:** con $\mu = 0.5\,\%$ por día, G3 ($a \cdot m = 1.125$ días) gana ≈ 0.56 % bruto, más del doble de los costos. G4 ($a \cdot m = 0.48$ días) gana ≈ 0.24 %, justo los costos. Por eso, en G4, todos los modelos dieron **WR de 70–74 % pero E negativa** (−0.31 % el ensamble con futuros). Ese win rate lo pone la geometría, no el modelo.

### 3.4 Paso 3 — Variables (74, sin identificar la moneda)

Todas son causales (en la vela $i$ solo usan datos hasta su cierre) y se normalizan por la volatilidad propia de la moneda, para que el modelo sirva en monedas que no vio:

| Familia | Ejemplos | Fórmula típica |
|---|---|---|
| Precio | retornos a 1, 4, 16, 48, 96, 288 y 672 velas; z-scores a 20, 96 y 672 velas; posición en el rango; caída desde el máximo de 7 días; RSI | $\text{ret}_k = \ln(c_t/c_{t-k})/(\sigma_{15}\sqrt{k})$ |
| Volatilidad | cocientes de volatilidad corta/larga, ATR relativo, rango de la vela, nivel de volatilidad | $\sigma_{16}/\sigma_{96}$ |
| Volumen y flujo | volumen relativo a su media de 7 días, desequilibrio de compradores agresivos, cuerpo y mechas de la vela | $\text{imb} = v_{\text{taker}}/v - 0.5$ |
| Futuros (25) | cambio de open interest a 1, 4, 16 y 96 velas; z del open interest; open interest/volumen; ratios long/short de *top traders* y de todas las cuentas; *funding* y su z a 21 días; prima y base | $\text{oi\_chg}_k = \ln(OI_t/OI_{t-k})$ |
| Contexto BTC | retornos de BTC, z de 7 días, beta de la moneda frente a BTC, retorno relativo | $\beta = \text{cov}(r, r_{BTC})/\text{var}(r_{BTC})$ |
| Tiempo | hora y día de la semana en seno y coseno | $\sin(2\pi h/24)$ |

> **Ejemplo de normalización:** ETH sube 1.5 % en 4 horas con $\sigma_{15} = 0.4\,\%$: $\text{ret}_{16} = \ln(1.015)/(0.004 \times 4) = 0.93$. Es un movimiento de 0.93 desviaciones, comparable con el de cualquier otra moneda.

Para las redes, cada variable se estandariza con la media y la desviación **del tramo de entrenamiento** y se recorta a ±5: $z = \text{clip}((x - \mu_{\text{ajuste}})/s_{\text{ajuste}}, -5, 5)$. La CNN recibe además una secuencia de 96 velas con 10 canales (retorno, rango, cuerpo, volumen relativo, desequilibrio, retorno de BTC, cambio de open interest, ratio de futuros, prima y desequilibrio de futuros).

**Qué aprende el modelo.** Las entradas que elige son **velas de capitulación**: rango de +2.3 desviaciones, volumen de +1.4 desviaciones, caída en la última hora y open interest bajo frente al volumen. Es decir, ventas forzadas que suelen rebotar.

### 3.5 Paso 4 — Arquitecturas

| Modelo | Arquitectura | Parámetros clave |
|---|---|---|
| **LightGBM** | Árboles de decisión con *boosting* | 15 hojas, `min_data_in_leaf` = 1 000 (cada hoja agrupa ~10 días de una moneda: el freno principal contra memorizar), `learning_rate` 0.03, `lambda_l2` 10, parada temprana por AUC de validación |
| **MLP** | 74 → 128 → 64 → 1, activación GELU, *dropout* 0.3 | ~18 000 parámetros; AdamW (lr 5·10⁻⁴, *weight decay* 10⁻³), lotes de 512, parada temprana (paciencia 3 épocas) |
| **CNN 1D dilatada** | 4 capas convolucionales de 24 filtros, núcleo 5, dilataciones 1/2/4/8 (campo receptivo de 61 velas) + rama tabular de 64 | *Pooling* de media, máximo y último paso; cabeza de 136 → 64 → 1 |
| **Ensamble ENS6** | Promedio de las probabilidades calibradas de 3 LightGBM y 3 MLP (semillas distintas) | El que mejor resultó en diseño |

**Por qué un ensamble.** Con un AUC de 0.50–0.59, cada modelo tiene mucho ruido. Promediar 6 modelos con semillas y sesgos distintos reduce la varianza justo en el 1–3 % superior de probabilidades, que es donde se opera.

**Cuándo una red más grande (LSTM, Transformer) tiene sentido y cuándo no:**

- **Tiene sentido** con mucha información independiente y de alta frecuencia: velas de 1 s, libro de órdenes, flujo de operaciones. Ahí el orden temporal dentro de la ventana importa y hay millones de eventos.
- **Aquí sobreajusta.** La parada temprana se detuvo en las épocas 1–3 en casi todos los pliegues, y la CNN, la red de secuencias, fue el modelo más débil. Las variables que más pesan son lentas (*funding* a 21 días, BTC a 7 días, ratios de *top traders*).
- **Regla práctica:** la red debe tener muchos menos parámetros que eventos independientes (aquí ≈ días × monedas ≈ 3 000). Si el AUC de validación de la red no supera al del árbol en al menos 2–3 de 6 pliegues, **no hay que agrandarla**.

### 3.6 Paso 5 — Entrenamiento, calibración y umbral

**Walk-forward con ventana expansiva.** Seis pliegues trimestrales (2024-T1 a 2025-T2). En cada uno: entrenamiento con todo lo anterior, validación con los 3 meses previos y prueba con el trimestre. El modelo se reentrena cada trimestre.

**Purga.** La etiqueta de la vela $i$ depende de las $H$ velas siguientes, así que se descartan las últimas $H + 1$ velas antes de cada corte:

$$
t_i + (H + 1)\,\Delta \le t_{\text{corte}} \quad\Longrightarrow\quad i_{\max} = i_{\text{corte}} - H - 1
$$

> **Ejemplo:** con $H = 192$ y $\Delta = 15$ min, se descartan las 193 velas (48 h 15 min) previas a cada corte.

**Calibración de Platt.** Convierte la salida cruda del modelo en una probabilidad real, ajustada con la validación:

$$
\hat p = \frac{1}{1 + e^{-(A s + B)}}
$$

**Qué es cada símbolo:** $s$ es la salida cruda del modelo; $A$ y $B$ se ajustan para minimizar el error de predicción (*log loss*) en la validación; $\hat p$ es la probabilidad calibrada de que la operación gane.

> **Ejemplo:** con $A = 2.38$ y $B = -0.35$ (uno de los LightGBM finales), una salida $s = 0.5$ da $\hat p = 1/(1 + e^{-0.84}) = 0.70$.

**Umbral para operar** (elegido **solo** con la validación, nunca con la prueba):

$$
\theta^{*} = \arg\max_{\theta}\ \bar E_{\text{val}}(\theta)
\quad\text{sujeto a}\quad
WR_{\text{val}}(\theta) \ge 0.70,\ \ \bar E_{\text{val}}(\theta) > 0,\ \ n \ge 150,\ \ \text{días} \ge 15
$$

**Qué es cada símbolo:** $\theta$ es el umbral de probabilidad ($\hat p \ge \theta$ ⇒ comprar); $\bar E_{\text{val}}$ y $WR_{\text{val}}$ son la esperanza y el win rate de las velas que superan el umbral en la validación. Si ningún umbral cumple, ese trimestre no se opera. El modelo final congelado quedó con $\theta = 0.713$ (opera en el ~2 % superior de las velas).

### 3.7 Paso 6 — Verificación independiente

Para que el resultado no fuera otro espejismo como el de C1 en [matematica-aplicativa.md](matematica-aplicativa.md), la prueba se diseñó así:

1. **Pre-registro.** Antes de la prueba, el Verificador escribió los criterios de aprobación:
   - (a) E > 0 con $t$ agrupado por día > 1.645, y también con costos de 0.30 %;
   - (b) límite inferior de Wilson del win rate ≥ 0.70 (tu objetivo);
   - (c) ventaja significativa frente a entradas al azar con la misma moneda, mes y geometría;
   - (d) auditoría de fugas limpia.
2. **Auditoría de fugas.** El Verificador alteró el futuro en 16 puntos de corte y comprobó que **ninguna** de las 74 variables cambiaba antes de cada corte. También reprodujo el umbral exacto (0.713364) y la prueba de humo.
3. **Monedas nunca vistas.** La prueba principal se hizo sobre XRP, BNB, ADA, LINK, AVAX y LTC, descargadas y custodiadas solo por el Verificador, en 2025-07 a 2026-09.
4. **Una sola ejecución,** registrada con los hashes de los archivos.

### 3.8 Resultados

**Modelo v1 (ENS6):**

| | Diseño (walk-forward, 4 monedas) | **Prueba principal (6 monedas nunca vistas)** | Prueba de apoyo (4 monedas originales) |
|---|---|---|---|
| Operaciones (por moneda y año) | 132 (22) | **383 (51)** | 204 (41) |
| Win rate [IC 95 %] | 72.0 % [63.8, 78.9] | **68.7 % [63.9, 73.1]** | 60.8 % [53.9, 67.2] |
| Win rate del azar con la misma geometría | 55.2 % | 51.7 % | 52.3 % |
| **Ventaja sobre el azar (win rate)** | +16.7 puntos | **+16.9 puntos ($p < 0.001$)** | +8.5 puntos ($p = 0.04$) |
| E neta por operación | +0.93 % | **+0.41 %** ($t_{\text{día}} = 1.08$) | −0.22 % |
| **Ventaja sobre el azar (E)** | +1.41 % | **+1.13 % ($p = 0.005$)** | +0.51 % |
| E con costos de 0.30 % | +0.87 % | +0.35 % | −0.28 % |

**Veredicto pre-registrado: RECHAZADO**, pero con un matiz muy importante:

- ✅ **(c) y (d) se cumplen.** El modelo **elige entradas mucho mejores que el azar** en monedas que nunca vio: +16.9 puntos de win rate, casi igual que en diseño. Es la **primera ventaja de todo el proyecto que se replica fuera de muestra**.
- ❌ **(a) no se cumple.** La ganancia absoluta (+0.41 % por operación) no es significativa. El periodo fue bajista: entrar al azar perdía −0.73 % por operación, y la ventaja del modelo apenas compensó esa caída. Además, las ganancias se concentran en pocos días de capitulación simultánea en varias monedas (los 10 días más activos reúnen 136 de las 383 operaciones).
- ❌ **(b) no se cumple.** Win rate de 68.7 %, a 1.3 puntos del 70 %; su intervalo [63.9 %, 73.1 %] no permite afirmar el 70 % y **descarta el 80 %**.

**Modelo v2 (segundo intento, diseñado a ciegas).** El Constructor solo supo que la v1 no había aprobado, sin ningún detalle de la prueba, y rediseñó usando únicamente los datos de diseño. Cambios:

- **Salida más ancha y más larga (X5):** TP a 0.7·$s_d$, SL a 1.75·$s_d$ ($b = 0.4$) y hasta 288 velas (72 h), porque el rebote tras una capitulación necesita tiempo.
- **Umbral con win rate de validación ≥ 0.75**, elegido maximizando la esperanza; purga de 289 velas. El Verificador confirmó y corrigió una fuga leve en la purga de la versión anterior del walk-forward.
- **Ensamble de 13 modelos** (6 LightGBM, 6 MLP y 1 CNN).
- Un filtro de régimen (BTC sobre su media de 30 días) se probó y se **descartó**: eliminaba justo las capitulaciones.

Se probó una sola vez sobre **8 monedas nuevas**, fijadas antes de ver ningún resultado: DOT, ATOM, NEAR, ETC, FIL, TRX, UNI y BCH.

| | Diseño (walk-forward) | **Prueba principal (8 monedas nuevas)** | Descriptivo: 6 monedas de la v1 | Descriptivo: 4 originales |
|---|---|---|---|---|
| Operaciones (por moneda y año) | 188 (31) | **621 (62)** | 397 (53) | 203 (41) |
| Win rate [IC 95 %] | **81.4 %** [75.2, 86.3] | **69.4 %** [65.7, 72.9] | 71.5 % [66.9, 75.8] | 72.9 % [66.4, 78.6] |
| Win rate del azar con la misma geometría | 62.0 % | 60.0 % | 57.2 % | 58.3 % |
| Ventaja sobre el azar (win rate) | +19.4 | **+9.4** ($t = 3.29$) | +14.4 | +14.6 |
| E neta por operación | +1.41 % | **+0.32 %** ($t_{\text{día}} = 1.02$) | +0.22 % | +0.12 % |
| Ventaja sobre el azar (E) | +1.85 % | **+1.07 % ($p = 0.001$)** | +1.11 % | +0.94 % |
| DSR (corrección por ≈ 12 340 pruebas) | 0.755 | 0.02 | — | — |

**Veredicto pre-registrado: RECHAZADO**, igual que la v1:

- ✅ Sin fugas, y con ventaja significativa sobre el azar en las 8 monedas.
- ❌ La ganancia absoluta no es significativa: +0.32 % por operación, que en unidades de riesgo es prácticamente cero (+0.002 R). Para demostrarla harían falta unas 1 600–3 700 operaciones.
- ❌ El win rate (69.4 %) **descarta el 75 % y el 80 %**. Corregido por la correlación entre operaciones del mismo día, el límite inferior baja a 63.4 %. Ninguna moneda por separado alcanza un límite inferior de 70 % (el más alto, 62 %).
- 📉 **El 81 % de diseño fue selección:** la salida, el umbral y el ensamble se eligieron mirando el walk-forward. En datos nuevos, la v2 da prácticamente lo mismo que la v1 (69.4 % frente a 68.7 %).

**Desglose de la prueba principal de la v2:**

| Por moneda | WR | E | | Por trimestre | WR | E |
|---|---|---|---|---|---|---|
| FIL | 73 % | +1.71 % | | 2025-T3 | 78 % | +0.73 % |
| NEAR | 71 % | +0.62 % | | 2025-T4 | 71 % | +1.24 % |
| ETC | 68 % | +0.48 % | | 2026-T1 | 63 % | −0.20 % |
| UNI | 67 % | +0.34 % | | 2026-T2 | 60 % | −0.72 % |
| ATOM | 69 % | +0.25 % | | 2026-T3 | 78 % | +0.56 % |
| DOT | 70 % | +0.16 % | | | | |
| TRX | 71 % | −0.16 % | | | | |
| BCH | 66 % | −0.25 % | | | | |

**Dónde está la ganancia:** los 10 días con más operaciones (pánicos que afectan a varias monedas a la vez) reúnen 168 de las 621 operaciones y tienen E +1.18 %. El resto de las operaciones tiene E ≈ 0. Las salidas fueron 68 % por TP, 19 % por SL y 13 % por tiempo, con una ganancia media de 2.61 % y una pérdida media de 4.88 %.

### 3.9 ¿Es factible el 70–80 % "sí o sí"?

**No, y ningún método honesto puede garantizarlo.** Esto es lo que dicen los dos intentos:

| Pregunta | Respuesta con los datos medidos |
|---|---|
| ¿Se puede **fabricar** un win rate de 70–80 %? | Sí, siempre: con $b \le 0.33$ hasta el azar acierta el 71 %. Pero la esperanza queda negativa (G4: WR 72 %, E −0.31 %). Es el engaño más común en los bots que prometen win rates altos. |
| ¿Se puede lograr **con ganancia**? | No se demostró. Con ventaja real, en monedas nunca vistas, el win rate fue **68.7 % y 69.4 %**, y la ganancia no fue significativa. |
| ¿Es alcanzable el 80 %? | No con esta información: los intervalos de confianza de las dos pruebas lo **descartan**. |
| ¿Qué win rate es realista? | **≈ 68–70 %** con $b \approx 0.4$–$0.55$, y ganancia positiva solo si el mercado no está en caída sostenida. |
| ¿Cuánto tardaría demostrarlo en vivo? | La ganancia: unas 1 600–3 700 operaciones (≈ 3–7 años con 8 monedas a la frecuencia observada). Un win rate ≥ 70 % con un valor real del 72 %: unas 2 000 operaciones. |

**Por qué el modelo se queda en ≈ 69 % y no sube:**

1. **La geometría pone casi todo el win rate.** Con $b = 0.4$–$0.55$, entrar al azar ya gana el 57–62 % de las veces. El modelo suma 9–17 puntos encima, y eso lo deja en ≈ 69 %.
2. **Para pasar del 70 % con ganancia** hay dos caminos. Subir el umbral da menos operaciones y más ruido: en la v2, el 81 % de diseño no se sostuvo. Achicar $b$ sube el win rate, pero la ventaja necesaria sobre el azar crece (fórmula 2 de [matematica-aplicativa.md](matematica-aplicativa.md)) y la esperanza se vuelve negativa.
3. **La ventaja es relativa, no absoluta.** El modelo elige bien **cuándo** comprar dentro de un mes, pero si todo el mercado cae, comprar en el mejor momento igual pierde. Un bot *spot*, que solo compra, no puede cubrirse de esa caída. Una cobertura con un corto en BTC probablemente se comería la ventaja, porque las capitulaciones afectan a todo el mercado a la vez y BTC también rebota. Esto no se probó.

**Qué haría falta para acercarse al 70–80 % con ganancia** (en orden de prioridad):

1. **Liquidaciones** (Coinalyze o grabar `!forceOrder@arr`, sección 1.3). El modelo ya compra capitulaciones, que son justamente cascadas de liquidaciones: medirlas directamente es la fuente más prometedora.
2. **Libro de órdenes** (`bookDepth`, sección 1.1): saber si queda liquidez compradora en la caída.
3. **Prueba prospectiva pre-registrada** con datos desde 2026-10, con tamaño de posición por riesgo y el criterio de ganancia (a), sin reajustar nada. Es la única forma de saber si la ventaja relativa se convierte en ganancia en un mercado que no esté en caída.
4. **No** agrandar la red (LSTM, Transformer) con las mismas variables: en los dos intentos, la red de secuencias fue la pieza más débil y la parada temprana cortó en las primeras épocas.

> **En una frase:** con machine learning y datos de futuros se consiguió algo real (entradas ≈ 10–17 puntos mejores que el azar), pero eso equivale a un win rate de ≈ 69 % y a una ganancia que depende del mercado. Un 70–80 % garantizado no existe; quien lo prometa, lo está fabricando con la geometría o con un backtest sobreajustado.

### 3.10 Cómo llevarlo al bot (si alguna versión aprueba)

Solo después de aplicar las soluciones S1–S7 de [matematica-aplicativa.md](matematica-aplicativa.md) y de que una versión del modelo apruebe su prueba:

**Python (`binance-research/`):**

- Crear `nn_strategy/` con `features.py` (las 74 variables y la regla de alineación, copiadas de `research/nn/nn_common.py`), `model.py` (carga los 6 modelos, aplica Platt y el umbral, y verifica los hashes SHA-256 de la especificación) y `models/` (los archivos congelados, 348 KB en total).
- En `strategy_engine.py`, registrar la estrategia con un búfer por moneda (y para BTC) de al menos 3 360 velas de 15 min **cerradas** (35 días) más las series de futuros. Devuelve `BUY` con TP, SL y `max_hold_bars = 192`.
- En `server.py`, recibir la vela cerrada completa (apertura, máximo, mínimo, cierre, volumen y volumen comprador) y cargar el historial al arrancar desde archivos, no con 100 velas de 1 min.

**Datos de futuros en vivo:** cada 5 minutos, consultar open interest, ratios long/short, *funding*, prima y velas de futuros, aplicando la regla $T \le t_i + 5$ min. Si falta un dato por más de 30 minutos, **no se opera** esa vela.

> ⚠️ **Bloqueo:** esos datos vienen de `fapi.binance.com`, que está **bloqueada desde tu ubicación** (HTTP 451). Para operar en vivo hace falta un servidor en una región permitida, o una fuente alternativa en tiempo real (por ejemplo, Coinalyze o el WebSocket de futuros, si es accesible).

**Node (`src/`):** suscribirse a `kline_15m` y enviar solo velas cerradas; entrar a mercado con OCO de TP y SL; cerrar a mercado a las 192 velas (48 h); y **dimensionar por riesgo**: con $R \approx 6\,\%$ del precio, arriesgar 0.5–1 % del capital equivale a un nocional del 8–16 %. Con el 100 % del capital por operación, el drawdown máximo de la prueba habría sido del 73 %.

**Reentrenamiento y monitoreo:**

- Reentrenar cada trimestre con la misma receta; congelar con hashes, correr 2–4 semanas en sombra y registrar la variante.
- **Cómputo medido en esta máquina:** entrenamiento final de los 6 modelos ≈ 1 minuto; predicción de una vela 1.2 ms; modelos de 348 KB; con PyTorch en CPU, ~300 MB de RAM (estimado).
- **Alertas:** frecuencia de señales fuera de la mitad o el doble de lo esperado en 3 meses; win rate real frente a $\hat p$ medio con diferencia de más de 10 puntos; deriva de las variables clave; y pasar a `HOLD` si, con 30 operaciones o más, la esperanza es negativa con $t < -2$ o el win rate cae por debajo de 55 %.

### 3.11 Cómo construirlo desde cero (resumen operativo)

1. **Entorno** en el disco E: `python -m venv binance-research/.venv`; antes de instalar, apuntar `PIP_CACHE_DIR`, `TMP` y `TEMP` a una carpeta de E; instalar `torch` (CPU), `lightgbm`, `numpy` y `scipy`.
2. **Datos:** `research/nn/nn_download_futures.py --symbols ... --start ... --end ... --out ...` y las velas spot con `research/scripts/download_klines.py`.
3. **Variables y etiquetas:** `research/nn/nn_build.py` (aplica la regla de alineación y la triple barrera).
4. **Walk-forward:** `research/nn/nn_wf.py` (entrenamiento trimestral, Platt y umbral solo con validación; registra cada configuración con `harness.log_trials`).
5. **Modelo final congelado:** `research/nn/nn_final.py` genera los modelos y `output/constructor/spec_nn.json` con los hashes.
6. **Evaluación:** `research/nn/nn_eval.py --symbols ... --start ... --end ... --data-dir ...`, siempre sobre datos que el diseño no tocó, y verificación con `research/verificador/verify.py`.
