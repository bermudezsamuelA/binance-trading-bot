# Agente RL y esperanza positiva

Este documento resume lo que se investigó sobre el agente de aprendizaje por refuerzo (RL) de la [§20 de la matemática del bot](matematica-del-bot.md) y sobre cómo llevar el bot a una **esperanza neta positiva**. Las cifras salen de experimentos con los datos locales (velas de 15 min, 2023-01 a 2026-10-14) con las cuatro estrategias del modo experimental: BTC VolatilitySqueeze 96/2.0, ETH VWAP 84/2.6, SOL VolatilitySqueeze 64/3.2 y DOGE TrendFollowing 12/2.8. Todas usan 15 USDT por operación y un costo de 0.12 % por lado (0.10 % de comisión y 0.02 % de deslizamiento).

**Notación.** $E$ = PnL neto medio por operación (en % del nocional o en $R$). $R$ = riesgo inicial, entrada − SL. WR = tasa de operaciones con PnL **neto** > 0. $b$ = TP/SL en múltiplos de $R$. $c_R$ = costo de ida y vuelta medido en $R$. MFE/MAE = máximo movimiento a favor / en contra desde la entrada, en $R$. OOS = fuera de muestra. IC = correlación entre una variable y el resultado futuro.

## 1. Respuesta corta

- **El agente no puede crear ventaja donde no la hay.** Con las entradas actuales el precio se comporta casi como una martingala después de entrar: cualquier regla de salida deja la misma esperanza bruta (cero) y solo cambia la forma de la distribución. Subir el WR sin información nueva es geometría, no ganancia.
- **"Fabricar" WR es trivial y no sirve.** Un *lock-in* (subir el SL a ganancia tras $+m\,R$) da WR $= 1/(1+m)$: 71 % con $m = 0.4$. Los stops a equilibrio y las barreras de tiempo subieron el WR en los datos del bot y **bajaron** la $E$ en todos los casos.
- **Lo que sí sube la $E$ hoy es barato y no es RL:** pagar comisiones con BNB (+0.05 % por operación, PnL de +5.96 a +17.75 USDT en 2023-01..2026-08) y dejar de operar lo que no tiene ventaja (solo SOL Squeeze tiene $E$ claramente positiva).
- **Lo que copian los profesionales rentables es el proceso, no el WR:** operar solo setups con $E$ medida fuera de muestra, apagar automáticamente lo que deja de pagar, ejecutar barato y limitar el riesgo de cartera. Todo eso se automatiza con reglas, sin RL.
- **Las salidas aprendidas no mejoran nada con el estado observable.** Ninguna variable predice el PnL restante de forma estable ($|\rho| < 0.045$ dentro de muestra) y el prototipo de parada óptima con LightGBM empata con la salida fija fuera de muestra (t = −0.20 y +0.30).
- **Si se construye el agente, que sea así:** decide al cierre de vela, recompensa = PnL neto en $R$, algoritmo supervisado *offline* (mejora de política en un paso o *fitted-Q* con LightGBM), PPO solo como ajuste fino. Se acepta solo si gana en $E$ en una prueba pareada con corrección de Bonferroni; "rechazado" es un resultado esperable y válido.
- **El WR alto con ganancia exige ventaja en la entrada**, no en la salida: la estrategia v3 llega a ≈ 73–79 % fuera de muestra porque gana entre +9 y +17 puntos sobre el azar en la entrada.

## 2. Por qué subir el win rate no basta

**Teorema de parada opcional.** Si el precio después de la entrada es una martingala, para toda regla de salida acotada $\tau$ (cerrar antes, *trailing*, equilibrio, toma parcial, SL más ancho):

$$
\mathbb{E}[X_\tau] = 0 \;\Rightarrow\; E_{\text{neta}} = -c_R
$$

- $X_\tau$: ganancia bruta en $R$ al salir en el instante $\tau$.
- $c_R$: costo de ida y vuelta en $R$ (0.17 $R$ de media en el bot, 0.48 $R$ con el riesgo mínimo de 0.5 %).

La salida solo cambia la forma: mucho WR con ganancias pequeñas y cola gruesa, o al revés. El WR de equilibrio con costos es:

$$
p^{*} = \frac{1 + c_R}{1 + b}
$$

- $p^{*}$: WR mínimo para $E = 0$; $b$: relación TP/SL.

