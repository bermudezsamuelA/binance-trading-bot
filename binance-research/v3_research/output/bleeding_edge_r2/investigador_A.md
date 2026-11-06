# Investigador A — Fuentes de datos nuevas (ronda 2)

Fecha: 2026-10-16 (00:43–01:45, hora local). Alcance: buscar **información nueva**, con historial gratis o barato que cubra 2023-01..2025-06, que se pueda descargar **sin tocar dominios de Binance** y que mida algo del pánico o de su resolución que la v2 todavía no tenga.

**Reglas que se cumplieron.** No se hizo ninguna petición a dominios de Binance. Cada fuente se verificó con una petición pequeña (sondas en `E:/tmp/r2_probe/<fuente>/`). Para un chequeo descriptivo se bajaron ventanas pequeñas a `E:/tmp/r2_data/<fuente>/`. Los scripts están en `E:/tmp/r2_probe/_scripts/`. No se modificó ningún archivo del proyecto, no se registraron pruebas en `harness.log_trials` y no se hicieron *commits*.

> **Advertencia sobre la disponibilidad "desde tu ubicación".** Todas las sondas salieron por la **VPN activa**. Que un sitio responda aquí no garantiza que responda sin VPN, y viceversa: Bybit devolvió *"CloudFront … block access from your country"* para el país de salida de la VPN; GDELT y Dukascopy devolvieron HTTP 429 o error SSL, y Bitfinex limitó con 429, probablemente por la IP compartida. Cada ficha dice si la fuente quedó **"verificada vía VPN"** o **"no verificada"**. Conviene repetir las 10 sondas de la sección 5 sin VPN.

---

## 0. Resumen

**El hallazgo principal: el DVOL de Deribit.** Cuando el **índice de volatilidad implícita de BTC (DVOL) está muy por debajo de su media de 30 días** en el momento de la señal ($z_{30} < -1$), es decir, cuando el mercado cae **sin que las opciones paguen miedo**, las compras de la v2 + co-señal salen mucho peor:

| Muestra de diseño (descriptivo) | $z_{30} < -1$ | Resto |
|---|---|---|
| v2 + co-señal (131 ops) | n = 14: **WR 57 %, E −0.72 %** | n = 117: **WR 88.9 %, E +2.22 %** |
| Señales **aisladas** ($A = 0$; 83 ops **distintas**) | n = 21: WR 67 %, E −0.59 % | n = 62: WR 80.6 %, E +1.31 % |
| Señales aisladas, por tercil de $z_{30}$ | T1 68 % / −0.34 · T2 78 % / +1.16 · **T3 86 % / +1.67** (monotónico) | |

- Con $z_{30} < -1$ caen 6 de las 19 perdedoras: las del 2024-01-22 (salidas de GBTC; 2), 2024-04-12 (2), **2025-02-21 (hack de Bybit, −7.6 %)** y 2025-04-25. Son caídas "de vendedor", sin pánico de opciones. Las otras 8 operaciones vetadas eran ganadoras.
- Dentro de cada tercil de volatilidad realizada, el DVOL alto sigue siendo mejor (73 % → 90 % en el tercil medio y 86 % → 100 % en el alto). Además, la correlación con la volatilidad realizada es baja (0.15). **No parece redundante con lo que ya ve el modelo.**
- **Cautela:** el corte −1 se eligió mirando 4 cortes sobre las 131 operaciones (seis pliegues; con DVOL alto funciona mejor en 3 de los 4 pliegues donde hay datos). La réplica en las 83 señales aisladas es el dato más honesto, pero esas señales son del mismo periodo. **El laboratorio debe probarlo con el protocolo de la sección 2**, con el corte −1 y el signo ya fijados aquí.
- **Ganancia esperada si se confirma:** +2 a +3 pt de WR y +0.2 a +0.3 % de E en diseño, a cambio de perder ≈ 10 % de las operaciones. Fuera de muestra, la mitad, por la regresión hacia la media habitual: **≈ +1 a +1.5 pt**. Está **disponible en vivo** desde la API pública de Deribit.

**La restricción que manda: la muestra.** Las 131 operaciones de v2 + co-señal están repartidas en solo **41 días y 24 episodios**, de los cuales 4 terminan en pérdida, y hay 19 operaciones perdedoras en total. Con eso:

- Ganar **+1 pt de WR** sobre 131 operaciones equivale a quitar **≈ 1–2 perdedoras sin quitar ganadoras**. El error estándar de una diferencia entre terciles con n ≈ 45 es de ≈ 6–7 pt.
- Una variable **diaria** (Fear & Greed, flujos de ETF, oferta de *stablecoins*) solo actúa a nivel de episodio: su **n efectivo es ≈ 24**. Sirve para la higiene o el régimen, no como compuerta demostrable.
- Por eso se priorizan fuentes **intradía** y se propone medirlas también como **gradiente por vela** (2 703 velas con señal y $A \ge 1$) y en las **señales aisladas** ($A = 0$, otro conjunto de operaciones), con *bootstrap* por episodio.

**TOP 5 para el laboratorio** (orden por valor esperado: *prior* × costo × disponibilidad en vivo):

