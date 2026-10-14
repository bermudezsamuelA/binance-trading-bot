# Matemática aplicativa: qué mejorar en el bot y cómo aplicarlo

Este documento es el resultado del trabajo conjunto de tres agentes —**Analista Cuantitativo** (señales y filtrado), **Gestor de Riesgo** (tamaño de posición y salidas) y **Validador / Backtester** (evitar el sobreajuste)— que investigaron, durante tres rondas de discusión, cómo llevar el bot a un *win rate* de 70–80 % sin sacrificar la esperanza matemática. Está escrito para leerse y aplicarse tal cual: cada solución tiene su fórmula explicada, sus números medidos y los cambios exactos de código.

Complementa a [matematica-del-bot.md](matematica-del-bot.md), que explica la matemática que el bot usa **hoy**. Este documento explica la que **debería** usar y por qué.

---

## Respuesta corta

> **Un win rate de 70–80 % con esperanza positiva no es alcanzable con estas estrategias ni con estos datos.** Los tres agentes coinciden.

- Las estrategias actuales del bot **pierden dinero** después de costos en las 4 monedas, tanto en el periodo de diseño (2023-01 a 2025-06) como en el periodo reservado (2025-07 a 2026-09). Sus señales **aciertan lo mismo que entrar al azar**.
- Un win rate alto se puede fabricar con la geometría (take profit corto y stop loss largo), pero **sin ventaja la esperanza queda en −costos**. En velas de 1 h, entradas **al azar** con TP a 1 ATR y SL a 3 ATR ganan el 74.7 % de las veces y aun así pierden dinero.
- El equipo encontró un candidato serio (C1) con WR de 72 % y E > 0 en diseño. Se sometió a **una única prueba pre-registrada** en el periodo reservado y **fracasó**: WR 60.1 %, E −0.50 % por operación.
- **Win rate realista con E > 0: no determinado.** Ninguna estrategia mostró E > 0 fuera de muestra. Si algún día aparece una ventaja, la meta honesta es un WR de **55–60 % con b ≈ 1** (con $b = 1$, un 50 % siempre deja $E = -c$), no de 70–80 %.

Lo que **sí** se debe aplicar (secciones 2 y 3) no hace ganar dinero por sí mismo, pero hace que el bot **deje de perder por errores de implementación**, que el backtest diga la verdad y que cualquier estrategia futura pueda validarse sin engañarse:

| # | Solución consensuada | Qué arregla |
|---|---|---|
| S1 | Velas cerradas de 15 min, ventana continua y monedas sincronizadas | En vivo, el bot mide una volatilidad 13–16 veces menor que la del backtest |
| S2 | Redondeo por `tickSize` y `stepSize` | El 59.6 % de las señales de DOGE quedan inválidas por `round(x, 2)` |
| S3 | Backtest honesto (reemplaza a `optimize.py`) | El backtest actual inventa ganancias (paga 2R siempre, sin costos, solo cierres) |
| S4 | Protocolo de validación anti-sobreajuste | Hoy se elige la mejor de ~1 200 configuraciones con un solo mes de datos |
| S5 | Gestión de riesgo (tamaño, topes, interruptores) | Hoy el tamaño es fijo y no hay ningún freno ante una racha mala |
| S6 | Ejecución verificable en el exchange (OCO, llenado, barrera de tiempo) | Hoy el stop solo existe en la memoria de Node y la venta no se confirma |
| S7 | Dinero real en cero y motor en `HOLD` hasta validar | Hoy el motor carga estrategias con esperanza negativa |

---

## Tabla de contenido