El WR fuera de muestra actual es el del azar, $1/(1+b)$: MeanReversion 49.9 % (azar 50 %), TrendFollowing 33.2 % (33.3 %), VolatilitySqueeze 29.9 % (28.6 %). Las entradas no tienen ventaja medible y el WR que se ve es geometría.

**Monte Carlo con paseo aleatorio** (60 000 trayectorias, $R = 2\,\%$, $c_R = 0.12$):

| Política de salida | WR neto | $E$ ($R$) |
|---|---|---|
| Fija, TP +1 / SL −1 | 49.7 % | −0.125 |
| TP corto +0.5 | 65.7 % | −0.121 |
| 50 % en +0.5 y el resto a equilibrio | 65.7 % | −0.121 |
| SL ancho −2 ("aguantar") | 62.4 % | −0.131 (y pérdida máxima doble) |
| *Trailing* 1 $R$ sin TP (esqueleto de la §20) | 32.8 % | −0.126 |

En las ocho políticas simuladas el WR va del 30 al 66 % y la $E$ queda siempre en ≈ $-c_R$.

**Datos reales del bot** (2023-01..2026-08, 1 569 operaciones base):

| Salida | WR | $E$ %/op | PnL USDT | Lectura |
|---|---|---|---|---|
| **Base TP/SL actual** | 40.4 % | **+0.025** | +5.96 | Línea a batir |
| Equilibrio (BE) tras +0.5 $R$ | 55.1 % | −0.078 | −24.92 | WR fabricado |
| BE tras +1.5 $R$ (mejor regla simple) | 44.7 % | −0.002 | −0.53 | WR fabricado |
| Barrera de tiempo 16 velas | 41.0 % | −0.160 | −58.52 | WR fabricado |
| *Trailing* 1 % +TP (esqueleto) | 32.4 % | −0.186 | −64.90 | Peor que la base |
| Chandelier 4·ATR +TP | 34.5 % | −0.139 | −45.32 | Peor que la base |
| Azar dentro de la ventana (20 semillas) | 42.1 % | +0.034 | +11.10 | La base no supera al azar |
| Oráculo dentro de la ventana | 67.3 % | +1.292 | +390.24 | Techo inalcanzable |

Ninguna regla simple supera a la base, ni siquiera en el periodo donde se eligió su parámetro. La salida actual tampoco demuestra habilidad: su $E$ no se distingue de cero (t = 0.29) y solo supera al 36 % de las semillas que salen en una vela al azar dentro de la misma ventana. En SOL, la única estrategia con ventaja, todas las alternativas recortan ganadores.

**Cuándo una salida sí sube WR y $E$ a la vez.** Solo si hay deriva condicional predecible dentro de la operación:

$$
\Delta E \approx 0.4\,\rho\,\sigma_{\text{rem}}
$$

- $\rho$: correlación (IC) entre la señal y el PnL restante; $\sigma_{\text{rem}}$: desviación del PnL restante (1.44–1.47 $R$ medida).

Para cubrir 0.12 $R$ de costos hace falta $\rho \approx 0.3$; un buen IC intradía en cripto está entre 0.02 y 0.05. Incluso un oráculo perfecto del signo de una deriva de ±1.9 %/día solo lleva la $E$ de −0.25 % a +0.13 %.

## 3. Prácticas de traders profesionales que sí dan esperanza

Menos del 1 % de los *day traders* de Taiwán (1992–2006) gana de forma predecible tras comisiones; en Brasil, de quienes hicieron *day trading* más de 300 días, ~97 % perdió dinero. La ventaja de los profesionales no está en "acertar más": está en **operar solo lo que tiene esperanza medida, no destruirla con costos y sobreajuste, y dejar de operar cuando deja de pagar**. La gestión del riesgo no convierte una $E$ negativa en positiva; solo la escala o la protege. Kelly lo dice formalmente: con $E \le 0$, la fracción óptima es $f^{*} = 0$.

Efecto: **E** = sube la esperanza del conjunto; **R** = reduce riesgo o cola, no la $E$ por operación. Estado en el bot: ✅ existe · 🟡 parcial o solo en investigación · ❌ falta.