| # | Fuente | Qué mide que la v2 no tiene | Resolución e historial | Costo | *Prior* ΔWR fuera de muestra (con E ≥) | Chequeo descriptivo |
|---|---|---|---|---|---|---|
| **1** | **DVOL de Deribit** (BTC, ETH): $z_{30}$ y prima de varianza | El **miedo implícito** frente a la caída realizada | 1 h, desde 2021-03 | Gratis, sin clave; **ya descargado** | **+1 a +1.5 pt** | Fuerte, y se replica en las señales aisladas (arriba) |
| **2** | **GDELT DOC 2.0**: noticias cripto de hack, insolvencia o regulación frente a macro | El **tipo de choque**: estructural (hack, quiebra) o de liquidez | 15 min (por confirmar), desde 2017 | Gratis, sin clave, 1 petición cada 5 s | 0 a +2 pt | **No verificado** (429 vía VPN) |
| **3** | **Opciones de Deribit**: flujo de puts, IV ATM y *skew* (*trades* con IV) | Demanda de **cobertura** y su precio | Por *trade*, desde 2016 | Gratis, sin clave; pesado (solo ventanas) | 0 a +1 pt **adicional** al DVOL | Mixto: IV ATM alta 95 % (lo mismo que DVOL); *skew* sin gradiente |
| **4** | **Margen de Bitfinex** (*longs*/*shorts* de BTC, ETH, SOL y DOGE) | Si las "ballenas" de Bitfinex compran el pánico | 1 min, años antes de 2023 | Gratis, sin clave; límite de *rate* estricto | 0 a +1 pt | Contrario a la hipótesis: reducir *longs* en 4 h → 100 % (44 ops); por vela, sin gradiente |
| **5** | **Coinbase**: base USDT-USD y prima BTC ajustada | Si el dinero **sale a fiat** (USDT con descuento) o entra | 15 min, antes de 2023 | Gratis, sin clave | 0 a +1 pt | Mixto: USDT con descuento → 77 % frente a 86–93 %, pero solo en 2 de 6 pliegues |

**Lo que este informe NO puede prometer.** Salvo el DVOL, ninguna fuente mostró un gradiente consistente. Ninguna tiene evidencia publicada y rigurosa de que **separe los pánicos que rebotan de los que siguen cayendo**; casi toda la evidencia externa es anecdótica (CryptoQuant, K33, prensa). La probabilidad de que el DVOL sume **≥ +1 pt demostrable** con el protocolo de la sección 2 la estimo en ≈ 40–50 %. Para el resto del TOP 5, ≈ 10–20 % cada una. **Recomendación:** probar el DVOL ya (30 min de laboratorio) y **grabar hacia adelante** todo el TOP 5 para la prueba prospectiva, porque son datos públicos y baratos.

---

## 1. Chequeo descriptivo en diseño (no es una prueba)

**Qué se hizo.** Se reconstruyeron las señales de la v2 (ENS13, X5, 6 pliegues) con `be_common.load_ens`, en modo de solo lectura. Se reprodujo exacto **n = 131, WR 85.5 %, E +1.90 %** (y 188 / 81.4 % / +1.41 % sin compuerta). Los datos se volcaron a `E:/tmp/r2_probe/_trades/` (`trades_v2_A1.csv`, `trades_v2.csv` y `signal_candles.csv`). Cada variable se repartió en terciles sobre (a) las 131 operaciones y (b) las 2 703 velas con señal y $A \ge 1$ (por vela, sin la regla de una posición por moneda; muy correlacionadas entre sí). **Alineación:** solo datos **cerrados antes de la apertura de la vela de señal** (la entrada es a su cierre), con el retraso de publicación de cada fuente.

> **Esto consume grados de libertad.** Se miraron ≈ 30 variables y cortes (todas las tablas de abajo, más 4 cortes de DVOL). El laboratorio debe registrarlos como `harness.log_trials("bleeding_edge_r2_A_peek", 30, "chequeo descriptivo de fuentes nuevas, investigador A")`. Tampoco debe volver a elegir corte ni signo mirando estas tablas: los de la sección 2 quedan **fijados aquí**.

### 1.1 DVOL (historial completo) y Fear & Greed

Formato: WR / E media % (n) por tercil, de menor a mayor valor de la variable.

| Variable | Operaciones: T1 | T2 | T3 | Velas con señal: T1 | T2 | T3 |
|---|---|---|---|---|---|---|
| **DVOL BTC $z$ frente a 30 d** | 84 % / +1.43 (45) | 81 % / +1.29 (43) | **91 % / +3.00 (43)** | 83 % / +1.17 | 76 % / +1.52 | **93 % / +3.11** |
| DVOL BTC nivel | 82 % / +1.10 | 81 % / +1.45 | 93 % / +3.15 | 87 % / +1.39 | 78 % / +1.64 | 87 % / +2.74 |
| DVOL BTC cambio 24 h | 89 % / +2.02 | 88 % / +2.13 | 80 % / +1.56 | 79 % / +1.38 | 84 % / +1.60 | 90 % / +2.81 |
| F&G nivel | 89 % / +2.06 (45) | 84 % / +1.71 (44) | 83 % / +1.93 (42) | 89 % / +2.45 | 85 % / +1.80 | 78 % / +1.46 |
| F&G cambio 3 d | 86 % / +1.85 | 90 % / +2.36 | 80 % / +1.51 | 82 % / +2.09 | 86 % / +2.12 | 84 % / +1.56 |

**Cortes del DVOL $z_{30}$ (operaciones v2 + co-señal):**

| Corte | Operaciones bajo el corte | Resto |
|---|---|---|
| $z < -1.5$ | n = 8: 38 % / −2.36 | n = 123: 88.6 % / +2.18 |
| **$z < -1.0$** | **n = 14: 57 % / −0.72** | **n = 117: 88.9 % / +2.22** |
| $z < -0.5$ | n = 35: 80 % / +0.96 | n = 96: 87.5 % / +2.25 |
| $z < 0$ | n = 48: 85 % / +1.66 | n = 83: 85.5 % / +2.04 |

**Por pliegue** (tercil alto de $z_{30}$ frente al resto): pliegue 0, 100 % (5) frente a 62 % (8); pliegue 2, 90 % (20) frente a 58 % (12); pliegue 3, 83 % (6) frente a 85 % (20); pliegue 4, 92 % (12) frente a 88 % (8). En los pliegues 1 y 5 no hubo operaciones en el tercil alto.

**Controlando la volatilidad realizada** (7 días de velas de 15 min de la moneda, como *proxy* de $s_d$; correlación con $z_{30}$ = 0.15):

| Tercil de vol. realizada | $z_{30}$ > mediana | $z_{30}$ ≤ mediana |
|---|---|---|
| Baja (n = 44) | 82 % / +0.70 | 82 % / +1.00 |
| Media (n = 43) | **90 % / +2.18** | 73 % / −0.10 |
| Alta (n = 44) | **100 % / +4.95** | 86 % / +2.69 |

**Lectura.** El DVOL es la única variable con gradiente en ambas muestras, que además **se replica en las señales aisladas** (sección 0) y no se explica por la volatilidad realizada. La E más alta en el tercil alto es en parte mecánica (TP y SL en $s_d$), pero el **WR** también sube. Fear & Greed va en el sentido esperado (más miedo, mejor) en las velas, pero apenas en las operaciones; además es diario.

### 1.2 Coinbase, Upbit y *stablecoins* (ventanas de 72 h alrededor de los 49 días con señal)

| Variable | Operaciones: T1 | T2 | T3 | Velas: T1 | T2 | T3 |
|---|---|---|---|---|---|---|
| Prima BTC de Coinbase **ajustada** por USDT-USD (1 h) | 91 % / +2.23 | 74 % / +0.60 | 91 % / +2.85 | 84 % / +1.81 | 85 % / +2.02 | 83 % / +1.95 |
| Prima ajustada, cambio 24 h | 89 % / +2.46 | 81 % / +1.29 | 86 % / +1.95 | 81 % / +1.75 | 83 % / +1.76 | 88 % / +2.27 |
| **USDT-USD en Coinbase** (desvío de 1, pb, 1 h) | **77 % / +1.15** | 93 % / +1.86 | 86 % / +2.70 | **79 % / +1.34** | 88 % / +1.65 | 85 % / +2.79 |
| Prima "a lo CryptoQuant" (BTC-USD frente a BTCUSDT, sin ajustar) | 77 % / +1.15 | 93 % / +1.87 | 86 % / +2.71 | 80 % / +1.39 | 88 % / +1.81 | 84 % / +2.58 |
| Prima coreana (Upbit), cambio 24 h | 93 % / +1.77 | 77 % / +1.30 | 86 % / +2.64 | 87 % / +1.94 | 84 % / +1.91 | 81 % / +1.92 |
| Prima coreana, cambio 4 h | 86 % / +1.79 | 88 % / +2.20 | 82 % / +1.72 | 82 % / +1.99 | 85 % / +1.84 | 85 % / +1.95 |
| Oferta USDT, cambio 7 d | 88 % / +2.05 | 85 % / +1.17 | 83 % / +2.31 | 91 % / +2.57 | 87 % / +2.27 | 73 % / +0.89 |
| Oferta USDC, cambio 7 d | 85 % / +1.36 | 84 % / +1.51 | 88 % / +2.97 | 80 % / +1.78 | 88 % / +1.52 | 84 % / +2.61 |
| Oferta total de *stablecoins*, cambio 7 d | 89 % / +1.65 | 83 % / +1.51 | 85 % / +2.63 | 88 % / +2.23 | 87 % / +1.88 | 77 % / +1.66 |

**Lectura.**

- **La "prima de Coinbase" que publican los paneles es, a 15 min, casi toda la base USDT/USD.** Ajustada por USDT-USD, la prima de BTC queda en ±0.01 % (el arbitraje la cierra) y no muestra gradiente. La fila sin ajustar es casi idéntica a la de USDT-USD.
- **USDT con descuento** (≤ −2.8 pb: dinero saliendo de USDT hacia dólares) se asocia a peor WR en ambas muestras (77–79 % frente a 85–93 %). Pero **por pliegue no es consistente**: es peor en los pliegues 0 y 2 (57 % y 17 %) y mejor en los 1, 3, 4 y 5. Lo arrastra el 5 de agosto de 2024. Además, el nivel de la base deriva con el régimen. Queda como **secundaria** y debe probarse como $z$ frente a su mediana de 7–30 días.
- La prima coreana y la oferta de *stablecoins* no muestran nada consistente.

### 1.3 Opciones de Deribit (*trades* de las 6 h previas a cada operación; 406 989 *trades*)

| Variable | T1 | T2 | T3 | Mediana perdedoras / ganadoras |
|---|---|---|---|---|
| *Skew* put − call (IV de puts con $K/S$ 0.85–0.95 menos calls con 1.05–1.15; 2–45 días) | **91 % / +2.34** (46) | 80 % / +1.27 (41) | 84 % / +2.04 (44) | 4.19 / 3.33 |
| Fracción de puts con agresor comprador | 82 % / +1.20 | **93 % / +3.03** | 82 % / +1.50 | 0.523 / 0.554 |
| Volumen puts / calls | 84 % / +1.87 | 81 % / +1.60 | **91 % / +2.24** | 0.72 / 0.85 |
| Cambio del *skew* (últimas 2 h frente a las 4 h previas) | 91 % / +2.73 | 79 % / +0.65 | 86 % / +2.30 | −0.43 / −0.16 |
| IV ATM ($K/S$ 0.97–1.03) | 87 % / +1.49 | 74 % / +0.37 | **95 % / +3.87** | 56.4 / 57.0 |

**Lectura.** La IV ATM alta repite la señal del DVOL (es casi la misma información). **El *skew* no confirma la hipótesis** (un *skew* de puts alto **no** es mejor; si acaso, al revés), y la compra agresiva de puts sale en U. Solo el volumen relativo de puts va en el sentido esperado, y débil. Las opciones aportan poco **además** del DVOL, que es mucho más barato.

### 1.4 Bitfinex (margen *long*/*short* de BTC)

