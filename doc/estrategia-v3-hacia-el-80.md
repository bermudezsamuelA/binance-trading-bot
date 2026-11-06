# Estrategia v3: el camino hacia un 75-80 % de *win rate* con ganancia

Este documento reúne en un solo lugar lo mejor de tres investigaciones anteriores: el diagnóstico del bot y la matemática del *win rate* (WR), los modelos con datos de futuros y las estrategias extra probadas en 2026-10. Sustituye a `matematica-aplicativa.md`, `modelos-complejos-y-datos.md` y `estrategias-extra-hacia-el-80.md`. Está pensado para pasar a la **fase de implementación**: qué estrategia construir, con qué datos y reglas, qué resultados esperar de verdad, qué no repetir y cómo validarla sin engañarse.

Las fórmulas usan LaTeX y se ven bien en la vista previa de Markdown de VS Code (`Ctrl+Shift+V`) y en GitHub.

## Respuesta corta

> **La estrategia a implementar es la v3:** un ensamble de 13 modelos (ENS13) que compra **velas de capitulación** usando datos de futuros, y que solo opera cuando **otra de 4 monedas ancla también dio señal en las últimas 12 horas** (un pánico de mercado, no una caída aislada). Sale con TP a $+0.7\,s_d$, SL a $-1.75\,s_d$ y cierre forzado a las **96 h**.