| # | Práctica | Evidencia | Efecto | Cómo automatizarla aquí | Estado |
|---|---|---|---|---|---|
| 1 | **Operar solo setups con $E$ fuera de muestra demostrada**, corregida por pruebas múltiples | Harvey-Liu-Zhu (con muchas pruebas, t > 3); Sharpe deflactado y PBO | E (la mayor) | Tabla de $E$ en $R$ por estrategia × moneda, neta de costos, con intervalo de confianza *bootstrap*; operar solo si el límite inferior > 0 y DSR > 0. Hoy pasaría solo SOL Squeeze; el resto, en sombra | ✅ walk-forward · ❌ DSR/PBO, tabla |
| 2 | **Interruptor por $E$ móvil** con reactivación desde sombra | Práctica de CTA (Carver); *strategy risk* de López de Prado | E si la degradación persiste | Por setup, $E$ de las últimas 30–50 operaciones (o CUSUM en $R$): apagar si $E + 1.0\,SE < 0$; reactivar si en sombra $E - 0.5\,SE > 0$. Persistir en disco | ❌ |
| 3 | **Ejecutar barato** | Novy-Marx y Velikov: las anomalías de alta rotación mueren tras costos | E | Comisiones con BNB (§4); TP con LIMIT/OCO; no entrar si el objetivo < 2–3× el costo | ✅ costos en backtest · ❌ BNB, maker |
| 4 | **Filtro de régimen** de mayor marco (TSMOM de BTC 1d/7d, tendencia frente a lateral) | Liu y Tsyvinski (RFS 2021), Moskowitz-Ooi-Pedersen, Kaminski y Lo | E en la literatura | Como **variable** del filtro de entradas, no como regla dura: en este bot, "BTC sobre su media de 30 días" conservó señales **peores** (t = −3.47) | 🟡 HMM solo en investigación |
| 5 | **Comprar la sobrerreacción tras caídas extremas** con capitulación taker | De Nicola (2021); Miralles-Quirós (2022): solo tras *shocks* negativos | E (encaje natural para un bot solo largo en spot) | Disparar si $r_{1h} < -k\,\sigma_{1h}$ ($k$ = 2.5–3), `imb_z` < −2, volumen relativo > 3 y rango > 3·ATR; salida por tiempo de 1–4 h. Es una señal base nueva, no un ajuste de salida | ❌ |
| 6 | **Flujo taker** como *timing* y entrada maker | Kitron y Wengrowicz: reversión a 15 min en 90 % de 183 pares, pero ~1.3 pb brutos frente a 5 pb de costo | E pequeña, no rentable sola | `imb = 2·taker_buy/volumen − 1`, su z-score y CVD de 4/16/96 velas como variables; no comprar en la vela de un impulso comprador extremo | ❌ (los datos vienen en la vela) |
| 7 | **Meta-etiquetado: filtrar la señal, no reemplazarla** | López de Prado, AFML cap. 3; Hudson & Thames con Bollinger: +3 a +6 pp de precisión | WR y E si predice el resultado neto | Clasificador o regresión LightGBM tomar/omitir con etiqueta neta de triple barrera, entrenado en walk-forward purgado; es el "RL" de entrada correcto (§5) | ❌ |
| 8 | **Salida coherente con la fuente de ventaja** | Kaminski y Lo: los stops ayudan solo con *momentum*; Odean (efecto disposición) | E | Ruptura (Squeeze): SL 1 $R$ y dejar correr; reversión: TP en la media y salida por tiempo. Nunca *trailing* en reversión ni TP corto en ruptura | 🟡 SL/TP fijos por estrategia |
| 9 | **Liquidez y eventos** | Baur et al.: el calendario no persiste; Kaiko: el volumen de fin de semana cayó a ~13 % | R (menos costo y cola) | Sin rupturas en fin de semana o con volumen relativo < 0.7; sin entradas de 30 min antes a 60 min después de CPI/FOMC | ❌ |
| 10 | **Tamaño por riesgo y volatilidad**, ≤ ¼ Kelly sobre $E$ encogida | Van Tharp; Moreira y Muir; Harvey et al. (2018) | R | Nocional × clip(vol objetivo / σ, 0.5, 2); recompensa en R-múltiplos. En este bot el riesgo fijo por operación **empeoró** (§4) | ❌ (15 USDT fijos) |
| 11 | **Cortacircuitos de cartera** | Grossman y Zhou (exposición ∝ distancia al piso de *drawdown*); límites de *prop firms* | R | Sin entradas tras −3 $R$ en el día o −6 $R$ en la semana; riesgo abierto total ≤ 2 $R$ (las altcoins se mueven con BTC) | ❌ |
| 12 | **No escalar ni promediar a la baja** | Promediar sube el WR y crea cola izquierda (martingala) | Evita perder E | Con 15 USDT y un mínimo de ~5 USDT, escalar deja restos invendibles y duplica costos | ✅ no se hace |
| 13 | **Diario estadístico** (R-múltiplos, MAE/MFE, $E$ por celda, señales omitidas) | Van Tharp; Carver; Clenow | E indirecta | Ampliar `report.py` con `R_mult`, `MAE_R`, `MFE_R`, velas en la operación y régimen; es el *dataset* del agente | 🟡 informes sin $R$ ni MAE/MFE |