Ventanas de 72 h alrededor de los 49 días con señal (3 de 98 peticiones fallaron por 429, así que faltan unas pocas horas).

| Variable | Operaciones: T1 | T2 | T3 | Velas: T1 | T2 | T3 |
|---|---|---|---|---|---|---|
| *Longs* de BTC, cambio 24 h | **96 % / +2.93** (45) | 79 % / +1.23 (43) | 81 % / +1.49 (43) | 83 % / +1.57 | 87 % / +2.33 | 83 % / +1.89 |
| *Longs* de BTC, cambio 4 h | **100 % / +2.92** (44) | 72 % / +0.93 (43) | 84 % / +1.83 (44) | 83 % / +1.69 | 84 % / +1.79 | 85 % / +2.31 |
| *Shorts* de BTC, cambio 24 h | 89 % / +1.53 | 79 % / +1.44 | 89 % / +2.73 | 80 % / +0.99 | 87 % / +2.28 | 85 % / +2.50 |
| *Shorts* de BTC, cambio 4 h | 86 % / +1.93 | 91 % / +2.45 | 79 % / +1.31 | 82 % / +1.73 | 86 % / +1.99 | 84 % / +2.05 |

**Lectura.** En las operaciones, cuando las ballenas de Bitfinex **reducen** sus *longs* en las 4–24 h previas, el WR es de 96–100 %. Es **lo contrario** de la hipótesis fijada (signo +), aunque coincide con lo que la prensa dice de los suelos ("las ballenas reducen *longs* en los suelos"). **Por vela no hay ningún gradiente** (83 / 84 / 85 %), así que el resultado de las operaciones probablemente se debe a unos pocos episodios. No se debe adoptar el signo contrario mirando esta tabla. Si el laboratorio la prueba, que pre-registre **ambas colas** y aplique Holm.

---

## 2. Fichas del TOP 5

**Regla temporal común** (la del pre-registro): un dato con marca de publicación $T$ solo se usa en una vela que cierra en $t_c \ge T + \text{retraso}$. En diseño se recomienda, además, usar solo datos cerrados **antes de la apertura** de la vela de señal, como en el chequeo de la sección 1.

**Protocolo común de prueba (vale para las 5 fichas):**

1. **Signo y corte fijados de antemano** (los de cada ficha). Si se usan percentiles, se calculan **solo con entrenamiento y validación de cada pliegue** (ventana expansiva desde 2023-01).
2. **Tres muestras:** (a) v2 + co-señal (131 operaciones); (b) señales aisladas, $A = 0$ (≈ 85 operaciones, otro conjunto); (c) por vela, todas las velas de prueba con $\hat p \ge \theta$, más una banda $\hat p \ge \theta - 0.05$ para ganar n. *Bootstrap* por episodio (días a ≤ 2 días se unen). Exigir el mismo signo en ≥ 4 de los pliegues con datos.
3. **Compuerta:** simular con `be_common.simulate_entries` sin las entradas vetadas y comparar con (i) v2 + co-señal; (ii) el **azar condicionado** a la nueva compuerta (`be_common.cond_base`); (iii) **quitar el mismo número de operaciones al azar** (1 000 sorteos), para saber si +x pt es más de lo que da quitar operaciones cualesquiera.
4. **Control de la volatilidad:** repetir el gradiente dentro de terciles de $s_d$ (la del modelo, no el *proxy*), porque la E escala con $s_d$.
5. **Multiplicidad:** Holm sobre las 5 hipótesis y registro de todas las configuraciones en `log_trials`. **Pasa** si ΔWR ≥ +1 pt, ΔE ≥ 0, el gradiente es consistente por pliegue y se replica en las señales aisladas.
6. **Si no pasa en diseño, pero el *prior* es razonable:** se graba **hacia adelante** y entra en la fase 4 del pre-registro (≥ 150 señales prospectivas con gradiente monotónico, P ≤ 0.10).

### 2.1 DVOL de Deribit — **TOP 1**