- [Respuesta corta](#respuesta-corta)
- [0. Cómo se hizo y cómo reproducirlo](#0-cómo-se-hizo-y-cómo-reproducirlo)
- [1. Diagnóstico de la estrategia actual](#1-diagnóstico-de-la-estrategia-actual)
  - [1.1 Lo publicado frente a lo real](#11-lo-publicado-frente-a-lo-real)
  - [1.2 Los defectos que explican la diferencia](#12-los-defectos-que-explican-la-diferencia)
  - [1.3 Las señales no tienen información](#13-las-señales-no-tienen-información)
  - [1.4 La matemática del win rate: por qué 70–80 % no sale gratis](#14-la-matemática-del-win-rate-por-qué-7080--no-sale-gratis)
  - [1.5 Lo que se probó para alcanzar el objetivo](#15-lo-que-se-probó-para-alcanzar-el-objetivo)
- [2. Soluciones consensuadas](#2-soluciones-consensuadas)
  - [S1. Los datos en vivo deben ser los mismos que los del backtest](#s1-los-datos-en-vivo-deben-ser-los-mismos-que-los-del-backtest)
  - [S2. Redondeo por tickSize y stepSize](#s2-redondeo-por-ticksize-y-stepsize)
  - [S3. Backtest honesto](#s3-backtest-honesto)
  - [S4. Protocolo de validación anti-sobreajuste](#s4-protocolo-de-validación-anti-sobreajuste)
  - [S5. Gestión de riesgo](#s5-gestión-de-riesgo)
  - [S6. Ejecución verificable en el exchange](#s6-ejecución-verificable-en-el-exchange)
  - [S7. Dinero real en cero y motor en HOLD hasta validar](#s7-dinero-real-en-cero-y-motor-en-hold-hasta-validar)
- [3. Cambios concretos en el código](#3-cambios-concretos-en-el-código)
- [4. Tabla comparativa: antes frente a después](#4-tabla-comparativa-antes-frente-a-después)
- [5. Riesgos y limitaciones](#5-riesgos-y-limitaciones)
- [6. Lo que se probó y se rechazó (no repetir)](#6-lo-que-se-probó-y-se-rechazó-no-repetir)
- [7. Líneas abiertas para una validación futura](#7-líneas-abiertas-para-una-validación-futura)

---

## 0. Cómo se hizo y cómo reproducirlo

**Datos.** Velas *spot* de 15 minutos de BTCUSDT, ETHUSDT, SOLUSDT y DOGEUSDT del 2023-01-01 al 2026-09-30 (131 419 velas por moneda), descargadas de `data.binance.vision`. Para medir el desfase en vivo se usaron además 14 días de velas de 1 segundo (2025-06-02 a 2025-06-15).

**Particiones fijas para todo el equipo.**

| Partición | Periodo | Uso |
|---|---|---|
| Diseño | 2023-01-01 a 2025-06-30 | Toda la investigación, búsquedas y ajustes |
| Holdout (reservado) | 2025-07-01 a 2026-09-30 | Solo pruebas pre-registradas, ejecutadas por el Validador |

**Reglas de simulación** (las mismas para los tres agentes, verificadas entre sí):

- Entrada al cierre de la vela que da la señal (entrar a la apertura siguiente cambia E en ≤ 0.01 pp).
- TP y SL evaluados con el máximo y el mínimo de las velas siguientes. Si en la misma vela se tocan los dos, cuenta como **SL**. Si el precio abre por debajo del SL (hueco), se sale a la apertura.
- Costos: 0.10 % de comisión + 0.02 % de deslizamiento **por lado**, es decir, $c = 0.24\,\%$ ida y vuelta, con una prueba de estrés a 0.30 %.
- Solo compras (*spot*). Una posición por moneda a la vez.

**Volumen del trabajo.**

| Agente | Configuraciones registradas | Consultas al holdout |
|---|---|---|
| Analista | 1 372 | 0 |
| Gestor de Riesgo | 7 189 (incluye 294 controles aleatorios) | 1 (solo para evaluar el paquete de riesgo, después del veredicto) |
| Validador | 3 707 | 3 (configuración vigente del bot, reproducción de `ml_results.json` y la prueba única de C1) |
| **Total** | **≈ 12 300** | — |

El número total de configuraciones importa: con 12 300 pruebas, alguna sale "ganadora" por puro azar. Por eso la sección S4 corrige por comparaciones múltiples.

**Dónde está todo.** Los datos, los scripts y los informes de cada ronda están en `binance-research/data/research/` (carpeta ignorada por git):

| Ruta | Contenido |
|---|---|
| `klines/` | Velas en formato `.npy` (columnas: `open_time_ms, open, high, low, close, volume, taker_buy_base_volume`) |
| `scripts/harness.py`, `scripts/HARNESS.md`, `scripts/test_harness.py` | El arnés de backtest honesto, su API y sus 46 pruebas |
| `scripts/bot_replica.py`, `scripts/reproduce_ml_results.py` | Réplica exacta del bot y del optimizador actuales |
| `scripts/C1_eval.py`, `scripts/C1_eval_v2.py`, `scripts/holdout_C1_run.py` | Evaluación congelada del candidato C1 |
| `output/analista/`, `output/riesgo/`, `output/validador/` | Informes de las rondas 1, 2 y 3 de cada agente |
| `output/validador/trials_log.csv` | Registro de todas las configuraciones probadas |
| `output/validador/holdout_log.csv` | Registro de cada acceso al periodo reservado |

Para volver a ejecutar las pruebas del arnés:

```bash
cd binance-research/data/research/scripts
PYTHONIOENCODING=utf-8 python -I test_harness.py
```

---

## 1. Diagnóstico de la estrategia actual

### 1.1 Lo publicado frente a lo real

`ml_results.json` dice que el bot gana con todas las monedas. Al reevaluar exactamente las mismas configuraciones con una simulación honesta, el cuadro cambia por completo.

**El mes que usó el propio optimizador (septiembre de 2026):**

| Moneda | Estrategia cargada | WR publicado | WR honesto |
|---|---|---|---|
| BTCUSDT | MeanReversion (8, 1.4) | 58.8 % | 50.0 % |
| ETHUSDT | MeanReversion (20, 2.0) | 61.3 % | 56.2 % |
| SOLUSDT | MeanReversion (88, 0.8) | 64.3 % | 52.8 % |
| DOGEUSDT | TrendFollowing (24, 0.8) | **94.7 %** | **3.6 %** |

**Los dos periodos completos, estrategia limpia** (ventana continua, sin el error de redondeo, con costos, high/low y el *b* real de cada estrategia). La columna del holdout excluye septiembre de 2026, el mes con el que se optimizó el propio bot:

| Configuración | Diseño: n, WR [IC 95 %], E neta | Holdout 2025-07 a 2026-08: n, WR, E neta |
|---|---|---|
| BTC MR(8, 1.4) | 1 489, 50.8 % [48.3, 53.4], −0.214 % | 660, 49.7 %, −0.259 % |
| ETH MR(20, 2.0) | 1 395, 48.5 % [45.8, 51.1], −0.229 % | 687, 48.8 %, −0.287 % |
| SOL MR(88, 0.8) | 1 273, 49.1 % [46.4, 51.8], −0.201 % | 484, 49.0 %, −0.312 % |
| DOGE TF(24, 0.8) | 2 697, 31.8 % [30.1, 33.6], −0.274 % | 1 374, 31.0 %, −0.306 % |
| **Cartera de las 4** | 6 854, 42.5 %, −0.238 % | 3 205, 41.4 % [39.7, 43.1], −0.293 %, PF 0.62 |

**El bot tal como funciona** (ventana congelada mientras hay posición y redondeo a 2 decimales) es todavía peor en ese mismo holdout: 1 569 operaciones, **WR 7.1 %**, E −0.374 %, PF 0.40. El WR se hunde porque casi todas las operaciones de DOGE quedan inválidas (sección 1.2).

> **Conclusión del diagnóstico.** Ninguna de las cuatro configuraciones del bot tiene esperanza positiva significativa en ningún periodo. Con la simulación limpia, las cuatro son negativas en los dos periodos. La única esperanza puntual positiva (SOL con el bot tal como funciona, en diseño: +0.56 %, $p = 0.11$) viene del artefacto de la ventana congelada. Los resultados publicados son producto de los defectos que se explican a continuación.

### 1.2 Los defectos que explican la diferencia

| # | Defecto | Dónde | Efecto medido |
|---|---|---|---|
| D1 | El backtest paga siempre $+2R$ al ganar, aunque MeanReversion tiene $b = 1$ y el squeeze $b = 2.5$ | `optimize.py` | Duplica el *profit factor* de MeanReversion |
| D2 | El backtest solo mira cierres (no máximos ni mínimos) y no descuenta costos | `optimize.py` | Con costos de 0.24 %, el umbral de equilibrio $p^{*}$ sube a 57–67 % |
| D3 | Se optimiza con **un solo mes** (2 880 velas) eligiendo entre **1 196** configuraciones por moneda (son 13 valores de *k*, no 12) | `ml_evaluator.py` | Sobreajuste: PBO de hasta 0.51 y pendiente fuera/dentro de muestra negativa en las 4 monedas (tabla abajo) |
| D4 | `round(tp, 2)` y `round(sl, 2)` en todas las estrategias | `quantitative_strategies/*.py` | En DOGE (0.056–0.48 USDT en el periodo; 0.078–0.105 en septiembre de 2026), el TP queda igual o por debajo de la entrada. En la réplica del optimizador, 68 de 73 operaciones de TrendFollowing tenían el TP redondeado por debajo de la entrada o igual a ella, y 66 se contaron como ganadas (+2R) sin moverse el precio. Explica el 94.7 %. |
| D5 | En vivo, la ventana se alimenta con **fotos de la vela de 1 min en curso cada ~6 s**, no con velas de 15 min | `ws-client.ts` (`kline_1m`, filtro de 5 s) | La ventana cubre 48 s–9 min en lugar de 2–22 h; σ en vivo es 0.064–0.078 veces la del backtest |
| D6 | La ventana se **congela** mientras hay posición abierta | `ws-client.ts` (`return` en `handleMarketData`) | Tras un TP, el siguiente stop queda en una media vieja y R se triplica en cada racha |
| D7 | Tamaño fijo de 15 USDT, sin filtro de costos | `evaluateNewTrade` | ≈ 80 USDT/año perdidos en costos en MeanReversion; ≈ 400 USDT en 14 días en DOGE en vivo |
| D8 | El SL solo existe en la memoria de Node; las órdenes son límite GTC y no se confirma su llenado; el precio se redondea con `toFixed(2)` | `ws-client.ts`, `rest-client.ts` | Si Node se cae, la posición queda sin stop; la venta de cierre puede no ejecutarse y aun así la posición se borra |
| D9 | La ventana se precarga con velas del mercado **real** (`api.binance.com`) pero en vivo recibe precios de **testnet**, que es otro libro de órdenes | `server.py` (`pre_seed_engine`) y `ws-client.ts` | Mezcla dos series de precios distintas en la misma ventana. Además, `api.binance.com` está bloqueada desde la ubicación de esta máquina |

**El sobreajuste del procedimiento actual (D3)**, medido sobre las 897 configuraciones MR/TF/SQ de cada moneda en diseño:

| Moneda | PBO | P(la mejor en muestra pierde fuera) | Pendiente fuera ~ dentro | Walk-forward mes a mes (como el bot) |
|---|---|---|---|---|
| BTC | 0.05 | 0.45 | −0.89 | E −0.042 % |
| ETH | 0.36 | 0.94 | −1.08 | E −0.125 % |
| SOL | 0.13 | 0.40 | −1.17 | E −0.175 % |
| DOGE | 0.51 | 0.96 | −0.81 | E −0.279 % |

Una pendiente negativa significa que **cuanto mejor sale una configuración en el mes de optimización, peor tiende a salir el mes siguiente**: el optimizador elige ruido.

**El desfase en vivo (D5, D9)**, medido replicando exactamente lo que hace Node sobre 14 días de velas de 1 s:

| Moneda | Operaciones en 14 días | Resultado |
|---|---|---|
| BTC | 0 | El filtro del 0.5 % bloquea todo, porque la volatilidad medida es diminuta |
| ETH | 15 | WR 46.7 %, E −0.52 % |
| SOL | 29 | E −0.27 % |
| DOGE | 11 125, de las cuales **11 116 inválidas** por el redondeo | 799 operaciones por día, cada una con E −0.24 % (pura comisión) |

### 1.3 Las señales no tienen información

Si una señal no sabe nada del futuro, su tasa de acierto es la que fija la geometría TP/SL. Es lo que se observa:

| Familia | WR medido en diseño | WR que da la geometría sola, $1/(1+b)$ |
|---|---|---|
| MeanReversion ($b \approx 1$) | 46–54 % | ≈ 50 % |
| TrendFollowing ($b \approx 2$) | 31–40 % | ≈ 33 % |
| Squeeze ($b \approx 2.5$) | 28–35 % | ≈ 29 % |

Y frente a entradas al azar con la misma moneda, el mismo mes, el mismo R y la misma geometría, la señal de MeanReversion cambia la probabilidad de acierto en apenas $\Delta p \in [-1.1, +3.0]$ puntos y la esperanza en $\Delta E \approx 0$.

De 41 variables candidatas a filtro (régimen por razón de varianzas, autocorrelación, vida media de Ornstein-Uhlenbeck, profundidad del z-score, tendencia de 4 h, RSI, hora del día, volumen, desequilibrio de compradores, volatilidad relativa, etc.), **ninguna** llevó la esperanza a terreno positivo al replicarse en la segunda mitad del diseño. Las que sí replicaron una subida del acierto en las dos mitades (razón de varianzas de 16 velas, pendiente de la media de 4 h, volatilidad de 24 h y retorno de 7 días: entre +4.5 y +7.1 puntos) dejaron la esperanza por unidad de riesgo todavía negativa (de −0.06 a −0.12 R). Las que más prometían en la primera mitad **se invirtieron o se desvanecieron** en la segunda: el RSI pasó de +7.8 a −3.0 puntos de acierto, el volumen relativo de +2.9 a −5.4 y el retorno de 4 h de +10.0 a +0.2.

### 1.4 La matemática del win rate: por qué 70–80 % no sale gratis

Esta es la clave de todo el documento. Hay tres fórmulas.

#### Fórmula 1 — Sin ventaja, la geometría solo mueve el punto sobre una curva fija

Si el precio no tiene tendencia predecible (una *martingala*), la probabilidad de tocar primero el TP depende solo de las distancias:

$$
P(\text{TP primero}) = \frac{m}{a + m} = \frac{1}{1 + b},
\qquad b = \frac{a}{m}
$$

$$
E = p \cdot a - (1 - p)\cdot m - c = \frac{1}{1+b}\cdot a - \frac{b}{1+b}\cdot m - c = -c
$$

**Qué es cada símbolo:**

- $a$: distancia de la entrada al take profit (lo que se gana).
- $m$: distancia de la entrada al stop loss (lo que se pierde, es decir, $R$).
- $b$: cociente recompensa/riesgo.
- $p$: probabilidad de acertar (win rate).
- $c$: costos de ida y vuelta.
- $E$: esperanza por operación.

> **Qué calcula:** cuánto se gana en promedio cuando las entradas no tienen ninguna ventaja.
>
> **Ejemplo:** con TP a 1 y SL a 3 ($b = 1/3$), el precio toca primero el TP el $3/4 = 75\,\%$ de las veces. Pero $0.75 \times 1 - 0.25 \times 3 = 0$: el win rate de 75 % no gana nada, y con costos pierde $c$. Medido en diseño:
>
> - En velas de 1 h, entradas **al azar** con TP a 1 ATR, SL a 3 ATR y barrera de 96 velas ganan el **74.7 %** de las veces ($E = -0.09\,R$). La señal MeanReversion(48, 2) con la misma salida gana el 73.2 %. Las dos pierden dinero.
> - En velas de 15 min, con la misma geometría, las entradas al azar tocan primero el TP el 73.9 % de las veces (la teoría dice 75 %), pero como el TP es pequeño frente a los costos, el WR **neto** cae a 62.8 % y $E = -0.24\,\%$ por operación.

**Paso a paso:**

1. Achicar el TP y agrandar el SL ($b$ pequeño) sube el win rate, pero en la misma proporción en que agranda cada pérdida.
2. Mientras la señal no tenga información, $p(1 + b) = 1$ y la esperanza bruta es exactamente cero.
3. Los costos se pagan siempre, ganes o pierdas, así que la esperanza neta es $-c$.
4. Por eso **el win rate por sí solo no dice nada**: lo que importa es si la señal supera a la geometría.

#### Fórmula 2 — La ventaja mínima que hace falta sobre el azar

Para que la esperanza sea positiva con costos, el win rate debe superar:

$$
p^{*} = \frac{1 + c/R}{1 + b}
\qquad\Longrightarrow\qquad
\Delta p_{\min} = p^{*} - \frac{1}{1+b} = \frac{c}{R\,(1 + b)}
$$

**Qué es cada símbolo:**

- $p^{*}$: win rate mínimo para no perder dinero.
- $R$: riesgo por operación, como fracción del precio.
- $c / R$: qué parte del riesgo se va en costos.
- $\Delta p_{\min}$: cuántos puntos debe acertar la señal **por encima del azar**.

> **Qué calcula:** cuánto mejor que el azar tiene que ser una señal para que valga la pena.
>
> **Ejemplo:** con $b = 0.5$, $c = 0.24\,\%$ y $R = 2\,\%$: $p^{*} = (1 + 0.12)/1.5 = 74.7\,\%$ y la señal debe acertar $\Delta p = 0.0024/(0.02 \times 1.5) = 8$ puntos más que el azar. Con $R = 1\,\%$, $p^{*} = 82.7\,\%$. Las señales del bot logran entre −1.5 y +6 puntos.

#### Fórmula 3 — El riesgo mínimo, como múltiplo de los costos

Despejando $R$ de $E > 0$:

$$
\frac{E}{R} = p\,(1 + b) - 1 - \frac{c}{R} > 0
\qquad\Longrightarrow\qquad
\frac{R}{c} > \frac{1}{p\,(1+b) - 1}
$$

> **Qué calcula:** cuán grande debe ser la operación, comparada con los costos, para que un win rate dado deje ganancia.
>
> **Ejemplo:**
>
> | $p$ \ $b$ | 1/3 | 0.43 | 0.50 | 0.75 | 1.0 |
> |---|---|---|---|---|---|
> | 0.70 | ∞ | 1 000 | 20 | 4.4 | 2.5 |
> | 0.75 | ∞ | 13.8 | 8 | 3.2 | 2.0 |
> | 0.80 | 15 | 6.9 | 5 | 2.5 | 1.7 |
>
> Con WR 75 % y $b = 0.5$ hace falta $R \ge 8c = 1.92\,\%$, y eso **suponiendo** que la señal realmente logra el 75 % con esa geometría. El ATR de 15 min mediano es 0.27 % en BTC, 0.35 % en ETH, 0.60 % en SOL y 0.53 % en DOGE: **los costos equivalen a casi un ATR de BTC**.

**Paso a paso de la conclusión:**

1. Un WR de 70–80 % con E > 0 exige a la vez un $b$ pequeño (≈ 0.3–0.5), un riesgo grande ($R \ge 5$–$20\,c$, e infinito si $b \le 1/3$ y $p \le 0.75$) y una ventaja sobre el azar de ≈ 8 puntos o más.
2. La ventaja bruta medida en las señales va de ≈ 0 a +0.08 R. Lo necesario es superar $c/R$: entre 0.11 y 0.56 R en las geometrías de 15 min medidas (0.125 R en el ejemplo de WR 75 %, $b = 0.5$ y $R = 8c$).
3. Ninguna señal medida, ni dentro ni fuera de muestra, alcanza esa ventaja de forma sostenida.

### 1.5 Lo que se probó para alcanzar el objetivo

| Intento | Resultado en diseño | Resultado fuera de muestra | Veredicto |
|---|---|---|---|
| 3 447 combinaciones de entrada y salida en 15 min (TP/SL en ATR, salida en la media, trailing, toma parcial, barreras de tiempo) | **0** con $E_R > 0$; una sola con E en % > 0 (+0.022 %, sin significancia) | — | Rechazado |
| 3 447 combinaciones en 1 h | 45 con $E_R > 0$ en mercado alcista: 44 rupturas de 4 días y 1 de 2 días; la mejor con t mensual 2.05 (Bonferroni exige 4.18) | Walk-forward: 3 de 6 pliegues positivos | Rechazado |
| 41 filtros de señal, uno por uno | Ninguno con E > 0 al replicarse | — | Rechazado |
| Meta-etiquetado con regresión logística (45 columnas) | AUC fuera de muestra 0.52–0.55; decil superior WR 70 % pero $E_R = -0.03$ | — | Rechazado |
| **C1**: MeanReversion20 filtrada por un modelo ridge (sección 6) | WR 72.4 %, E +0.54 %, 5/6 pliegues; sin fugas; placebo 0/20 | **Holdout: WR 60.1 %, E −0.50 %** | **Rechazado** en la prueba única pre-registrada |

---

## 2. Soluciones consensuadas

Cada solución fue aceptada por los tres agentes según la regla de la mesa: el **Analista** confirma que no empeora la calidad de las señales, el **Gestor de Riesgo** que la esperanza no se sacrifica y el capital sobrevive, y el **Validador** que no introduce sobreajuste. Ninguna de estas soluciones **crea** una ventaja: quitan los errores que hoy hacen perder dinero y que harían imposible detectar una ventaja real.

---

### S1. Los datos en vivo deben ser los mismos que los del backtest

**Problema que resuelve.** D5, D6 y D9: en vivo, el bot mide una volatilidad que no tiene nada que ver con la del backtest, congela la ventana mientras opera y mezcla precios de dos mercados distintos.

**Fórmula que la sustenta.** Para un precio que se mueve al azar, la volatilidad crece con la raíz del tiempo, así que la escala de la ventana cambia con el intervalo entre muestras:

$$
\frac{\sigma_{\text{vivo}}}{\sigma_{\text{backtest}}} \approx \sqrt{\frac{\Delta t_{\text{vivo}}}{\Delta t_{\text{backtest}}}}
\qquad\qquad
\text{tiempo cubierto} = n \times \Delta t
$$

**Qué es cada símbolo:**

- $\Delta t_{\text{vivo}}$: tiempo entre dos muestras que entran a la ventana en vivo (hoy, ~6 s).
- $\Delta t_{\text{backtest}}$: tiempo entre dos velas del backtest (15 min = 900 s).
- $n$: tamaño de la ventana.

> **Qué calcula:** cuánto más pequeña es la volatilidad que ve el bot en vivo comparada con la que se optimizó.
>
> **Ejemplo:** $\sqrt{6/900} = 0.082$, es decir, unas 12 veces menos en teoría. Medido con velas de 1 s: entre 0.064 y 0.078, es decir, **13–16 veces menos**. Con $n = 20$, la ventana cubre 2 minutos en vivo y 5 horas en el backtest. Las bandas en vivo son 13–16 veces más estrechas que las optimizadas.

**Paso a paso de la solución:**

1. Node se suscribe a `kline_15m` en lugar de `kline_1m` y solo reenvía a Python las velas **cerradas** (campo `k.x === true`).
2. Python recibe **todas** las velas cerradas, haya o no una posición abierta. La ventana nunca se congela.
3. Las 4 monedas se sincronizan por `open_time`: Python evalúa un instante solo cuando tiene la vela cerrada de las 4 (las estrategias futuras pueden usar variables que cruzan monedas). Si falta una a los 60 s, ese instante se omite.
4. La precarga y la ejecución usan **el mismo mercado**. Mientras el bot opere en testnet, la historia se pide al REST de testnet (`/api/v3/klines` en `testnet.binance.vision`), no a `api.binance.com`. Con dinero real, ambos vienen del mercado real. Ojo: una esperanza medida con precios de testnet **solo valida la infraestructura**; la calidad de una señal se mide siempre con velas del mercado real.
5. Historial mínimo de 900 velas antes de evaluar cualquier señal.

**Cómo contribuyó cada agente.**

- **Validador:** midió el desfase replicando exactamente a Node con 14 días de velas de 1 s, y lo declaró condición obligatoria: sin esto, ningún resultado del backtest se traslada al bot.
- **Analista:** añadió la sincronización de las 4 monedas, el historial mínimo y el límite de latencia. Con una vela de retraso, la esperanza de C1 cayó ~30 % en diseño (G3H96: de +0.54 % a +0.37 %; T48: de +0.73 % a +0.52 %; medido por el Validador).
- **Gestor de Riesgo:** mostró que, con la escala de vivo, $c/R$ explota y el umbral $p^{*}$ llega a 150 %, es decir, es imposible ganar.

**Votos:** Analista **acepta** · Gestor **acepta** · Validador **acepta**.

---

### S2. Redondeo por tickSize y stepSize

**Problema que resuelve.** D4 y parte de D8: `round(x, 2)` en Python y `toFixed(2)` en Node destruyen los precios de monedas baratas.

**Fórmula que la sustenta.**

$$
TP' = \left\lfloor \frac{TP}{\text{tick}} \right\rfloor \cdot \text{tick},
\qquad
SL' = \left\lceil \frac{SL}{\text{tick}} \right\rceil \cdot \text{tick},
\qquad
q' = \left\lfloor \frac{q}{\text{step}} \right\rfloor \cdot \text{step}
$$

$$
\text{válida solo si}\quad TP' \ge P + \text{tick}
\quad\text{y}\quad SL' \le P - \text{tick}
$$

**Qué es cada símbolo:**

- $\text{tick}$: `tickSize` del filtro `PRICE_FILTER` del símbolo (el menor cambio de precio permitido).
- $\text{step}$: `stepSize` del filtro `LOT_SIZE` (el menor cambio de cantidad permitido).
- $\lfloor\cdot\rfloor$, $\lceil\cdot\rceil$: redondear hacia abajo y hacia arriba.
- $P$: precio de entrada.

> **Qué calcula:** el TP, el SL y la cantidad más cercanos que Binance acepta, siempre del lado conservador (TP un poco más bajo y SL un poco más cerca), y descarta la señal si el redondeo la vuelve absurda.
>
> **Ejemplo:** DOGE a 0.09000 con TP en 0.09150. Hoy: `round(0.0915, 2) = 0.09`, es decir, TP = entrada y la operación "gana" en el siguiente tick. Con $\text{tick} = 0.00001$: $TP' = 0.09150$, correcto.

**Paso a paso:**

1. Al arrancar, Node pide `GET /api/v3/exchangeInfo` y guarda, por símbolo, `tickSize`, `stepSize`, `minQty` y `minNotional`.
2. Python deja de redondear: devuelve TP y SL en precisión completa.
3. Node redondea con las fórmulas de arriba, comprueba que la operación siga siendo válida y formatea el número con los decimales del `tick` (nunca con `toFixed(2)`).

**Cómo contribuyó cada agente.** Los tres llegaron por su lado al mismo artefacto:

- **Gestor de Riesgo:** midió que el 59.6 % de las señales de DOGE en diseño quedan con TP ≤ entrada o SL ≥ entrada, y extendió el problema a Node (`toFixed(2)` en `placeLimitOrder`) y a la cantidad (`stepSize` en lugar de los decimales fijos 5 y 3).
- **Analista:** replicó el backtest original en los 30 meses de diseño. Con redondeo: 3 295 operaciones y un WR mensual que salta entre 10 % y 80 %. Sin redondeo: 585 operaciones con WR 38.6 %.
- **Validador:** en la réplica del optimizador, 68 de 73 operaciones de septiembre tenían el TP redondeado por debajo de la entrada, y 66 se contaron como ganadas.

**Votos:** Analista **acepta** · Gestor **acepta** · Validador **acepta**.

---

### S3. Backtest honesto

**Problema que resuelve.** D1, D2 y D3: el backtest actual no puede distinguir una estrategia ganadora de una perdedora.

**Fórmulas que la sustentan.**

**(a) Retorno neto de una operación**, con costos por lado $s$:

$$
r_{\text{neto}} = \left(\frac{x}{e} - 1\right) - s\left(1 + \frac{x}{e}\right),
\qquad s = 0.0012
$$

**Qué es cada símbolo:**

- $e$: precio de entrada.
- $x$: precio de salida.
- $s$: costo por lado (0.10 % de comisión + 0.02 % de deslizamiento).

> **Ejemplo:** entrada 100, salida 101: $r = 0.01 - 0.0012 \times 2.01 = 0.759\,\%$. Una operación que sube 0.2 % **pierde** dinero: $0.002 - 0.0012 \times 2.002 = -0.04\,\%$.

**(b) Intervalo de confianza de Wilson** para el win rate (más fiable que $\hat p \pm 1.96\sqrt{\hat p(1-\hat p)/n}$ cuando $\hat p$ está lejos de 50 %):

$$
\text{IC} = \frac{\hat p + \frac{z^2}{2n} \pm z\sqrt{\frac{\hat p(1-\hat p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}},
\qquad z = 1.96
$$

> **Ejemplo:** 338 aciertos en 467 operaciones ($\hat p = 72.4\,\%$): IC 95 % = [68.2 %, 76.2 %]. Afirmar "WR ≥ 70 %" exige que el **límite inferior** pase de 70 %, y aquí no pasa.

**(c) t agrupado por día.** Las operaciones de un mismo día no son independientes (las 4 monedas suelen moverse juntas). Se suman los retornos de cada día y se calcula el error estándar con esas sumas:

$$
t_{\text{día}} = \frac{\bar r}{\text{EE}_{\text{día}}},
\qquad
\text{EE}_{\text{día}} = \frac{1}{n}\sqrt{\frac{G}{G-1}\sum_{g=1}^{G}\Big(\sum_{i \in g} (r_i - \bar r)\Big)^2}
$$

**Qué es cada símbolo:**

- $\bar r$: retorno medio por operación.
- $G$: número de días con operaciones; $g$: cada día.
- $\sum_{i \in g}$: suma sobre las operaciones del día $g$.

> **Qué calcula:** si la esperanza es distinta de cero teniendo en cuenta que las pérdidas llegan juntas.
>
> **Ejemplo:** C1 con salida G3H96 en diseño tenía $t$ por operación 2.67 ($p = 0.004$) y $t_{\text{día}} = 2.22$: la dependencia entre operaciones del mismo día reduce la evidencia ~17 %. Con la salida T48, de 3.27 a 2.27 (~31 %).

**(d) Comparación contra el azar.** Toda señal se compara con entradas aleatorias de la misma moneda, el mismo mes, el mismo $R$ y la misma geometría. La métrica que importa es $\Delta E = E_{\text{señal}} - E_{\text{azar}}$, no el win rate.

**Reglas del backtest nuevo** (todas implementadas y probadas en `harness.py`):

1. Datos: **todos** los meses desde 2023-01, concatenados (no `m15_files[-1]`).
2. Entrada al cierre de la vela cerrada de la señal.
3. TP/SL con high/low; empate en la misma vela = SL; hueco bajo el SL = salida a la apertura.
4. Barrera de tiempo opcional; una posición por moneda; redondeo por `tickSize`.
5. La ventana sigue recibiendo velas aunque haya posición abierta.
6. Se paga el $b$ real de cada operación (no un $+2R$ fijo).
7. Costos de 0.24 % ida y vuelta, con estrés a 0.30 %.
8. Métricas obligatorias: $n$, WR con IC de Wilson, $b$ efectivo, E neta (en % y en R) y E bruta, *profit factor*, máximo drawdown (en % y en R), racha perdedora máxima, $t_{\text{día}}$, IC por bootstrap y $\Delta E$ frente al azar.
9. Cada configuración probada se anota en `trials_log.csv`; cada acceso al periodo reservado, en `holdout_log.csv` con su motivo.

**Cómo contribuyó cada agente.** El **Validador** escribió el arnés (`harness.py`), sus 46 pruebas sintéticas y una réplica exacta del optimizador actual, que reprodujo 15 de 16 entradas de `ml_results.json`. El **Analista** verificó que su simulador coincide exactamente con el arnés en 8 casos. El **Gestor** lo contrastó con el suyo: 2 446 operaciones en ambos y E de −0.2412 % frente a −0.2414 %.

**Votos:** Analista **acepta** · Gestor **acepta** · Validador **acepta**.

---

### S4. Protocolo de validación anti-sobreajuste

**Problema que resuelve.** D3: elegir la mejor de miles de configuraciones garantiza encontrar algo que parece ganar. El caso C1 lo demostró: buen resultado en diseño, fracaso fuera de muestra.

**Fórmulas que la sustentan.**

**(a) Deflated Sharpe Ratio (DSR).** Corrige el Sharpe observado por el número de configuraciones probadas y por la forma de la distribución:

$$
\text{DSR} = \Phi\!\left(\frac{(\widehat{SR} - SR_0)\sqrt{T - 1}}{\sqrt{1 - \hat\gamma_3\,\widehat{SR} + \frac{\hat\gamma_4 - 1}{4}\,\widehat{SR}^2}}\right),
\qquad
SR_0 = \sqrt{V[\widehat{SR}_k]}\,\Big[(1-\gamma)\,\Phi^{-1}\!\big(1 - \tfrac{1}{N}\big) + \gamma\,\Phi^{-1}\!\big(1 - \tfrac{1}{N e}\big)\Big]
$$

**Qué es cada símbolo:**

- $\widehat{SR}$: Sharpe observado de la configuración elegida (por operación o por periodo).
- $T$: número de observaciones.
- $\hat\gamma_3$, $\hat\gamma_4$: asimetría y curtosis de los retornos.
- $N$: número de configuraciones probadas; $V[\widehat{SR}_k]$: varianza de sus Sharpe.
- $SR_0$: el Sharpe que se esperaría obtener **por azar** como máximo de $N$ pruebas.
- $\gamma \approx 0.5772$ (constante de Euler-Mascheroni); $e \approx 2.718$; $\Phi$: normal acumulada.

> **Qué calcula:** la probabilidad de que el Sharpe observado sea real después de descontar la suerte de haber probado $N$ configuraciones. Se exige $\text{DSR} \ge 0.95$.
>
> **Ejemplo:** C1 con salida G3H96 tenía DSR = 0.62 contando solo su familia ($N = 56$) y **0.13** contando todas las pruebas del equipo ($N = 12\,268$). Un DSR bajo no predice un fracaso: indica que la evidencia de diseño **no supera** la corrección por pruebas múltiples, y por eso C1 no podía aceptarse sin una prueba fuera de muestra (que después falló).

**(b) Probabilidad de sobreajuste del backtest (PBO) con CSCV.** Se parte la historia en $S$ bloques, se forman todas las combinaciones de mitades "dentro" y "fuera", y en cada una se mira qué lugar ocupa fuera de muestra la configuración que salió mejor dentro:

$$
\text{PBO} = P\big(\text{rango fuera de muestra del mejor de dentro} < \text{mediana}\big)
$$

> **Qué calcula:** qué tan seguido la "mejor" configuración es, en realidad, de las peores fuera de muestra. Se exige $\text{PBO} \le 0.2$. El optimizador actual llega a 0.51 en DOGE (tabla de la sección 1.2).

**(c) Muestra mínima.** Para que la esperanza sea significativa con potencia del 80 %:

$$
n_{\min} = \left(\frac{(z_{1-\alpha} + z_{0.8})\,\sigma}{\mu}\right)^2 \cdot \text{DEFF}
$$

**Qué es cada símbolo:**

- $\mu$: esperanza por operación que se quiere detectar. Por la "maldición del ganador", se usa **la mitad** de la medida en diseño.
- $\sigma$: desviación estándar del retorno por operación.
- $z_{1-\alpha} = 1.645$ (unilateral, α = 0.05); $z_{0.8} = 0.84$.
- $\text{DEFF}$: factor de diseño por operaciones simultáneas correlacionadas (1.45–2.07 medido).

> **Ejemplo:** con $\sigma = 4.4\,\%$, $\mu = 0.27\,\%$ y $\text{DEFF} = 1.45$: $n_{\min} = (2.485 \times 16.3)^2 \times 1.45 \approx 2\,400$ operaciones. A ~120–280 operaciones por año, eso son **años** de prueba.

**Muestra mínima para afirmar un win rate** (que el límite inferior de Wilson supere el umbral):

| WR observado | Para afirmar WR ≥ 70 % hacen falta | Con corrección por 100 pruebas |
|---|---|---|
| 72 % | 2 017 operaciones | 5 685 |
| 75 % | 323 | 910 |
| 80 % | 81 | 228 |

**(d) Procedimiento de Holm** para probar varias hipótesis sin inflar el error. Se ordenan los p-valores $p_{(1)} \le p_{(2)} \le \dots \le p_{(K)}$ y se rechaza $H_{(j)}$ mientras $p_{(j)} \le \alpha/(K - j + 1)$. Con dos hipótesis: la de menor $p$ debe pasar $0.025$ y la otra $0.05$.

**(e) Revisiones intermedias (gasto de α de O'Brien-Fleming).** En una prueba prospectiva que se revisa cada cierto número de operaciones, el α se gasta así:

$$
\alpha(t) = 2\left[1 - \Phi\!\left(\frac{z_{1-\alpha/2}}{\sqrt{t}}\right)\right],
\qquad t = \frac{\text{operaciones acumuladas}}{n_{\min}}
$$

> **Ejemplo:** con α = 0.05, al 25 % de la muestra solo se gasta α = 0.00009; al 50 %, 0.0056; al 75 %, 0.0236; al 100 %, 0.05. Las primeras revisiones casi nunca aprueban: evitan detener la prueba por una buena racha inicial.

**El protocolo completo**, obligatorio para cualquier estrategia nueva:

1. **Pre-registro** antes de mirar resultados: especificación completa, hashes SHA-256 de los archivos de código, hipótesis y umbrales de aprobación.
2. **Diseño** (datos hasta 2026-09-30), con walk-forward de 12 meses de entrenamiento y 3 de prueba, avanzando de 3 en 3, con un embargo de al menos la duración máxima de una operación. Se aprueba si, en el resultado fuera de muestra concatenado:
   - E > 0 en al menos 4 de 6 pliegues;
   - E > 0 con costos de 0.30 % y con 1 vela de retraso;
   - $\Delta E > 0$ frente a entradas al azar emparejadas;
   - $\text{DSR} \ge 0.95$, con $N$ igual a **todas** las configuraciones registradas de esa línea de investigación;
   - $\text{PBO} \le 0.2$, o $P(\text{la elegida pierde fuera de muestra}) \le 0.1$.
3. **Prueba prospectiva en testnet** con datos posteriores a 2026-10-01 (el holdout 2025-07 a 2026-09 **ya está gastado**):
   - $H_0$: E ≤ 0. Estadístico: $t_{\text{día}}$ unilateral, α = 0.05.
   - Muestra: $n = \max(200,\ n_{\min})$.
   - Revisiones cada 100 operaciones con gasto de α de O'Brien-Fleming.
   - Futilidad: si tras 200 operaciones $t_{\text{día}} < 0$, se rechaza.
   - Afirmar un WR ≥ 70 % solo si el límite inferior de Wilson ≥ 0.70.
4. **Dinero real** solo si aprueba el paso 3: se empieza con $w = 0.05$ (sección S5).

**Cómo contribuyó cada agente.**

- **Validador:** diseñó el protocolo, calculó PBO y DSR, auditó C1 con una reimplementación independiente (1 567 de 1 567 señales idénticas) y un placebo con etiquetas permutadas (0 de 20 corridas igualaron al real), y ejecutó él solo la única prueba en el holdout.
- **Analista:** auditó las fugas de información de C1 (truncamiento en 25 cortes y "envenenamiento" del futuro), congeló la especificación con hashes y aceptó el rechazo sin reajustar nada.
- **Gestor:** aportó la lección clave del holdout: **los umbrales se calibran con la esperanza desplazada a cero**, nunca con la E de diseño, que está inflada por la selección.

**Votos:** Analista **acepta** · Gestor **acepta** · Validador **acepta**.

---

### S5. Gestión de riesgo

**Problema que resuelve.** D7: tamaño fijo sin relación con el riesgo, sin filtro de costos y sin ningún freno ante una racha mala o ante pérdidas simultáneas en las 4 monedas.

**Fórmulas que la sustentan.**

**(a) Pérdida y ganancia por unidad, incluyendo costos:**

$$
\text{lossU} = (P - SL) + s\,(P + SL),
\qquad
\text{gainU} = (TP - P) - s\,(P + TP)
$$

Si la estrategia no tiene SL, $\text{lossU} = Q_0 \cdot P$, con $Q_0$ la pérdida de cola declarada por la estrategia (por defecto 0.15). Si $\text{gainU} \le 0$, no se opera: el TP no cubre los costos.

**(b) Cola de cada posición y tamaño:**

$$
Q_i = \max\!\left(\frac{\text{lossU}_i}{P_i} + 0.02,\ 0.15\right)
$$

$$
w_i = \min\!\left(0.10,\ \frac{F_{\text{RISK}}}{\text{lossU}_i/P_i},\ 0.40 - \sum_{j\ \text{abiertas}} w_j,\ \frac{0.06 - \sum_j w_j\,Q_j}{Q_i}\right),
\qquad
\text{si } w_i < 0.01 \text{ no se opera}
$$

$$
q_i = \left\lfloor \frac{\min(w_i \cdot \text{capital},\ 0.99 \cdot \text{USDT libre})}{P_i\,(1 + s)\,\text{step}} \right\rfloor \cdot \text{step},
\qquad q_i \ge \text{minQty},\quad q_i P_i \ge \text{minNotional}
$$

Si no hay SL, $Q_i = \max(Q_0,\ 0.15)$ sin el margen de 0.02 (la cola declarada ya lo incluye). Si $SL \ge P$, la señal se descarta.

**Qué es cada símbolo:**

- $w_i$: fracción del capital invertida (nocional) en la operación $i$.
- $F_{\text{RISK}}$: fracción del capital que se acepta perder si se toca el SL (1.5 % por defecto).
- $Q_i$: pérdida de cola de la posición; el $+0.02$ cubre huecos bajo el stop y el piso de 0.15 protege contra estrategias de stop lejano.
- $0.10$: tope por operación; $0.40$: tope de nocional total; $0.06$: tope de **riesgo de cola total** (la pérdida si todas las posiciones abiertas tocaran su cola a la vez).
- $\text{capital}$: USDT libres + valor de mercado de las posiciones abiertas.

> **Qué calcula:** cuánto comprar para que ninguna operación, ni todas juntas, puedan hundir la cuenta.
>
> **Ejemplo:** capital 1 000 USDT, entrada 2 400, SL 2 304 (4 % abajo). $\text{lossU}/P = 0.04 + 0.0012 \times 1.96 \approx 4.24\,\%$; $F_{\text{RISK}}/(\text{lossU}/P) = 0.015/0.0424 = 0.35$; $Q = \max(0.062, 0.15) = 0.15$. Sin posiciones abiertas, $w = \min(0.10,\ 0.35,\ 0.40,\ 0.06/0.15 = 0.40) = 0.10$: se invierten 100 USDT, y tocar el SL cuesta ≈ 4.2 USDT (0.42 % del capital). Si ya hay 3 posiciones abiertas de $w = 0.10$ y $Q = 0.15$ (4.5 % de cola) y llega una entrada con el SL un 23 % por debajo ($Q \approx 0.25$), recibe $w = \min(0.10,\ 0.065,\ 0.10,\ 0.015/0.25 = 0.06) = 0.06$: el tope de cola recorta la posición más arriesgada.

**(c) Por qué no se usa Kelly con la esperanza de diseño.** El criterio de Kelly maximiza el crecimiento logarítmico:

$$
f^{*} = p - \frac{1 - p}{b},
\qquad
g(f) = \mathbb{E}\big[\ln(1 + f\,X)\big]
$$

pero con la esperanza de diseño (inflada por la selección) el Kelly completo arruinaba entre el 31 % y el 55 % de los años simulados. Con la esperanza corregida por comparaciones múltiples, $f^{*} = 0$. Con la cota inferior del 95 % sin corregir, ¼ de Kelly daba $w = 0.20$–$0.34$ para C1, y el holdout demostró que esa esperanza estaba inflada. Por eso el tamaño queda fijado por topes, no por Kelly.

**(d) Diversificación real entre las 4 monedas.** Las monedas se mueven juntas (correlación de retornos ≈ 0.70; entre operaciones abiertas a la vez, 0.30–0.54):

$$
N_{\text{ef}} = \frac{N}{1 + (N - 1)\,\rho}
$$

> **Ejemplo:** $N = 4$, $\rho = 0.4$: $N_{\text{ef}} = 4/2.2 = 1.8$. Cuatro posiciones valen menos que dos apuestas independientes. Por eso el tope importante es el **total** (nocional ≤ 40 %, cola ≤ 6 %), no el de cada moneda.

No se reduce el tamaño según el número de posiciones abiertas: en diseño, reducirlo con $f/(1 + 0.4k)$ bajaba la esperanza por nocional (T48: de 0.73 % a 0.61 %; G3H96: de 0.40 % a 0.35 %) y el retorno del peor 5 % de los años; el drawdown empeoraba en T48 (percentil 95 de 6.3 % a 7.5 %) y mejoraba poco en G3H96 (de 9.3 % a 8.5 %). El tope total ya acota la pérdida correlacionada.

**(e) Probabilidad de una racha de $L$ pérdidas en un año** (aproximación de la cadena de Markov exacta usada por el Gestor):

$$
P(\text{racha} \ge L) \approx 1 - \exp\!\big(-n_{\text{año}}\cdot p\cdot(1-p)^{L}\big)
$$

> **Ejemplo:** WR 72.4 %, 267 operaciones al año, $L = 8$: $(0.276)^8 = 3.4 \times 10^{-5}$; $267 \times 0.724 \times 3.4 \times 10^{-5} = 0.0065$; $P \approx 0.65\,\%$. Una racha de 8 pérdidas con ese WR es tan improbable que justifica detener el bot.

**(f) CUSUM: detectar que la ventaja desapareció.** A partir de 30 operaciones:

$$
\text{detener si}\quad \sum_{i=1}^{n} r_i < n\,E_{\text{lcb}} - 2\,\sigma\sqrt{n}
$$

**Qué es cada símbolo:**

- $r_i$: retorno neto de cada operación.
- $E_{\text{lcb}}$: cota inferior del 95 % de la esperanza (bootstrap semanal, costos de 0.30 %).
- $\sigma$: desviación estándar del retorno por operación.

> **Ejemplo:** aplicado a C1-G3H96 en el holdout, el CUSUM la habría detenido en la **operación 34** (2025-10-17), con el capital en −4.33 % en lugar de −7.42 %. *Ilustrativo:* esta cifra, la del interruptor 5 (T48 con $t = 0.13$) y la diferencia de 0.1 pp entre los topes de 6 % y 10 % salen de una consulta al holdout hecha **después** del veredicto; el holdout está gastado y no valida estos parámetros.

**Interruptores por defecto** (se recalibran para cada estrategia validada con su Monte Carlo, **desplazando la esperanza a cero**):

| # | Interruptor | Umbral por defecto | Acción |
|---|---|---|---|
| 1 | Caída desde el máximo de capital | ≥ 10 % | Detener y revisar |
| 2 | Pérdida del día UTC (abiertas + cerradas) | ≥ 5 % | Sin entradas nuevas durante 24 h |
| 3 | Racha de pérdidas | ≥ $L$ con $P < 1\,\%$ al año (por defecto 8) | Detener |
| 4 | CUSUM (desde 30 operaciones) | Fórmula (f) | Detener |
| 5 | Revisión a las 150 operaciones | $t_{\text{día}} < 1$ | Detener (con esto, T48 de C1 se habría detenido con $t = 0.13$) |
| 6 | Fallos operativos | Deslizamiento > 0.10 % por lado en 50 operaciones; datos con más de 2 velas de atraso; modelo sin reajustar en más de 35 días | Detener |

**Recalibración por estrategia:** caída = 1.2 × percentil 99 del drawdown simulado; pérdida diaria = 1.25 × el peor día; $L$ con la fórmula (e); CUSUM con su $E_{\text{lcb}}$ y su $\sigma$. El tope de cola de 6 % solo puede subirse (por ejemplo, a 10 %) con un Monte Carlo de esa estrategia ya validada, hecho con operaciones fuera de muestra o prospectivas, y exigiendo $P(\text{MDD} > 20\,\%) \le 5\,\%$.

**Dinero real.** $w = 0$ hasta que una estrategia pase el protocolo S4 completo y acumule al menos 200 operaciones en testnet con E > 0 sin disparar el CUSUM. Después se empieza con $w = 0.05$ y nunca más de $0.25$ o ¼ del Kelly calculado con la esperanza en su cota inferior.

**Cómo contribuyó cada agente.**

- **Gestor de Riesgo:** propuso las fórmulas de tamaño, los topes, los interruptores y su calibración. Retiró su propio candidato (ruptura de 1 h) al no pasar el protocolo. Aceptó el tope de 6 % después de comprobar que en el holdout la diferencia con 10 % fue de 0.1 pp.
- **Analista:** retiró su propuesta de reducir el tamaño por correlación, $f/(1 + 0.4k)$, cuando el Gestor midió que empeoraba la esperanza.
- **Validador:** añadió el piso $Q_i \ge 0.15$ (la peor operación de C1-G3H96 perdió 19.8 % al tocar un SL profundo, aunque ninguna de las 467 perforó su SL por un hueco) y exigió que la recalibración use datos fuera de muestra.

**Votos:** Analista **acepta** · Gestor **acepta** · Validador **acepta**.

---

### S6. Ejecución verificable en el exchange

**Problema que resuelve.** D8: hoy el stop vive solo en la memoria de Node, la compra se registra sin saber si se llenó, la venta de cierre es una orden límite que puede quedar sin ejecutar y no existe la salida por tiempo.

**Fórmula que la sustenta.** La esperanza medida en el backtest solo se traslada al bot si la ejecución reproduce el simulador. La **prueba de paridad** lo comprueba con cualquier estrategia y tamaño mínimo, durante al menos 2 semanas o 50 operaciones:

| Paridad | Qué se compara | Umbral |
|---|---|---|
| Datos | Velas recibidas frente a las del REST del mismo mercado (testnet o real) | 100 % idénticas; 0 velas faltantes |
| Señales | Señales en vivo frente a las simuladas sobre las mismas velas (índice de Jaccard) | = 1.0 |
| Ejecución | Precio de llenado frente al cierre de la vela; latencia | Deslizamiento medio ≤ 0.02 % por lado; latencia mediana ≤ 5 s. Si se supera, se actualizan los costos del simulador |
| Salidas | Motivo y vela de salida, operación por operación | ≥ 95 % coinciden; diferencias de precio ≤ 1 tick + deslizamiento |
| PnL | Vivo − simulado por operación | Media con $\lvert t \rvert < 2$ |

$$
J = \frac{\lvert S_{\text{vivo}} \cap S_{\text{sim}} \rvert}{\lvert S_{\text{vivo}} \cup S_{\text{sim}} \rvert}
$$

**Qué es cada símbolo:** $S_{\text{vivo}}$ y $S_{\text{sim}}$ son los conjuntos de pares (moneda, vela) en los que hubo señal en vivo y en el simulador. $J = 1$ significa que coinciden exactamente.

**Paso a paso de la ejecución nueva:**

1. **Entrada a mercado** (`type=MARKET`, `newOrderRespType=FULL`) al recibir la señal, en menos de 60 s desde el cierre de la vela. Se usan `executedQty` y el precio medio de llenado (`cummulativeQuoteQty / executedQty`) para registrar la posición y recalcular TP y SL relativos al precio real.
2. **OCO en el exchange** justo después del llenado: rama superior `LIMIT_MAKER` en el TP y rama inferior `STOP_LOSS` (o `STOP_LOSS_LIMIT` con el límite 2 % por debajo del disparo). Si la estrategia no tiene SL, se coloca un stop de catástrofe en $P\,(1 - \max(Q_0,\ 1.2 \times \text{peor excursión adversa de diseño}))$.
3. **Barrera de tiempo** guardada en el registro de operaciones (`time_stop_ts`), para que sobreviva a reinicios. Al vencer: se cancela la OCO y se vende a mercado.
4. **Vigilancia:** Node consulta el estado de la OCO en cada vela cerrada (o escucha el *user data stream*) y registra la salida real (precio, motivo, PnL neto). Solo si el exchange no acepta OCO, Node vigila TP y SL con la misma regla que el simulador.

**Cómo contribuyó cada agente.** El **Gestor** propuso OCO, `executedQty`, el stop de catástrofe y la barrera de tiempo persistente. El **Validador**, la prueba de paridad y sus umbrales. El **Analista**, el límite de latencia de 60 s (con una vela de retraso, la E de C1-G3H96 cae de +0.54 % a +0.37 % en diseño, medido por el Validador).

**Votos:** Analista **acepta** · Gestor **acepta** · Validador **acepta**.

---

### S7. Dinero real en cero y motor en HOLD hasta validar

**Problema que resuelve.** Hoy `strategy_engine.py` carga, para cada moneda, la estrategia de mayor PnL en `ml_results.json`, y las cuatro tienen esperanza negativa.

**Fórmula que la sustenta.** Con la esperanza en su cota inferior, la fracción óptima es cero:

$$
E_{\text{lcb}} \le 0 \quad\Longrightarrow\quad f^{*}_{\text{Kelly}} = 0
$$

Y operar una estrategia de esperanza $-c$ con $n$ operaciones al año cuesta, en promedio, $n \cdot c \cdot \text{nocional}$: con las ~2 300 operaciones anuales de MeanReversion a 15 USDT, ≈ 80 USDT al año.

**Paso a paso:**

1. `ml_results.json` se reemplaza por un **registro de estrategias** con, para cada una: especificación pre-registrada, hashes, estado (`rechazada`, `paridad`, `prospectiva`, `validada`) y fecha.
2. El motor solo genera señales de estrategias en estado `validada` (dinero real) o `prospectiva`/`paridad` (solo testnet, con tamaño mínimo). Para todo lo demás devuelve `HOLD`.
3. Hoy, **todas** las estrategias quedan en `rechazada`. Para correr la prueba de paridad (S6) se puede activar cualquiera en estado `paridad`, con $w$ igual al mínimo que acepta Binance.

**Votos:** Analista **acepta** · Gestor **acepta** · Validador **acepta**.

---

## 3. Cambios concretos en el código

Los cambios se listan en el orden en que deben aplicarse. Cada uno indica el archivo, la función y el código propuesto. Los fragmentos son implementaciones de referencia: deben adaptarse a las firmas exactas del proyecto y verificarse contra la documentación vigente de la API de Binance Spot (especialmente OCO, que tiene un endpoint nuevo y uno antiguo).

### 3.1 Python: estrategias como funciones puras, sin redondeo

**Archivos:** todo `binance-research/quantitative_strategies/`.

1. Quitar `round(tp, 2)` y `round(sl, 2)` (líneas 49–50 de `mean_reversion.py`, 57–58 de `rolling_volatility.py`, 62–63 de `volatility_squeeze.py`, 55–56 de `vwap_strategy.py`, 72–74 de `statistical_arbitrage.py`). El redondeo pasa a Node (S2).
2. Reemplazar las clases con estado (`price_history`, `pop(0)`) por funciones puras que reciben las velas cerradas como arreglos y solo miran datos hasta el índice actual. El backtest y el motor en vivo llaman al **mismo** código:

```python
# binance-research/strategies/base.py
from dataclasses import dataclass
import numpy as np

@dataclass
class Bars:
    """Velas cerradas de 15m de una moneda, ordenadas y sin huecos."""
    open_time: np.ndarray   # ms
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    taker_buy: np.ndarray

@dataclass
class Signal:
    symbol: str
    bar_open_time: int      # vela que generó la señal
    take_profit: float | None
    stop_loss: float | None
    time_stop_bars: int     # barrera de tiempo, en velas de 15m
    tail_q: float = 0.15    # Q0: pérdida de cola declarada si no hay SL

def mean_reversion(bars: Bars, i: int, n: int, k: float) -> Signal | None:
    """Ejemplo de función pura: solo usa bars[..i]."""
    if i < max(n, 900):
        return None
    w = bars.close[i - n + 1 : i + 1]
    mu, sd = w.mean(), w.std(ddof=1)
    c = bars.close[i]
    if sd == 0 or c >= mu - k * sd:
        return None
    r = mu - c
    if r < 0.005 * c:            # riesgo mínimo del 0.5 %, como en todas las mediciones
        return None
    return Signal(symbol="", bar_open_time=int(bars.open_time[i]),
                  take_profit=mu, stop_loss=c - r, time_stop_bars=96)
```

### 3.2 Python: motor con registro de estrategias

**Archivo:** `binance-research/strategy_engine.py`.

1. Eliminar `load_best_strategies` (el argmax de PnL de un mes).
2. Leer un registro nuevo `binance-research/strategy_registry.json`:

```json
{
  "MR20_k2": {
    "estado": "rechazada",
    "spec": "doc/especificaciones/MR20_k2.json",
    "sha256": {"strategies/mean_reversion.py": "<hash>"},
    "monedas": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"],
    "fecha": "2026-10-14",
    "motivo": "E neta < 0 en diseño y holdout (matematica-aplicativa.md, 1.1)"
  }
}
```

3. `get_signals(bars_by_symbol, open_time)` recorre solo las estrategias en estado `validada` (o `prospectiva`/`paridad` si la variable de entorno `BOT_MODE=testnet`), verifica los hashes al arrancar y devuelve una lista de `Signal`. Si ninguna aplica, devuelve una lista vacía (equivale a `HOLD`).

### 3.3 Python: servidor con velas cerradas y registro ampliado

**Archivo:** `binance-research/server.py`.

1. **Nuevo mensaje ZMQ `bars`:** Node envía, para un mismo `open_time`, las velas cerradas de las 4 monedas. El servidor las añade a arreglos por moneda y llama al motor. Cuánta historia se conserva lo declara la especificación de cada estrategia (nunca menos de 900 velas); las estrategias con estadísticos acumulados o que se reentrenan necesitan **toda** la historia desde 2023-01, que se guarda en disco y se completa por REST si hay huecos. Se elimina el mensaje `evaluate` con fotos de la vela en curso.
2. **`pre_seed_engine`:** pedir **velas de 15m cerradas** (al menos 900) al REST **del mismo mercado en que se opera**: `https://testnet.binance.vision/api/v3/klines` en testnet. No usar `api.binance.com` mientras se opere en testnet (D9). Descartar la última vela si `close_time > ahora`.
3. **Registro de operaciones (`orders/trades.csv`):** añadir las columnas `strategy_id`, `spec_hash`, `entry_fill_price`, `executed_qty`, `oco_order_list_id`, `time_stop_ts`, `w`, `q_tail`, `loss_per_unit`, `exit_price`, `exit_reason` (`TP`, `SL`, `TIEMPO`, `MANUAL`, `INTERRUPTOR`), `pnl_neto_usdt` y `pnl_neto_pct`. `ledger_close` debe recibir y guardar el precio y el motivo de salida reales.
4. **Registro de interruptores:** guardar el estado de los interruptores (máximo de capital, pérdida del día, racha, suma CUSUM, contador de operaciones) en `orders/risk_state.json`, para que sobreviva a reinicios.

### 3.4 Node: filtros del exchange y redondeo

**Archivo nuevo:** `src/api/exchange-filters.ts`.

```typescript
export interface SymbolFilters {
    tickSize: number;
    stepSize: number;
    minQty: number;
    minNotional: number;
}

// Decimales de un paso: 0.00001 -> 5, 1 -> 0.
export const decimalsOf = (step: number): number =>
    Math.max(0, Math.round(-Math.log10(step)));

export const floorTo = (x: number, step: number): number =>
    Math.floor(x / step + 1e-9) * step;

export const ceilTo = (x: number, step: number): number =>
    Math.ceil(x / step - 1e-9) * step;

export const fmt = (x: number, step: number): string =>
    x.toFixed(decimalsOf(step));

export function parseFilters(symbolInfo: any): SymbolFilters {
    const f = (type: string) => symbolInfo.filters.find((x: any) => x.filterType === type);
    const price = f('PRICE_FILTER');
    const lot = f('LOT_SIZE');
    const notional = f('NOTIONAL') ?? f('MIN_NOTIONAL');
    return {
        tickSize: parseFloat(price.tickSize),
        stepSize: parseFloat(lot.stepSize),
        minQty: parseFloat(lot.minQty),
        minNotional: parseFloat(notional?.minNotional ?? '0'),
    };
}
```

**En `rest-client.ts`:** añadir `getExchangeInfo(symbols)` (`GET /v3/exchangeInfo?symbols=[...]`), y cambiar `placeLimitOrder` para recibir el precio ya formateado como texto (eliminar `price.toFixed(2)` de la línea 45).

### 3.5 Node: órdenes a mercado, OCO y consulta de estado

**Archivo:** `src/api/rest-client.ts`. Mantener el patrón actual de firma (`sign`) y añadir:

```typescript
// Compra o venta a mercado; devuelve executedQty y el precio medio de llenado.
public async placeMarketOrder(symbol: string, side: 'BUY' | 'SELL', quantity: string) {
    const params = [
        `symbol=${symbol}`, `side=${side}`, `type=MARKET`,
        `quantity=${quantity}`, `newOrderRespType=FULL`, `timestamp=${Date.now()}`,
    ].join('&');
    const url = `${this.baseUrl}/v3/order?${params}&signature=${this.sign(params)}`;
    const { data } = await axios.post(url, null, { headers: { 'X-MBX-APIKEY': this.apiKey } });
    const qty = parseFloat(data.executedQty);
    const avg = qty > 0 ? parseFloat(data.cummulativeQuoteQty) / qty : NaN;
    return { orderId: data.orderId, executedQty: qty, avgPrice: avg, raw: data };
}

// OCO de venta: TP arriba (LIMIT_MAKER) y SL abajo (STOP_LOSS, stop a mercado).
// Verificar en la documentación vigente de Binance Spot: endpoint nuevo /v3/orderList/oco
// (parámetros above*/below*); el antiguo /v3/order/oco está en desuso.
// Solo si el exchange no acepta STOP_LOSS en la rama inferior, usar STOP_LOSS_LIMIT con
// belowPrice = 2 % por debajo de belowStopPrice y belowTimeInForce=GTC, y que Node vigile
// (si el precio cae por debajo del límite sin llenarse, vender a mercado).
public async placeSellOco(symbol: string, quantity: string, tp: string, stopTrigger: string) {
    const params = [
        `symbol=${symbol}`, `side=SELL`, `quantity=${quantity}`,
        `aboveType=LIMIT_MAKER`, `abovePrice=${tp}`,
        `belowType=STOP_LOSS`, `belowStopPrice=${stopTrigger}`,
        `timestamp=${Date.now()}`,
    ].join('&');
    const url = `${this.baseUrl}/v3/orderList/oco?${params}&signature=${this.sign(params)}`;
    const { data } = await axios.post(url, null, { headers: { 'X-MBX-APIKEY': this.apiKey } });
    return data; // contiene orderListId
}

public async getOrderList(orderListId: number) { /* GET /v3/orderList?orderListId=... */ }
public async cancelOrderList(symbol: string, orderListId: number) { /* DELETE /v3/orderList */ }
```

### 3.6 Node: velas cerradas, sincronización y alimentación continua

**Archivo:** `src/api/ws-client.ts`.

1. Línea 25: `@kline_1m` → `@kline_15m`.
2. Reescribir `handleMarketData` (líneas 50–75): ignorar las velas no cerradas, acumular las cerradas por `open_time` y enviarlas a Python cuando estén las 4 monedas. Eliminar el filtro de 5 s (líneas 68–74) y el `return` que congela la ventana cuando hay posición (líneas 63–66):

```typescript
private pending: Map<number, Map<string, any>> = new Map();

private async handleMarketData(data: any) {
    const k = data.k;
    if (!k.x) return;                                  // solo velas cerradas
    // Las posiciones de ESTA moneda se revisan con cada vela cerrada propia,
    // aunque la sincronización de las 4 falle (OCO y barrera de tiempo).
    await this.checkOpenPosition(data.s, k);
    const bar = {
        open_time: k.t, open: +k.o, high: +k.h, low: +k.l,
        close: +k.c, volume: +k.v, taker_buy: +k.V,
    };
    const slot = this.pending.get(k.t) ?? new Map();
    slot.set(data.s, bar);
    this.pending.set(k.t, slot);
    if (slot.size === this.roster.length) {
        this.pending.delete(k.t);
        await this.onClosedBars(k.t, Object.fromEntries(slot));
    } else if (slot.size === 1) {
        // Si falta alguna moneda a los 60 s, se omite el instante para todas.
        setTimeout(() => this.pending.delete(k.t), 60_000);
    }
}

private async onClosedBars(openTime: number, bars: Record<string, any>) {
    if (this.risk.blocked()) return;                   // interruptores (sección 3.8)
    const signals = await brain.ask('bars', { open_time: openTime, bars });
    for (const s of signals ?? []) {
        if (!this.activePositions.has(s.symbol)) await this.openPosition(s);
    }
}
```

3. Guardar el `roster` en la clase (hoy solo se usa en el constructor).

### 3.7 Node: apertura con tamaño por riesgo y cierre confirmado

**Archivo nuevo:** `src/risk/sizing.ts`.

```typescript
const S = 0.0012;           // costo por lado (comisión + deslizamiento)
const W_MAX = 0.10;         // nocional máximo por operación
const NOT_TOT = 0.40;       // nocional total máximo
const TAIL_TOT = 0.06;      // riesgo de cola total máximo
const F_RISK = 0.015;       // pérdida aceptada al tocar el SL (fracción del capital)

export function positionSize(p: {
    price: number; tp: number | null; sl: number | null; tailQ0: number;
    capital: number; usdtFree: number;
    open: { w: number; q: number }[];
    filters: SymbolFilters;
}): { qty: number; w: number; q: number } | null {
    const P = p.price;
    if (p.sl !== null && p.sl >= P) return null;                          // SL inválido
    const lossU = p.sl !== null ? (P - p.sl) + S * (P + p.sl) : p.tailQ0 * P;
    if (p.tp !== null && (p.tp - P) - S * (P + p.tp) <= 0) return null;   // TP no cubre costos
    // Con SL: cola = distancia al SL + margen por hueco. Sin SL: la cola declarada Q0.
    const Q = p.sl !== null ? Math.max(lossU / P + 0.02, 0.15) : Math.max(p.tailQ0, 0.15);
    const sumW = p.open.reduce((a, o) => a + o.w, 0);
    const sumTail = p.open.reduce((a, o) => a + o.w * o.q, 0);
    const w = Math.min(W_MAX, F_RISK * P / lossU, NOT_TOT - sumW, (TAIL_TOT - sumTail) / Q);
    if (w < 0.01) return null;
    const budget = Math.min(w * p.capital, 0.99 * p.usdtFree);
    const qty = floorTo(budget / (P * (1 + S)), p.filters.stepSize);
    if (qty < p.filters.minQty || qty * P < p.filters.minNotional) return null;
    return { qty, w: qty * P / p.capital, q: Q };   // w real, por si el USDT libre recortó el monto
}
```

**En `ws-client.ts`, reemplazar `evaluateNewTrade` (líneas 90–158) por `openPosition(signal)`:**

1. Calcular el tamaño con `positionSize` (si devuelve `null`, no operar).
2. Comprar a mercado con `placeMarketOrder`; si `executedQty = 0`, no registrar nada.
3. Recalcular TP y SL **relativos al precio real de llenado** (manteniendo las distancias de la señal) y redondearlos con `floorTo`/`ceilTo` según S2; si quedan inválidos, vender a mercado y registrar `exit_reason = INVALIDA`.
4. Colocar la OCO de venta con `executedQty` y guardar `orderListId`.
5. Calcular `time_stop_ts = open_time + (time_stop_bars + 1) · 900 000`.
6. Registrar en el ledger con todas las columnas nuevas y notificar por Telegram.

**Reemplazar `manageExistingPosition` y `closePosition` (líneas 77–88 y 160–189) por `checkOpenPosition(symbol, kline)`:** en cada vela cerrada de **cada** moneda, si esa moneda tiene posición:

1. Consultar la OCO (`getOrderList`). Si una rama se ejecutó, registrar la salida real (precio, motivo, PnL neto) y liberar la moneda.
2. Si `Date.now() >= time_stop_ts`, cancelar la OCO y vender a mercado; motivo `TIEMPO`.
3. Actualizar el estado de los interruptores con el PnL neto.

### 3.8 Node: interruptores

**Archivo nuevo:** `src/risk/kill-switches.ts`. Mantiene el máximo de capital, la pérdida del día UTC, la racha de pérdidas, la suma CUSUM y el número de operaciones, y expone `blocked()`. Implementa la tabla de interruptores de S5 con los umbrales por defecto, leídos de la especificación de cada estrategia cuando se recalibren. Cada disparo se notifica por Telegram y se guarda en `orders/risk_state.json` (vía un nuevo mensaje ZMQ `risk_state`).

### 3.9 Backtest: reemplazar optimize.py y ml_evaluator.py

1. Crear `binance-research/backtest/` a partir de `binance-research/data/research/scripts/harness.py`: carga y particiones (`load`, `bounds`, `walk_forward`), indicadores causales, simulación (`simulate`, `resolve_exit`), estadística (`metrics`, `wilson`, `bootstrap`, `deflated_sharpe`, `pbo_cscv`) y registros (`log_trials`, `log_holdout`). Copiar también `test_harness.py` con sus 46 pruebas.
2. Las estrategias del backtest son las mismas funciones de `strategies/` (3.1).
3. `download_data.py` sigue descargando, pero la carga debe **concatenar todos los CSV** desde 2023-01 (como ya hace `analyze_data.py`), no quedarse con `m15_files[-1]`.
4. Marcar `optimize.py` y `ml_evaluator.py` como obsoletos y dejar de llamarlos al arrancar `server.py`. El arranque ya no reoptimiza nada: solo carga el registro (3.2).
5. XGBoost (`xgboost_classifier.py`) no se usa: dejarlo fuera del arranque.

### 3.10 Pruebas de aceptación de la implementación

| Prueba | Cómo | Criterio |
|---|---|---|
| Arnés | `python test_harness.py` | 46/46 |
| Paridad de estrategias | La función pura en vivo y en el backtest, sobre las mismas velas | Mismas señales, índice a índice |
| Redondeo | TP/SL/cantidad de DOGE, BTC, ETH y SOL con sus filtros reales | Ninguna operación con $TP' \le P$ o $SL' \ge P$ |
| Tamaño | Casos sintéticos de `positionSize` (sin posiciones, con 4 abiertas, SL lejano, TP que no cubre costos) | Los resultados del ejemplo de S5 |
| Paridad en testnet | 2 semanas o 50 operaciones con una estrategia en estado `paridad` | Tabla de S6 |

---

## 4. Tabla comparativa: antes frente a después

"Después" significa con las soluciones S1–S7 aplicadas. Las cifras de "después" con las estrategias actuales son medidas (backtest honesto); las demás son estimaciones directas de la mecánica.

| Métrica | Antes (bot actual) | Después (soluciones aplicadas) |
|---|---|---|
| Win rate publicado | 58.8 / 61.3 / 64.3 / **94.7 %** | El que mida el backtest honesto (coincide con el vivo por la paridad) |
| Win rate real de la cartera, holdout 2025-07 a 2026-08 | 7.1 % (con los artefactos) | 41.4 % si se siguieran operando las señales actuales; **no se operan** (motor en `HOLD`) |
| Esperanza por operación, holdout 2025-07 a 2026-08 | −0.374 % | −0.293 % con las señales actuales; **0 operaciones** con el motor en `HOLD` |
| Operaciones inválidas de DOGE en 14 días | 11 116 de 11 125 | 0 |
| Costos en comisiones | ≈ 400 USDT en 14 días (DOGE en vivo) y ≈ 80 USDT/año (MeanReversion) | 0 hasta tener una estrategia validada |
| Tiempo que cubre la ventana en vivo | 48 s – 9 min | 2 h – 22 h, igual que el backtest |
| Volatilidad en vivo frente al backtest | 0.064–0.078 veces | 1 vez (misma escala) |
| Datos de la ventana | Mezcla del mercado real (precarga) y de testnet (vivo) | Un solo mercado |
| Stop si Node se cae | Ninguno (solo en memoria) | OCO en el exchange |
| Confirmación de llenado | Ninguna | `executedQty` y precio medio |
| Salida por tiempo | No existe | Barrera persistente en el registro |
| Tamaño por operación | 15 USDT fijos | Por riesgo, con topes de 10 % por operación, 40 % total y 6 % de cola |
| Frenos ante rachas | Ninguno | 6 interruptores (CUSUM, racha, caída, día, revisión a 150, fallos) |
| Selección de estrategia | La mejor de 1 196 en un mes (PBO hasta 0.51) | Protocolo S4 (walk-forward, DSR ≥ 0.95, PBO ≤ 0.2, prospectiva) |
| Dinero real | 15 USDT por operación sin validación | $w = 0$ hasta validar |
| WR objetivo 70–80 % con E > 0 | No | No (no demostrado con estos datos) |

> **Lo que se puede afirmar honestamente:** con las soluciones aplicadas, el bot **deja de perder dinero por errores de implementación** y queda listo para validar estrategias de verdad. **No gana dinero**, porque hoy no hay ninguna estrategia con ventaja demostrada.

---

## 5. Riesgos y limitaciones

1. **El objetivo de 70–80 % no se alcanzó y no hay un win rate realista demostrado.** Lo único medido fuera de muestra es que las estrategias probadas no tienen ventaja.
2. **El holdout 2025-07 a 2026-09 está gastado.** Cualquier idea nueva solo puede validarse con datos posteriores a 2026-10-01, es decir, de forma **prospectiva**, lo que lleva meses o años según la frecuencia de la estrategia (sección S4).
3. **Régimen de mercado.** El diseño (2023–2025-S1) fue mayormente alcista; las pocas configuraciones positivas en diseño eran, en buena medida, exposición a esa subida. El holdout tuvo menos señales de las esperadas (148 frente a ~300), compatible con un cambio de régimen. No se usó ese argumento para rescatar nada.
4. **Solo 4 monedas, solo velas de 15 min y 1 h, solo compras.** No se exploraron otras temporalidades, otros activos ni ventas en corto (que el bot no puede hacer en *spot*).
5. **Costos supuestos.** 0.12 % por lado es una estimación (comisión estándar sin descuento + deslizamiento pequeño). Con órdenes *maker* y descuento por BNB podrían bajar a ~0.15 % ida y vuelta, pero **eso no crea ventaja**: la ventaja bruta medida es ≈ 0.
6. **Testnet no es el mercado real.** Su libro de órdenes, su liquidez y sus precios son distintos. Una estrategia validada con datos del mercado real puede comportarse distinto en testnet, y al revés. La paridad (S6) debe medirse contra el mercado en el que se opera, y una esperanza medida con precios de testnet **solo valida la infraestructura**: la calidad de la señal se mide con velas del mercado real.
7. **Pruebas múltiples.** Se registraron ≈ 12 300 configuraciones. Incluso con el protocolo, una línea de investigación que pruebe muchas variantes necesitará muestras muy grandes para aprobar el DSR.
8. **Los fragmentos de código de la sección 3 son de referencia.** Los endpoints de OCO de Binance cambiaron (el nuevo es `/api/v3/orderList/oco`); hay que verificar la documentación vigente y el soporte en testnet antes de implementar.
9. **El análisis de riesgo usa Monte Carlo sobre operaciones de diseño.** El Gestor demostró en el holdout que esos Monte Carlo subestiman las pérdidas cuando la esperanza de diseño está inflada. Por eso los umbrales deben recalibrarse con la esperanza desplazada a cero.

---

## 6. Lo que se probó y se rechazó (no repetir)

Esta sección deja constancia de cada candidato, para que nadie lo vuelva a implementar creyendo que es nuevo.

### C1 — MeanReversion20 filtrada por un modelo ridge

**Especificación congelada** (completa en `binance-research/data/research/output/analista/C1_spec_v2.json`, evaluada por `scripts/C1_eval_v2.py` con hashes SHA-256 verificados):

- **Señal primaria** (velas cerradas de 15 min): $z_t = (C_t - SMA20_t)/STD20_t < -2$ y $R_t = (SMA20_t - C_t)/C_t \ge 0.5\,\%$.
- **Score:** regresión ridge con $\lambda = 0.1 \cdot N_{\text{train}}$ sobre 45 columnas (39 variables causales de tendencia, volatilidad, posición en el rango de 7 días, régimen, volumen y contexto de BTC, más la hora en seno y coseno y 4 indicadoras de moneda). Objetivo: retorno a 24 h recortado a ±20 %. Reentrenamiento mensual con ventana expansiva desde 2023-01 y purga de 96 velas. Estandarización y umbral calculados solo con el entrenamiento.
- **Regla:** comprar si el score supera el percentil 90 de los scores del entrenamiento.
- **Geometrías probadas:** G3H96 (TP en la SMA20, SL a $3R$ bajo la entrada, barrera de 24 h) y T48 (solo salida por tiempo a las 12 h).

**Resultados:**

| | Diseño (2023-10 a 2025-06, walk-forward) | Holdout (2025-07 a 2026-09, prueba única) |
|---|---|---|
| G3H96: n | 467 | 148 |
| G3H96: WR [IC 95 %] | 72.4 % [68.2, 76.2] | **60.1 % [52.1, 67.7]** |
| G3H96: E neta ($t_{\text{día}}$) | +0.541 % (2.22) | **−0.498 % (−1.31)** |
| T48: n | 459 | 150 |
| T48: WR | 61.7 % | 48.7 % |
| T48: E neta ($t_{\text{día}}$) | +0.728 % (2.27) | +0.056 % (0.13) |
| Decisión (Holm, α de familia 0.05) | — | **Rechaza las dos** |

La diferencia entre diseño y holdout en G3H96 es significativa ($z = 2.30$, $p = 0.022$): no es solo falta de evidencia, es evidencia en contra. El win rate del holdout (60.1 %) cae en el rango que lograban en diseño las entradas **al azar** con la misma geometría (55–62 %).

**Por qué se veía bien en diseño:** la especificación se eligió viendo los dos subperiodos de diseño; el DSR con todas las pruebas del equipo era 0.13–0.27, y el PBO de la familia de 32 variantes, 0.49–0.60. El protocolo S4 lo habría rechazado antes de llegar al holdout.

### Otros candidatos rechazados

| Candidato | Por qué se rechazó |
|---|---|
| MeanReversion, TrendFollowing, Squeeze y VWAP actuales | WR igual al de la geometría; E neta de −0.27 % a +0.17 % en las 184 configuraciones de diseño, ninguna significativa (las 4 cargadas en el bot, de −0.20 % a −0.27 %); negativa en el holdout; $\Delta p$ frente al azar entre −1 y +3 puntos |
| TP corto para subir el win rate | WR de 70–80 % con $b \approx 0.3$, pero E de −0.17 % a −0.24 % (−0.12 a −0.16 R); el azar logra el mismo WR |
| Ruptura de 4 días en velas de 1 h con trailing *chandelier* | WR 42 %; $\Delta E$ frente al azar +0.33 % con $t = 1.29$; E −0.56 % en meses bajistas de BTC; 3 de 6 pliegues |
| Filtros univariados (41 variables) | Ninguno con E > 0 al replicarse. RSI (+7.8 → −3.0 puntos) y volumen relativo (+2.9 → −5.4) se invirtieron; el retorno de 4 h se desvaneció (+10.0 → +0.2). Los que replicaron (+4.5 a +7.1 puntos) dejaron $E_R$ entre −0.06 y −0.12 |
| Meta-etiquetado con regresión logística | AUC fuera de muestra 0.52–0.55; $E_R < 0$ |
| XGBoost con la etiqueta actual ("¿sube 1 % en 3 h?") | Etiqueta desconectada de cómo opera el bot; nunca se usó en vivo |
| Optimizar con un mes de datos | PBO hasta 0.51; walk-forward mes a mes con E < 0 en las 4 monedas |

---

## 7. Líneas abiertas para una validación futura

Solo pueden probarse con datos **posteriores a 2026-10-01**, siguiendo el protocolo S4 completo y después de aplicar S1–S7. El tamaño de muestra sale de $n = ((1.645 + 0.84)\,\sigma/\mu)^2 \cdot \text{DEFF}$, con $\sigma \approx 4.4\,\%$ por operación y $\text{DEFF} \approx 1.5$.

| Línea | Hipótesis exacta | Muestra necesaria | Plazo estimado |
|---|---|---|---|
| L1: compra de caídas condicionada al régimen | MR20 + score con E > 0 solo cuando BTC está sobre su SMA de 30 días (en diseño: +0.76 %, $t = 2.6$; es **exploratoria**, porque se formuló después de ver los datos) | ≈ 2 000 operaciones si $\mu = 0.3\,\%$; ≈ 500 si $\mu = 0.6\,\%$ | 4–17 años a ~120 operaciones por año (el doble a la frecuencia observada en el holdout, ≈ 60 por año): probablemente impracticable |
| L2: momentum diario con salida *chandelier* | E > 0 neta con WR esperado de 35–45 % | ≈ 600 operaciones ($\mu = 0.5\,\%$, $\sigma = 4\,\%$) | Varios años a frecuencia diaria |
| L3: reducir costos | Bajar de 0.24 % a ≈ 0.15 % ida y vuelta con órdenes *maker* y descuento por BNB | ≈ 50 órdenes en testnet | Corto, pero por sí sola no crea ventaja |

> **Meta honesta si alguna línea aprueba:** un win rate de **55–60 % con $b \approx 1$** y esperanza positiva demostrada fuera de muestra. Con $b = 1$, un 50 % deja siempre $E = -c$; un 55 % exige $R \ge 2.4\,\%$ y un 60 %, $R \ge 1.2\,\%$ (fórmula 3). Un 70–80 % exigiría superar al azar por ≈ 8 puntos con un riesgo de al menos 8 veces los costos, algo que no se observó en ninguna prueba.