**Mitos (no automatizar):** el 80 % de WR como objetivo, Fibonacci, *smart money concepts* sin cuantificar, el 1:2 fijo por sí mismo, la estacionalidad horaria como señal y las tomas parciales en estrategias de tendencia (suben el WR y cortan la cola derecha).

## 4. Lo que dicen hoy los datos de este bot

Desarrollo = 2023-01..2026-08 (1 569 operaciones); RES = 2026-09-01..10-14 (48 operaciones, solo comprueba el signo).

| Medida | Efecto medido en $E$ | Efecto en WR | Veredicto |
|---|---|---|---|
| **Comisiones con BNB** | +0.05 %/op (+0.036 $R$); PnL +5.96 → +17.75 USDT | Ninguno (40.4 %) | **Hacer ya.** Sin cambio de órdenes; vigilar el saldo de BNB |
| TP con orden LIMIT (maker) | +0.009 %/op (+0.006 $R$) | Ninguno | Valor de ejecución (precio exacto), no de costo |
| Maker en las dos patas | En $R$ sigue negativa (−0.009 $R$) | Ninguno | La entrada LIMIT sufre selección adversa; no hacerlo |
| Costo cero (cota) | BTC +0.111 %, ETH +0.040 % | Ninguno | BTC y ETH no tienen ventaja bruta: el problema no es el costo |
| Solo SOL Squeeze | SOL +0.887 %/op (257 ops); BTC −0.129, ETH −0.200, DOGE −0.019 | — | La única ventaja real del conjunto |
| Selección por *momentum* de 12 meses | +0.244 %/op; MDD 27.6 → 10.0 USDT | 38.1 % (no sube) | Prometedora, **no demostrada**: ninguna variante pasa Bonferroni (α = 0.005); en RES la base fue mejor |
| Nocional ∝ $E$ de 12 meses (0–2×) | +0.364 % por USDT; PnL/MDD 2.42 frente a 0.22 | No sube | Regla base que el RL de tamaño debe batir |
| Riesgo fijo por operación | PnL −26.67 USDT | No sube | **Descartar**: da más nocional a los SL estrechos, donde el costo domina |
| Filtro riesgo ≥ 1.5 % del precio | +0.157 %/op; PnL +21.25 | — | Hipótesis: no es monótono y RES no lo confirma |
| Geometría TP/SL (72 variantes) | SOL: meseta positiva con TP 2–4 $R$ y SL 1 $R$; ETH y DOGE: las 18 geometrías pierden en 2026-01..08 | TP alto baja el WR | Mantener la actual; el problema de ETH y DOGE es la entrada |
| Quitar el TP y seguir la media | SOL: +1.27 → −0.10 %/op en 2026-01..08 | — | Empeora las 3 estrategias de tendencia |
| Día de la semana | Lunes y martes negativos en 2023–25 y en 2026 (Spearman +0.71) | — | Única variable de calendario algo estable |
| Hora UTC y volatilidad relativa | Bloque 08-12h: +0.18 → −1.24; vol 1d/30d **se invierte** (Spearman −0.80) | — | No usar como filtro fijo |
| Co-señal entre monedas (12 h) | ΔE +0.26 pp en 2026; +0.19 pp de media; mejora en 3 de 4 años | No sube (−3.4 a +1.7 pt) | Candidata a hipótesis prerregistrada; actúa como apuesta a la beta |
| Filtro LightGBM (20 % superior) | +1.28 % dentro de muestra → −0.21 % fuera | 57.4 % → **37.3 %** | Sobreajuste (AUC 0.714 → 0.577; ≈ 0.5 dentro de cada moneda) |
| *Bandit* con exploración (Thompson, LinUCB) | −0.149 % y −0.260 % frente a +0.090 % y +0.284 % con información completa | Menor | Explorar cuesta datos sin aportar: el resultado de cada señal se puede simular |
| Variables de estado para la salida (22) | Pearson OOS de ridge y LightGBM: −0.16 a −0.19 → ΔE ≈ −0.10 a +0.02 $R$ | — | Ninguna predice el PnL restante; 2026 invirtió la relación ("dejar correr" pasó a devolver ganancias) |
| Prototipo de parada óptima (CLOSE, BE) | 2026-01..08: −0.43 USDT (t = −0.20) y +0.45 USDT (t = +0.30); RES: 0 | +0.5 a +1.0 pt | Empata con la base; los +24.57 USDT (t = 4.48) dentro de muestra eran sobreajuste |