- **Endpoint (verificado vía VPN):** `GET https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&start_timestamp=<ms>&end_timestamp=<ms>&resolution=3600`. También acepta `currency=ETH`. Devuelve `[ts_apertura_ms, open, high, low, close]` y `continuation`.
- **Autenticación y límites:** ninguna (método público). Los límites por créditos son holgados: se bajaron 2 × 21 889 puntos en < 1 min con 0.2 s de pausa entre las 25 peticiones.
- **Resolución e historial:** 1 h desde 2021-03-24 para BTC y ETH. **La resolución de 1 min no existe para 2024** (se probó: lista vacía), y **no hay DVOL de SOL** en 2024. Para SOL y DOGE se usa el DVOL de BTC como factor de mercado (en el chequeo se usó el de BTC para las 4 monedas).
- **Tamaño 2023-01..2025-06:** 21 889 horas por moneda, ≈ 1 MB en JSON. **Ya descargado:** `E:/tmp/r2_data/deribit/dvol_BTC_1h.json` y `dvol_ETH_1h.json`.
- **En vivo:** sí, cada hora (API pública de Deribit; verificado vía VPN). Deribit no permite operar a residentes de algunos países, pero el método público de datos responde. Hay que verificarlo sin VPN. Para más resolución en vivo, `public/ticker?instrument_name=…` o `get_index_price` permiten reconstruir minuto a minuto, aunque el modelo de diseño debe usar el dato horario.
- **Hipótesis (signo + fijado *antes* del chequeo; el corte −1, *después* de ver los terciles, por lo que la referencia honesta es la réplica en las señales aisladas):** **$z_{30} = (\text{DVOL}_h - \text{media}_{30d}) / \text{desv}_{30d}$; signo +.** Si el precio cae fuerte pero el DVOL está **bajo su media del mes** ($z_{30} < -1$), el mercado de opciones **no** está pagando miedo. Eso no es un pánico de liquidez (que se revierte), sino una venta **ordenada** de un vendedor con información o con un flujo estructural: salidas de GBTC, hack de Bybit, distribuciones de Mt. Gox. Esas caídas siguen. Si el DVOL salta sobre su media, hay pánico de cobertura y el miedo está sobrepreciado, lo que favorece el rebote (como el VIX alto en acciones). **Variables secundarias:** prima de varianza `vrp = DVOL − vol. realizada de 30 d anualizada (×√365)`; `dvol_eth − dvol_btc` para las operaciones de ETH.
- **Por qué es nueva:** la v2 tiene la volatilidad **realizada** y los datos de futuros, pero ninguna variable de **opciones**.
- **Plan de prueba:**
  - **Alineación:** la vela horaria con marca $h$ cierra en $h + 1$ h y se publica al instante. Úsala en la vela de 15 min cuya apertura es ≥ $h + 1$ h (en el chequeo se pidió `ts + 1 h ≤ apertura + 15 min`; en el laboratorio, mejor `ts + 1 h ≤ apertura`). La media y la desviación de 30 días usan solo horas cerradas.
  - **Compuerta pre-registrada:** **no comprar si $z_{30}(\text{BTC}) < -1$.** Secundaria: tercil bajo calculado en entrenamiento y validación.
  - **Muestras:** las tres del protocolo, además de ENS6 y v1 si sus predicciones están guardadas (`output/bleeding_edge/preds`).
  - **Controles:** $s_d$ del modelo; $\hat p$ (¿el modelo ya pone menos probabilidad a esas velas?); día de la semana (el DVOL se mueve menos en fin de semana).