- **Qué WR esperar de verdad:** **≈ 73-79 % fuera de muestra**, con una esperanza de **+0.6 a +1.2 %** por operación. El **87.8 %** que da en diseño es una **cota optimista**: la v2 marcó 81 % en diseño y 69 % en monedas nuevas.
- **Techo realista: ≈ 75-78 %.** Un 80 % por operación **demostrado** es improbable (15-25 %, según el juicio del laboratorio). La meta alcanzable es **≈ 80 % de meses ganadores**.
- **Lo único demostrado fuera de muestra** es una ventaja **relativa** sobre el azar: +9 a +17 puntos de WR y ≈ +1.1 % de E en 14 monedas nunca vistas ($p \approx 0.001$-$0.005$). La co-señal y la barrera de 96 h **no tienen** validación fuera de muestra todavía.
- **Bloqueo práctico:** el modelo necesita datos de futuros cada 5 min, que vienen de `fapi.binance.com`, **bloqueada desde tu ubicación (HTTP 451)**. Sin una de las tres salidas de la [sección 7.6](#76-el-bloqueo-de-fapi-y-sus-tres-salidas), la v3 no puede operar en vivo. Sí puede validarse en **sombra diferida** con los archivos diarios de `data.binance.vision`.
- **Siguiente paso:** infraestructura honesta (sección 7), canal sombra de 18 monedas, estrés 2022 y prueba prospectiva pre-registrada desde 2026-10-01 (sección 8). Dinero real en cero hasta aprobar.

## Tabla de contenido

- [Respuesta corta](#respuesta-corta)
- [Convenciones](#convenciones)
- [1. Por qué llegar al 80 es difícil](#1-por-qué-llegar-al-80-es-difícil)
- [2. La estrategia v3 paso a paso](#2-la-estrategia-v3-paso-a-paso)
- [3. Qué resultados esperar](#3-qué-resultados-esperar)
- [4. Piezas opcionales y con reserva](#4-piezas-opcionales-y-con-reserva)
- [5. Lo que no funciona: no repetir](#5-lo-que-no-funciona-no-repetir)
- [6. Trampas del WR fabricado](#6-trampas-del-wr-fabricado)
- [7. Especificación para implementar](#7-especificación-para-implementar)
- [8. Hoja de ruta y pre-registro](#8-hoja-de-ruta-y-pre-registro)
- [9. Dónde está todo](#9-dónde-está-todo)

---

## Convenciones

| Término | Significado |
|---|---|
| Diseño | 2023-01-01 a 2025-06-30. Toda la investigación se hizo aquí |
| *Holdout* | 2025-07-01 a 2026-09-30. **Gastado**: ya no valida nada |
| Prospectivo | Desde 2026-10-01. Es el único periodo que puede validar la v3 |
| $c$ | Costo ida y vuelta: 0.10 % de comisión + 0.02 % de deslizamiento por lado = **0.24 %**. Estrés: 0.30 %. Con BNB y TP límite: 0.19 % |
| $s_d$ | Volatilidad diaria de la moneda (sección 2.4) |
| WR | Fracción de operaciones con retorno **neto** > 0 |
| E | Esperanza neta por operación, en % del precio |
| Azar | Entradas al azar con la misma moneda, mes y geometría de salida |
| Azar condicionado | Entradas al azar **solo** en las velas donde la regla nueva está activa |
| Episodio | Grupo de días con operaciones separados por ≤ 2 días. Es la unidad real de muestra |

Todo es *spot* y solo compras. Las cifras de diseño de la v3 suman **12 666** configuraciones registradas en `trials_log.csv`; cualquier corrección por pruebas múltiples debe usar ese número.

---

## 1. Por qué llegar al 80 es difícil

### 1.1 Sin ventaja, el WR lo pone la geometría

Si el precio se mueve al azar, la probabilidad de tocar primero el TP depende solo de las distancias. Con una deriva favorable $\nu$, sube:

$$
P(\text{TP primero}) = \frac{m}{a+m} = \frac{1}{1+b},
\qquad
P_{\nu}(\text{TP primero}) = \frac{1 - e^{2\nu m}}{e^{-2\nu a} - e^{2\nu m}}
$$

**Qué es cada símbolo:**

- $a$, $m$: distancia al TP y al SL, en volatilidades diarias $s_d$.
- $b = a/m$: cociente recompensa/riesgo.
- $\nu$: deriva favorable, en $s_d$ por día. Con $\nu = 0$ es el azar puro, y entonces $E = -c$.

> **Ejemplo:** en velas de 1 h, entradas **al azar** con TP a 1 ATR, SL a 3 ATR y barrera de 96 velas ganan el **74.7 %** de las veces ($E = -0.09\,R$). La señal MeanReversion(48, 2) con la misma salida gana el 73.2 %. Las dos pierden dinero. En velas de 15 min, el azar toca el TP el 73.9 % de las veces, pero el WR neto cae a 62.8 % y $E = -0.24\,\%$.
>
> Con la salida X5 de la v3 ($a = 0.7$, $m = 1.75$), sin barrera ni costos:
>
> | Deriva $\nu$ ($s_d$/día) | WR teórico | Deriva en %/día ($s_d \approx 4.3\,\%$) |
> |---|---|---|
> | 0 | 71.4 % | 0 |
> | 0.07 | 75 % | +0.3 % |
> | **0.19** | **80 %** | **+0.8 %** |
> | 0.32 | 85 % | +1.4 % |

El 80 % exige una subida sostenida de ≈ 0.8 % por día mientras dura la operación (mediana: 11 h). Esa deriva solo aparece en los **rebotes tras una capitulación**. Medida en diseño: las operaciones del modelo con co-señal tienen $\nu \approx 0.43$; el azar con la misma co-señal, ≈ 0.18, y el azar sin ella, ≈ 0.06. La duda es cuánto de esos 0.43 se conserva fuera de muestra.

### 1.2 El WR mínimo con costos

$$
p^{*} = \frac{1 + c/R}{1 + b},
\qquad
\Delta p_{\min} = \frac{c}{R\,(1+b)},
\qquad
\frac{R}{c} > \frac{1}{p\,(1+b) - 1}
$$

**Qué es cada símbolo:**

- $p^{*}$: WR mínimo para no perder dinero.
- $R$: distancia al SL, como fracción del precio.
- $\Delta p_{\min}$: puntos que la señal debe acertar **por encima del azar**.
- $R/c$: tamaño mínimo de la operación, en múltiplos de los costos, para que un WR $p$ deje ganancia.

> **Ejemplo:** con $b = 0.5$, $c = 0.24\,\%$ y $R = 2\,\%$: $p^{*} = 1.12/1.5 = 74.7\,\%$, es decir, 8 puntos sobre el azar. Con $R = 1\,\%$, $p^{*} = 82.7\,\%$. Valores mínimos de $R/c$:
>
> | $p$ \ $b$ | 1/3 | 0.43 | 0.5 | 0.75 | 1 |
> |---|---|---|---|---|---|
> | 0.70 | ∞ | 1 000 | 20 | 4.4 | 2.5 |
> | 0.75 | ∞ | 13.8 | 8 | 3.2 | 2.0 |
> | 0.80 | 15 | 6.9 | 5 | 2.5 | 1.7 |

El ATR mediano de 15 min es 0.27 % en BTC, 0.35 % en ETH, 0.60 % en SOL y 0.53 % en DOGE: **los costos equivalen a casi un ATR de BTC**. Regla práctica: $R \ge 8$-$10\,c$ (≈ 2-2.5 %). Por eso la v3 usa $R$ mediano ≈ 7.5 %.

Para X5 ($b = 0.4$, $R \approx 7.5\,\%$), $p^{*}$ teórico = $1.032/1.4 = 73.7\,\%$. El equilibrio **empírico** es ≈ 65 %, porque las salidas por tiempo suben el $b$ efectivo a ≈ 0.53.

### 1.3 El WR se descompone en geometría más ventaja

$$
p = p_{\text{azar}}(a, m, H, \text{régimen}) + \Delta_{\text{modelo}} + \Delta_{\text{compuerta}}
$$

**Qué es cada símbolo:**

- $p_{\text{azar}}$: WR del azar con la misma salida ($H$ = barrera de tiempo). Con X5: 61.7 % en diseño (alcista) y ≈ 60 % en el *holdout* (bajista).
- $\Delta_{\text{modelo}}$: ventaja del ensamble fuera de muestra. Medida: de +9.4 pt (v2, X5) a +16.9 pt (v1, G3).
- $\Delta_{\text{compuerta}}$: lo que añade la co-señal. Medido en diseño: +2.1 a +4.5 pt, según el ensamble.

> **Ejemplo:** 60 % + 9.4 = **69.4 %**, exactamente lo que dio la v2 en monedas nuevas. Para el 80 % con X5 harían falta ≈ +20 pt fuera de muestra entre modelo y compuerta. Nunca se ha replicado algo así.

### 1.4 Cuánto vale cada punto de WR

$$
E = (\bar W + \bar L)\,(p - p^{*}_{\text{emp}}),
\qquad
p^{*}_{\text{emp}} = \frac{\bar L}{\bar W + \bar L}
$$

**Qué es cada símbolo:**

- $\bar W$, $\bar L$: ganancia y pérdida netas medias por operación, en %.
- $p^{*}_{\text{emp}}$: WR de equilibrio real con esos tamaños.
- $(\bar W + \bar L)/100$: lo que vale **un punto** de WR en esperanza.

> **Ejemplo (v2 en las 8 monedas nuevas):** $\bar W = 2.61\,\%$ y $\bar L = 4.88\,\%$ dan $p^{*}_{\text{emp}} = 65.2\,\%$, y **1 pt = 0.075 % de E**. Con WR 70 % ⇒ E ≈ +0.36 %; con 75 % ⇒ +0.73 %; con 80 % ⇒ +1.11 %.

### 1.5 Por qué X5 y no una geometría de WR más alto

Si el modelo detecta una deriva $\mu$ por día, la ganancia bruta crece con la duración de la operación:

$$
E_{\text{bruta}} \approx \mu \cdot \mathbb{E}[\tau],
\qquad
\mathbb{E}[\tau] \approx a \cdot m \ \text{días}
$$

**Qué es cada símbolo:** $\mu$ es la deriva favorable que detecta el modelo; $\mathbb{E}[\tau]$ es la duración media de la operación entre barreras a $a$ y $m$ volatilidades diarias.

> **Ejemplo:** con $\mu = 0.5\,\%$ por día, G3 ($a \cdot m = 1.125$ días) gana ≈ 0.56 % bruto, más del doble de los costos. G4 ($a \cdot m = 0.48$) gana ≈ 0.24 %, justo los costos.
>
> | Geometría ($a$, $m$, $H$) | $b$ | $R$ mediano | $p^{*}$ | Azar medido | Resultado |
> |---|---|---|---|---|---|
> | G4 (0.4, 1.2, 192) | 0.33 | 3.98 % | 79.5 % | 71.2 % | WR 70-74 %, E −0.31 %: **WR fabricado** |
> | G3 (0.75, 1.5, 192) | 0.50 | 4.97 % | 69.9 % | 58.6 % | Etiqueta de entrenamiento |
> | X5 (0.7, 1.75, 384) | 0.40 | ≈ 7.5 % | 73.7 % (≈ 65 % empírico) | 61.7 % | Salida de la v3 |

Ninguna geometría fija domina a X5: bajar el TP sube el WR y baja la E. La única mejora de salida que sube **las dos** es alargar la barrera de tiempo (E7), porque no toca el TP ni el SL: solo da tiempo a que actúe la deriva.

### 1.6 Selectividad frente a tamaño de muestra

Cuanto más selectiva es una regla, menos operaciones da y más difícil es **demostrar** su WR. Operaciones **independientes** necesarias para que el límite inferior de Wilson al 95 % supere el objetivo:

| WR real | Para afirmar ≥ 70 % | Para afirmar ≥ 75 % |
|---|---|---|
| 76 % | 225 | — |
| 78 % | 127 | 801 |
| 80 % | 81 | 289 |
| 85 % | 36 | 73 |

Estas cifras se multiplican por el efecto de diseño $DEFF$: 1.0-1.2 por día con 4 monedas, y probablemente 2-3 con 18, porque los pánicos son simultáneos. **La unidad real es el episodio:** en diseño hubo ≈ 16 por año con 4 monedas.

Para la esperanza:

$$
n_{\min} = \left(\frac{(z_{1-\alpha} + z_{0.8})\,\sigma}{\mu}\right)^2 \cdot DEFF
$$

**Qué es cada símbolo:**

- $\mu$: E por operación a detectar. Por la "maldición del ganador" se usa **la mitad** de la de diseño.
- $\sigma$: desviación del retorno por operación (≈ 4.0-4.4 %).
- $z_{1-\alpha} = 1.645$, $z_{0.8} = 0.84$; $DEFF$ medido: 1.45-2.07.

> **Ejemplo:** con $\mu = 0.7\,\%$, $\sigma = 4\,\%$ y $DEFF = 2$: $(2.485 \times 4/0.7)^2 \times 2 \approx 400$ operaciones. Es el tamaño de la prueba prospectiva (sección 8).

**Un +1 pt real es invisible en diseño.** Si un filtro quita $m$ operaciones con WR $p_r$ y deja otras con WR $p_k$:

$$
\Delta WR = \frac{m}{131}\,(p_k - p_r)
$$

> **Ejemplo:** con $m = 25$, el error estándar de $p_k - p_r$ es ≈ 0.086. Para detectarlo con potencia 0.8 y α = 0.10 hace falta $p_k - p_r \approx 0.18$, es decir, **ΔWR ≈ +3.5 pt**. Con 131 operaciones y 24 episodios, un +1 pt no se distingue del ruido: el veredicto debe venir de datos nuevos.

### 1.7 La meta honesta son los meses ganadores

$$
P(\text{mes} > 0) \approx \Phi\!\left(\frac{\mu\, n_m}{\sigma\sqrt{n_m\,DEFF}}\right)
$$

**Qué es cada símbolo:** $\Phi$ es la normal acumulada; $\mu$, la E por operación; $\sigma$, su desviación (≈ 4.2 %); $n_m$, operaciones por mes; $DEFF$, el efecto de diseño.

> **Ejemplo:** con $\mu = 1\,\%$, $n_m = 15$ y $DEFF = 1.5$: $15/(4.2 \times \sqrt{22.5}) = 0.75$ y $\Phi(0.75) = 77\,\%$ de meses ganadores. Con $\mu = 0.5\,\%$, 65 %.

---

## 2. La estrategia v3 paso a paso

### 2.1 Resumen de la v3

| Paso | Regla |
|---|---|
| Datos | Velas spot de 15 min + *metrics*, *funding*, prima y velas de futuros de Binance, con alineación sin fuga |
| Variables | 74, normalizadas por la volatilidad propia, sin identificar la moneda |
| Modelo | ENS13: 6 LightGBM + 6 MLP + 1 CNN, Platt por miembro, media de probabilidades |
| Señal | $\hat p \ge \theta = 0.7142683625605063$ |
| Compuerta | Otra de las 4 anclas (BTC, ETH, SOL, DOGE) tuvo $\hat p \ge \theta$ en las últimas 48 velas |
| Entrada | Al cierre de la vela de señal; una posición por moneda; máximo 3 abiertas |
| Salida | TP límite a $+0.7\,s_d$, SL a $-1.75\,s_d$, cierre a mercado a las 384 velas (96 h) |
| Riesgo | 0.5 % del capital por operación; ≤ 1.5 % por episodio; pausas |
| Universo | 18 pares USDT: BTC, ETH, SOL, DOGE, ADA, ATOM, AVAX, BCH, BNB, DOT, ETC, FIL, LINK, LTC, NEAR, TRX, UNI, XRP |

### 2.2 Datos de entrada

Todo es gratis en `data.binance.vision`: ≈ 90 MB para 4 monedas y 2.5 años, en menos de 3 min con 32 hilos. **Antes de descargar, apaga la VPN.**

| Fuente | Ruta | Resolución |
|---|---|---|
| Velas spot (open_time, OHLC, volume, taker_buy_base) | `spot/monthly/klines/{SYM}/15m/` | 15 min |
| *Metrics*: OI, ratios long/short de *top traders* (cuentas y posiciones) y de todas las cuentas, ratio *taker* | `futures/um/daily/metrics/{SYM}/` | 5 min |
| *Funding* | `futures/um/monthly/fundingRate/{SYM}/` | 8 h |
| Prima del perpetuo | `futures/um/monthly/premiumIndexKlines/{SYM}/15m/` | 15 min |
| Velas de futuros | `futures/um/monthly/klines/{SYM}/15m/` | 15 min |

Siempre hace falta también BTCUSDT de 15 min para el contexto de BTC. Historial mínimo: **≥ 35 días** antes del inicio (3 360 velas). Descarga: `nn/nn_download_futures.py` y `scripts/download_klines.py`.

### 2.3 Alineación temporal sin fuga

El campo `create_time` de los *metrics* **cambia de significado el 2024-03-04**: antes marcaba el final del intervalo de 5 min y desde entonces marca el inicio. Si se ignora, el modelo ve el futuro.

$$
\text{usar el registro con marca } T \text{ en la vela } i \iff T \le t_i + 5\ \text{min}
$$

**Qué es cada símbolo:**

- $T$: `create_time` del registro de futuros.
- $t_i$: apertura de la vela de 15 min. La decisión se toma al cierre, en $t_i + 15$ min.
- La regla teórica segura es $T \le t_i + 10$ min; la **vigente** (código, especificación y pre-registro) es la más estricta, $T \le t_i + 5$ min.

> **Ejemplo:** para la vela de 12:00 a 12:15 se usan los registros de 11:55, 12:00 y 12:05. Los de 12:10 y 12:15 **no**.

Reglas complementarias:

- *Funding*: `calc_time` ≤ $t_i$ + 15 min. Prima y velas de futuros: la vela con el mismo `open_time`.
- Ordenar las filas (hay archivos diarios desordenados). Rellenar **solo hacia adelante**: *metrics* hasta 30 min; prima y velas de futuros, 2 velas; *funding*, 40. Nunca hacia atrás.
- Columna `metrics_missing`. **En vivo, si falta un dato más de 30 min, esa vela no opera.**
- Control de alineación: el *taker* de futuros correlaciona 0.84 con el desequilibrio spot; desplazado 15 min, cae a 0.12-0.16.
- Auditoría: alterar el futuro en 16 cortes no cambió ninguna de las 74 variables. Repetirla tras cualquier cambio de código.

### 2.4 Volatilidad diaria

$$
s_d = \text{std}\big(\ln(c_t/c_{t-1}),\ 672 \text{ velas},\ \text{ddof} = 1\big)\cdot\sqrt{96}
$$

**Qué es cada símbolo:** $c_t$ es el cierre de la vela; 672 velas son 7 días; $\sqrt{96}$ pasa de 15 min a un día; ddof = 1 es la desviación muestral.

> **Ejemplo:** si la desviación de 15 min es 0.44 %, $s_d = 0.44 \times 9.80 = 4.31\,\%$.

### 2.5 Las 74 variables

Todas son causales y se normalizan por la volatilidad propia, para que el modelo sirva en monedas que no vio. Lista exacta (código fuente: `nn/nn_common.py`):

> atr_rel, bar_body, bar_range, bar_upwick, basis, basis_z_672, beta_btc, btc_ret_16/4/672/96, btc_vol_ratio, btc_z_672, dd_672, dd_96, funding, funding_z_2016, fut_imb_1/16, fut_spot_vol, fut_taker_1/4/16, glob_acc_chg_16/96, glob_acc_lvl, glob_acc_z_672, hour_sin/cos, metrics_missing, oi_chg_1/4/16/96, oi_to_vol, oi_z_672, premium, premium_16, premium_z_672, rel_btc_96/672, ret_1/4/16/48/96/288/672, rngpos_96/672, rsi14, taker_imb_1/4/16/96, top_acc_chg_16/96, top_acc_lvl, top_acc_z_672, top_pos_chg_16/96, top_pos_lvl, top_pos_z_672, vol_level, vol_ratio_16_96, vol_ratio_96_672, vol_rel_1/16/96, wd_sin/cos, z_20, z_96, z_672.

$$
\text{ret}_k = \frac{\ln(c_t/c_{t-k})}{\sigma_{15}\sqrt{k}},
\qquad
\text{oi\_chg}_k = \ln\frac{OI_t}{OI_{t-k}},
\qquad
\text{imb} = \frac{v_{\text{taker}}}{v} - 0.5
$$

**Qué es cada símbolo:** $\sigma_{15}$ es la desviación de 15 min (672 velas); $OI$, el open interest; $v_{\text{taker}}$, el volumen comprador agresivo; $v$, el volumen total.

> **Ejemplo:** ETH sube 1.5 % en 4 h con $\sigma_{15} = 0.4\,\%$: $\text{ret}_{16} = \ln(1.015)/(0.004 \times 4) = 0.93$ desviaciones, comparable con cualquier otra moneda.

Las redes estandarizan con la media y la desviación **del tramo de entrenamiento** y recortan a ±5. La CNN recibe además una secuencia de 96 velas con 10 canales. Lo que el modelo aprende a comprar son **velas de capitulación**: rango de +2.3 desviaciones, volumen de +1.4, caída en la última hora y OI bajo frente al volumen.

### 2.6 Etiqueta de entrenamiento

El modelo no predice el precio: predice si una operación con geometría fija ganará (meta-etiquetado con triple barrera).

$$
TP = c\,(1 + 0.75\,s_d),\qquad SL = c\,(1 - 1.5\,s_d),\qquad H = 192,\qquad y = \mathbb{1}[\text{retorno neto} > 0]
$$

**Qué es cada símbolo:** $c$ es el precio de entrada; $H$, la barrera de tiempo en velas (48 h); $y$, la etiqueta, con costos de 0.24 %. Es la geometría **G3**. La salida operativa, en cambio, es X5 (sección 2.10).

**Purga:** la etiqueta depende de las $H$ velas siguientes, así que se descartan las últimas $H + 1$ velas antes de cada corte (193 con G3; 289 para la etiqueta de salida en validación).

### 2.7 Ensamble ENS13 y calibración

| Miembro | Arquitectura |
|---|---|
| 6 LightGBM (semillas 0-5) | 50 iteraciones, 15 hojas, `min_data_in_leaf` 1 000, lr 0.03, $\lambda_{l2}$ 10 |
| 6 MLP | 74 → 128 → 64 → 1, GELU, *dropout* 0.3, AdamW (lr 5·10⁻⁴, wd 10⁻³), lotes de 512, paciencia 3 |
| 1 CNN 1D dilatada | 4 capas de 24 filtros, núcleo 5, dilataciones 1/2/4/8, rama tabular de 64, cabeza 136 → 64 → 1; usa 1 de cada 4 velas |

$$
\hat p_k = \frac{1}{1 + e^{-(A_k s_k + B_k)}},
\qquad
\hat p = \frac{1}{13}\sum_{k=1}^{13}\hat p_k
$$

**Qué es cada símbolo:** $s_k$ es la salida cruda del miembro $k$; $A_k$, $B_k$ son sus coeficientes de Platt, ajustados en validación; $\hat p$ es la media de las probabilidades calibradas.

| Miembro | $A$ | $B$ | AUC val | | Miembro | $A$ | $B$ | AUC val |
|---|---|---|---|---|---|---|---|---|
| lgb s0 | 2.553 | −0.419 | 0.607 | | mlp s0 | 0.320 | 0.304 | 0.532 |
| lgb s1 | 7.290 | −2.039 | 0.608 | | mlp s1 | 0.554 | 0.222 | 0.561 |
| lgb s2 | 6.465 | −1.727 | 0.605 | | mlp s2 | 0.477 | 0.254 | 0.549 |
| lgb s3 | 2.510 | −0.401 | 0.607 | | mlp s3 | 0.398 | 0.277 | 0.543 |
| lgb s4 | 20.747 | −6.519 | 0.612 | | mlp s4 | 0.522 | 0.246 | 0.551 |
| lgb s5 | 14.089 | −4.298 | 0.616 | | mlp s5 | 0.417 | 0.254 | 0.540 |
| cnn s0 | 1.723 | −0.277 | 0.581 | | | | | |

> **Ejemplo:** el lgb s0 con salida cruda $s = 0.5$: $A s + B = 1.277 - 0.419 = 0.857$ y $\hat p_k = 1/(1 + e^{-0.857}) = 0.70$.

Ajuste: [2023-01-01 + 800 velas, 2025-04-01 − 193 velas), $n$ = 311 272. Validación: [2025-04-01, 2025-07-01 − 289 velas), $n$ = 33 788. **Los datos de entrenamiento llegan hasta 2025-03.** Los coeficientes y los *hashes* de los 20 archivos están en `spec_nn_v2.json`; se cargan de ahí, nunca se copian a mano.

### 2.8 Umbral

$$
\theta = \arg\max_{\theta}\ \bar E_{\text{val}}(\theta)
\quad\text{sujeto a}\quad
WR_{\text{val}} \ge 0.75,\ \ n \ge 150 \text{ velas},\ \ \text{días} \ge 15
$$

**Qué es cada símbolo:** $\bar E_{\text{val}}$ y $WR_{\text{val}}$ son la E y el WR (con salida X5) de las velas de validación con $\hat p \ge \theta$.

> **Resultado congelado:** $\theta$ = **0.7142683625605063** (cuantil 0.98 de la validación: opera el 2 % superior). En validación: WR 98.7 %, E 2.18 %, 676 velas.

**Advertencia:** el $\theta$ congelado es mayor que los umbrales del *walk-forward* (0.705, 0.667, 0.695, 0.616, 0.67 y 0.591). Fuera de muestra puede haber **menos de 31 operaciones por moneda y año** (dentro de muestra da 45). **No se relaja $\theta$:** todo cambio de calibración o de umbral perdió entre 8 y 13 pt en diseño.

### 2.9 Co-señal con las 4 anclas

$$
A_{i,t} = \sum_{j \in \mathcal{A},\ j \ne i} \mathbb{1}\!\left[\max_{t-W < s \le t} \mathbb{1}\big(\hat p_{j,s} \ge \theta\big) = 1\right],
\qquad
\text{comprar } i \text{ en } t \iff \hat p_{i,t} \ge \theta \ \text{ y } \ A_{i,t} \ge 1
$$

**Qué es cada símbolo:**

- $\mathcal{A}$ = {BTC, ETH, SOL, DOGE}: las 4 monedas ancla, con las que se diseñó y validó la regla.
- $A_{i,t}$: cuántas anclas **distintas de $i$** dieron señal en la ventana.
- $W$ = 48 velas cerradas (12 h). La ventana **incluye la vela actual** ($t - W < s \le t$), como `roll_any` en `be_breadth.py`.

> **Ejemplo:** a las 14:00, ETH tiene $\hat p = 0.73 \ge \theta$. A las 08:30, SOL tuvo $\hat p = 0.72$. Entonces $A = 1$ y **se compra ETH**. Si ninguna otra ancla dio señal desde las 02:00, la señal es **aislada** y no se compra. Para comprar LINK, alguna de las 4 anclas tiene que haber dado señal en las últimas 12 h.

**Por qué funciona:** si caen varias monedas a la vez, suele ser un pánico de liquidez que rebota. Si cae una sola, puede haber un vendedor informado. En diseño, las señales con co-señal ganaron 85.5 % (+1.90 %) y las aisladas, 75.9 % (+0.88 %).

**Usar $A \ge 1$, no $A \ge 2$:** con $A \ge 2$ la ventaja del modelo sobre el azar condicionado desaparece (+3.3 pt, $t = 0.29$); todo lo pone el día.

### 2.10 Salida X5 con barrera de 96 h

$$
TP = c\,(1 + 0.7\,s_d),\qquad SL = c\,(1 - 1.75\,s_d),\qquad H = 384 \text{ velas}
$$

**Qué es cada símbolo:** $c$ es el precio de entrada; $b = 0.4$; $R$ mediano ≈ 7.5 %; si no se toca ninguna barrera en 384 velas (96 h), se vende a mercado.

> **Ejemplo:** entrada 100 con $s_d = 4.31\,\%$: TP = 103.02 (orden límite), SL = 92.46 y cierre forzado a las 96 h.

- Entrada al cierre de la vela de señal; las barreras rigen desde la vela siguiente.
- Empate TP/SL en la misma vela = SL. Hueco bajo el SL = salida a la apertura.
- Una posición por moneda.

**Por qué 96 h y no 72 h (E7):** de 131 operaciones, 8 salían por tiempo a las 72 h con WR 37.5 %. Con 96 h, 5 de ellas tocan el TP y ninguna el SL. En los tres ensambles, las operaciones resueltas entre 72 y 96 h terminan en **18 TP frente a 2 SL**. Con 576 velas el WR es igual y la E baja (+1.99 %).

### 2.11 Riesgo y tamaño de la posición

$$
\text{nocional} = \frac{\text{riesgo por operación}}{R}
$$

**Qué es cada símbolo:** el riesgo por operación es la fracción del capital que se pierde si salta el SL; $R$ es la distancia al SL en % del precio.

> **Ejemplo:** con 0.5 % de riesgo y $R = 7.5\,\%$, el nocional es $0.5/7.5 = 6.7\,\%$ del capital. Con 1 000 USDT: 67 USDT por operación, y tocar el SL cuesta ≈ 5 USDT.

- Máximo **3 posiciones** abiertas ⇒ riesgo por episodio ≤ 1.5 %. El tope cuesta ≈ 0.1 % de E.
- **Pausa** si la pérdida acumulada supera 10 R o si hay 3 episodios negativos seguidos.
- Freno adicional (de la gestión de riesgo general): caída ≥ 10 % desde el máximo, pérdida del día ≥ 5 %, CUSUM y fallos operativos (sección 7.2).
- **No usar Kelly con la E de diseño:** arruinaba entre el 31 y el 55 % de los años simulados.
- Referencia: con el 100 % del capital por operación, el *drawdown* de diseño de la v2 fue de 41 %, y el de la prueba de la v1 habría sido de 73 %.

### 2.12 Costos

Pagar comisiones con BNB (0.075 % por lado) y salir del TP con orden límite baja $c$ de 0.24 % a ≈ 0.19 %. Suma **+0.05 % de E y 0 de WR**. Hay que mantener saldo en BNB y verificar la comisión vigente en la propia cuenta.

### 2.13 Higiene de eventos

Excluir la moneda desde que:

- recibe un aviso de **deslistado** o la **etiqueta de monitoreo** de Binance;
- tiene un **desbloqueo** grande de tokens en ±14-30 días (SOL, NEAR, DOT, FIL, ATOM, UNI, AVAX y similares);
- se listó hace poco.

Los choques con noticia siguen la tendencia; los choques sin noticia revierten. La página de anuncios es un dominio de Binance: **consúltala con la VPN apagada.**

### 2.14 La v3 vela a vela

1. Al cerrar cada vela de 15 min, comprobar que las 18 monedas y BTCUSDT tienen la vela cerrada y los datos de futuros alineados (sección 2.3). Si falta un dato más de 30 min, esa moneda no opera.
2. Calcular las 74 variables y $\hat p$ con ENS13 para cada moneda.
3. Actualizar el registro de señales de las 4 anclas (últimas 48 velas).
4. Para cada moneda con $\hat p \ge \theta$: exigir $A_{i,t} \ge 1$, que pase la higiene, que no tenga posición y que haya cupo (< 3 abiertas) y no haya pausa.
5. Comprar a mercado en menos de 60 s; recalcular TP y SL sobre el precio real de llenado; colocar la OCO; guardar `time_stop_ts`.
6. Vigilar la OCO en cada vela; a las 384 velas, cancelar la OCO y vender a mercado.
7. Registrar todo (incluidos los marcadores de la sección 4.4) y actualizar los interruptores.

---

## 3. Qué resultados esperar

### 3.1 Historial de versiones

| Versión | Diseño (*walk-forward*, 4 monedas) | *Holdout* o monedas nuevas | Lectura |
|---|---|---|---|
| Bot actual, cartera de 4 | 6 854 op, 42.5 %, −0.238 % | 3 205 op, 41.4 %, −0.293 %, PF 0.62. El bot tal cual: 1 569 op, **7.1 %**, −0.374 % | Sin ventaja |
| C1, ridge + MR20 | 467 op, 72.4 % [68.2, 76.2], +0.541 % ($t_{\text{día}}$ 2.22) | 148 op, **60.1 %**, −0.498 % (−1.31) | Rechazado ($z = 2.30$, $p = 0.022$) |
| v1, ENS6, G3 | 132 op, 72.0 %, +0.93 %; ΔWR +16.1 | 6 monedas nuevas: 383 op, **68.7 % [63.9, 73.1]**, +0.41 % ($t_{\text{día}}$ 1.08); ΔWR **+16.9** ($p < 0.001$); ΔE +1.13 % ($p = 0.005$) | Rechazado |
| v2, ENS13, X5 | 188 op, **81.4 % [75.2, 86.3]**, +1.41 %, PF 2.31, $t_{\text{día}}$ 4.8, 6/6 pliegues, 17/18 meses, DSR 0.755 | 8 monedas nuevas: 621 op, **69.4 % [65.7, 72.9]**, +0.32 % ($t_{\text{día}}$ 1.02; +0.002 R); ΔWR +9.4 ($t = 3.29$); ΔE +1.07 % ($p = 0.001$); DSR 0.02 | Rechazado: **el 81 % era selección** |
| v2 + co-señal | 131 op, 85.5 % [78.5, 90.5], +1.90 % | — | Inflado |
| **v3** | 131 op, **87.8 % [81.1, 92.3]** (beta-binomial [81.6, 93.0]), +2.02 % (+2.07 % con BNB), +0.213 R, $t_{\text{día}}$ 5.90, 24 episodios con 92 % positivos, 15/15 meses activos | — | **Cota optimista** |
| **v3 esperada** | — | **WR ≈ 73-79 %, E +0.6 a +1.2 %**, 250-400 op/año con 18 monedas, 70-85 % de meses ganadores | Estimación |

En la v2 sobre monedas nuevas, el límite inferior del WR corregido por la correlación entre operaciones del mismo día baja a **63.4 %**.

### 3.2 Lo demostrado y lo que no

- **Demostrado:** el modelo elige entradas mejores que el azar en 14 monedas nunca vistas (+9 a +17 pt, ≈ +1.1 % de E). Es la primera ventaja del proyecto que se replica fuera de muestra.
- **No demostrado:** la E absoluta. El *holdout* fue bajista: el azar perdía −0.73 % por operación (v1) y la ventaja apenas lo compensó.
- **No validado fuera de muestra:** la co-señal, E7 y D1.
- **La ganancia se concentra:** en la v2, los 10 días más activos (pánicos multi-moneda) reúnen 168 de 621 operaciones con E +1.18 %; el resto tiene E ≈ 0.
- **Medición descriptiva de P1 (2026-10-22)** sobre las 4 monedas originales en 2025-07..2026-09 (periodo ya gastado; no decide nada; `nn/nn_v3_desc.py`, reproduce exacto el v2 de `desc_v2_originales`): P1 = 169 op, WR **75.7 % [68.8, 81.6]**, E **+0.17 %** ($t_{\text{día}}$ 0.37), 10/12 meses positivos; C0 (sin compuerta, 384 velas) = 200 op, 75.5 %, +0.23 %; señales aisladas ($A_4 = 0$) = 49 op, 71.4 %, +0.41 %. Ventaja sobre el azar: +12.9 pt y +0.88 % ($t$ 1.89). **La barrera de 384 velas sube WR y E frente a 288; la compuerta no mejoró en este periodo.** La E absoluta sigue sin distinguirse de 0.
- **El modelo envejece:** por trimestre, la v2 dio 78 % (2025-T3), 71 % (T4), 63 % (2026-T1), 60 % (T2) y 78 % (T3). Salidas: 68 % por TP, 19 % por SL y 13 % por tiempo.

**La información manda, no la arquitectura** (E en *walk-forward*):

| Modelo | Solo velas | Con futuros |
|---|---|---|
| LightGBM | +0.04 % | +0.71 % |
| MLP | +0.20 % | +0.83 % |
| CNN | +0.19 % | +0.37 % |

### 3.3 Robustez de la co-señal

**Aporte de la co-señal:** +4.1 pt y +0.49 % en diseño; **+3 a +6 pt y +0.3 a +0.6 %** esperados fuera de muestra, con −30 % de operaciones.

- **Pliegues:** positiva en los 6 (WR 77, 85, 78, 85, 90 y 96 %). **Monedas:** BTC 89.7 %, ETH 88.0 %, SOL 82.1 %, DOGE 84.2 %.
- **Episodios:** 24, con el 83 % positivos; sin los 5 mayores, E +2.20 %.
- **Sobre el azar condicionado:** +12.0 pt y +1.19 % ($t = 2.76$). El azar con la misma compuerta gana 73.5 %: parte del efecto es "el día era bueno".
- ***Bootstrap* por día:** ΔE frente a $A = 0$ = +1.04 % [+0.15, +1.97], P = 0.010; ΔWR +8.1 pt [−2.2, +19.5], P = 0.066. Son optimistas: lo vigente es agrupar **por episodio**.
- **Deslizamiento extra de 0.5-1 % en los SL:** E baja solo a +1.85 / +1.80 %.
- **Réplicas:** ENS12 79.1 → 83.6 %; ENS12U 76.5 → 78.6 %.
- **Gradiente por vela** ($W$ = 4 h): $A = 0$ → 66.4 % / −0.31 %; $A = 1$ → 79.3 % / +1.29 %; $A \ge 2$ → 88.5 % / +2.50 %.

**E7 (96 h):** +2.3 pt / +0.12 % en ENS13, P(ΔWR ≤ 0) = 0.04; ENS12 +3.4 / +0.21; ENS12U +3.3 / +0.11. Versión honesta (barrera elegida con pliegues anteriores): +1.5 pt / +0.07 %. Mejora 3/6 pliegues y no empeora ninguno. El azar explica el 74 / 56 / 85 % de la mejora, lo que es válido para una regla de salida en la que suben WR y E a la vez. Esperado fuera de muestra: **+1 a +1.5 pt y 0 a +0.1 % de E**. Riesgo: con deriva negativa podría costar E; verlo en el estrés de 2022.

**Cuidado con estas cifras de diseño.** Las cifras de diseño de la co-señal y de la v3 usan el **umbral de cada pliegue** (0.591-0.705, con los modelos del *walk-forward*), no el $\theta$ congelado 0.71427 con el modelo final. En producción rige el congelado: la frecuencia y el WR pueden diferir. Lo que se puede leer con confianza es la **diferencia** que añade cada capa, no el nivel absoluto.

### 3.4 Cifras corregidas y contradicciones resueltas

**Error en `nn_report.summarize`** (**corregido el 2026-10-18** en `nn/nn_report.py`): `Trades.concat` ya ordena por hora de entrada, pero `summarize` reordenaba las monedas con un índice calculado sobre el vector ya ordenado. Con el código viejo, 145 de las 188 operaciones de diseño de la v2 quedaban asociadas a la **moneda equivocada**. El error afectaba al desglose por moneda y al azar "misma moneda y mes" de `nn_report.py`, `nn_v2_report.py`, `nn_eval.py` y `nn_v2_eval.py`. Ahora `summarize` ordena las monedas con la misma permutación que `concat`, igual que `be_common.simulate_entries`. Las cifras agregadas del modelo (n, WR, E) no cambian. Se volvió a firmar el *hash* de `nn_report.py` en `spec_nn.json` y `spec_nn_v2.json`, con una advertencia que lo explica.

| Cifra (re-emitida y verificada por dos caminos) | Antes | Vigente |
|---|---|---|
| Azar de diseño de la v2 | 62.0 % / −0.441 % | **61.7 % / −0.426 %** |
| ΔWR / ΔE de diseño de la v2 | +19.4 pt / +1.85 % | **+19.7 pt / +1.83 %** |
| BTC en diseño (v2) | 80.9 % / +1.85 % | **80.9 % / +0.74 %** (n = 47) |
| ETH en diseño (v2) | 74 % / +0.62 % | **87.1 % / +1.67 %** (n = 31) |
| SOL en diseño (v2) | 85.5 % / +1.64 % | **80.0 % / +1.30 %** (n = 55) |
| DOGE en diseño (v2) | 81.8 % / +1.24 % | **80.0 % / +1.94 %** (n = 55) |
| Azar de diseño de la v1 | 55.2 % / −0.487 % | **55.8 % / −0.409 %** |
| ΔWR / ΔE de diseño de la v1 | +16.7 pt / +1.41 % | **+16.1 pt / +1.34 %** |
| ETH / BTC en diseño (v1) | 41.7 % / −2.29 % y 73.0 % / +1.38 % | **70.8 % / +0.77 %** y **67.6 % / +0.14 %** |

**Siempre fue correcta** la tabla por moneda del *holdout* de la v2 (FIL 73 % … BCH 66 %): sale de `por_moneda`, que se calcula moneda por moneda sin pasar por `summarize`. **Re-emitido el 2026-10-18** con `nn_eval.py` y `nn_v2_eval.py` corregidos: el "WR del azar" de las pruebas en monedas nuevas **se confirma** en 51.7 % (v1) y 60.0 % (v2). Lo que cambia es lo que imprimían esos scripts, que usaban el `summarize` viejo:

| Prueba (monedas nuevas, 2025-07..2026-09) | Modelo (sin cambios) | Azar viejo → corregido | Ventaja corregida: ΔWR / ΔE ($t_{\text{día}}$) |
|---|---|---|---|
| Primaria v1 (6 monedas) | 383 op, 68.7 %, +0.41 % | 54.4 % → **51.7 %** | **+17.0 pt / +1.08 %** (2.86) |
| Primaria v2 (8 monedas) | 621 op, 69.4 %, +0.32 % | 61.7 % → **60.0 %** | **+9.4 pt / +1.00 %** (3.18) |
| Secundaria v1 (BTC, ETH, SOL, DOGE) | 204 op, 60.8 %, −0.22 % | 51.3 % → **54.2 %** | **+6.6 pt / +0.39 %** (0.84) |

Los veredictos no cambian.

| Tema | Versión vieja | Vigente |
|---|---|---|
| Alineación de *metrics* | $T \le t_i + 10$ min | $T \le t_i + 5$ min |
| Ensamble y barrera | ENS6, 348 KB, 192 velas (v1); X5 con 288 (spec v2) | ENS13, 20 archivos (796 KB), X5 con **384** |
| Nombre "v3" | Ensamble con pesos de unicidad | v2 + $A_4$ + 384 velas; aquel ensamble es ENS12U |
| Reentrenamiento | Cada trimestre | **Prohibido** durante la prueba prospectiva |
| *Holdout* de 20 monedas | Confirmaría la co-señal | Solo confirma reglas **dentro** del episodio |
| *Bootstrap* | Por día | Por episodio |
| Tamaño | 1.5 % de riesgo, $w \le 10\,\%$; o 0.5-1 % con nocional 8-16 % | 0.5 % de riesgo, nocional 6.7 %, máx. 3 posiciones |
| Filtro BTC > SMA30 | Hipótesis L1 | No adoptar; solo grabar |
| Pruebas para el DSR | 12 268 / ≈ 12 340 / 12 396 | **12 666** |
| *Metrics* de 2022 | "Desde 2023" | Pendiente de verificar (necesarios para el estrés) |

"17/18 meses" (v2 sin compuerta, meses con E > 0) y "15/15 meses activos" (v3) son métricas distintas, no una contradicción.

---

## 4. Piezas opcionales y con reserva

### 4.1 D1, veto por DVOL bajo (brazo S3)

Si el precio cae **sin que las opciones paguen miedo**, la caída se parece a la de un vendedor informado o estructural (salidas de GBTC, el hack de Bybit). Esas no rebotan.

$$
z_{30}(t) = \frac{\text{DVOL}_{h(t)} - \overline{\text{DVOL}}_{720}}{\sigma_{720}},
\qquad
\text{no comprar en } t \iff z_{30}(t) < -1
$$

**Qué es cada símbolo:**

- $h(t)$: última hora cerrada, con marca $ts$ tal que $ts + 1\text{ h} \le$ apertura de la vela.
- $\text{DVOL}$: índice de volatilidad implícita de Deribit **de BTC**, usado para todas las monedas.
- $\overline{\text{DVOL}}_{720}$, $\sigma_{720}$: media y desviación de las últimas 720 horas cerradas (30 días).
- Fuente: Deribit `public/get_volatility_index_data`, `resolution=3600`, desde 2021-03, gratis y sin clave. No depende de Binance.

> **Ejemplo (ilustrativo):** DVOL 45, media 52 y desviación 5: $z_{30} = -1.4 < -1$, no se compra aunque haya co-señal. Con DVOL 50, $z_{30} = -0.4$ y se compra.

| Ensamble | ΔWR / ΔE sobre la v3 | Vetadas: n, WR, E |
|---|---|---|
| ENS13 (contaminado) | +3.3 pt / +0.33 % | 14, 64 %, −0.50 % |
| ENS12 | +4.1 / +0.41 | 13, 62 %, −0.79 % |
| ENS12U | +2.1 / +0.20 | 54, 69 %, −0.13 % |
| ENS6 | +2.7 / +0.26 | 11, 55 %, −1.32 % |

- **A favor:** P por episodio 0.01-0.05 (Holm 0.04-0.16); percentil 98-100 frente a quitar operaciones al azar; el gradiente se mantiene en 11 de 12 celdas por tercil de $s_d$.
- **En contra:** el azar condicionado explica entre el 63 y el 129 % del efecto; descansa en ≈ 5-7 episodios; el corte salió de mirar 4 cortes y ≈ 30 variables.
- Días vetados: 2024-01-22 y 23 (GBTC), 2024-04-12 y 13, 2024-06-18, 2025-02-21 (hack de Bybit), 2025-04-25, 2025-06-02 y 2025-06-23.
- **Si se confirma:** +0.5 a +2 pt y +0.05 a +0.2 % de E (v3 + D1 ≈ 74-80 %), con 35-45 % de probabilidad de efecto nulo. Solo se confirma con episodios nuevos (2022 o prospectiva). Hay caché en `E:/tmp/r2_data/deribit/dvol_{BTC,ETH}_1h.json`. **Grabar el DVOL desde ya.**

### 4.2 ENS12U, pesos de unicidad (brazo S2)

$$
u_i = \frac{1}{|T_i|}\sum_{t \in T_i} \frac{1}{c_t}
$$

**Qué es cada símbolo:** $T_i$ son las velas que abarca la etiqueta $i$; $c_t$ es el número de etiquetas activas en la vela $t$, **sumando las 4 monedas**; $u_i$ es el peso de la vela $i$ en el entrenamiento.

> **Ejemplo:** si durante una etiqueta hay en promedio 40 etiquetas activas, su peso es ≈ 1/40. Una vela tranquila con 5 activas pesa 8 veces más.

La brecha de WR entre validación y prueba baja en las 5 comparaciones (LightGBM 13.8 → 7.6 y 10.7 → 3.9; MLP 18.8 → 0.8; ENS6 9.7 → 5.8; ENS12 8.6 → 3.9), pero **no sube el WR** (76.5 % frente a 79.1 %, con el doble de operaciones). Lo vuelve más creíble. Se reentrena hasta 2026-09-30, se congela con *hash* y corre como brazo aparte.

### 4.3 S4, palanca de preferencias (no es una mejora)

Desde las 36 h, si no tocó el TP, bajarlo a +0.6 % sobre la entrada. Da 133 op, **90.2 % [84.0, 94.2]** y +1.86 %: +2.4 pt y **−0.16 % de E** frente a la v3. Compra WR con E y es *post hoc*. Solo si priorizas el WR sobre la ganancia.

**S1:** v2 + $A_{18} \ge 3$ (≥ 3 de las otras 17 monedas en 12 h). Brazo secundario.

### 4.4 Hipótesis abiertas: grabar, no adoptar

| Hipótesis | ENS13: ΔWR / ΔE | Problema |
|---|---|---|
| G_BE: la co-señal viene de BTC o ETH | +2.4 / +0.26 | 3/6 pliegues; P 0.14 |
| F_rank1: la moneda que inicia el episodio | +4.3 / +0.22 | −63 % de operaciones; ninguna de ETH |
| Episodio ≥ 3 días después del anterior | +2.8 / +0.38 | n = 60; P 0.23 |
| BTC > SMA30 | +4.7 / +0.34 | ENS12U no lo replica; 2/6 pliegues; habría apagado el bot en el *holdout* |
| H1, rezagados (grabar L4) | +0.8 / −0.04 | Contaminada |
| H5, prioridad por antigüedad bajo cupo | No medible con 4 monedas | Medir en el *holdout* de 20 |
| Liquidaciones exactas | No probado | Hyperliquid tiene marca; `!forceOrder@arr` da 1 por símbolo cada 1 000 ms y probablemente está bloqueado; Coinalyze guarda 1 500-2 000 puntos |
| Tipo de choque (GDELT, LLM clasificador de titulares) | No probado | GDELT dio HTTP 429 vía VPN |

Sin probar todavía: `bookDepth` de futuros y CTREND (segunda manga diaria, que exige correlación ≤ 0.2 y E > 0). Una variable entra al modelo solo si, con ≥ 150 señales prospectivas, muestra un gradiente monotónico con P ≤ 0.10.

---

## 5. Lo que no funciona: no repetir

Cifras de diseño salvo que se indique. Referencia de la v2: 81.4 % y +1.41 %; de la pila con co-señal: 85.5 % y +1.90 %.

| Pieza | Número clave | Por qué falla |
|---|---|---|
| Estrategias actuales (MR, TF, Squeeze, VWAP) | WR = geometría; Δp −1 a +3 pt; E −0.20 a −0.27 % | Sin información |
| Optimizar con 1 mes y 1 196 configuraciones | PBO hasta 0.51; pendiente fuera/dentro −0.81 a −1.17 | Elige ruido |
| 3 447 combinaciones en 15 min / 1 h | 0 con $E_R > 0$ / 45 en mercado alcista, $t$ 2.05 < 4.18 | Rechazado |
| 41 filtros univariados | RSI +7.8 → −3.0 pt; volumen +2.9 → −5.4 | Se invierten |
| Meta-etiquetado logístico | AUC 0.52-0.55; $E_R$ −0.03 | Sin ventaja |
| C1, ridge + MR20 | 72.4 → 60.1 % | Selección; DSR 0.13 |
| TP corto ($b \approx 0.3$), G4 | WR 70-80 %, E −0.17 a −0.31 % | El azar logra lo mismo |
| Ruptura de 4 días en 1 h, *chandelier* | WR 42 %, $t$ 1.29, 3/6 pliegues | Sin evidencia |
| LSTM, Transformer, CNN más grande | Parada en las épocas 1-3; la CNN fue la más débil | Sobreajuste |
| Entrada *maker* escalonada | E por señal +0.61 a +1.22 %; las no llenadas daban +1.5 a +1.95 % | Selección adversa |
| Confirmación por absorción | Se ejecuta el 25-64 %; E +0.32 a +0.70 % | El rebote ocurre en la primera vela |
| Toma parcial + stop a equilibrio; stop a equilibrio puro | 90.4 % "contable" (azar 79.5 %), −0.6 % de E; WR 42 % | WR fabricado; las salidas "en cero" pierden costos |
| SL ancho, salida a 24 h, "tesis rota" | +1.27 / +1.25 / +0.55 % | Peores que X5 |
| Learn-then-Test, selección conforme + BH | BH pidió 80 % y entregó 75.2 % | Sin intercambiabilidad; solo chequeo de honestidad |
| ACI (umbral adaptativo) | 72.5-78.2 % | Persigue ruido |
| Abstención por desacuerdo, isotónica | 78.9 % / 80.5 % | Las señales con más desacuerdo son mejores (84.1 %) |
| *Proxies* de liquidación (*OI flush*) | 77.4 % | Ya están en el modelo |
| $\theta$ más bajo en pánico (Nagel) | 70-72 %, E +0.08 a +0.35 % | Añade beta del día |
| Rezago relativo | 79.8 / 79.6 / 79.0 % por tercil | Sin gradiente |
| Amplitud con precios ($B_{\text{precio}}$, $A_{\text{cap}}$) | Las descartadas ganan igual o más (80.3 %, 82.2 %) | La información está en los futuros |
| Cobertura con corto en BTC | Media: 78.7 % / +0.95 %; entera: 59.6 % / +0.27 % | Pierde en los rebotes; exige margen |
| *Grid* spot | 100 % de ciclos; lotes liquidados −5.7 a −27.9 % | Pérdida en el inventario |
| DCA, martingala | 98.7-99.9 % de ciclos; latente −20 a −46 % | Ruina |
| TabPFN v2 | Pierde AUC en 5/6 pliegues | Neutro |
| Geometría elegida en *walk-forward* | +0.0 pt / −0.09 % | Ninguna domina a X5 |
| Re-entrada tras TP; segunda etapa logística | −3.1 a −4.9 pt; −2.5 a −0.2 pt | Re-entradas ganan 77 %; signos inestables |
| Cortacircuitos tras SL; cupo de 2 o 3 como mejora | −1.4 a 0 pt; −1.4 / −0.5 pt | El cupo queda solo como regla de riesgo |
| Co-firma de ENS12U o de G5 (H10) | −0.2 / +0.6 pt | Sin efecto |
| $\theta$ re-elegido con la compuerta | −8.0 a −8.4 pt / −0.82 % | No relajar $\theta$ |
| H2, TP anclado a la brecha | +1.1 pt / −0.26 % | Solo redistribuye |
| H3, TP por estado | 93.9 %, −1.01 % | Toma parcial disfrazada |
| H4, meta-etiquetado bayesiano | −1.2 pt | Signos contrarios |
| H6 *funding* 24 h; H7 divergencia OI/*taker* | −2.4 / −1.4 pt | Sin mejora |
| H8 calibración beta; H9 Platt mensual | −11.7 a −12.7 pt | La cola de Platt es frágil |
| C1-Coinbase USDT-USD; B1 margen de Bitfinex | −0.6 pt; −2.5 / −0.6 pt | Mixta / negativa |
| Fear & Greed, *stablecoins*, prima coreana, *skew* de Deribit | Sin gradiente | Ruido |
| LLM como decisor, modelos fundacionales de series | Flota LLM: WR 41 % frente a 50 %; los TSFM rinden mal | Solo vale un LLM como clasificador de titulares, hacia adelante |
| *Carry*, *market making*, *Dual Investment*, arbitraje | — | Bloqueado, E < 0 o venta de cola |

**Lecciones comunes:**

1. Lo que **espera** o **recorta** después de la señal pierde los mejores rebotes.
2. Lo que sube el WR sin información nueva lo paga con E o lo esconde en la cola.
3. Toda calibración o cambio de $\theta$ pierde 8-13 pt.

---

## 6. Trampas del WR fabricado

| Trampa | Cómo se ve |
|---|---|
| Geometría | TP corto y SL largo: el azar ya acierta $1/(1+b)$ |
| Pérdidas que no se cierran | Martingala, DCA, *grid*, "mantener hasta que dé ganancia" |
| Contar mal | Cada TP parcial como ganancia; salidas "en cero" como ganadas; órdenes en vez de posiciones |
| Costos irreales | Comisión cero o toda orden límite llenada al tocar el precio |
| Selección | Miles de variantes y se publica la mejor (v2: 81 → 69 %; C1: 72 → 60 %) |
| Fugas del futuro | `create_time` desde el 2024-03-04, velas abiertas, un LLM que "recuerda" precios |
| Ventanas y rankings | "Últimos 90 días" alcistas, *copy-trading* con sobrevivientes, concursos de dos semanas |
| Productos de "rendimiento" | APR "garantizado" que es una prima de opción vendida |

**Antes de creer cualquier WR, exige:** (a) E neta con $t$ agrupado por día; (b) WR del azar con la misma geometría; (c) pérdida máxima y *drawdown* con posiciones valoradas a mercado; (d) número de configuraciones probadas; (e) resultados posteriores al congelamiento. **Si la mejora viene de cambiar la salida, la E también debe subir.**

---

## 7. Especificación para implementar

### 7.1 Estado actual del código

| Pieza | Hoy | Falta |
|---|---|---|
| `src/api/ws-client.ts` | **Corregido el 2026-10-18:** suscrito a `@kline_15m`; la estrategia solo ve velas cerradas (`k.x`), una vez por vela; el TP/SL se vigila con cada precio; la ventana no se congela con posición; sin doble SELL; reconexión con *backoff* | Sincronizar varias monedas por `open_time` (v3) |
| `src/api/rest-client.ts` | Ya redondea cantidad y precio por `stepSize`/`tickSize`, siempre hacia abajo | SL con `ceil`; órdenes `MARKET` con `newOrderRespType=FULL`; OCO |
| `binance-research/quantitative_strategies/` | Bollinger (MR, TF, Squeeze, VWAP, StatArb) con `round(x, 8)`. **2026-10-19:** las cuatro conectadas quedaron `rechazada` en las 4 monedas (*walk-forward*, sección 14 de [matematica-del-bot.md](matematica-del-bot.md)) | — |
| `binance-research/strategy_engine.py` y `optimize.py` | **Corregido el 2026-10-18:** `optimize.py` simula lo mismo que el bot en vivo (paridad verificada) y con costos. **Desde el 2026-10-19:** `ml_evaluator.py` elige con *walk-forward* (6 meses de entrenamiento y 1 de prueba, 38 meses fuera de muestra, validación final reservada) y marca cada estrategia `validada` o `rechazada` en `ml_results.json`; el motor solo carga las validadas y explica por qué una moneda no opera | Estados `prospectiva` y `paridad`, y `strategy_registry.json` |
| `binance-research/server.py` | **Corregido el 2026-10-18:** precarga velas cerradas de 15 min del mismo mercado que el WS (`MARKET_DATA_REST_URL` en `config.py`); descarta duplicados por `open_time` y rellena huecos (`fill_gap`); ZMQ `evaluate` | Mensaje `bars` con velas de varias monedas; precarga ≥ 35 días para la v3 |
| `src/risk/`, OCO, `strategy_registry.json`, `nn_strategy/`, `backtest/` | **No existen** | Crear (secciones 7.3 y 7.4) |

### 7.2 Infraestructura obligatoria antes de operar

| # | Requisito | Detalle clave |
|---|---|---|
| S1 | Datos en vivo = datos del backtest | Velas de 15 min **cerradas**; ventana que nunca se congela; precarga del mismo mercado (testnet o real); entrada en < 60 s (una vela de retraso le costó a C1 ≈ 30 % de E) |
| S2 | Redondeo por filtros | Fórmula abajo |
| S3 | Backtest honesto | `harness.py` y sus 46 pruebas; costos, high/low, empate = SL, $b$ real |
| S4 | Protocolo de validación | Wilson, $t$ por día, ΔE frente al azar, DSR ≥ 0.95, PBO ≤ 0.2, Holm, O'Brien-Fleming |
| S5 | Gestión de riesgo | Topes e interruptores (abajo) |
| S6 | Ejecución verificable | MARKET + OCO + `time_stop_ts` persistente + prueba de paridad |
| S7 | Motor en `HOLD` | Registro de estrategias con estado; dinero real en cero |

$$
TP' = \left\lfloor \frac{TP}{\text{tick}} \right\rfloor \text{tick},
\qquad
SL' = \left\lceil \frac{SL}{\text{tick}} \right\rceil \text{tick},
\qquad
q' = \left\lfloor \frac{q}{\text{step}} \right\rfloor \text{step},
\qquad
\text{válida si } TP' \ge P + \text{tick} \text{ y } SL' \le P - \text{tick}
$$

**Qué es cada símbolo:** tick es `tickSize` (`PRICE_FILTER`); step es `stepSize` (`LOT_SIZE`); $P$ es el precio de llenado.

> **Ejemplo:** DOGE a 0.09000 con TP 0.09150. Con `round(x, 2)` el TP quedaba en 0.09 (igual a la entrada). Con tick = 0.00001: $TP' = 0.09150$.

**Topes adicionales e interruptores** (freno sobre la regla de riesgo de la v3, sección 2.11): nocional por operación ≤ 10 %, total ≤ 40 %, cola total ≤ 6 %; detener con caída ≥ 10 %, pérdida del día ≥ 5 %, racha ≥ 8, CUSUM desde 30 operaciones, revisión a las 150 operaciones con $t_{\text{día}} < 1$, o fallos operativos (deslizamiento > 0.10 % por lado en 50 operaciones, datos con más de 2 velas de atraso).

**Paridad (S6), al menos 2 semanas o 50 operaciones:** velas 100 % idénticas al REST del mismo mercado; señales con Jaccard = 1; deslizamiento ≤ 0.02 % por lado; ≥ 95 % de salidas coincidentes. **La testnet solo valida infraestructura**, nunca la calidad de la señal.

### 7.3 Módulos nuevos en Python (propuesta)

Las rutas de `binance-research/` que no existen hoy son propuestas. El código de investigación vive en `binance-research/data/research/nn/` (no en `research/nn/`).

| Módulo | Entrada | Salida | Notas |
|---|---|---|---|
| `nn_strategy/features.py` | Velas 15 min (18 + BTC) y series de futuros con marcas $T$ | Matriz de 74 variables por moneda y vela | Copia de `nn/nn_common.py`; aplica $T \le t_i + 5$ min y rellenos máximos |
| `nn_strategy/model.py` | Variables; `spec_nn_v2.json`; `models_v2/` | $\hat p$ por moneda | Verifica los SHA-256 al arrancar; Platt por miembro; media |
| `nn_strategy/gate.py` | $\hat p$ de las 4 anclas | $A_{i,t}$ | Búfer de 48 velas cerradas que incluye la actual |
| `nn_strategy/exits.py` | Precio de llenado, $s_d$ | TP, SL, `time_stop_ts` | $TP = c(1 + 0.7 s_d)$, $SL = c(1 - 1.75 s_d)$, 384 velas |
| `nn_strategy/hygiene.py` | Lista manual de deslistados, monitoreo y desbloqueos | Monedas excluidas | Se actualiza con la VPN apagada |
| `feeds/futures_shadow.py` | Archivos diarios de `data.binance.vision` | Series alineadas, con `metrics_missing` | Canal sombra (fase 1); llegan con 1 día de retraso |
| `feeds/dvol.py` | API de Deribit, cada hora | `dvol_{BTC,ETH}_1h` y $z_{30}$ | Brazo S3; no depende de Binance |
| `strategy_registry.json` | — | Estado de cada estrategia | `rechazada`, `paridad`, `prospectiva`, `validada` |
| `shadow/run_daily.py` | Todo lo anterior | Simulación de los brazos P1, C0, S1-S4 y azar | Registra con *hashes*; no ejecuta órdenes |
| `backtest/` | `harness.py` + `test_harness.py` | — | Reemplaza a `optimize.py` y `ml_evaluator.py` |

`strategy_engine.py` solo devuelve señales de estrategias `validada` (o `prospectiva`/`paridad` en testnet); todo lo demás es `HOLD`. `server.py` recibe un mensaje `bars` con las velas cerradas de un mismo `open_time` y precarga ≥ 3 360 velas de 15 min.

### 7.4 Cambios en Node (propuesta)

1. `ws-client.ts`: `@kline_15m`; ignorar velas con `k.x === false`; acumular por `open_time` y enviar a Python. Propuesta para 18 monedas: si a los 60 s faltan BTC o alguna ancla, se omite el instante; si falta otra moneda, solo esa no opera.
2. `rest-client.ts`: `placeMarketOrder` (`MARKET`, `newOrderRespType=FULL`, precio medio = `cummulativeQuoteQty / executedQty`); `placeSellOco` en `/api/v3/orderList/oco` (`LIMIT_MAKER` arriba y `STOP_LOSS` abajo); `getOrderList` y `cancelOrderList`. Verificar la documentación vigente y el soporte en testnet.
3. `src/risk/sizing.ts`: nocional = 0.5 % / $R$, máximo 3 posiciones, con los topes de la sección 7.2.
4. `src/risk/kill-switches.ts`: pausas de la v3 (10 R, 3 episodios negativos) e interruptores, guardados en `orders/risk_state.json`.
5. Barrera persistente: `time_stop_ts = open_time + (384 + 1) · 900 000` ms. Al vencer, cancelar la OCO y vender a mercado.
6. Registro en `orders/trades.csv`: `strategy_id`, `spec_hash`, `entry_fill_price`, `executed_qty`, `oco_order_list_id`, `time_stop_ts`, `exit_price`, `exit_reason`, PnL neto y los marcadores $A_{i,t}$, G_BE, F_rank1 y $z_{30}$.

### 7.5 Reglas anti-fuga: lista de control

- [ ] Solo velas **cerradas**; la decisión se toma en $t_i + 15$ min. *Metrics* con $T \le t_i + 5$ min; *funding* con `calc_time` ≤ $t_i$ + 15 min; relleno solo hacia adelante y con tope.
- [ ] Estandarización con estadísticos del entrenamiento; purga de $H + 1$ velas antes de cada corte.
- [ ] Co-señal con señales de velas ya cerradas; DVOL con horas cerradas.
- [ ] Tras cualquier cambio en las variables: auditoría de los 16 cortes y prueba de alineación (0.84 frente a 0.12-0.16).
- [ ] Ninguna decisión con datos del *holdout* 2025-07..2026-09.

### 7.6 El bloqueo de fapi y sus tres salidas

El modelo necesita cada 5 min el OI, los ratios long/short, el *funding* y la prima. Vienen de `fapi.binance.com`, que responde **HTTP 451** desde tu ubicación.

1. **Sombra diferida:** los archivos diarios de `data.binance.vision` llegan con 1 día de retraso. Bastan para la prueba prospectiva, que no necesita operar en tiempo real. **Descargarlos con la VPN apagada.**
2. **Fuente sustituta en vivo** (Coinalyze, OKX *rubik*), con prueba de equivalencia: correlación de cada variable con la de Binance y repetición de la simulación. Si no es equivalente, reentrenar con esa fuente.
3. **Servidor en una jurisdicción permitida**, cumpliendo los términos de servicio de Binance.

Sin una de las tres, nada se opera en vivo. D1 no depende de Binance.

### 7.7 Monitoreo en vivo

- Frecuencia de señales fuera de ×0.5-×2 de lo esperado en 3 meses.
- WR real frente a $\hat p$ medio con diferencia de más de 10 pt.
- Deriva de las variables clave.
- Pasar a `HOLD` si, con ≥ 30 operaciones, E < 0 con $t < -2$ o el WR cae por debajo del 55 %.

Cómputo: predicción de una vela 1.2 ms; entrenar 6 modelos ≈ 1 min; ~300 MB de RAM (estimado); modelos v2 en disco, 796 KB. Entorno: Python 3.11.4, torch 2.14.1+cpu, lightgbm 4.7.0, numpy 2.4.6, scipy 1.17.1.

### 7.8 Pruebas de aceptación

- Arnés (`test_harness.py`): 46/46.
- Sombra: reproduce bit a bit 3 días de control (2025-06) frente a las predicciones de diseño.
- Redondeo: ninguna operación con $TP' \le P$ o $SL' \ge P$ en las 18 monedas.
- Tamaño: casos sintéticos sin posiciones, con 3 abiertas y con SL lejano.
- Paridad en testnet (sección 7.2) y *hashes* de la especificación, los 20 modelos y los scripts al arrancar.

---

## 8. Hoja de ruta y pre-registro

### 8.1 Fases

**Cada paso que descarga de Binance requiere la VPN apagada.**

| Fase | Prioridad | Plazo | Qué | Criterio |
|---|---|---|---|---|
| 0 | P0 | 1-3 días | Corregir `summarize`, reemitir tablas, firmar el pre-registro con *hash*; repetir sin VPN las 10 sondas de terceros | Si el azar corregido mueve ΔWR más de 2 pt, se anota |
| 1 | P0 | Semanas 1-2 | Canal sombra diario de 18 monedas + DVOL | Reproduce bit a bit 3 días de control (2025-06); faltan ≤ 5 % de los datos |
| 2 | P1 | Semanas 2-6 | *Holdout* fresco de 20 monedas nunca usadas (lista sellada), 2023-01..2025-06 | Solo confirma reglas dentro del episodio (E7: 384 ≥ 288 en WR y E; H5). La co-señal, solo descriptiva |
| 3 | P1 | Semanas 3-6 | Estrés 2022 (LUNA, FTX) con modelo congelado, v3, D1 y topes | Pérdida por episodio ≤ 3 R. Antes, verificar que existan *metrics* de 2022 |
| 4 | P2 | Desde ya | Grabar hacia adelante: DVOL de BTC y ETH, USDT-USD de Coinbase, Bitfinex `…/last`, L4, G_BE, F_rank1, Hyperliquid, anuncios, titulares con LLM | Entra con ≥ 150 señales y gradiente monotónico con P ≤ 0.10 |
| 5 | P2 | Mes 1 | ENS12U reentrenado hasta 2026-09-30 y congelado | Brazo S2 |
| 6 | P0 | Meses 1-15 | Prospectiva con revisión mensual | Aprobar, futilidad o seguir |
| 7 | P3 | Solo si aprueba | Operación real pequeña con BNB, TP límite y topes | 3 meses con deslizamiento ≤ 0.1 % por lado |
| B | P3 | En paralelo | CTREND en velas diarias | Correlación ≤ 0.2 y E > 0 |

**Qué confirma cada fuente:** las reglas **de episodio** (co-señal, D1, G_BE) solo se confirman con el estrés 2022 o la prospectiva, porque el *holdout* de 20 monedas cubre los mismos pánicos que el diseño. Las reglas **dentro del episodio** (E7, H5) se confirman con cualquiera de las tres.

### 8.2 Pre-registro y brazos

Redactado el 2026-10-15 y actualizado el 2026-10-16. **Especificación congelada:** `spec_nn_v2.json` con los *hashes* de la especificación, los 20 archivos de modelo y los scripts; salida X5 con 384 velas; universo de 18; regla $T \le t_i + 5$ min.

| Brazo | Regla | Papel |
|---|---|---|
| **P1** | v3 = v2 + $A_4 \ge 1$ ($W$ = 12 h) + 384 velas | Primario |
| C0 | v2 sin compuerta | Control |
| S1 | v2 + $A_{18} \ge 3$ | Secundario |
| S2 | ENS12U + $A_4 \ge 1$ | Secundario |
| S3 | v3 + D1 | Secundario; regla de episodio |
| S4 | v3 + TP a +0.6 % desde las 36 h | Opcional |
| Azar | Misma moneda, mes y geometría; y azar condicionado a $A_4$ | Referencia |

Costos: 0.24 % (principal), 0.30 % (estrés), 0.19 % (informativo). **Periodo:** desde 2026-10-01 hasta 400 operaciones de P1 o el 2027-12-31, lo que llegue primero (12-18 meses esperados). Con WR 76 % hacen falta ≈ 225 operaciones independientes, ≈ 400-450 con $DEFF \approx 2$.

### 8.3 Criterios de aprobación de P1

Todos, con $c = 0.24\,\%$ salvo que se indique otra cosa:

1. E > 0 con $t$ por día ≥ 1.645, y E > 0 también con $c = 0.30\,\%$.
2. Límite inferior de Wilson ≥ 0.70 ("aprueba 70") o ≥ 0.75 ("aprueba 75"). **El 80 % solo se declara con límite inferior ≥ 0.80.**
3. ΔE frente al azar > 0 con $t$ ≥ 1.645, y ΔWR > 0.
4. E(P1) − E(C0 con $A_4 = 0$) > 0, con P ≤ 0.10 por *bootstrap* (el pre-registro dice por días; reportar también por episodio, que es más estricto).
5. ≥ 60 % de los episodios en positivo.
6. *Hashes* intactos. Todo lo demás es "exploratorio".

**Criterio de S3:** con ≥ 150 señales de P1, las vetadas por D1 deben tener menos WR, con P ≤ 0.10 en *bootstrap* por episodio y ≥ 5 episodios vetados.

Ojo con el criterio 2: el intervalo de Wilson de C1 (338 aciertos en 467, $\hat p = 72.4\,\%$) fue [68.2 %, 76.2 %], así que no permitía afirmar "≥ 70 %" aunque el WR observado lo superara.

### 8.4 Vigilancia mensual con e-procesos y futilidad

Mirar cada mes y detenerse cuando "se ve bien" infla los falsos positivos. Un e-proceso permite mirar cuando se quiera:

$$
M_n = \prod_{i=1}^{n}\big(1 + \lambda_i\,(X_i - p_0)\big),
\qquad \text{rechazar } H_0: p \le p_0 \ \text{ si } \ M_n \ge 20
$$

**Qué es cada símbolo:**

- $X_i$: 1 si la operación $i$ ganó (neto > 0) y 0 si perdió.
- $p_0$ = 0.70: el WR que se quiere superar.
- $\lambda_i \in [0, 1.43]$: tamaño de la apuesta, elegido **solo** con operaciones anteriores.
- 20 = $1/\alpha$ con α = 0.05.

> **Ejemplo:** con $\lambda = 0.5$, cada acierto multiplica $M$ por 1.15 y cada fallo por 0.65. Con WR real de 78 %, $\ln M$ crece $0.78 \ln 1.15 + 0.22 \ln 0.65 = +0.014$ por operación y llega a $\ln 20 = 3.0$ en ≈ 210 operaciones independientes. Con WR 70 %, no crece.

Para la E se usa lo mismo con la media diaria de resultados en R, recortados a [−1.2, 0.6] y $\lambda_d \in [0, 0.8]$. Si se usan revisiones clásicas, el gasto de α de O'Brien-Fleming es 0.00009 al 25 % de la muestra, 0.0056 al 50 % y 0.0236 al 75 %.

**Futilidad:** con ≥ 200 operaciones, si el límite superior de Wilson es < 0.70 o el intervalo de E queda entero bajo 0, se detiene y se declara "no aprobado".

### 8.5 Prohibiciones y dinero real

- **Durante la prueba no se cambian** $\theta$, la geometría (incluida la barrera de 384), el corte de D1, el universo ni $W$. No se reentrena la v2. No se usa el *holdout*.
- **No hacer:** *grid*, DCA, martingala, toma parcial o TP por estado, recalibrar $\theta$, LLM como decisor, entradas *maker* o confirmadas, nada que requiera ejecutar futuros.
- **Dinero real:** $w = 0$ hasta aprobar. Después, empezar con $w = 0.05$ y nunca más de 0.25 o ¼ de Kelly calculado con la E en su cota inferior.

---

## 9. Dónde está todo

Raíz: `E:\GitHub\binance-trading-bot\binance-research\data\research\` (ignorada por git).

| Ruta | Contenido |
|---|---|
| `output/constructor/spec_nn_v2.json` | Especificación congelada de la v2: variables, Platt, $\theta$, *hashes*, entorno |
| `output/constructor/spec_nn.json` | v1 ($\theta$ 0.7133642) |
| `output/constructor/` | `fase1.md`, `fase3.md`, `guia_nn.md`, `wf_results.jsonl`, `wf_results_v2.jsonl` |
| `nn/models_v2/` | 20 archivos, 796 KB: `lgb_G3_s0..s5.txt`, `mlp_G3_s0..s5.pt` + `_scaler.npz`, `cnn_G3_s0.pt` + `_scaler.npz` |
| `nn/models/` | v1, 9 archivos, 352 KB |
| `nn/` | `nn_common.py` (variables y alineación), `nn_build.py`, `nn_wf.py`, `nn_final.py`, `nn_v2_final.py`, `nn_eval.py`, `nn_v2_eval.py`, `nn_report.py`, `nn_v2_report.py`, `nn_download_futures.py`, `nn_log_trials.py`, `nn_v2_log_trials.py`, `nn_stats.py` |
| `scripts/` | `harness.py`, `HARNESS.md`, `test_harness.py`, `download_klines.py`, `download_1s.py`, `bot_replica.py`, `reproduce_ml_results.py`, `C1_eval.py`, `C1_eval_v2.py`, `holdout_C1_run.py` |
| `scripts/be_*.py` | Primera iteración; `be_common.py` contiene `simulate_entries` corregido; `be_breadth.py`, la co-señal |
| `scripts/be2_*.py`, `be2b_*.py`, `be2c_*.py` | Segunda iteración; `be2_v3.py` es la pila v3 con 384 velas; `be2c_dvol.py`, D1 |
| `verificador/verify.py` | Verificación independiente; datos en `verificador/data` (14 monedas), `data_v2` (8), `data_sec`; corridas en `verificador/runs/` |
| `output/verificador/` | `preregistro_nn(_v2).md`, `auditoria_nn(_v2).md`, `ejecuciones_log.csv` |
| `output/bleeding_edge/`, `output/bleeding_edge_r2/` | Informes, predicciones (`preds/`) y `laboratorio_consolidado.md` |
| `output/validador/` | `trials_log.csv` (12 666 configuraciones) y `holdout_log.csv` (12 entradas; la última, `be_structural_bear`) |
| `output/analista/C1_spec_v2.json` | Especificación de C1 (rechazado) |
| `klines/`, `futures/` | Solo las 4 monedas de diseño |
| `tmp/be2_geom/` | Caché de etiquetas por geometría |

Fuera de la carpeta, en E: `E:/tmp/r2_data/` (Bitfinex, Coinbase, DefiLlama, Deribit, Fear & Greed, Upbit), `E:/tmp/r2_probe`, y los temporales de TabPFN (`E:/tmp/be_pkgs`, `E:/tmp/be_dl`, `E:/tmp/be_tabpfn_stub.py`, `E:/tmp/be_tabpfn_probe.py`, `E:/hf-cache`).

**Bot actual:** `src/api/` (`rest-client.ts`, `ws-client.ts`, `zmq-client.ts`, `telegram-client.ts`) y `binance-research/` (`server.py`, `strategy_engine.py`, `quantitative_strategies/`, `optimize.py`). La matemática que usa hoy está en [matematica-del-bot.md](matematica-del-bot.md), partes 7 y 8.

**Citados antes pero inexistentes** (son propuestas pendientes): `binance-research/nn_strategy/`, `strategies/`, `backtest/`, `strategy_registry.json`, `doc/especificaciones/`, `src/risk/sizing.ts`, `src/risk/kill-switches.ts`, `src/api/exchange-filters.ts` (el redondeo ya vive en `rest-client.ts`) y `orders/risk_state.json`.

---

> **En una frase:** la v3 compra solo **capitulaciones que ocurren en un pánico de mercado** y les da **96 h para rebotar**. En diseño marca 88 %, pero lo honesto es esperar **≈ 73-79 % con E de +0.6 a +1.2 %**. Antes de operar hay que construir la infraestructura honesta, resolver el acceso a los datos de futuros y dejar que la prueba prospectiva decida.