**Tamaño de muestra.** Para detectar ΔE = 0.02 $R$ en una prueba pareada hacen falta 6 107 operaciones con α = 0.05 y 12 631 con α = 0.003125; para 0.076 $R$, 466 y 964. Para un ΔE de 0.25 pp por moneda, ≈ 1 300 operaciones; hay entre 160 y 480 por moneda en 2023–25. **Una mejora realista de salida no es demostrable con los datos actuales.**

## 5. Diseño del agente recomendado

### Qué decide

| Decisión | Puede subir $E$ | Prioridad |
|---|---|---|
| Entrada: tomar u omitir (y tamaño 0/0.5/1/2×) | Sí, si quita señales con $E[G \mid x] < 0$ | 1.ª |
| Salida: parada óptima | Solo si hay deriva predecible (hoy no la hay) | 2.ª |
| Geometría TP/SL | No (meseta en SOL, pérdida en ETH y DOGE) | No darla como acción |

El filtro de entradas es un *bandit* de dos brazos con **información completa** (la recompensa de omitir es 0 y la de tomar se simula), así que equivale a regresión supervisada (*meta-labeling*). Con 15 USDT el bot no mueve el precio: el resultado de cualquier acción se calcula exactamente con las velas. Por eso no hacen falta exploración, CQL ni IQL.

### Estado, acciones y recompensa

- **Paso:** cierre de cada vela de 15 min. El TP y el SL se siguen vigilando con cada precio, como ahora.
- **Estado** normalizado en $R$ y en $\sigma$: $u_t = (P_t - P_e)/R_0$, MFE, MAE, nivel del stop, distancias a TP/SL en $\sigma$, velas transcurridas, costo en $R$ (0.24 % / riesgo), $E$ reciente del par (3 y 12 meses), día de la semana, retornos propios y de BTC (1d/7d), régimen (HMM, *Efficiency Ratio*), flujo taker (`imb`, `imb_z`, CVD), PnL del día en $R$ y riesgo abierto total. Ninguna variable entra sin demostrar antes IC > 0.1 fuera de muestra.
- **Reglas duras fuera del agente** (no se aprenden ni se negocian): límites de pérdida diaria y semanal, tope de riesgo abierto, interruptor por $E$ móvil y nocional mínimo y máximo.
- **Acciones de salida (v1):** `HOLD`, `CLOSE`, `SL_BE` (entrada × (1 + 2 × 0.0012)), `SL_TRAIL_1σ`, `SL_TRAIL_2σ`. El stop solo sube; el TP no cambia; nada de DCA, martingala ni *grid*. Barrera de tiempo de 384 velas.
- **Recompensa = PnL neto en $R$** por posición, con $\gamma = 1$. Prohibido premiar conteos (aciertos, "no tocar el SL"): con $r = \text{PnL} - \lambda\,\mathbb 1\{\text{pérdida}\}$ el agente maximiza el WR por geometría. Línea base pareada: $r = \text{PnL}_{\text{agente}} - \text{PnL}_{\text{fijo}}$ sobre la misma entrada (baja la desviación de ≈ 1.0 a 0.66 $R$).
- **Costos de entrenamiento:** los actuales (o un deslizamiento algo peor), nunca costo cero: con costo cero aprende a cortar pronto y pierde en real.