- ***Prior* fuera de muestra:** +1 a +1.5 pt de WR, con E +0.1 a +0.3 %. **Justificación:** el efecto en diseño (+3.4 pt y +0.32 % de E sobre la co-señal) se replica en las señales aisladas, pero el corte salió de mirar los datos y en diseño solo hay 14 operaciones afectadas (≈ 5 episodios). Lo habitual es que el efecto se reduzca a la mitad. La literatura documenta la prima de varianza de BTC (Almeida et al.: mucho mayor que la del S&P 500 y dependiente del régimen), pero **no** encontré una prueba publicada de que prediga rebotes intradía.
- **Evidencia:** [Deribit DVOL (The Block, 2021)](https://www.theblock.co/linked/99971/deribit-bitcoin-volatility-index); [Almeida, Grith, Miftachov y Wang, *Risk Premia in the Bitcoin Market* (arXiv 2410.15195)](https://arxiv.org/html/2410.15195v2); [Alexander e Imeraj, *The Bitcoin VIX and its variance risk premium*](https://sro.sussex.ac.uk/id/eprint/91094/).

```python
# E:/tmp/r2_data/deribit/  -- DVOL horario BTC y ETH, 2023-01-01 .. 2025-07-01 (ya ejecutado: dl_dvol_fng.py)
import json, time, urllib.request, os
OUT = r"E:/tmp/r2_data/deribit"; os.makedirs(OUT, exist_ok=True)
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "r2"}), timeout=60) as r:
        return json.loads(r.read().decode())
for cur in ("BTC", "ETH"):
    rows, s, t1, step = [], 1672531200000, 1751328000000, 900 * 3600 * 1000
    while s < t1:
        e = min(s + step, t1)
        rows += get("https://www.deribit.com/api/v2/public/get_volatility_index_data"
                    f"?currency={cur}&start_timestamp={s}&end_timestamp={e}&resolution=3600")["result"]["data"]
        s = e; time.sleep(0.2)
    rows = sorted({r[0]: r for r in rows}.values())          # [ts_apertura_ms, o, h, l, c]
    json.dump(rows, open(os.path.join(OUT, f"dvol_{cur}_1h.json"), "w"))

# Variable causal para una vela de 15 min con apertura t_open (ms):
import numpy as np
d = np.array(json.load(open(os.path.join(OUT, "dvol_BTC_1h.json"))))
close_t, dv = d[:, 0].astype(np.int64) + 3_600_000, d[:, 4]
def dvol_z30(t_open):
    i = np.searchsorted(close_t, t_open, side="right") - 1      # ultima hora cerrada antes de abrir la vela
    w = dv[max(0, i - 719):i + 1]
    return (w[-1] - w.mean()) / (w.std() + 1e-9)
```

### 2.2 GDELT: tipo de choque en las noticias — **TOP 2** (no verificado)

- **Endpoint:** `GET https://api.gdeltproject.org/api/v2/doc/doc?query=<consulta>&mode=timelinevolraw&format=json&startdatetime=YYYYMMDDHHMMSS&enddatetime=YYYYMMDDHHMMSS`. **Sin clave.** Límite: **1 petición cada 5 s** (lo dice el propio mensaje del 429).
- **Estado: no verificado.** Las 3 sondas devolvieron HTTP 429 vía VPN, aun con 25 s de espera (la IP compartida está limitada). El servidor de archivos (`data.gdeltproject.org`) sí respondió, pero el GKG de 15 min pesa ≈ 7.6 MB por archivo (≈ 500 GB en 2.5 años), así que se propone la API DOC.
- **Historial:** el blog de GDELT dice que la API DOC 2.0 busca desde el 2017-01-01 con fechas absolutas. La resolución del *timeline* en rangos cortos (¿15 min?) está **por confirmar**.
- **Tamaño:** con ventanas de 3 días y 5 consultas, ≈ 300 × 5 = 1 500 peticiones × 6 s ≈ 2.5 h. Solo pesa unos MB. Alternativa más rápida: consultar solo las ventanas de 24 h antes de cada día con $\hat p \ge \theta - 0.05$ (≈ 150 días × 5 consultas × 6 s ≈ 75 min).
- **En vivo:** sí (la misma API, con ≈ 15 min de retraso). Hay que verificarlo sin VPN.
- **Consultas fijadas:** Q1 `(bitcoin OR crypto OR ethereum OR solana) (hack OR exploit OR hacked OR drained)`; Q2 `(crypto OR exchange OR bitcoin) (bankruptcy OR insolvent OR "withdrawals halted" OR "suspends withdrawals")`; Q3 `(crypto OR bitcoin) (SEC OR lawsuit OR ban OR indictment OR "sell-off" OR "selling pressure" OR "Mt. Gox" OR "government wallet")`; Q4 macro `(tariff OR "Federal Reserve" OR recession OR "rate hike" OR "jobs report")`; Q0 base `(bitcoin OR crypto)` para normalizar.
- **Hipótesis (signo −):** si el pánico coincide con un **pico de noticias cripto-específicas** (Q1–Q3 en las 12 h previas con $z > 3$ frente a 30 días, normalizado por Q0), el choque es **estructural** y la caída sigue (LUNA, FTX, hack de Bybit). Si el pico es **macro** (Q4) o no hay noticias, es un pánico de liquidez que rebota. **Complementa al DVOL:** dos de las caídas "sin miedo implícito" de diseño tienen noticia identificable (hack de Bybit; salidas de GBTC).
- **Plan de prueba:** el *bin* con marca $T$ se publica ≈ 15 min después, así que se usa en velas con apertura ≥ $T + 30$ min. Compuerta pre-registrada: "no comprar si $z(Q1+Q2+Q3) > 3$ en las 12 h previas". Por ser un evento raro, se prueba (a) que **no quite ganadoras** de los episodios macro, (b) que quite alguno de los 4 episodios perdedores, (c) su interacción con el DVOL, y (d) en el estrés 2022 (LUNA, FTX; fase 3 del pre-registro), donde GDELT sí tiene historial.
- ***Prior*:** 0 a +2 pt, muy incierto. Es el único dato que ataca directamente "¿qué pánicos siguen cayendo?" (la pieza E04 del documento, "no probada") y se puede probar **con historial** en lugar de solo grabar hacia adelante. Pero las noticias son ruidosas, los medios generalistas llegan tarde, y en diseño hay muy pocos choques estructurales.
- **Evidencia:** [GDELT, *DOC 2.0: búsqueda desde 2017*](https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/); [cliente `gdeltdoc` (PyPI)](https://pypi.org/project/gdeltdoc/); K33 vía [The Block](https://www.theblock.co/amp/post/372115/whats-next-after-cryptos-fourth-largest-long-liquidation-event-of-2025): solo ≈ 1 de cada 4 días de liquidaciones extremas marca suelo, así que hace falta filtrar.

```python
# E:/tmp/r2_data/gdelt/  -- volumen de noticias por consulta (timelinevolraw), ventanas de 3 dias, 1 peticion / 6 s
import json, time, urllib.request, urllib.parse, os, datetime as dt
OUT = r"E:/tmp/r2_data/gdelt"; os.makedirs(OUT, exist_ok=True)
Q = {"q1_hack": '(bitcoin OR crypto OR ethereum OR solana) (hack OR exploit OR hacked OR drained)',
     "q2_insolv": '(crypto OR exchange OR bitcoin) (bankruptcy OR insolvent OR "withdrawals halted" OR "suspends withdrawals")',
     "q3_struct": '(crypto OR bitcoin) (SEC OR lawsuit OR ban OR indictment OR "sell-off" OR "selling pressure" OR "Mt. Gox" OR "government wallet")',
     "q4_macro": '(tariff OR "Federal Reserve" OR recession OR "rate hike" OR "jobs report")',
     "q0_base": '(bitcoin OR crypto)'}
f = lambda d: d.strftime("%Y%m%d%H%M%S")
for k, q in Q.items():
    res, d0 = [], dt.datetime(2023, 1, 1)
    while d0 < dt.datetime(2025, 7, 1):
        d1 = d0 + dt.timedelta(days=3)
        u = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
            {"query": q, "mode": "timelinevolraw", "format": "json", "startdatetime": f(d0), "enddatetime": f(d1)})
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "r2"}), timeout=90) as r:
                res.append({"start": f(d0), "data": json.loads(r.read().decode())})
        except Exception as e:
            res.append({"start": f(d0), "error": str(e)})
        d0 = d1; time.sleep(6)
    json.dump(res, open(os.path.join(OUT, f"gdelt_{k}.json"), "w"))
```

### 2.3 Opciones de Deribit: flujo de puts, IV ATM y *skew* — **TOP 3**

- **Endpoint (verificado vía VPN):** `GET https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time?currency=BTC&kind=option&start_timestamp=<ms>&end_timestamp=<ms>&count=1000&sorting=asc`. Cada *trade* trae `timestamp`, `instrument_name` (vencimiento, *strike*, C/P), **`iv`**, `index_price`, `mark_price`, `direction` (lado del agresor) y `amount`. **Ojo:** el *host* normal (`www.deribit.com`) solo guarda 24 h de este método; el histórico está en `history.deribit.com`.
- **Autenticación y límites:** ninguna. Se bajaron 407 peticiones en ≈ 7 min sin errores (≈ 1 petición/s en serie, limitado por la latencia).
- **Resolución e historial:** por *trade*, desde el inicio de la plataforma (también ETH).
- **Tamaño:** en ventanas de pánico, ≈ 1 050 *trades*/h; en total, ≈ 15–25 M de *trades* entre 2023-01 y 2025-06 (≈ 1.2–1.9 GB en CSV, ≈ 20 000 peticiones, ≈ 6 h en serie). **Recomendación:** bajar solo las ventanas de 6 h antes de cada vela candidata. Las de las 131 operaciones ya están: 31 MB en `E:/tmp/r2_data/deribit_opt/btc_opt_trades_win.csv`.
- **En vivo:** sí; basta con `public/get_book_summary_by_currency?currency=BTC&kind=option` cada 15 min.
- **Hipótesis (fijada antes del chequeo; signo +):** compra agresiva de puts y *skew* disparado ⇒ el miedo ya está cubierto, y la cobertura de delta de los *market makers* acelera el rebote. **El chequeo no la apoya** (sección 1.3): el *skew* alto no es mejor. Solo la **IV ATM** (≈ DVOL) y, débilmente, el **volumen relativo de puts** van en el sentido esperado.
- **Plan de prueba:** *trades* con `timestamp` < apertura de la vela de señal. Mismo protocolo, pero **condicionado al DVOL**: ¿aportan `put_call_vol` o `skew` algo dentro de los terciles de $z_{30}$? Si no, se descarta.
- ***Prior*:** 0 a +1 pt **adicional** al DVOL. El mecanismo es fuerte en acciones, pero en cripto la evidencia es anecdótica y mixta (K33: el *skew* se dio vuelta antes de caídas que siguieron dos meses).
- **Evidencia:** [K33, flujos de opciones OTM antes de las ventas](https://k33.com/research/archive/articles/medium-term-far-out-the-money-option-flows-foreshadowing-bitcoin-sell-offs); [Glassnode, *Navigating Bitcoin Options*](https://research.glassnode.com/content/navigating-bitcoin-options/); [Deribit, acceso a *trades* históricos](https://docs.deribit.com/articles/accessing-historical-trades-orders).

```python
# E:/tmp/r2_data/deribit_opt/  -- trades de opciones BTC en ventanas [t-6h, t) (t = aperturas de velas candidatas)
import json, time, urllib.request, csv, os
OUT = r"E:/tmp/r2_data/deribit_opt"; os.makedirs(OUT, exist_ok=True)
def get(u):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "r2"}), timeout=60) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(2 + 3 * k)
def dump(windows, fname="btc_opt_trades.csv", cur="BTC"):     # windows: lista de [a_ms, b_ms] ya fusionadas
    seen = set()
    with open(os.path.join(OUT, fname), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ts", "trade_id", "instrument", "iv", "index_price", "mark_price", "price", "direction", "amount"])
        for a, b in windows:
            s = a
            while s < b:
                d = get("https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
                        f"?currency={cur}&kind=option&start_timestamp={s}&end_timestamp={b}&count=1000&sorting=asc")
                tr = d["result"]["trades"] if d else []
                for x in tr:
                    if x["trade_id"] in seen: continue
                    seen.add(x["trade_id"])
                    w.writerow([x["timestamp"], x["trade_id"], x["instrument_name"], x.get("iv"), x.get("index_price"),
                                x.get("mark_price"), x["price"], x["direction"], x["amount"]])
                if not tr or not d["result"].get("has_more"): break
                s = tr[-1]["timestamp"]                         # mismo ms: se deduplica por trade_id
                time.sleep(0.12)
```

### 2.4 Margen de Bitfinex — **TOP 4**

- **Endpoint (verificado vía VPN):** `GET https://api-pub.bitfinex.com/v2/stats1/pos.size:1m:{tBTCUSD|tETHUSD|tSOLUSD|tDOGE:USD}:{long|short}/hist?start=<ms>&end=<ms>&limit=10000&sort=1`. Devuelve `[ts_ms, tamaño_en_moneda]`. Se verificaron BTC, ETH, SOL y DOGE con datos de 2023-01 y 2024-01.
- **Autenticación y límites:** ninguna. **El límite de *rate* es estricto:** con 0.7–3 s de pausa aparecieron 429 que bloquean ≈ 60 s. Conviene ≥ 6 s por petición o esperar 65 s tras cada 429.
- **Resolución e historial:** 1 min, desde antes de 2023. Hasta 10 000 puntos por petición (≈ 7 días).
- **Tamaño 2023-01..2025-06:** 1.3 M de puntos y 131 peticiones por serie; 8 series (4 monedas × *long*/*short*) ≈ 1 050 peticiones, ≈ 2 h con 6 s de pausa. ≈ 250 MB en JSON, ≈ 10 MB tras pasar a 15 min.
- **En vivo:** sí (`…/last`; verificado vía VPN).
- **Variables:** `bfx_long_d24h`, `bfx_long_d4h` (% de cambio), `bfx_short_d24h`, `bfx_ls = long/short`.
- **Hipótesis (fijada; signo +):** las "ballenas" de Bitfinex compran caídas con horizonte de días. Si **aumentan sus *longs*** durante el pánico, hay demanda paciente que absorbe la venta. *Shorts* crecientes son combustible para un *short squeeze*. **Matiz:** parte del aumento de *longs* es *carry* (largo en margen contra corto en futuros), no convicción.
- **Por qué es nueva:** la v2 ve ratios *long/short* de cuentas de Binance (minoristas, futuros), no el **margen spot** de un grupo de manos grandes de otra plataforma.
- **Plan de prueba:** valor del último minuto cerrado < apertura de la vela de señal; mismo protocolo común.
- **Chequeo descriptivo (sección 1.4):** contrario a la hipótesis en las operaciones (reducir *longs* → 96–100 %) y sin gradiente por vela. Si se prueba, hay que pre-registrar **las dos colas**.
- ***Prior*:** 0 a +1 pt. La prensa documenta ambos signos: *longs* que suben durante caídas largas sin suelo inmediato (2025) y suelos que coinciden con **reducción** de *longs*.
- **Evidencia:** [Cointelegraph: *longs* de Bitfinex en 5.1 B, ¿compra o cobertura?](https://cointelegraph.com/markets/bitfinex-bitcoin-long-positions-reach-5-1-b-is-someone-buying-or-hedging); [MEXC News](https://www.mexc.com/it-IT/news/323129); [ChainCatcher](https://www.chaincatcher.com/en/article/2243796).

```python
# E:/tmp/r2_data/bitfinex/  -- margen long/short por minuto, 2023-01-01 .. 2025-07-01, re-muestreado a 15 min
import json, time, urllib.request, urllib.error, os
OUT = r"E:/tmp/r2_data/bitfinex"; os.makedirs(OUT, exist_ok=True)
def get(u):
    for k in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "r2"}), timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            time.sleep(65 if e.code == 429 else 5)
        except Exception:
            time.sleep(5)
    return []
for sym in ("tBTCUSD", "tETHUSD", "tSOLUSD", "tDOGE:USD"):
    for side in ("long", "short"):
        rows, s, t1 = {}, 1672531200000, 1751328000000
        while s < t1:
            d = get(f"https://api-pub.bitfinex.com/v2/stats1/pos.size:1m:{sym}:{side}/hist?start={s}&end={t1}&limit=10000&sort=1")
            if not d: break
            for ts, v in d:
                rows[ts // 900_000 * 900_000] = (ts, v)           # ultimo minuto de cada bloque de 15 min
            s = d[-1][0] + 60_000; time.sleep(6)
        json.dump(sorted(rows.values()), open(os.path.join(OUT, f"{sym.replace(':', '')}_{side}_15m.json"), "w"))
```

### 2.5 Coinbase: base USDT-USD y prima BTC ajustada — **TOP 5**

- **Endpoint (verificado vía VPN):** `GET https://api.exchange.coinbase.com/products/{USDT-USD|USDC-USD|BTC-USD|ETH-USD|SOL-USD|DOGE-USD}/candles?granularity=900&start=<ISO>&end=<ISO>`. Devuelve `[time_s, low, high, open, close, volume]` en orden descendente, con un máximo de 300 velas por petición.
- **Autenticación y límites:** ninguna; ≈ 10 peticiones/s por IP.
- **Resolución e historial:** 15 min (también 1, 5 y 60 min, 6 h y 1 d), desde antes de 2023 (verificado 2023-01-01 para BTC-USD y 2023-03-11 para USDT-USD: durante el *depeg* de USDC, USDT cotizaba a 1.006–1.009).
- **Tamaño 2023-01..2025-06:** 292 peticiones por producto; 6 productos ≈ 1 750 peticiones (≈ 5 min) y ≈ 25 MB.
- **En vivo:** sí (API pública; verificado vía VPN).
- **Variables:** `usdt_dev = close(USDT-USD) − 1` en pb, media de 1 h, y su **$z$ frente a la mediana de 7 y 30 días** (el nivel deriva con el régimen); `usdc_dev`; `cbp_adj = close(BTC-USD) / (close_Binance_local(BTCUSDT) × close(USDT-USD)) − 1`.
- **Hipótesis (fijada antes del chequeo; signo + para `usdt_dev`):** USDT con **descuento** en Coinbase significa que se vende USDT por dólares: el dinero **sale** de cripto hacia fiat y el pánico tiene un vendedor que no vuelve, así que la caída sigue. USDT con **prima** significa que el dinero entra a comprar la caída. **Hallazgo lateral:** la "prima de Coinbase" de los paneles es, a 15 min, casi toda esta base; la prima de BTC ajustada es ≈ 0 y no tiene gradiente.
- **Plan de prueba:** vela de Coinbase cerrada antes de la apertura de la vela de señal; usar el **$z$**, no el nivel. Compuerta pre-registrada: "no comprar si $z_{30}(\text{usdt\_dev}) < -1$". Atención especial a la consistencia por pliegue: el chequeo solo la mostró en 2 de 6.
- ***Prior*:** 0 a +1 pt. El mecanismo es claro y el dato es barato y está disponible en vivo, pero el gradiente descriptivo no es estable entre pliegues. Como regla de **higiene**, sí conviene adoptar ya: no operar si USDT o USDC se desvían > 50 pb de 1 (*depeg*).
- **Evidencia:** [CoinDesk, 2024-07-01, *Coinbase Premium Index*](https://coindesk.com/markets/2024/07/01/bitcoin-s-bottom-in-price-could-be-near-or-already-in-the-coinbase-premium-index-suggests); [BIT Knowledge Hub, *Coinbase premium*](https://www.bit.com/knowledge-hub/coinbase-premium). No encontré estudios académicos intradía.

```python
# E:/tmp/r2_data/coinbase/  -- velas de 15 min, 2023-01-01 .. 2025-07-01
import json, time, urllib.request, os, datetime as dt
OUT = r"E:/tmp/r2_data/coinbase"; os.makedirs(OUT, exist_ok=True)
iso = lambda s: dt.datetime.utcfromtimestamp(s).strftime("%Y-%m-%dT%H:%M:%SZ")
def get(u):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "r2"}), timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(2 + 3 * k)
    return []
for p in ("USDT-USD", "USDC-USD", "BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"):
    rows, s, t1 = [], 1672531200, 1751328000
    while s < t1:
        e = min(s + 300 * 900, t1)
        rows += get(f"https://api.exchange.coinbase.com/products/{p}/candles?granularity=900&start={iso(s)}&end={iso(e - 900)}")
        s = e; time.sleep(0.15)
    rows = sorted({r[0]: r for r in rows}.values())          # [t_apertura_s, low, high, open, close, vol]
    json.dump(rows, open(os.path.join(OUT, f"{p}_15m.json"), "w"))
```

---

## 3. Otras fuentes evaluadas (fuera del TOP 5)

| Fuente | Endpoint (estado) | Resolución / historial | Hipótesis y signo | Veredicto y *prior* |
|---|---|---|---|---|
| **Fear & Greed** (alternative.me) | `https://api.alternative.me/fng/?limit=0&format=json` (**verificado**; ya descargado: 3 176 días en `E:/tmp/r2_data/fng/fng_all.json`) | Diario (00:00 UTC), desde 2018-02 | Más miedo, mejor rebote (−) | Es un compuesto de volatilidad, *momentum*, redes, dominancia y Trends, **casi todo derivado de precios** que el modelo ya ve. Al ser diario, el n efectivo es ≈ 24 episodios. Gradiente en las velas (89 / 85 / 78 %), débil en las operaciones. **0 a +1 pt**, como variable de régimen. |
| **Oferta de *stablecoins*** (DefiLlama) | `https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=1` (USDT), `=2` (USDC) y sin parámetro (total) (**verificado**; ya descargado). Hay versión por cadena en CoinMetrics community (`SplyCur` de `usdt_eth`, `usdt_trx` y `usdc`; verificado). | Diario, desde 2017 | Crecimiento de 7 d = "pólvora seca" (+) | Sin gradiente consistente (sección 1.2). La emisión de USDT **sigue** a las caídas (Ante, Fiedler y Strehle: retornos anormales positivos **antes** de la emisión; Wei: sin efecto en precio). **≈ 0 pt.** |
| **Emisiones de Tether por hora** (eventos `Issue` en Ethereum y Tron) | Etherscan V2 `getLogs` (clave gratis) o TronGrid. **No verificado:** el RPC público de publicnode exige *token* para consultas de archivo (403). | Por evento | Emisión grande durante o tras el pánico ⇒ compra inminente (+) | Interesante por la hora exacta (Griffin y Shams), pero la literatura está dividida y la emisión suele llegar **después** del suelo. **0 a +1 pt.** |
| **Prima coreana** (Upbit) | `https://api.upbit.com/v1/candles/minutes/15?market=KRW-BTC&to=<ISO>&count=200` (**verificado** desde 2023-01). **KRW-USDT no existe antes de 2024-H2**; el tipo de cambio sale de FRED `DEXKOUS` (diario; verificado). | 15 min | Capitulación minorista coreana ⇒ rebote (+), o FOMO (−) | Signo incierto y sin gradiente (sección 1.2). **≈ 0 a +0.5 pt.** |
| **Flujos de ETF de BTC y ETH** (Farside, SoSoValue) | Farside: **403 de Cloudflare** con `curl` y WebFetch. SoSoValue: 403 sin clave (gratis con registro). Alternativas: NewHedge (*token*), Glassnode (gráfico). | Diario, desde 2024-01-11 (BTC) y 2024-07-23 (ETH); se publica tras el cierre de EE. UU. y se revisa hasta 7 días | Salidas fuertes los 3 días previos ⇒ vendedor estructural ⇒ la caída sigue (−) | Cubre los 6 pliegues de prueba, pero es diario (n ≈ 24). Enero de 2024 (GBTC) y febrero de 2025 coinciden con perdedores, pero eso es *ex post*, y el DVOL ya marca esas fechas. Retraso: el dato del día $D$ se usa desde $D+1$ a las 14:00 UTC. **0 a +1 pt.** |
| **Macro intradía** (Dukascopy: US500, USDJPY, XAU) | `https://datafeed.dukascopy.com/datafeed/USA500IDXUSD/YYYY/MM-1/DD/BID_candles_min_1.bi5` (LZMA). **No verificado:** 429 y luego error SSL vía VPN. Alpha Vantage intradía con `month=` parece *premium*; Tiingo IEX guarda ≈ 2 000 puntos. | 1 min, desde 2003; sin fines de semana | Pánico cripto **con** caída de acciones = choque macro de liquidez ⇒ rebote (+) | Complementa a GDELT para el "tipo de choque", pero sin datos en fin de semana; además, el CME opera 24/7 desde 2026-05. **0 a +1 pt.** |
| **Liquidaciones DeFi *on-chain*** (Aave, Compound, Maker) | Eventos `LiquidationCall` vía Etherscan V2 (clave gratis) o Dune (cuenta). **No verificado.** | Por bloque | Venta forzada agotada (+) | Son las únicas **liquidaciones exactas** con historial gratis, pero el *proxy* "*OI flush*" ya **bajó** el WR. **0 a +0.5 pt.** |
| **Coinalyze** | `https://api.coinalyze.net/v1/…` (clave gratis, 40 llamadas/min) | **Intradía: guarda solo 1 500–2 000 puntos**; según su documentación, "*We keep only between 1500 and 2000 datapoints for intraday timeframe… the old data is deleted each day*". Diario: completo. | — | **Sin historial intradía para diseño.** Vale **en vivo** como sustituto de `fapi` (sección 8.3 del documento). **0 pt en diseño.** |
| **Bybit** | `https://api.bybit.com/v5/market/open-interest…`: **403, "CloudFront … block access from your country"** (país de salida de la VPN) | 5 min | Redundante con los *metrics* de Binance | Bloqueado al menos desde ese país, y redundante. **≈ 0 pt.** |
| **OKX** (*rubik*) | `https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history` (responde, pero **vacío para 2024**: retención corta) | 5 min, solo reciente | Redundante | **≈ 0 pt en diseño.** Posible sustituto en vivo. |
| **Tardis.dev** | CSV gratis **solo del primer día de cada mes**; el resto, de pago | *Tick* | Liquidaciones exactas (+) | 30 días sueltos no sirven para compuertas. Solo vale de pago. |
| **Hyperliquid** | API de información y S3 | Sin historial público de 2023–2024 | Liquidaciones exactas (+) | Solo **hacia adelante** (ya está en la fase 4). |
| **Flujos a plataformas *on-chain*** (CoinMetrics community) | `https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=FlowInExNtv,FlowOutExNtv` (**verificado**, diario). **1 h no disponible** en community (403). Los valores se **revisan** (estado `flash`, revisados en 2026). | Diario | Capitulación en curso (contemporáneo) | Diario, revisado (riesgo de fuga) y contemporáneo. **≈ 0 pt.** El *netflow* de BGeometrics parece del plan de pago. |
| **Liquidaciones en CoinMetrics community** | `timeseries/market-liquidations`: **403** ("*not available with supplied credentials*") | — | — | Solo de pago. |
| **Dominancia y capitalización** | CoinGecko *demo*: solo 365 días. CoinMetrics `CapMrktCurUSD`: diario (verificado). | Diario | — | Derivada de precios; la amplitud con precios ya falló. **≈ 0 pt.** |
| **Google Trends** | `pytrends` (no oficial; diario solo en ventanas ≤ 9 meses; 429 frecuentes) | Diario o semanal | Contemporáneo | **≈ 0 pt.** |

---

## 4. Ranking final por valor esperado

| Rango | Fuente | *Prior* ΔWR fuera de muestra | Costo | ¿Probable en diseño? | ¿En vivo? |
|---|---|---|---|---|---|
| 1 | **DVOL $z_{30}$ (Deribit)** | **+1 a +1.5** | Ninguno (ya descargado) | Sí | Sí, cada hora |
| 2 | GDELT, tipo de choque | 0 a +2 (muy incierto) | Bajo en MB, 1–2.5 h de peticiones | Si responde sin VPN | Sí (15 min de retraso) |
| 3 | Opciones de Deribit (flujo de puts) | 0 a +1 adicional | Medio (ventanas) | Sí | Sí |
| 4 | Margen de Bitfinex | 0 a +1 | Bajo, pero lento (*rate limit*) | Sí | Sí |
| 5 | Base USDT-USD en Coinbase | 0 a +1 | Bajo | Sí | Sí |
| 6 | Macro intradía (Dukascopy) | 0 a +1 | Bajo | Si responde sin VPN | Sí (no en fin de semana) |
| 7 | Flujos de ETF | 0 a +1 | Manual o con clave | Solo episodios | Con 1 día de retraso |
| 8 | Fear & Greed | 0 a +1 (régimen) | Ninguno | Solo régimen | Sí |
| 9 | Emisiones de Tether, liquidaciones DeFi | 0 a +1 | Clave de Etherscan | Sí | Sí |
| 10 | Prima coreana, oferta de *stablecoins* | ≈ 0 | Ninguno | Sin gradiente | Sí |
| — | Coinalyze, Bybit, OKX, Tardis gratis, Hyperliquid, flujos *on-chain*, Trends, dominancia | ≈ 0 en diseño | — | No | Algunos, como sustitutos de `fapi` |

**Recomendación al laboratorio, en orden:**

1. **DVOL $z_{30} < -1$ como compuerta** sobre v2 + co-señal, con el protocolo de la sección 2. Los datos ya están en disco; cuesta ≈ 30 min. Si pasa, añádelo como brazo **S3** del pre-registro (P1 + DVOL), no como reemplazo de P1, hasta que lo confirme la prueba prospectiva.
2. **GDELT** sin VPN: correr las 5 consultas y probar la compuerta de choque estructural, sola y en conjunto con el DVOL.
3. **Bitfinex y base USDT** como variables secundarias (pocas horas de descarga).
4. **Grabar hacia adelante** desde ya: DVOL (cada hora), resumen de opciones de Deribit (cada 15 min), Bitfinex `…/last`, velas de Coinbase USDT-USD y GDELT. Todo es público y no depende de `fapi`.

---

## 5. Sondas para repetir sin VPN (1 minuto)

Ninguna toca Binance, así que se pueden correr con la VPN apagada. Sirven para confirmar la disponibilidad real desde tu ubicación:

```bash
curl -s "https://api.alternative.me/fng/?limit=1" | head -c 200; echo
curl -s "https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&start_timestamp=1722816000000&end_timestamp=1722826000000&resolution=3600" | head -c 200; echo
curl -s "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time?currency=BTC&kind=option&start_timestamp=1722816000000&end_timestamp=1722819600000&count=1" | head -c 200; echo
curl -s "https://api.exchange.coinbase.com/products/USDT-USD/candles?granularity=900&start=2024-08-05T00:00:00Z&end=2024-08-05T01:00:00Z" | head -c 200; echo
curl -s "https://api.upbit.com/v1/candles/minutes/15?market=KRW-BTC&count=1" | head -c 200; echo
curl -s "https://api-pub.bitfinex.com/v2/stats1/pos.size:1m:tBTCUSD:long/last"; echo
curl -s "https://api.gdeltproject.org/api/v2/doc/doc?query=bitcoin%20hack&mode=timelinevolraw&format=json&startdatetime=20250220000000&enddatetime=20250223000000" | head -c 300; echo
curl -s -o /dev/null -w "%{http_code}\n" "https://datafeed.dukascopy.com/datafeed/USA500IDXUSD/2024/07/05/BID_candles_min_1.bi5"
curl -s "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT" | head -c 200; echo
curl -s "https://stablecoins.llama.fi/stablecoins?includePrices=false" | head -c 200; echo
```

---

## 6. Archivos

- **Sondas** (pocos KB, datos no confiables): `E:/tmp/r2_probe/{fng,deribit,deribit_hist,coinbase,upbit,bitfinex,defillama,coinmetrics,coinalyze,gdelt,okx,bybit,fred,eth_rpc,dukascopy,dukascopy2,farside,sosovalue}/`.
- **Datos descargados:**
  - Historial completo 2023-01..2025-06: `E:/tmp/r2_data/deribit/dvol_{BTC,ETH}_1h.json`, `E:/tmp/r2_data/fng/fng_all.json` y `E:/tmp/r2_data/defillama/{usdt,usdc,total}_all.json`.
  - Ventanas de 72 h alrededor de los 49 días con señal: `E:/tmp/r2_data/coinbase/{BTC-USD,USDT-USD}_15m_win.json`, `E:/tmp/r2_data/upbit/KRW-BTC_15m_win.json` y `E:/tmp/r2_data/bitfinex/pos_{long,short}_1m_win.json`.
  - 6 h antes de cada operación: `E:/tmp/r2_data/deribit_opt/btc_opt_trades_win.csv`.
- **Operaciones y señales de diseño reconstruidas** (solo lectura): `E:/tmp/r2_probe/_trades/{trades_v2_A1,trades_v2,signal_candles}.csv`.
- **Scripts:** `E:/tmp/r2_probe/_scripts/dump_trades.py` (reconstrucción), `dl_dvol_fng.py`, `dl_windows2.py`, `dl_deribit_opt.py` (descargas) y `desc_check.py`, `desc_check2.py`, `desc_check3.py`, `desc_check4.py` (chequeos descriptivos).