### Algoritmo

**Mejora de política en un paso** (primera versión del "RL"):

$$
A(s_t, a) = \hat E\big[G \mid s_t, a,\ \text{luego } \pi^0\big] - \hat E\big[G \mid s_t, \pi^0\big],
\qquad a^{*} = \arg\max_a \hat A \ \text{ si } \hat A > \delta
$$

- $G$: PnL neto final en $R$; $\pi^0$: salida fija TP/SL; $\delta$: margen mínimo elegido fuera de muestra.

Después, *fitted-Q* por inducción hacia atrás con LightGBM (variante Longstaff–Schwartz: usar el flujo realizado bajo la política estimada, no $\max \hat Q$, para evitar el sesgo del máximo). PPO solo como ajuste fino de la política supervisada, con penalización KL, al menos 5 semillas y reportando la media. LightGBM además cumple el límite de inferencia en vivo (< 10 ms, porque el REQ de ZMQ no tiene *timeout*).

### Criterio de aceptación

1. **Walk-forward** del bot (38 pliegues, 6 meses de entrenamiento y 1 de prueba, embargo de $H$), hiperparámetros congelados de antemano y costos de 0.12 % por lado.
2. **Prueba pareada:** ΔE (agente − salida fija, mismas entradas) > 0 con prueba $t$ de una cola sobre la suma diaria de diferencias y **Bonferroni** $\alpha = 0.05/K$ ($K = 16$ → 0.003125).
3. **Antifabricación:** si ΔWR > 0 y ΔE ≤ 0, se rechaza. Correr el agente sobre entradas al azar (≥ 20 réplicas): si $FWR = \Delta WR_{\text{azar}} / \Delta WR_{\text{señal}} > 0.5$, la subida del WR es geometría. Superar también al p95 del azar dentro de la ventana (+0.065 %/op).
4. **Cola:** peor operación ≥ −(1 $R$ + costo), CVaR 5 % y *drawdown* no peores que la base.
5. **Consistencia:** ΔE > 0 en ≥ 60 % de los pliegues con operaciones; PBO < 0.2.
6. **Filtro de entradas:** evaluar señal a señal (conservadas frente a descartadas, agrupando por día) y contra el azar **simulado en secuencia** con la misma proporción: saltar al azar el 50 % baja por sí solo el WR secuencial de 43.1 a ~40 %.
7. **Veto final:** en 2026-09-01..10-14, ΔE ≥ 0 y PnL ≥ 0. Luego sombra en testnet (≥ 2 semanas o 50 posiciones) con acciones idénticas al backtest en ≥ 99 % de los casos y deslizamiento mediano de `CLOSE` ≤ 0.05 %.
8. **Reportar siempre:** WR, $E$, factor de beneficio, ganancia media / pérdida media, CVaR 5 % y asimetría.

## 6. Plan por fases

Ordenado por impacto demostrado en la $E$ y por esfuerzo.

| Fase | Qué | Impacto en $E$ | Esfuerzo | Condición para seguir |
|---|---|---|---|---|
| 0 | **Comisiones con BNB** y alerta de saldo | +0.05 %/op, demostrado | Minutos (ajuste de cuenta) | — |
| 1 | **Operar solo lo que tiene ventaja:** tabla de $E$ en $R$ por estrategia × moneda con intervalo de confianza; hoy SOL Squeeze en real y BTC, ETH y DOGE en sombra | Evita −0.13 a −0.20 %/op en BTC y ETH | Configuración + 1 día | Revisión mensual |
| 2 | **Diario de señales:** todas las señales (también las omitidas) con su resultado en sombra, R-múltiplos, MAE/MFE y costo en $R$ | Indirecto: crea el *dataset* | 1–2 días | — |
| 3 | **Interruptor por $E$ móvil y cortacircuitos** (−3 $R$ día, −6 $R$ semana, riesgo abierto ≤ 2 $R$), persistidos en disco | Protege la $E$; no la crea | 1–2 días | — |
| 4 | **Reglas base de cartera** en sombra: nocional ∝ $E$ de 12 meses (0–2×) | +0.36 % por USDT en desarrollo, sin significancia | 1 día | Pasar Bonferroni en walk-forward |
| 5 | **Filtro de entradas** (*meta-labeling* LightGBM en `StrategyEngine.get_signal`, sin tocar Node) con variables de régimen, flujo taker y co-señal como hipótesis prerregistradas | ΔE ≈ +0.2 pp esperado, no demostrado | 2 días | Prueba señal a señal y contra azar secuencial |
| 6 | **Señal base nueva:** sobrerreacción tras caída extrema con capitulación taker, o ENS13 + geometría X5 de la [estrategia v3](estrategia-v3-hacia-el-80.md) | Única vía a WR alto **con** $E$ > 0 | Investigación (semanas) | El mismo walk-forward con Bonferroni |
| 7 | **TP con LIMIT u OCO** | +0.009 %/op; mejora la ejecución | 2–3 días (cancelación, carreras, reinicios) | — |
| 8 | **Agente de salida** (entorno con paridad, mejora en un paso / *fitted-Q*, sombra, Node activo, testnet) | Hoy ≈ 0; techo del oráculo +0.86 $R$ | ≈ 10–15 días + 2–4 semanas de testnet | Solo si alguna variable nueva da IC > 0.1 OOS y ΔE pareado con t > 2 en los dos tramos de 2026 |
| 9 | PPO como ajuste fino | Desconocido | 1–1.5 días de CPU por cada 3 semillas | Solo si la fase 8 es significativa |

Las fases 0–4 no necesitan RL y son las que más esperanza protegen o añaden por unidad de esfuerzo. El agente de salida va al final porque los datos actuales no le dan nada que aprender.

## 7. Fuentes clave

- Harvey, Liu y Zhu, *…and the Cross-Section of Expected Returns* (RFS 2016): https://doi.org/10.1093/rfs/hhv059
- Bailey y López de Prado, *The Deflated Sharpe Ratio*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- Novy-Marx y Velikov, costos de las anomalías (RFS 2016): https://doi.org/10.1093/rfs/hhv063
- Barber, Lee, Liu y Odean, *day traders* de Taiwán: https://www.escholarship.org/content/qt7k75v0qx/qt7k75v0qx.pdf
- Kaminski y Lo, cuándo ayudan los stops: https://dspace.mit.edu/handle/1721.1/114876
- Bailey, Borwein, López de Prado y Zhu, *The Probability of Backtest Overfitting*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Grossman y Zhou, exposición con restricción de *drawdown*: https://doi.org/10.1111/j.1467-9965.1993.tb00092.x
- Chague, De-Losso y Giovannetti, *Day Trading for a Living?*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101
- Moreira y Muir, volatilidad objetivo: https://www.nber.org/papers/w22208.pdf
- Moskowitz, Ooi y Pedersen, *Time Series Momentum*: https://doi.org/10.1016/j.jfineco.2011.11.003
- Liu y Tsyvinski, *Risks and Returns of Cryptocurrency*: https://doi.org/10.1093/rfs/hhaa113
- Hudson & Thames, *meta-labeling* con Bollinger: https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy/
- Reversión y flujo taker a 15 min en Binance: https://arxiv.org/abs/2608.21888
- De Nicola, reversiones intradía y cascadas de liquidación: https://ledger.pitt.edu/ojs/ledger/article/view/213
- Miralles-Quirós, sobrerreacción tras *shocks* horarios negativos: https://doaj.org/article/889af1e55ca44d83bcb079580903b1b0
- Shen, Urquhart y Wang, *Bitcoin Intraday Time-Series Momentum*: https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/
- Baur et al., efectos de calendario en Bitcoin que no persisten: https://quantpedia.com/are-there-any-simple-calendar-effects-in-bitcoin-market/
- Gort et al., sobreajuste de backtest en DRL para cripto: https://arxiv.org/abs/2209.05559
- Salidas supervisadas frente a RL desde cero: https://arxiv.org/abs/2610.13126
- Li, Szepesvári y Schuurmans, FQI frente a Longstaff–Schwartz: https://proceedings.mlr.press/v5/li09d.html
- Hambly, Xu y Yang, panorama de RL en finanzas: https://arxiv.org/abs/2112.04553
- Pricope, crítica del DRL en trading: https://arxiv.org/abs/2106.00123
- López de Prado, *Advances in Financial Machine Learning* (2018), caps. 3, 4 y 7 (triple barrera, *meta-labeling*, CV purgada).
