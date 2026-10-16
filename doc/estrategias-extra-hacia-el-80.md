# Estrategias extra para acercarse al 80 % de *win rate*: qué funciona, qué no y qué es lo más reciente (2024–2026)

Este documento continúa [matematica-aplicativa.md](matematica-aplicativa.md) y [modelos-complejos-y-datos.md](modelos-complejos-y-datos.md). Allí el mejor resultado fue un ensamble con datos de futuros que compra **velas de capitulación**: en monedas que nunca vio logró un *win rate* (WR) de ≈ 69 %, con ventaja real sobre el azar, pero sin ganancia significativa. Aquí se buscan **estrategias extra** para acercarse al 80 % **con esperanza positiva**, usando lo más reciente de 2024–2026.

Se hizo en dos iteraciones, siempre **solo en el periodo de diseño**:

- **Primera iteración** (2026-10-15), con dos agentes en cadena. Un **Explorador** (58 búsquedas web y 40 estrategias candidatas, cada una con sus fuentes, los datos que necesita y si funciona en *spot*) y un **Juez y laboratorio**, que buscó el argumento más fuerte en contra de cada candidata, verificó las fuentes, añadió 8 piezas que faltaban y corrió 15 experimentos (≈ 100 configuraciones registradas).
- **Segunda iteración** (2026-10-16, [sección 11](#11-segunda-iteración-2026-10-16-buscando-1-punto)), con cuatro agentes: dos investigadores (fuentes de datos y métodos), el laboratorio y el redactor. Buscó **al menos +1 punto más** sobre la pila de la primera, con 208 configuraciones nuevas.

## Respuesta corta

> **La pila recomendada ahora es la v3: la v2 con la "co-señal" y con la barrera de tiempo alargada de 72 h a 96 h.** La co-señal (comprar solo si **otra moneda ancla también dio señal en las últimas 12 horas**, es decir, en un pánico de mercado y no en una caída aislada) llevó la v2 en diseño de **81.4 % a 85.5 %** de WR. Alargar la barrera (E7, segunda iteración) la lleva a **87.8 % [81.1, 92.3]** y a **+2.02 %** de esperanza por operación (+2.07 % con BNB). Fuera de muestra se espera **≈ 73–79 % de WR y +0.6 a +1.2 % de E**, no 88 %, porque las cifras de diseño están infladas: la v2 dio 81 % en diseño y 69 % en monedas nuevas.

- **Frente al objetivo de "+1 punto" de la segunda iteración:** se logró en lo **esperado**, no en lo **demostrado**. E7 suma +2.3 pt en diseño y ≈ **+1 a +1.5 pt** esperados fuera de muestra. Con 24 episodios en diseño, una mejora de ese tamaño no se puede demostrar: el veredicto vendrá de la prueba prospectiva.
- **Con reserva, D1: no comprar si el DVOL de BTC está muy por debajo de su media de 30 días** ($z_{30} < -1$), es decir, si el mercado cae **sin que las opciones paguen miedo**. Es el efecto más consistente de todo el laboratorio (+2 a +5 pt y +0.2 a +0.4 % de E en los 4 ensambles), pero descansa en ≈ 5–7 episodios y el azar con la misma regla mejora casi lo mismo. Va como **brazo S3** del pre-registro. Si se confirma, sumaría **+0.5 a +2 pt** (v3 + D1 ≈ 74–80 %), con un 35–45 % de probabilidad de que su efecto real sea nulo.
- **Techo realista: ≈ 75–78 % de WR.** Un 80 % por operación **demostrado** (límite inferior de Wilson ≥ 0.75) sigue siendo improbable: el Juez le dio entre un 15 y un 25 % de probabilidad. **La meta alcanzable es un ≈ 80 % de meses ganadores** (sección 1.5).
- **Casi todo lo demás que se probó no sube el WR con ganancia.** En la primera iteración: entradas *maker*, esperar confirmación, toma parcial, umbrales con garantía conforme, *proxies* de liquidaciones, amplitud medida con precios, cobertura con BTC, *grid* y DCA, y TabPFN (neutro). En la segunda: geometrías elegidas en *walk-forward*, re-entradas, segundas etapas, recalibraciones, TP dependientes del estado y tres fuentes de datos nuevas (sección 11.5).
- **Lo más "de frontera" de 2025–2026 no muestra ventaja neta** en las evaluaciones independientes (modelos fundacionales y agentes LLM). Lo que mueve el WR es **la información** (datos de futuros y, quizá, el DVOL) y **elegir qué pánicos comprar**.
- **Siguiente paso:** el estrés de 2022 y una prueba prospectiva pre-registrada desde 2026-10-01 con la v3 como brazo principal (sección 8). El *holdout* fresco de 20 monedas solo puede confirmar reglas **dentro** del episodio (como E7), no reglas **de episodio** (como la co-señal o D1). Conviene **grabar el DVOL desde ya**.

| Pieza | Efecto en el WR | Efecto en la E | Veredicto |
|---|---|---|---|
| **Co-señal del modelo** ($A_4 \ge 1$) | +4.1 pt en diseño; +3 a +6 pt esperados | +0.49 % en diseño; +0.3 a +0.6 % esperado | **Adoptar (en la v3)** |
| **Barrera de tiempo de 96 h** (E7) | +2.3 pt en diseño; +1 a +1.5 pt esperados | +0.12 % en diseño; 0 a +0.1 % esperado | **Adoptar (en la v3)** |
| **Veto por DVOL bajo** (D1) | +3.3 pt sobre la v3 en diseño; +0.5 a +2 pt si se confirma | +0.33 %; +0.05 a +0.2 % si se confirma | Brazo S3, con reserva |
| Comisiones con BNB y TP con orden límite | 0 | +0.05 % | Adoptar (costo cero) |
| Higiene: deslistados, etiqueta de monitoreo, desbloqueos | ≈ 0 | Evita la cola | Adoptar como regla |
| Riesgo por episodio (máx. 3 posiciones y topes) | 0 | Evita la ruina (cuesta ≈ 0.1 %) | Obligatorio |
| TP reducido a +0.6 % desde las 36 h | +2.4 pt sobre la v3 | −0.16 % | Solo si se prioriza el WR (brazo S4) |
| Pesos de unicidad (ENS12U) | 0 en diseño; achica la caída de diseño a prueba | — | Brazo secundario (S2) |
| Liquidaciones exactas y filtro de noticias | 0 a +3 pt (no probado) | 0 a +0.2 % | Grabar desde ahora |
| Todo lo demás (secciones 4 y 11.5) | ≤ 0, o solo "contable" | Negativa o menor | Descartar |

**La v3 en una línea:** ensamble ENS13 con $\theta = 0.71427$; comprar solo si otra de las 4 monedas ancla dio señal en las últimas 48 velas cerradas; TP a $0.7\,s_d$, SL a $1.75\,s_d$ y cierre forzado a las **384 velas (96 h)**; comisiones con BNB y TP con orden límite; como máximo 3 posiciones y riesgo por episodio ≤ 1.5 % del capital. Los detalles están en la sección 3.5.

De paso, la primera iteración encontró un **error** en `nn_report.summarize` que desalinea monedas y operaciones (sección 9).

## Tabla de contenido

- [Respuesta corta](#respuesta-corta)
- [0. Cómo se hizo](#0-cómo-se-hizo)
- [1. Por qué el 80 % es tan difícil: el techo en números](#1-por-qué-el-80--es-tan-difícil-el-techo-en-números)
- [2. La pieza nueva que funciona: la co-señal del modelo](#2-la-pieza-nueva-que-funciona-la-co-señal-del-modelo)
- [3. Capas complementarias que conviene adoptar](#3-capas-complementarias-que-conviene-adoptar)
- [4. Lo que se probó en la primera iteración y se rechazó (no repetir)](#4-lo-que-se-probó-en-la-primera-iteración-y-se-rechazó-no-repetir)
- [5. Lo más reciente (2024–2026): qué dice la evidencia](#5-lo-más-reciente-20242026-qué-dice-la-evidencia)
- [6. Catálogo completo de candidatas](#6-catálogo-completo-de-candidatas)
- [7. Trampas: cómo se fabrican win rates de 70–95 %](#7-trampas-cómo-se-fabrican-win-rates-de-7095-)
- [8. Hoja de ruta y pre-registro](#8-hoja-de-ruta-y-pre-registro)
- [9. Correcciones al trabajo anterior](#9-correcciones-al-trabajo-anterior)
- [10. Dónde está todo](#10-dónde-está-todo)
- [11. Segunda iteración (2026-10-16): buscando +1 punto](#11-segunda-iteración-2026-10-16-buscando-1-punto)

---

## 0. Cómo se hizo

**Datos y periodo.** Solo el periodo de **diseño** (2023-01-01 a 2025-06-30) y el mismo *walk-forward* de 6 pliegues de [modelos-complejos-y-datos.md](modelos-complejos-y-datos.md) (pruebas trimestrales de 2024-01 a 2025-06). Se usaron las predicciones ya guardadas de los ensambles sobre BTC, ETH, SOL y DOGE. Para medir la amplitud del mercado se añadieron las velas *spot* de 2023–2025 de las otras 14 monedas del Verificador. El *holdout* 2025-07..2026-09 **no** se usó para decidir nada. La única consulta fue un chequeo descriptivo de *grid* y DCA en mercado bajista, solo con precios, y quedó registrada en `holdout_log.csv`.

**Reglas de simulación.** Las mismas de los documentos anteriores: entrada al cierre de la vela, empate TP/SL = SL, $c = 0.24\,\%$ ida y vuelta, una posición por moneda y salida **X5**: TP a $0.7\,s_d$, SL a $1.75\,s_d$ y 288 velas (72 h), donde $s_d$ es la volatilidad diaria. Cada configuración se compara con dos referencias:

- **Azar:** entradas al azar con la misma moneda, el mismo mes y la misma geometría. Da $\Delta WR$ y $\Delta E$.
- **Azar condicionado:** entradas al azar **solo en las velas donde la regla nueva está activa**. Separa "ese día era bueno para cualquier compra" de "el modelo eligió bien".

Cada familia de pruebas se registró con `harness.log_trials("bleeding_edge", ...)`: unas 101 configuraciones distintas, que se suman a las ≈ 12 300 del proyecto. La segunda iteración siguió las mismas reglas, con algunas mejoras de método (sección 11.1).

> **Advertencia que vale para todas las cifras de diseño.** La v2 se eligió mirando este mismo *walk-forward*, así que su 81.4 % de diseño está inflado: en monedas nuevas dio 69.4 %. Lo que se puede leer con confianza es la **diferencia** que añade cada capa nueva sobre la v2, no el nivel absoluto.

---

## 1. Por qué el 80 % es tan difícil: el techo en números

### 1.1 El win rate se descompone en geometría más ventaja

$$
p = p_{\text{azar}}(a, m, H, \text{régimen}) + \Delta_{\text{modelo}} + \Delta_{\text{compuerta}}
$$

**Qué es cada símbolo:**

- $p$: *win rate* neto (operaciones con retorno neto > 0).
- $p_{\text{azar}}$: WR de entrar al azar con la misma salida ($a$ = TP y $m$ = SL en volatilidades diarias, $H$ = barrera de tiempo). Medido con X5: 61.7 % en diseño (alcista) y ≈ 60 % en el *holdout* (bajista).
- $\Delta_{\text{modelo}}$: ventaja del ensamble fuera de muestra. Medida: entre +9.4 pt (v2, X5) y +16.9 pt (v1, G3).
- $\Delta_{\text{compuerta}}$: ventaja que añade la co-señal de la sección 2. Medida en diseño: entre +2.1 y +4.5 pt, según el ensamble.

> **Ejemplo:** 60 % + 9.4 = **69.4 %**, exactamente lo que dio la v2 en monedas nuevas. Para llegar al 80 % con X5 harían falta $\Delta_{\text{modelo}} + \Delta_{\text{compuerta}} \approx +20$ pt fuera de muestra, más de lo que se ha replicado nunca.

### 1.2 Cuánto vale cada punto de win rate

$$
E = p\,\bar W - (1-p)\,\bar L = (\bar W + \bar L)\,(p - p^{*}_{\text{emp}}),
\qquad
p^{*}_{\text{emp}} = \frac{\bar L}{\bar W + \bar L}
$$

**Qué es cada símbolo:**

- $\bar W$, $\bar L$: ganancia y pérdida netas medias por operación, en %.
- $p^{*}_{\text{emp}}$: WR de equilibrio con esos tamaños (el que deja $E = 0$).
- $(\bar W + \bar L)/100$: lo que vale **un punto** de WR en esperanza.

> **Ejemplo (v2 en las 8 monedas nuevas):** $\bar W = 2.61\,\%$ y $\bar L = 4.88\,\%$ dan $p^{*}_{\text{emp}} = 65.2\,\%$, y cada punto de WR vale 0.075 % de E. Con WR 70 % ⇒ $E \approx +0.36\,\%$; con 75 % ⇒ +0.73 %; con 80 % ⇒ +1.11 %.

La fórmula teórica $p^{*} = (1 + c/R)/(1 + b)$ da para X5 ($b = 0.4$, $R \approx 7.5\,\%$, $c = 0.24\,\%$) un equilibrio de $1.032/1.4 = 73.7\,\%$. El equilibrio real es más bajo, ≈ 65 %, porque las salidas por tiempo suben el $b$ efectivo a ≈ 0.53.

### 1.3 Cuánta "deriva" hace falta para el 80 %

Si el precio se mueve como un paseo aleatorio con una deriva favorable $\nu$, la probabilidad de tocar el TP antes que el SL es:

$$
P(\text{TP antes que SL}) = \frac{1 - e^{2\nu m}}{e^{-2\nu a} - e^{2\nu m}}
\quad\xrightarrow{\ \nu \to 0\ }\quad
\frac{m}{a + m}
$$

**Qué es cada símbolo:**

- $a$, $m$: distancia al TP y al SL, en volatilidades diarias $s_d$.
- $\nu$: deriva favorable, en $s_d$ por día. Con $\nu = 0$ es el azar puro.

> **Ejemplo (X5: $a = 0.7$, $m = 1.75$, sin barrera de tiempo ni costos):**
>
> | Deriva $\nu$ | WR teórico | Deriva en % por día (con $s_d \approx 4.3\,\%$) |
> |---|---|---|
> | 0 | 71.4 % | 0 |
> | 0.07 | 75 % | +0.3 % |
> | **0.19** | **80 %** | **+0.8 %** |
> | 0.32 | 85 % | +1.4 % |
>
> El 80 % exige una subida sostenida de ≈ 0.8 % por día mientras dura la operación (la mediana es de 11 h). Esa deriva solo existe en los **rebotes tras una capitulación**, así que el techo depende de cuántas capitulaciones genuinas se logren separar de las caídas que siguen cayendo. Con la geometría G4 ($a = 0.4$, $m = 1.2$) el 80 % exige la misma deriva, pero con un TP de la mitad de tamaño: por eso G4 dio un WR de 70–74 % con E negativa.

**Deriva medida en la segunda iteración.** Invirtiendo la fórmula con la fracción de operaciones que tocan el TP antes que el SL, las operaciones del modelo con compuerta tienen $\nu \approx 0.43\,s_d$ por día; el azar con la misma compuerta, ≈ 0.18, y el azar sin compuerta, ≈ 0.06. La compuerta triplica la deriva del azar y el modelo la vuelve a duplicar. En diseño, 0.43 supera con holgura los 0.19 que pide el 80 %: la duda es cuánto de esa deriva se conserva fuera de muestra.

### 1.4 Selectividad frente a tamaño de muestra

Cuanto más selectiva es una regla, menos operaciones da, y más difícil es **demostrar** su WR. Operaciones **independientes** necesarias para que el límite inferior de Wilson al 95 % supere el objetivo $p_0$:

| WR real | Para afirmar ≥ 70 % | Para afirmar ≥ 75 % |
|---|---|---|
| 76 % | 225 | — |
| 78 % | 127 | 801 |
| 80 % | 81 | 289 |
| 85 % | 36 | 73 |

Estas cifras se multiplican por el efecto de diseño $DEFF$, porque las operaciones del mismo pánico no son independientes: 1.0–1.2 por día con 4 monedas, y probablemente 2–3 con 18 monedas, porque los pánicos son simultáneos. **La unidad real de muestra es el episodio:** en diseño hubo unos **16 episodios por año** con 4 monedas.

### 1.5 Conclusión numérica

| Escenario | WR esperado | E por operación |
|---|---|---|
| v2 tal cual (medido en monedas nuevas) | 69–70 % | +0.3 a +0.4 % |
| + co-señal $A \ge 1$ (estimado) | 72–78 % | +0.6 a +1.1 % |
| **+ barrera de 96 h = v3** (estimado) | **73–79 %** | **+0.6 a +1.2 %** |
| + D1, si se confirma (brazo S3; estimado) | ≈ 74–80 % | +0.65 a +1.4 % |
| + higiene, noticias y liquidaciones (estimado, no probado) | +0 a +3 pt adicionales | +0 a +0.2 % |
| **Techo realista** | **≈ 75–78 %** | ≈ +0.6 a +1.2 % (el de la v3) |
| 80 % con límite de Wilson ≥ 0.75 | Improbable (15–25 %, juicio del Juez) | Exigiría E ≈ +1.1 % sostenida |

**La alternativa honesta: contar meses, no operaciones.** Si la ventaja por operación es $\mu$, la probabilidad de que un mes termine en positivo es aproximadamente:

$$
P(\text{mes} > 0) \approx \Phi\!\left(\frac{\mu\, n_m}{\sigma\sqrt{n_m\,DEFF}}\right)
$$

**Qué es cada símbolo:** $\Phi$ es la función de distribución normal; $\mu$, la E media por operación; $\sigma$, su desviación (≈ 4.2 %); $n_m$, las operaciones por mes; $DEFF$, el efecto de diseño.

> **Ejemplo:** con $\mu = 1\,\%$, $\sigma = 4.2\,\%$, $n_m = 15$ y $DEFF = 1.5$: $1 \times 15 / (4.2 \times \sqrt{22.5}) = 0.75$ y $\Phi(0.75) = 77\,\%$ de meses ganadores. Con $\mu = 0.5\,\%$ baja a 65 %. En diseño, la v2 con co-señal y la v3 tuvieron **15 de 15 meses activos en positivo**.

---

## 2. La pieza nueva que funciona: la co-señal del modelo

### 2.1 De dónde sale la idea

En [modelos-complejos-y-datos.md](modelos-complejos-y-datos.md) (sección 3.8) se vio que, en el *holdout*, la ganancia de la v2 se concentraba en **pánicos que afectan a varias monedas a la vez**: los 10 días más activos tenían E +1.18 % y el resto, E ≈ 0. Como esa observación salió del *holdout*, aquí se trató como una **hipótesis externa** y se probó por primera vez en el periodo de diseño, donde nunca se había mirado. Esa es una prueba legítima.

### 2.2 La regla

$$
A_{i,t} = \sum_{j \ne i} \mathbb{1}\!\left[\max_{t-W < s \le t} \mathbb{1}\big(\hat p_{j,s} \ge \theta\big) = 1\right],
\qquad
\text{comprar } i \text{ en } t \iff \hat p_{i,t} \ge \theta \ \text{ y } \ A_{i,t} \ge 1
$$

**Qué es cada símbolo:**

- $A_{i,t}$: cuántas **otras** monedas $j$ tuvieron señal del ensamble en las últimas $W$ velas cerradas.
- $\hat p_{j,s}$: probabilidad calibrada del ensamble para la moneda $j$ en la vela $s$.
- $\theta$: umbral de la v2 (0.71427).
- $W$: ventana; la recomendada es 48 velas de 15 min (12 h).

> **Ejemplo:** a las 14:00, ETH tiene $\hat p = 0.73 \ge \theta$. A las 08:30, SOL tuvo $\hat p = 0.72$. Entonces $A = 1$ y **se compra ETH**. Si ninguna otra moneda hubiera dado señal desde las 02:00, la señal de ETH sería **aislada** y no se compraría.

La regla es causal: en la vela $t$ solo usa señales de velas ya cerradas.

### 2.3 Resultados en diseño

Ensamble v2 (ENS13), salida X5, 4 monedas, 6 pliegues:

| Configuración | n | WR [IC 95 %] | E neta | Azar: WR / E | Azar condicionado: WR / E | Ventaja del modelo sobre el azar condicionado: ΔWR / ΔE ($t$) |
|---|---|---|---|---|---|---|
| v2 sin compuerta | 188 | 81.4 % [75.2, 86.3] | +1.41 % | 61.7 / −0.43 | — | — |
| $A \ge 1$, $W$ = 4 h | 122 | 86.9 % [79.8, 91.8] | +1.98 % | 61.5 / −0.40 | 76.0 / +0.96 | +10.8 / +1.02 (2.61) |
| **$A \ge 1$, $W$ = 12 h** | **131** | **85.5 % [78.5, 90.5]** | **+1.90 %** | 61.3 / −0.43 | 73.5 / +0.71 | **+12.0 / +1.19 (2.76)** |
| $A \ge 1$, $W$ = 24 h | 140 | 85.7 % [79.0, 90.6] | +1.92 % | 60.8 / −0.49 | 71.2 / +0.56 | +14.5 / +1.37 (3.56) |
| $A \ge 2$, $W$ = 12 h | 78 | 89.7 % [81.0, 94.7] | +2.06 % | 63.2 / −0.25 | 86.4 / +1.94 | +3.3 / +0.13 (0.29) |
| Señal aislada ($A = 0$, $W$ = 12 h) | 87 | 75.9 % [65.9, 83.6] | +0.88 % | 62.4 / −0.41 | 60.9 / −0.52 | +14.9 / +1.40 (3.07) |

**Se replica en los otros dos ensambles:**

| Ensamble | Sin compuerta | Con $A \ge 1$ | Señales aisladas ($A = 0$) |
|---|---|---|---|
| ENS13 (v2) | 188 · 81.4 % · +1.41 % | 131 · 85.5 % · +1.90 % | 87 · 75.9 % · +0.88 % |
| ENS12 (sin la CNN) | 177 · 79.1 % · +1.25 % | 110 · 83.6 % · +1.69 % | 88 · 73.9 % · +0.72 % |
| ENS12 con pesos de unicidad | 391 · 76.5 % · +0.74 % | 341 · 78.6 % · +0.99 % | 91 · 68.1 % · **−0.33 %** |

Por vela (resultado X5 solapado, $W$ = 4 h) se ve un gradiente limpio: $A = 0$ → 66.4 % y −0.31 %; $A = 1$ → 79.3 % y +1.29 %; $A \ge 2$ → 88.5 % y +2.50 %.

### 2.4 Qué tan robusto es

- **Pliegues:** positivo en los 6. WR por pliegue con $A \ge 1$: 77, 85, 78, 85, 90 y 96 %.
- **Monedas:** positivo en las 4. BTC 89.7 %, ETH 88.0 %, SOL 82.1 % y DOGE 84.2 %.
- **Episodios:** 24 en 18 meses, con el 83 % en positivo. Sin los 5 episodios mayores, E sigue en +2.20 % (WR 85 %).
- **Meses:** 15 de 15 meses activos en positivo.
- ***Bootstrap* por días** (5 000 réplicas): E($A \ge 1$) − E($A = 0$) = **+1.04 %** [IC 95 %: +0.15, +1.97], P(≤ 0) = 0.010. En WR: +8.1 pt [−2.2, +19.5], P(≤ 0) = 0.066. La mejora de la E es significativa; la del WR, casi. **Matiz de la segunda iteración:** el *bootstrap* debe agruparse por **episodio**, no por día, porque los episodios duran varios días (sección 11.8). Agrupar por día subestima la varianza, así que estas P son algo optimistas.
- **Deslizamiento de los SL en el pánico:** sumando 0.5 % o 1 % de deslizamiento extra a cada salida por SL, E baja solo a +1.85 % y +1.80 %.

### 2.5 El argumento en contra, y por qué sobrevive solo en parte

1. **Parte del efecto es "el día era bueno".** El azar condicionado a la misma compuerta gana 73.5 % y +0.71 %: en un pánico de mercado, casi cualquier compra rebota. Aun así, el modelo suma **+12.0 pt y +1.19 %** encima de ese azar ($t = 2.76$). La compuerta es, en parte, una apuesta al rebote del mercado.
2. **Con $A \ge 2$ la ventaja del modelo desaparece** (+3.3 pt, $t = 0.29$): ahí todo lo pone el día. Por eso la compuerta debe ser $A \ge 1$, no más estricta.
3. **Un pánico sin rebote lo pierde todo a la vez.** LUNA y FTX (2022) no se pudieron probar porque no hay datos de futuros de 2022 en la máquina. Es la prueba de estrés obligatoria (sección 8).
4. **La hipótesis nació en el *holdout* gastado y solo hay 24 episodios.** Hace falta confirmarla con datos nuevos antes de operar.

### 2.6 Por qué medir el pánico con precios no sirve

El Explorador propuso medir la amplitud del pánico con precios: qué fracción de 18 monedas cae 2 desviaciones en una hora ($B_{\text{precio}}$), o cuántas forman una vela de capitulación ($A_{\text{cap}}$). **No reproduce el efecto:**

| Compuerta | n | WR | E | Complemento: n, WR, E |
|---|---|---|---|---|
| v2 sin compuerta | 188 | 81.4 % | +1.41 % | — |
| $B_{\text{precio}} \ge 0.4$, $W$ = 4 h | 128 | 84.4 % | +1.59 % | 136, 77.9 %, +1.06 % |
| $B_{\text{precio}} \ge 0.4$, $W$ = 12 h | 148 | 82.4 % | +1.41 % | 76, **80.3 %**, +1.43 % |
| $A_{\text{cap}} \ge 4$, $W$ = 12 h | 134 | 82.1 % | +1.37 % | 101, **82.2 %**, +1.53 % |
| Bajar $\theta$ en 0.03 durante pánicos de precio | 959 | 71.9 % | +0.35 % | — |

Con ventanas de 12–24 h, las operaciones que la compuerta de precio **descarta** ganan igual o más que las que deja. **La información útil está en los datos de futuros de varias monedas**, que es lo que resume la co-señal del modelo, no en el precio.

### 2.7 La regla que se debe pre-registrar

- **$A_4 \ge 1$:** al menos una de las 4 monedas ancla (BTC, ETH, SOL, DOGE), distinta de la operada, tuvo $\hat p \ge \theta$ en alguna de las últimas 48 velas cerradas (12 h).
- Se puede **operar en 18 monedas** usando como detector de pánico solo esas 4 anclas. Así la definición de la compuerta sigue siendo exactamente la validada, aunque crezca el universo, y la prueba gana potencia.

---

## 3. Capas complementarias que conviene adoptar

### 3.1 Costos: BNB y TP con orden límite

Pagar comisiones con BNB (0.075 % por lado en lugar de 0.10 %) y salir del TP con una orden límite, sin deslizamiento, baja el costo de ida y vuelta de 0.24 % a ≈ 0.19 %:

| Pila | Costo | n | WR | E |
|---|---|---|---|---|
| v2 | 0.24 % | 188 | 81.4 % | +1.41 % |
| v2 | 0.19 % | 188 | 81.4 % | +1.46 % |
| v2 + co-señal | 0.24 % | 131 | 85.5 % | +1.90 % |
| v2 + co-señal | 0.19 % | 131 | 85.5 % | +1.95 % |

Aporta +0.05 % de E y **nada de WR**. Conviene adoptarlo porque no cuesta nada, pero no acerca al 80 %. Hay que mantener saldo en BNB (expuesto a su precio) y verificar la comisión vigente en la propia cuenta: la tarifa solo se confirmó en fuentes secundarias.

### 3.2 Higiene de eventos (regla de costo cero)

Excluir las señales de una moneda desde que:

- recibe un aviso de **deslistado** o la **etiqueta de monitoreo** de Binance;
- tiene un **desbloqueo** grande de tokens en los ±14–30 días (solo importa en *altcoins* con *vesting*: SOL, NEAR, DOT, FIL, ATOM, UNI, AVAX y similares);
- se listó hace poco.

En monedas grandes no mueve el WR medible, pero evita comprar caídas con un **vendedor informado**. Esas no rebotan: según Chan (2003) y Savor (2012), los choques con noticia siguen la tendencia y los choques sin noticia revierten. La página de anuncios es un dominio de Binance: hay que consultarla con la VPN apagada.

### 3.3 Riesgo por episodio (obligatorio con la compuerta)

La co-señal **concentra la exposición**: casi todas las operaciones de un día son la misma apuesta al rebote del mercado. Topes recomendados:

$$
\text{nocional} = \frac{\text{riesgo por operación}}{R}
$$

**Qué es cada símbolo:** el riesgo por operación es la fracción del capital que se pierde si salta el SL; $R$ es la distancia al SL en % del precio (con X5, ≈ 7.5 %).

> **Ejemplo:** con 0.5 % del capital en riesgo y $R = 7.5\,\%$, el nocional es $0.5/7.5 = 6.7\,\%$ del capital por operación. Con un máximo de 3 posiciones a la vez, el riesgo por episodio queda en ≤ 1.5 %. Pausa obligatoria si la pérdida acumulada supera 10 R o si hay 3 episodios negativos seguidos.

Un solo pánico sin rebote con 10–18 monedas abiertas puede borrar un año de ventaja. Por eso la prueba de estrés de 2022 (LUNA, FTX) es requisito antes de operar.

### 3.4 Pesos de unicidad: el antídoto contra la caída de diseño a prueba (brazo secundario ENS12U)

El principal enemigo del objetivo es que el WR de diseño **no se sostiene**: la v2 pasó de 81 % a 69 %. Una causa es que una sola capitulación genera decenas de velas con la misma etiqueta, y el modelo "memoriza" pocos pánicos. La ponderación por unicidad (López de Prado) le da menos peso a cada vela cuanto más solapada está su etiqueta con otras:

$$
u_i = \frac{1}{|T_i|}\sum_{t \in T_i} \frac{1}{c_t}
$$

**Qué es cada símbolo:** $T_i$ son las velas que abarca la etiqueta $i$ (hasta 288); $c_t$ es el número de etiquetas activas en la vela $t$, **sumando las 4 monedas**; $u_i$ es el peso de la vela $i$ en el entrenamiento.

> **Ejemplo:** si durante las 72 h de una etiqueta hay, en promedio, 40 etiquetas activas entre las 4 monedas, su peso es $\approx 1/40$. Una vela de un periodo tranquilo, con 5 etiquetas activas, pesa 8 veces más.

Resultado (mismas variables, *walk-forward* e hiperparámetros, reentrenando 6 LightGBM y 6 MLP):

| Modelo | Brecha de WR validación − prueba, sin pesos | Con pesos de unicidad |
|---|---|---|
| LightGBM, semillas 0–2 | 13.8 pt | 7.6 pt |
| LightGBM, semillas 3–5 | 10.7 pt | 3.9 pt |
| MLP | 18.8 pt | 0.8 pt |
| ENS6 | 9.7 pt | 5.8 pt |
| ENS12 | 8.6 pt | 3.9 pt |

La brecha baja en las 5 comparaciones. Pero el ensamble ponderado, con la regla de la v2, opera el doble y con menos WR de diseño (76.5 % frente a 79.1 %). **No sube el WR; lo vuelve más creíble.** Por eso entra como **brazo secundario** (ENS12U, brazo S2) en la prueba prospectiva, no como reemplazo. En la primera iteración este modelo se llamaba "v3"; ese nombre pasó a la pila nueva de la sección 3.5.

### 3.5 La pila completa (v3)

| # | Capa | Medido en diseño | Esperado fuera de muestra | Estado |
|---|---|---|---|---|
| 0 | Base v2 (ENS13 + X5 + $\theta$ = 0.714) | 81.4 % · +1.41 % (inflado) | 69–70 % · +0.3 a +0.4 % (medido) | Existe |
| 1 | **Co-señal $A_4 \ge 1$** | +4.1 pt · +0.49 % | **+3 a +6 pt · +0.3 a +0.6 %**, con −30 % de operaciones | **En la v3** |
| 2 | **Barrera de tiempo de 96 h** (E7, sección 11.3) | +2.3 pt · +0.12 % | **+1 a +1.5 pt · 0 a +0.1 %** | **En la v3** |
| 3 | BNB + TP límite | +0.05 % de E | Igual | Adoptar |
| 4 | Higiene de eventos | No medible | 0 a +1 pt | Adoptar como regla |
| 5 | Riesgo por episodio (máx. 3 posiciones y topes) | No sube el WR; el tope de 3 cuesta ≈ 0.1 % de E | Evita la ruina | Obligatorio |
| 6 | Veto D1 por DVOL bajo (sección 11.4) | +3.3 pt · +0.33 % sobre la v3 (ENS13) | +0.5 a +2 pt, o nada (35–45 %) | Brazo S3, con reserva |
| 7 | Pesos de unicidad (ENS12U) | Brecha −4 a −18 pt | 0 a +3 pt, más estable | Brazo S2 |
| 8 | Filtro de tipo de choque (noticias) | No probado | 0 a +3 pt | Grabar desde ahora |
| 9 | Liquidaciones exactas | El *proxy* no aportó | 0 a +3 pt | Grabar desde ahora |

**La v3 (capas 0 a 3) en diseño:** 131 operaciones, WR **87.8 % [81.1, 92.3]** (IC beta-binomial por episodio: [81.6, 93.0]), E **+2.07 %** con BNB (+2.02 % con 0.24 %), +0.213 R, $t$ por día 5.90, 24 episodios con el 92 % en positivo y 15 de 15 meses activos en positivo. Es una cota optimista. La pila anterior (capas 0 + 1 + 3) daba 85.5 % y +1.95 %.

**Lo que se espera de forma prospectiva:** WR **≈ 73–79 %** y E de **+0.6 a +1.2 %** por operación. Según la estimación del Juez para la pila anterior, entre 250 y 400 operaciones al año con 18 monedas y entre un 70 y un 85 % de meses ganadores.

**Cómo se opera la v3, paso a paso:**

1. En cada vela cerrada de 15 min, calcular $\hat p$ con el ensamble ENS13 (Platt por modelo) para cada moneda. Hay señal si $\hat p \ge \theta = 0.71427$.
2. Comprar solo si, además, **otra** de las 4 monedas ancla (BTC, ETH, SOL, DOGE) tuvo $\hat p \ge \theta$ en alguna de las últimas 48 velas cerradas (12 h), y si la moneda pasa la higiene de eventos.
3. Entrar al cierre de la vela, con una posición por moneda y como máximo 3 abiertas. Nocional = riesgo por operación / $R$ (sección 3.3).
4. Salida: TP con orden límite a $+0.7\,s_d$, SL a $-1.75\,s_d$, y cierre a mercado si ninguno se toca en **384 velas (96 h)**. Empate TP/SL = SL.
5. Pausa si la pérdida acumulada supera 10 R o si hay 3 episodios negativos seguidos. En el brazo S3, además, no comprar si $z_{30}$ del DVOL de BTC < −1 (sección 11.4).

---

## 4. Lo que se probó en la primera iteración y se rechazó (no repetir)

Todas las cifras son del periodo de diseño, sobre las mismas 188 señales de la v2 salvo que se indique otra cosa. Referencia: **81.4 % y +1.41 %**. Los rechazos de la segunda iteración están en la sección 11.5.

| Pieza | Idea | Resultado medido | Por qué falla |
|---|---|---|---|
| **Entrada *maker* escalonada** | Orden límite $k\sigma$ bajo el cierre, durante $J$ velas | WR de las llenadas 75–81 %; E por **señal** +0.61 a +1.22 % | Selección adversa: se llenan las capitulaciones que siguen cayendo, y las no llenadas eran los mejores rebotes (+1.5 a +1.95 %) |
| **Confirmación por absorción** | Esperar 1–4 velas sin mínimo nuevo y con compradores ≥ 50 % | Se ejecuta el 25–64 %; E por señal +0.32 a +0.70 % | El rebote ocurre en la **primera** vela; las canceladas habrían ganado +1.06 a +1.33 % |
| **Toma parcial + stop a equilibrio** | 50 % fuera en +0.35·$s_d$; el resto, con stop en la entrada | **WR "contable" 90.4 % [85.4, 93.9]**, E +0.81 % | WR fabricado: el azar con la misma regla también da 79.5 %, y se pierden 0.6 % de E por operación |
| Stop a equilibrio puro | Stop en la entrada al tocar +0.35·$s_d$ | WR 42 %, E +0.78 % | Las salidas "en cero" pierden los costos y cuentan como pérdidas |
| SL ancho (2.5·$s_d$), salida a 24 h, "tesis rota" | Variantes de salida | E +1.27 %, +1.25 % y +0.55 % | Ninguna mejora la salida X5 fija (Kaminski y Lo, 2014) |
| **Umbral con garantía** (Learn-then-Test, selección conforme + BH) | Elegir $\theta$ con garantía de precisión ≥ 75–80 % | LTT no certifica 75 % en ningún pliegue; BH pidió ≥ 80 % y entregó **75.2 %**, bajo el objetivo en 3 de 6 pliegues | La garantía exige intercambiabilidad: aquí las etiquetas están agrupadas y hay deriva. Sirve como **chequeo de honestidad**, no como fuente de WR |
| Umbral adaptativo en línea (ACI) | Ajustar $\theta$ según los aciertos recientes | 72.5–78.2 %, E +0.51 a +1.12 % | Con ≈ 30 operaciones por trimestre persigue ruido |
| Abstención por desacuerdo del ensamble; calibración isotónica | Operar solo cuando los 13 modelos coinciden | Exigir desacuerdo bajo: 78.9 %; isotónica ≥ 0.85: 80.5 % | Al revés de lo esperado: las señales **con más** desacuerdo son las mejores (84.1 % frente a 77 % por vela). La isotónica sobreajusta la cola |
| ***Proxies* de liquidación** (caída de OI, vendedor agresivo, prima negativa) | Las capitulaciones con flujo forzado rebotan más | El "*OI flush*" **baja** el WR a 77.4 %; los demás, sin mejora | El flujo forzado ya está en las variables del modelo |
| Umbral más bajo en pánico (Nagel) | Exigir menos $\hat p$ cuando hay estrés | 70–72 %, E +0.08 a +0.35 % | Las velas que se añaden son beta del día, no selección |
| Rezago relativo dentro del pánico | Comprar la moneda que cae más (o menos) que el mercado | Sin gradiente: 79.8 / 79.6 / 79.0 % por tercil | — |
| Cobertura con un corto en BTC | Convertir la ventaja relativa en absoluta | Cubierta a la mitad: 78.7 %, +0.95 %; cubierta entera: 59.6 %, +0.27 % (frente a 81.6 %, +1.63 %) | En mercado alcista, la pata corta pierde justo cuando BTC rebota. Además exige margen |
| ***Grid* spot** | Rejilla de 20 niveles, inventario liquidado a fin de mes | **100 % de ciclos ganadores**; E por lote de −0.35 a +0.40 % | La pérdida vive en el inventario: lotes liquidados de −5.7 a −27.9 % |
| **DCA o martingala** | 5 órdenes de seguridad ×2, TP +1.5 % | **98.7–99.9 % de ciclos ganadores** | Sin stop, pérdida latente de −20 a −46 % del capital (DOGE quedó atrapado en −44 %); con stop de −35 %, E de −0.17 a −0.71 % por ciclo en el mercado bajista |
| TabPFN v2 (modelo fundacional tabular) | Ordenar mejor las candidatas con pocas muestras | Pierde en AUC en 5 de 6 pliegues; mezclado con el ensamble suma ≈ +2 pt por vela, dentro del ruido | No cumple la regla del proyecto (ganar en ≥ 3 de 6 pliegues). Queda **neutro** |

**La lección común.** La ventaja del modelo es de **reversión**: el rebote ocurre enseguida. Todo lo que **espera** después de la señal (confirmación, orden límite más abajo) o la **recorta** (toma parcial, stop a equilibrio) se queda sin los mejores rebotes. Y todo lo que sube el WR **contable** sin información nueva (toma parcial, *grid*, DCA) lo hace a costa de la esperanza o escondiendo la pérdida en la cola.

---

## 5. Lo más reciente (2024–2026): qué dice la evidencia

En esta sección, "verificado" significa que el Juez o el autor de este documento abrieron la fuente y confirmaron la afirmación. Muchas fuentes de 2026 son *preprints* sin revisión por pares.

### 5.1 Microestructura y cascadas: lo más relevante para la ventaja actual

- **Reversión de corto plazo en cripto** (Kitron y Wengrowicz, [arXiv 2608.21888](https://arxiv.org/abs/2608.21888), agosto de 2026; verificado). En velas de 15 min, el 90 % de 183 pares de Binance muestra reversión significativa, frente al 2.7 % de 187 acciones y ETF de EE. UU. Pero la ventaja bruta máxima es de **1.3 pb por operación** frente a un costo de 5 pb: se detecta, pero no paga los costos. **Lectura:** la reversión existe en todas partes, pero solo deja ganancia en los extremos, es decir, en las capitulaciones que ya compra el modelo.
- **Física de las cascadas de liquidación** (Garcia Seuma, [arXiv 2607.27070](https://arxiv.org/abs/2607.27070) y [2608.03616](https://arxiv.org/abs/2608.03616), 2026). En las cascadas de 2022–2025, el acoplamiento entre activos salta de 1.6 a 4.4 desviaciones. Las cifras más extremas (casi toda la venta forzada en los primeros 30 min, absorción por el fondo de respaldo) corresponden al crash de octubre de 2025. **Lectura:** el pánico es un fenómeno **de mercado**, y por eso la co-señal entre monedas funciona.
- **Comprar después de liquidaciones no basta** (K33, vía [The Block](https://www.theblock.co/amp/post/372115/whats-next-after-cryptos-fourth-largest-long-liquidation-event-of-2025), 2025). Después del 5 % de los días con más liquidaciones, BTC rinde en promedio +0.78 % a 30 días (mediana −1.1 %), frente a +5.9 % en días normales. Solo ≈ 1 de cada 4 marca un suelo. Hace falta **filtrar**.
- **La deriva negativa de las órdenes límite** (DeLise, [arXiv 2407.16527](https://arxiv.org/abs/2407.16527); "The Market Maker's Dilemma", [arXiv 2502.18625](https://arxiv.org/abs/2502.18625); verificado). En Binance, la probabilidad de que una orden *maker* se llene está correlacionada negativamente con el retorno posterior. Es lo mismo que midió el experimento de entradas *maker* de la sección 4.

### 5.2 Predicción selectiva con garantía

Selección conforme con control de FDR (Jin y Candès, [arXiv 2210.01408](https://arxiv.org/abs/2210.01408)), Learn-then-Test ([arXiv 2110.01052](https://arxiv.org/abs/2110.01052)), inferencia conforme adaptativa para deriva (Gibbs y Candès, [arXiv 2106.00170](https://arxiv.org/abs/2106.00170)) y conformidad sin intercambiabilidad (Barber et al., [arXiv 2202.13415](https://arxiv.org/abs/2202.13415)). En teoría permiten "operar solo cuando el acierto está garantizado". **En la práctica, con los datos de este bot, la garantía se rompe** (sección 4): una capitulación produce decenas de etiquetas iguales y el mercado cambia entre trimestres. Su valor es de **honestidad**: si Learn-then-Test no certifica un 75 %, un "80 % de diseño" no debe creerse.

### 5.3 Modelos fundacionales

- **Series de tiempo:** Kronos ([arXiv 2508.02739](https://arxiv.org/abs/2508.02739), 2025) está preentrenado con más de 12 000 millones de velas de 45 plataformas. Le siguen Chronos-2 ([arXiv 2510.15821](https://arxiv.org/abs/2510.15821), con covariables), TimesFM-2.5 y Moirai-2. La evaluación independiente más clara (Rahimikia, Ni y Wang, [arXiv 2511.18578](https://arxiv.org/abs/2511.18578); verificado) concluye que **los modelos preentrenados genéricos rinden mal** en *zero-shot* y con ajuste fino para retornos financieros. Solo ayuda preentrenar desde cero con datos financieros, algo fuera del alcance de este proyecto. [arXiv 2606.27100](https://arxiv.org/abs/2606.27100) reporta ganancias "pequeñas y escasas" frente al paseo aleatorio y no descuenta costos. Kronos, además, incluye datos hasta 2025 en su preentrenamiento, así que cualquier *backtest* sobre ese periodo está contaminado.
- **Tabulares:** TabPFN-3 ([arXiv 2605.13986](https://arxiv.org/abs/2605.13986), mayo de 2026) supera a los árboles ajustados en *benchmarks* generales, pero no hay evidencia financiera independiente. Aquí se probó la versión abierta v2: **neutra** (sección 4).

### 5.4 Agentes LLM

- **Flotas reales en producción** ([arXiv 2609.05663](https://arxiv.org/abs/2609.05663), septiembre de 2026; verificado): seis meses, 7.5 millones de invocaciones y ≈ 300 000 acciones en Hyperliquid. WR de ida y vuelta de **41 % frente a 50 %** del minorista de referencia, sin ventaja direccional y sin rentabilidad.
- **Estrategias descubiertas por LLM** (Gençay, [arXiv 2608.27734](https://arxiv.org/abs/2608.27734), agosto de 2026; verificado, sobre acciones y ETF de EE. UU.): con evaluación sin fugas y deflación por número de pruebas, **todas** se rechazan. Además, un oráculo con fuga deliberada y Sharpe de 35 **pasó** el DSR y el PBO: las salvaguardas estructurales contra fugas importan más que las correcciones estadísticas.
- **Memoria del pasado** (Look-Ahead-Bench, [arXiv 2601.13770](https://arxiv.org/abs/2601.13770)): los LLM "recuerdan" precios anteriores a su fecha de corte, así que todo *backtest* con LLM sobre ese periodo está contaminado.
- **Concursos cortos:** Alpha Arena (octubre–noviembre de 2025) duró dos semanas, y más de la mitad de los modelos perdió. Quien gana un concurso así gana por suerte.

**Uso aceptable de un LLM:** solo como **clasificador de titulares** ("noticia específica de la moneda", "noticia de mercado", "ninguna") para el filtro de tipo de choque, y **grabando hacia adelante**, nunca sobre datos anteriores a su fecha de corte.

### 5.5 Hechos de mercado 2025–2026 que cambian el tablero

- **Crash del 10 de octubre de 2025:** ≈ 19 000 millones de USD liquidados y la profundidad del libro cayó más de 90 %. Los SL se llenan peor justo en las capitulaciones, aunque el costo medido (+0.5–1 % de deslizamiento en cada SL) fue solo de 0.05–0.13 % de E.
- **CME opera 24/7 desde el 29 de mayo de 2026** (según el Explorador): las estrategias de "huecos de CME" dejaron de existir.
- **El *carry* de base se comprimió** en 2025: solo fue atractivo ≈ 8 % de los días, según Amberdata. Además requiere futuros, bloqueados desde la ubicación del usuario.
- **Liquidaciones exactas:** Hyperliquid publica sus *fills* con una marca de liquidación (verificado en el formato de su API). El *stream* de Binance `!forceOrder@arr`, en cambio, entrega **solo una** liquidación por símbolo cada 1 000 ms (verificado en su documentación), y probablemente está bloqueado igual que `fapi`.

---

## 6. Catálogo completo de candidatas

**Niveles:** **A** = adoptar o probar ya; **B** = prometedor, requiere datos nuevos; **C** = especulativo; **D** = descartar. "Medido" = probado con datos locales; "(2.ª)" = actualizado en la segunda iteración.

| # | Estrategia | Nivel | WR realista | ¿Spot desde tu ubicación? | Estado |
|---|---|---|---|---|---|
| E01 | Co-señal del modelo (amplitud del pánico) | **A** | 72–78 % | Sí | Medido |
| E02 | Umbral con garantía (conforme, Learn-then-Test) | C | No lo sube | Sí | Medido |
| E03 | Liquidaciones exactas (Hyperliquid, Coinalyze) | B | +0 a +3 pt | Sí (solo como dato) | *Proxy* medido; exactas, no. (2.ª) Coinalyze solo guarda 1 500–2 000 puntos intradía |
| E04 | Filtro de tipo de choque con LLM clasificador | B | +1 a +3 pt | Sí | No probado |
| E05 | Umbral dinámico por estrés (Nagel) | D | 70–72 % | Sí | Medido |
| E06 | Entrada confirmada por absorción | D | Peor | Sí | Medido |
| E07 | Escalera *maker* bajo el cierre | D | Peor por señal | Sí | Medido |
| E08 | Costos: BNB y TP límite | **A** | Sin cambio (+0.05 % de E) | Sí | Medido |
| E09 | Venn-Abers o isotónica y abstención por desacuerdo | D | Peor | Sí | Medido |
| E10 | TabPFN como modelo adicional | C | ≈ 0 | Sí | Medido (neutro) |
| E11 | Pesos de unicidad de la etiqueta | B | ≈ 0 en diseño; más estable | Sí | Medido |
| E12 | Salida dinámica (tesis rota, SL ancho, 24 h) | D | Peor E | Sí | Medido. (2.ª) La excepción es alargar la barrera (E41) |
| E13 | Profundidad del libro de futuros (*bookDepth*) | C | 0 a +2 pt | Sí (solo como dato) | No probado |
| E14 | Efecto del cuarto de hora | C | 0 a +1 pt | Sí | No probado |
| E15 | Prima de Coinbase y prima coreana | D | ≈ 0 | Sí | (2.ª) Medido: la prima es casi toda la base USDT/USD; C1 mixta; la coreana, sin gradiente |
| E16 | DVOL, *skew* y prima de varianza (Deribit) | B | +0.5 a +2 pt si se confirma | Sí | (2.ª) Medido: DVOL → D1 (E42); el *skew* no aporta |
| E17 | *Funding* y *basis* entre plataformas | C | 0 a +1 pt | Sí | Redundante con el modelo |
| E18 | Flujos de ETF y emisión de *stablecoins* | C | 0 a +1 pt | Sí | (2.ª) *Stablecoins*: sin gradiente. ETF: no probado (Farside respondió 403) |
| E19 | Filtro de desbloqueos de tokens | C (va en la higiene) | ≈ 0 en monedas grandes | Sí | Regla |
| E20 | Deslistados, etiqueta de monitoreo, listados | **A** | ≈ 0; evita la cola | Sí | Regla |
| E21 | Calendario macro (FOMC, CPI, vencimientos) | C | 0 a +1 pt | Sí | No probado |
| E22 | Kronos como generador de variables | C | 0 a +1 pt | Sí | No probado |
| E23 | Chronos-2, TimesFM o Moirai para la volatilidad | C | 0 a +1 pt | Sí | No probado |
| E24 | Agentes LLM como decisores | D | ≤ azar | Sí | Evidencia externa en contra |
| E25 | Rezago relativo dentro del pánico | D | Sin gradiente | Sí | Medido |
| E26 | Umbral adaptativo (ACI) | D | 72–78 % (peor) | Sí | Medido |
| E27 | Cobertura con corto en BTC (margen) | C | Baja el WR | No verificado (margen) | Medido |
| E28 | Segunda manga de tendencia transversal (CTREND) | B | 35–45 % por operación; sube el % de meses ganadores | Sí | No probado |
| E29 | Medir el % de meses ganadores | **A** | 15 de 15 meses en diseño | Sí | Medido |
| E30 | Toma parcial + stop a equilibrio | D | 90 % contable, E peor | Sí | Medido |
| E31 | *Grid* spot | D | 100 % de ciclos, E ≤ 0 | Sí | Medido |
| E32 | DCA o martingala | D | 99 % de ciclos, ruina | Sí | Medido |
| E33 | *Dual Investment* "Buy Low" (venta de *puts*) | D | 70–90 % de cobros | No verificado | Venta de cola |
| E34 | *Market making* (Avellaneda-Stoikov) | D | E < 0 con comisión minorista | Sí | Evidencia externa en contra |
| E35 | *Cash-and-carry* y arbitraje de *funding* | D | 80–95 % de periodos | **No** (futuros) | Bloqueado |
| E36 | Arbitraje triangular o entre plataformas | D | No aplica | Sí | Sin oportunidades netas |
| E37 | Prueba prospectiva secuencial con e-valores | **A** | No aplica | Sí | En el pre-registro |
| E38 | *Holdout* fresco con monedas nuevas + estrés 2022 | **A** | No aplica | Sí | En la hoja de ruta |
| E39 | VPIN o toxicidad del flujo | D | ≈ 0 | Sí | Evidencia en contra |
| E40 | Sentimiento de noticias o redes como variable | D | ≈ 0 | Sí | Evidencia en contra |

**Añadidas por el Juez** (el Explorador no las tenía):

| Pieza | Nivel | Por qué importa |
|---|---|---|
| Corregir `nn_report.summarize` | **A** | Los análisis por moneda y del azar del *holdout* usan esa función (sección 9) |
| La amplitud útil es la co-señal del modelo, no la de precio | **A** | Define la regla exacta que se debe pre-registrar |
| Fuente en vivo de los datos de futuros y evaluación "sombra" diferida | **A** | Sin esto, ninguna mejora se puede operar desde tu ubicación (sección 8.3) |
| Política de reentrenamiento y brazo ENS12U | **A** | La v2 se entrenó hasta 2025-03; en 2026-T1 y T2 su WR cayó a 60–63 % |
| Riesgo por episodio | **A** | La compuerta concentra la exposición en pocos días |
| El episodio como unidad de muestra | **A** | ≈ 16 episodios por año con 4 monedas: fija la duración de la prueba |
| Pesos de unicidad como antídoto contra la caída de diseño a prueba | B | Es la única técnica probada que achica esa brecha |
| Separar el universo que se opera del que alimenta la compuerta | B | Permite operar 18 monedas sin cambiar la definición validada |

**Añadidas en la segunda iteración** (efecto en diseño sobre la pila v2 + co-señal, en ENS13, salvo que se indique otra cosa):

| # | Estrategia | Nivel | ΔWR / ΔE en diseño | Estado |
|---|---|---|---|---|
| E41 | **Barrera de tiempo de 96 h** (E7) | **A** | +2.3 pt / +0.12 %; réplica en 3 de 3 ensambles | **Adoptada en la v3** (11.3) |
| E42 | **Veto por DVOL bajo** (D1, $z_{30} < -1$) | B | +3.3 pt / +0.33 % sobre la v3; +2.1 a +4.7 pt en 4 ensambles | Brazo S3 y estrés de 2022 (11.4) |
| E43 | TP reducido a +0.6 % desde las 36 h | C | +2.4 pt / −0.16 % sobre la v3 | Brazo opcional S4 (palanca de preferencias) |
| E44 | Co-señal que viene de BTC o ETH (G_BE) | B | +2.4 pt / +0.26 % | Hipótesis; grabar el marcador |
| E45 | Moneda que inicia el episodio (F_rank1) | B | +4.3 pt / +0.22 %, con −63 % de operaciones | Hipótesis; grabar el marcador |
| E46 | Episodio que empieza ≥ 3 días después del anterior | C | +2.8 pt / +0.38 % (n = 60) | Hipótesis |
| E47 | Régimen BTC > SMA de 30 días | C | +4.7 pt / +0.34 %; ENS12U no lo replica | Hipótesis |
| E48 | Rezagados: no comprar si las otras anclas ya rebotaron (H1) | C | +0.8 pt / −0.04 % (contaminada) | Hipótesis; grabar L4 |
| E49 | Prioridad por antigüedad bajo cupo (H5) | B | No medible con 4 monedas | *Holdout* de 20 monedas |
| E50 | Tipo de choque en noticias (GDELT) | B | No probado (HTTP 429 vía VPN) | Repetir la sonda sin VPN |
| — | Las demás reglas de la segunda iteración | D | ≤ 0, o WR a costa de E | Sección 11.5 |

---

## 7. Trampas: cómo se fabrican win rates de 70–95 %

1. **La geometría.** Con un TP corto y un SL largo, el azar ya acierta $1/(1+b)$ de las veces. En este proyecto, entradas al azar con TP de 1 ATR y SL de 3 ATR ganaron el 74.7 % y perdieron dinero.
2. **Pérdidas que no se cierran.** En martingalas, DCA, *grids* y la táctica de "mantener hasta que dé ganancia", las posiciones perdedoras siguen abiertas y **no cuentan** en el WR. Esta ronda lo midió: 99–100 % de ciclos ganadores, con pérdidas latentes de hasta −46 %.
3. **Contar mal.** Cada TP parcial cuenta como una ganancia, las salidas "en cero" que pierden los costos se cuentan como ganadas, o se cuentan órdenes en vez de posiciones. La toma parcial de esta ronda dio 90.4 % "contable" con menos esperanza.
4. **Costos irreales.** Comisión cero o llenado de toda orden límite al tocar el precio, ignorando la selección adversa.
5. **Selección.** Se prueban miles de variantes y se publica la mejor. La v2 marcó 81 % en diseño y 69 % en datos nuevos; C1, 72 % y 60 %.
6. **Fugas del futuro.** Marcas de tiempo mal alineadas (el `create_time` de Binance cambió de significado el 2024-03-04), velas aún abiertas o un LLM que "recuerda" el precio.
7. **Ventanas, rankings y canales.** *Backtests* de "los últimos 90 días" en mercado alcista, rankings de *copy-trading* que solo muestran a los sobrevivientes, canales que borran las señales fallidas y concursos de dos semanas.
8. **Productos de "rendimiento".** *Dual Investment*, *Shark Fin* y similares muestran un APR "garantizado" que en realidad es una prima de opción vendida: se cobra casi siempre y, cuando se pierde, se pierde la caída completa.

**Regla para detectar el engaño.** Antes de creer cualquier WR, pide: (a) la esperanza neta por operación y su $t$ agrupado por día; (b) el WR del **azar con la misma geometría**; (c) la pérdida máxima por posición y el *drawdown* con las posiciones abiertas valoradas a mercado; (d) el número de configuraciones probadas; y (e) resultados posteriores a la fecha en que se congeló la estrategia. Si falta cualquiera de los cinco, el WR no significa nada. Y si la mejora viene de cambiar la **salida**, comprueba que la E también suba: un WR que sube con E que baja es WR fabricado (sección 11.2).

---

## 8. Hoja de ruta y pre-registro

### 8.1 Hoja de ruta

Todo es *spot*: los futuros no se pueden ejecutar desde tu ubicación. **Cada paso que descarga de Binance requiere la VPN apagada.**

| Fase | Prioridad | Plazo | Qué se hace | Criterio de paso o fallo |
|---|---|---|---|---|
| 0 | P0 | 1–3 días | Corregir `nn_report.summarize`; volver a emitir el desglose por moneda de diseño y, como corrección **descriptiva**, el azar del *holdout*; firmar el pre-registro con *hash*. Repetir **sin VPN** las 10 sondas de la sección 11.7 (no tocan Binance) | Pasa si las tablas se vuelven a emitir con el cambio documentado. Si el azar corregido del *holdout* mueve ΔWR más de 2 pt, se anota |
| 1 | P0 | Semanas 1–2 | Canal **sombra**: cada día se descargan velas spot de 15 min, *metrics*, *funding*, prima y velas de futuros de 18 monedas desde `data.binance.vision` (llegan al día siguiente), más el DVOL horario de Deribit; un script calcula $\hat p$, la co-señal, $z_{30}$ y la simulación, y lo registra con *hashes* | Pasa si reproduce bit a bit las predicciones de diseño en 3 días de control (2025-06) y faltan ≤ 5 % de los datos |
| 2 | P1 | Semanas 2–6 | **Holdout fresco:** descargar *metrics*, *funding* y prima 2023-01..2025-06 de **20 monedas nunca usadas** (lista sellada antes de mirar) y volver a correr el *walk-forward* solo como prueba. **Cubre las mismas fechas que el diseño**, es decir, los mismos pánicos: solo confirma reglas **dentro del episodio** (que el modelo elige bien monedas nuevas, E7 y H5), no reglas **de episodio** (co-señal, D1, H1) | E7 se confirma si 384 velas no bajan ni el WR ni la E frente a 288 en las monedas nuevas (*bootstrap* por episodio). H5 se mide con cupo de 3 posiciones. La co-señal solo se reporta como descriptivo |
| 3 | P1 | Semanas 3–6 | **Estrés 2022** (LUNA, FTX) con el modelo congelado, la v3, D1 y los topes de riesgo. Requiere los *metrics* de futuros de Binance de 2022 (descargarlos **con la VPN apagada**); el DVOL existe desde 2021-03. Es la única fuente de **episodios nuevos** antes de la prospectiva | Pasa si la pérdida por episodio es ≤ 3 R con los topes; si no, se endurecen los topes. Se reporta, además, si las vetadas por D1 ganan menos que las conservadas |
| 4 | P2 | Desde ya | Grabar **hacia adelante**: DVOL de BTC y ETH (cada hora), USDT-USD de Coinbase (15 min), margen de Bitfinex (`…/last`), el rebote de las otras 3 anclas (L4, para H1), los marcadores G_BE y F_rank1 de cada señal, *fills* de Hyperliquid con marca de liquidación, anuncios de Binance y titulares clasificados por un LLM | Una variable entra al modelo solo si, con ≥ 150 señales prospectivas, muestra un gradiente monotónico con P ≤ 0.10 |
| 5 | P2 | Mes 1 | **ENS12U** (pesos de unicidad), reentrenado hasta 2026-09-30 y congelado con *hash* | Corre como brazo S2; no reemplaza a la v3 salvo que gane la prueba prospectiva |
| 6 | P0 | Meses 1–15 | Prueba prospectiva pre-registrada (8.2), con revisión mensual | Aprobar, declarar futilidad o seguir |
| 7 | P3 | Solo si aprueba | Operación real pequeña con BNB, TP límite y topes de riesgo | 3 meses en vivo con deslizamiento ≤ 0.1 % por lado y resultados dentro del intervalo de la sombra |
| B | P3 | En paralelo | Segunda manga de tendencia transversal (CTREND, solo largos) en velas diarias de 30–50 monedas, para subir el % de meses ganadores | Correlación mensual ≤ 0.2 con la manga de capitulaciones y E > 0 en un *walk-forward* sin ajuste fino |

**No hacer:** *grid*, DCA o martingala; toma parcial o TP reducido por estado para inflar el WR; recalibrar o cambiar $\theta$; agentes LLM como decisores; entradas *maker* escalonadas o confirmadas; ninguna estrategia que requiera ejecutar futuros.

### 8.2 Pre-registro de la prueba prospectiva

Redactado el 2026-10-15 y actualizado el 2026-10-16 (P1 pasa a la v3; se añaden S3 y S4). Los datos locales terminan el 2026-09-30, así que no se ha visto ningún dato posterior.

**Especificación congelada.** Modelo v2 de `output/constructor/spec_nn_v2.json` (ENS13 = 6 LightGBM + 6 MLP + 1 CNN, Platt por modelo, $\theta$ = 0.71427), con los *hashes* SHA-256 de la especificación, los 20 archivos de modelo y los scripts. Salida X5 con barrera de **384 velas** ($TP = c\,(1 + 0.7\,s_d)$, $SL = c\,(1 - 1.75\,s_d)$, cierre a las 96 h), común a todos los brazos, entrada al cierre de la vela de señal, empate TP/SL = SL y una posición por moneda. Universo fijo de 18 pares USDT: BTC, ETH, SOL, DOGE, ADA, ATOM, AVAX, BCH, BNB, DOT, ETC, FIL, LINK, LTC, NEAR, TRX, UNI y XRP. Regla temporal: un registro con marca $T$ se puede usar en la vela $i$ solo si $T \le t_i + 5$ min; si falta un dato por más de 30 min, esa vela no opera.

**Brazos:**

| Brazo | Regla | Papel |
|---|---|---|
| **P1** | **v3** = v2 + co-señal $A_4 \ge 1$ ($W$ = 12 h) + barrera de 384 velas | Primario |
| C0 | v2 sin compuerta | Control: mide el valor de la compuerta |
| S1 | v2 + $A_{18} \ge 3$ (≥ 3 de las otras 17 monedas en 12 h) | Secundario |
| S2 | ENS12U (pesos de unicidad) + $A_4 \ge 1$ | Secundario |
| S3 | v3 + D1: no comprar si $z_{30}$ del DVOL de BTC < −1 (definición en 11.4) | Secundario; regla **de episodio** |
| S4 (opcional) | v3 + TP reducido a +0.6 % sobre la entrada desde las 36 h | Solo si el usuario prioriza el WR sobre la E; es *post hoc* |
| Azar | Todas las velas válidas con la misma moneda, mes y geometría, más el azar condicionado a $A_4 \ge 1$ | Referencia |

Costos: 0.24 % (principal), 0.30 % (estrés) y 0.19 % (BNB, informativo).

**Criterio de S3.** Tras ≥ 150 señales de P1, las vetadas por D1 deben tener un WR **menor** que las conservadas, con P ≤ 0.10 en un *bootstrap* por episodio y con ≥ 5 episodios vetados. S4 se evalúa por su cuenta: solo se adopta si el usuario acepta perder E a cambio de WR.

**Periodo y tamaño.** Desde el 2026-10-01 hasta lo primero que ocurra entre **400 operaciones de P1** y el **2027-12-31**. Con un WR real de 76 %, el límite de Wilson supera 70 % con ≈ 225 operaciones independientes, ≈ 400–450 con $DEFF \approx 2$. Para demostrar $E > 0$ con $\mu = 0.7\,\%$, $\sigma = 4\,\%$, $\alpha = 0.05$, potencia 0.8 y $DEFF = 2$ hacen falta ≈ 400 operaciones. Se esperan entre 250 y 400 operaciones de P1 al año, es decir, **12 a 18 meses**.

**Criterios de aprobación de P1** (todos, con $c = 0.24\,\%$ salvo que se indique otra cosa):

1. **E neta > 0** con $t$ agrupado por día ≥ 1.645, y E > 0 también con $c = 0.30\,\%$.
2. **WR:** límite inferior de Wilson al 95 % ≥ 0.70 ("aprueba 70"); ≥ 0.75 → "aprueba 75". El **80 % solo se declara si el límite inferior es ≥ 0.80**.
3. **Ventaja sobre el azar** de la misma moneda, mes y geometría: $\Delta E > 0$ con $t$ por día ≥ 1.645, y $\Delta WR > 0$.
4. **Valor de la compuerta:** E(P1) − E(C0 con $A_4 = 0$) > 0 con *bootstrap* por días, P ≤ 0.10.
5. **Episodios:** ≥ 60 % de los episodios en positivo.
6. **Auditoría:** los *hashes* coinciden y ningún parámetro cambió. Todo análisis que no esté en esta lista se etiqueta "exploratorio".

**Vigilancia mensual sin inflar el error (e-procesos).** Mirar los resultados cada mes y detenerse en cuanto "se vean bien" infla los falsos positivos. Un e-proceso permite mirar cuando se quiera:

$$
M_n = \prod_{i=1}^{n}\big(1 + \lambda_i\,(X_i - p_0)\big),
\qquad \text{rechazar } H_0: p \le p_0 \ \text{ si } \ M_n \ge 1/\alpha
$$

**Qué es cada símbolo:**

- $X_i$: 1 si la operación $i$ ganó (neto > 0) y 0 si perdió.
- $p_0$: el WR que se quiere superar (0.70).
- $\lambda_i$: tamaño de la "apuesta", elegido solo con las operaciones anteriores, entre 0 y $1/p_0 = 1.43$.
- $M_n$: el "capital" de un apostador que apuesta contra $H_0$. Si $H_0$ fuera cierta, sería muy raro que se multiplicara por 20.
- $\alpha = 0.05$ ⇒ se rechaza cuando $M_n \ge 20$.

> **Ejemplo:** con $\lambda = 0.5$ y $p_0 = 0.70$, cada acierto multiplica $M$ por $1 + 0.5 \times 0.30 = 1.15$ y cada fallo por $1 - 0.5 \times 0.70 = 0.65$. Si el WR real fuera 78 %, $\ln M$ crecería en promedio $0.78 \ln 1.15 + 0.22 \ln 0.65 = +0.014$ por operación, y llegaría a $\ln 20 = 3.0$ en ≈ 210 operaciones independientes. Si el WR real fuera 70 %, $M$ no crecería.

Para la esperanza se usa lo mismo sobre la media diaria de los resultados en R, recortados a [−1.2, 0.6] para que el producto nunca se vuelva negativo ($\lambda_d \in [0, 0.8]$). **Futilidad:** con 200 operaciones o más, si el límite superior de Wilson del WR es < 0.70, o si el intervalo de E (*bootstrap* por días) queda entero por debajo de 0, se detiene y se declara "no aprobado".

**Prohibiciones.** Durante la prueba no se cambian $\theta$, la geometría (incluida la barrera de 384 velas), el corte de D1, el universo ni $W$; no se reentrena la v2, y ninguna decisión usa el *holdout* 2025-07..2026-09.

### 8.3 El bloqueo práctico: los datos de futuros en vivo

El modelo necesita cada 5 minutos el open interest, los ratios long/short, el *funding* y la prima, que vienen de `fapi.binance.com`, **bloqueada desde tu ubicación** (HTTP 451). Hay tres caminos:

1. **Evaluación sombra diferida** (lo que propone la fase 1): los archivos diarios de `data.binance.vision` llegan con un día de retraso. Sirven para la prueba prospectiva, que no necesita operar en tiempo real.
2. **Fuente sustituta en vivo** (Coinalyze u otra), validada con una prueba de equivalencia: correlación de cada variable con la de Binance y repetición de la simulación con la fuente sustituta. Si no es equivalente, hay que reentrenar con esa fuente. Coinalyze solo guarda 1 500–2 000 puntos intradía: no sirve para diseño, pero sí en vivo. OKX (*rubik*) es otra opción en vivo, con retención corta.
3. **Un servidor en una jurisdicción permitida**, siempre cumpliendo los términos de servicio de Binance.

Sin una de estas tres opciones, ninguna mejora del WR se puede operar en vivo. El DVOL que necesita D1, en cambio, viene de la API pública de Deribit: gratis, sin clave y sin depender de Binance (verificado vía VPN; falta verificarlo sin ella).

---

## 9. Correcciones al trabajo anterior

**Error en `nn_report.summarize`.** `Trades.concat` (en `harness.py`) **ya ordena** las operaciones por hora de entrada, pero `summarize` arma el vector de monedas en el orden original de concatenación y después lo "reordena" con un índice calculado sobre las operaciones ya ordenadas, que no cambia nada. Resultado: **cada operación queda asociada a la moneda equivocada**. Esto afecta al azar "misma moneda y mes" y al desglose por moneda de `nn_report.py`, `nn_v2_report.py`, `nn_eval.py` y `nn_v2_eval.py`.

| Qué cambia | Antes | Corregido |
|---|---|---|
| Azar agregado de diseño (v2) | 62.0 % / −0.441 % | 61.7 % / −0.426 % (cambio pequeño) |
| ETH en el desglose de diseño de `fase3.md` | 74 % / +0.62 % | **87.1 % / +1.67 %** |
| BTC en el desglose de diseño | +1.85 % | **80.9 % / +0.74 %** |

**Qué hay que revisar en [modelos-complejos-y-datos.md](modelos-complejos-y-datos.md):** la tabla "Desglose de la prueba principal de la v2", por moneda (sección 3.8), y el "WR del azar con la misma geometría" de las pruebas en monedas nuevas salen de esa función. Las cifras agregadas del modelo (n, WR y E del candidato) no dependen de la asignación de monedas, pero el desglose por moneda sí, y el azar puede moverse un poco. La corrección ya está en `be_common.simulate_entries`. Hay que volver a emitir esas tablas como corrección descriptiva (fase 0).

**Afirmaciones del Explorador que el Juez corrigió:**

- El "81 % con pánico multi-moneda" que citó el Explorador salió del subconjunto *ex post* del *holdout*; no es un resultado independiente.
- En Garcia Seuma, las cifras más extremas son del crash de octubre de 2025, no de las 7 cascadas.
- En Kim y Hansen (efecto del cuarto de hora), "el retorno de apertura se revierte en la primera media hora" no aparece en el resumen.
- El trabajo de 2608.27734 evalúa acciones y ETF de EE. UU., no cripto.
- La evaluación independiente de Kronos en BTC (Brier 0.189 frente a 0.188) no se pudo verificar porque la página no abrió.

**Correcciones de la segunda iteración a este mismo documento:**

- **Fase 2 de la hoja de ruta.** Decía que el *holdout* fresco de 20 monedas confirmaría la co-señal. No puede: cubre las mismas fechas, y por tanto los mismos pánicos, que el diseño. Solo confirma reglas dentro del episodio (sección 8.1 corregida).
- ***Bootstrap* por día.** Los intervalos y las P de la sección 2.4 agrupan por día; con episodios de varios días eso subestima la varianza. Desde la segunda iteración se agrupa por episodio.
- **Nombre "v3".** En la primera iteración designaba el ensamble con pesos de unicidad; ahora ese modelo se llama ENS12U y "v3" es la pila principal (v2 + co-señal + barrera de 96 h).

---

## 10. Dónde está todo

Todo está en `binance-research/data/research/` (carpeta ignorada por git):

| Ruta | Contenido |
|---|---|
| `scripts/be_common.py` | Funciones comunes, incluida `simulate_entries` con la alineación corregida |
| `scripts/be_breadth.py`, `be_breadth2.py`, `be_uniq_gate.py`, `be_events.py` | Co-señal del modelo, réplicas, episodios y *bootstrap* |
| `scripts/be_capbreadth.py`, `be_leadlag.py` | Amplitud de precio y rezago relativo (rechazados) |
| `scripts/be_liqproxy.py` | *Proxies* de liquidación |
| `scripts/be_conformal.py`, `be_hedge_aci.py`, `be_disagree.py` | Garantía conforme, ACI, cobertura con BTC, desacuerdo e isotónica |
| `scripts/be_maker.py`, `be_confirm.py`, `be_manage.py`, `be_stack.py` | Ejecución, gestión, costos y pila combinada |
| `scripts/be_structural.py`, `be_structural_bear.py` | *Grid* y DCA |
| `scripts/be_uniq.py`, `be_uniq2.py` | Pesos de unicidad |
| `scripts/be_tabpfn.py` | TabPFN v2 |
| `output/bleeding_edge/` | Informes (`be_*.md`), datos (`be_*.json`), registros (`be_*.log`) y las 12 predicciones nuevas con pesos de unicidad (`preds/`) |
| `scripts/be2_*.py` | Segunda iteración, ronda 1: `be2_common.py`, geometrías (`be2_geom.py`, `be2_geom2.py`), compuertas (`be2_gatevar.py`), re-entrada, segunda etapa, simulador conjunto (`be2_joint.py`), TP decreciente (`be2_tpdecay.py`), `be2_extra*.py`, la pila v3 (`be2_v3.py`) y `be2_report.py` |
| `scripts/be2b_*.py` | Ronda 2A (hipótesis del Investigador B): `be2b_common.py`, `be2b_sel.py`, `be2b_h2.py`, `be2b_h3.py`, `be2b_h4h5.py`, `be2b_h8h9.py` y `be2b_final.py` |
| `scripts/be2c_*.py` | Ronda 2B (fuentes del Investigador A): `be2c_dvol.py` (D1, D2, C1 y B1) y `be2c_report.py` |
| `output/bleeding_edge_r2/` | Informes de los cuatro agentes (`investigador_A.md`, `investigador_B.md`, `laboratorio_r1.md`, `laboratorio_r2a.md`, `laboratorio_r2b.md` y `laboratorio_consolidado.md`) y las salidas `be2*_*.md`, `.json` y `.log` |
| `tmp/be2_geom/` | Caché de etiquetas por geometría (incluida la salida anclada de H2) |
| `output/validador/trials_log.csv` | Registro de configuraciones: ≈ 101 de la primera iteración y 208 de la segunda (`bleeding_edge_r2`, 178; `bleeding_edge_r2_A_peek`, 30) |
| `output/validador/holdout_log.csv` | Una entrada descriptiva nueva (`be_structural_bear`, solo precios) |

Fuera del proyecto, todo en el disco E:

- **Temporales de TabPFN** (primera iteración): `E:/tmp/be_pkgs` (78 MB, paquetes aislados; no se tocó el `.venv`), `E:/tmp/be_dl`, `E:/tmp/be_tabpfn_stub.py`, `E:/tmp/be_tabpfn_probe.py` y `E:/hf-cache` (28 MB con los pesos del modelo). Se pueden borrar si no se va a volver a usar TabPFN.
- **Datos de terceros de la segunda iteración** (no confiables; nunca se ejecutaron): `E:/tmp/r2_data/` (DVOL de BTC y ETH, Fear & Greed, *stablecoins*, Coinbase, Upbit, Bitfinex y opciones de Deribit) y `E:/tmp/r2_probe/` (sondas, operaciones de diseño reconstruidas y los scripts del Investigador A). Se pueden borrar; si se borran, `be2c_dvol.py` necesitará volver a descargar el DVOL.

---

## 11. Segunda iteración (2026-10-16): buscando +1 punto

**Objetivo:** sumar al menos +1 punto de WR, sin bajar la E, a la pila de la primera iteración (v2 + co-señal: 131 operaciones, 85.5 % y +1.90 % en diseño; 72–78 % esperado fuera de muestra). **Resultado:** una pieza adoptada (E7, la barrera de 96 h), una con reserva (D1, el veto por DVOL bajo), seis hipótesis abiertas, una palanca de preferencias y el resto rechazado.

### 11.1 Cómo se hizo

Cuatro agentes: el **Investigador A** buscó fuentes de datos nuevas, con historial gratis de 2023–2025 y sin tocar dominios de Binance (unas 20 fuentes sondeadas y ≈ 30 variables miradas de forma descriptiva); el **Investigador B** propuso métodos (10 hipótesis, H1 a H10, con conteos de la muestra y simulaciones teóricas); el **laboratorio** las probó, y el **redactor** actualizó este documento. El laboratorio hizo una ronda 1 sobre la pila (132 configuraciones), una ronda 2A con las hipótesis de B (33) y una ronda 2B con las fuentes de A (13); con las 30 del vistazo descriptivo de A, suman **208 configuraciones**.

Las reglas fueron las de la sección 0: **solo diseño**, *holdout* intacto, nada descargado de Binance y cada configuración registrada antes de correrla. Tres novedades de método:

- ***Bootstrap* por episodio** (días con operaciones unidos si distan ≤ 2 días; 5 000 réplicas) e IC beta-binomial con efectos aleatorios por episodio.
- **Réplica en 3 o 4 ensambles:** ENS13 (la v2), ENS12 (sin la CNN), ENS12U (con pesos de unicidad) y, en la ronda 2B, ENS6 (la v1).
- **Tamiz** que debe pasar una pieza para entrar en la pila: ΔWR ≥ +1 pt y ΔE ≥ 0 en ENS13; mejora en ≥ 4 de 6 pliegues; P(ΔWR ≤ 0) ≤ 0.20; réplica en ≥ 2 de 3 ensambles; y que el azar condicionado a la regla no explique más de la mitad de la ΔWR.

### 11.2 Cuándo cuenta la mejora que también obtiene el azar

La última condición del tamiz separa "el modelo elige bien" de "ese día era bueno para cualquier compra". Tiene sentido para las reglas que deciden **qué comprar**, pero no para las que deciden **cómo salir**: una salida distinta cambia la geometría, y la geometría afecta igual al modelo y al azar. Por eso el orquestador fijó esta regla:

| Tipo de regla | Pregunta | Prueba decisiva |
|---|---|---|
| **De selección** (qué comprar) | ¿El modelo elige mejor, o la regla solo aparta días malos para cualquiera? | El azar condicionado no debe explicar más de la mitad de la ΔWR |
| **De salida** (cómo cerrar) | ¿El WR sube de verdad o es fabricado? | El WR y la E deben subir **a la vez**, también para el azar con la misma salida. Si el WR sube y la E baja, es WR fabricado |

**E7** es de salida y sube el WR y la E del modelo y del azar condicionado: **es una mejora legítima**. **D1** es de selección y el azar explica entre el 63 y el 129 % de su mejora: **no pasa**. Apartar días malos también le serviría al bot, pero una regla de días descansa en muy pocos episodios y no se distingue de la suerte; por eso va a la prueba prospectiva. **El TP reducido desde las 36 h** (S4) y **el TP por estado** (H3) suben el WR y bajan la E: son WR fabricado.

### 11.3 E7: alargar la barrera de tiempo de 72 h a 96 h (adoptada)

**La regla.** Mismo TP ($0.7\,s_d$) y mismo SL ($1.75\,s_d$); la barrera de tiempo pasa de 288 a **384 velas**. **Por qué funciona.** Una operación que llega a las 72 h sin tocar ni el TP ni el SL se cerraba "por tiempo", y esas salidas ganaban poco. Si sigue abierta, la probabilidad de tocar antes el TP que el SL, sin deriva, es aproximadamente la del paseo aleatorio de la sección 1.3:

$$
P(\text{TP antes que SL}) \approx \frac{m}{a + m} = \frac{1.75}{0.7 + 1.75} = 71.4\,\%
$$

**Qué es cada símbolo:** $a$ y $m$ son la distancia al TP y al SL en volatilidades diarias $s_d$ (0.7 y 1.75 con X5); 71.4 % es la probabilidad de que el TP llegue primero con deriva nula. Con la deriva positiva de los rebotes (sección 1.3) es mayor, y en cualquier caso muy superior al 37.5 % de WR que tenían las salidas por tiempo.

> **Ejemplo (ENS13):** de las 131 operaciones, 8 salían por tiempo a las 72 h, con un WR de 37.5 % y E −0.16 %. Con 96 h, 5 de esas 8 tocan el TP, ninguna toca el SL y el resto sigue saliendo por tiempo. El WR gana 3 operaciones netas (de 112 a 115 de 131). En los tres ensambles juntos, las operaciones lentas que se resuelven entre las 72 y las 96 h terminan en **18 TP frente a 2 SL**.

**Resultados en diseño** (*bootstrap* por episodio):

| Ensamble | Pila (288 velas): n · WR · E | v3 (384 velas): n · WR [Wilson] · E | ΔWR / ΔE | P(ΔWR ≤ 0) / P(ΔE ≤ 0) |
|---|---|---|---|---|
| **ENS13** | 131 · 85.5 % · +1.90 % | **131 · 87.8 % [81.1, 92.3] · +2.02 %** | **+2.3 pt / +0.12 %** | 0.04 / 0.00 |
| ENS12 | 110 · 83.6 % · +1.69 % | 108 · 87.0 % [79.4, 92.1] · +1.90 % | +3.4 pt / +0.21 % | 0.04 / 0.00 |
| ENS12U | 341 · 78.6 % · +0.99 % | 336 · 81.8 % [77.4, 85.6] · +1.09 % | +3.3 pt / +0.11 % | 0.00 / 0.00 |
| ENS13, barrera elegida en *walk-forward* | 131 · 85.5 % · +1.90 % | 131 · 87.0 % [80.2, 91.7] · +1.97 % | +1.5 pt / +0.07 % | 0.13 / 0.10 |

- En ENS13, el 92 % de los 24 episodios queda en positivo (antes, el 83 %) y los 15 meses activos siguen en positivo. Con BNB, la E sube a +2.07 %. Por moneda: BTC 93 %, ETH 92 %, SOL 85 % y DOGE 84 %, las 4 iguales o mejores que con 72 h. Con 576 velas (144 h) el WR es el mismo y la E algo menor (+1.99 %). **Costo:** la posición puede durar hasta 4 días en lugar de 3, y el capital queda inmovilizado ≈ 5 % más de tiempo. La peor operación no cambia (−10.5 %).

**Reservas:**

1. **La idea salió de la prueba.** Se inspiró en una rejilla de geometrías (en la que 288 velas ganaba a 192) medida sobre los mismos pliegues. La versión honesta, con la barrera elegida solo con pliegues anteriores, da +1.5 pt.
2. **Pocos pliegues la notan.** Mejora 3 de 6 pliegues, empata 2 y en el otro deja el WR igual con +0.05 % de E: solo afecta al ≈ 6 % de las operaciones (las que salen por tiempo). Ningún pliegue empeora, pero no llega a 4 de 6.
3. **Es sobre todo estructural.** El azar condicionado también sube 1.7 pt (de 73.5 % y +0.71 % a 75.2 % y +0.83 %), y en la v2 sin compuerta la barrera de 96 h suma de +1.6 a +2.9 pt. El azar explica el 74 %, el 56 % y el 85 % de la mejora en ENS13, ENS12 y ENS12U. Según la sección 11.2, eso no la invalida.
4. **En mercado bajista podría costar E.** La ganancia depende de que la deriva no sea negativa. Hay que verla en el estrés de 2022.

**Fuera de muestra.** De los +2.3 pt, ≈ +1.7 son estructurales y deberían conservarse en un 70–100 % si la deriva no es negativa. Los ≈ +0.6 restantes son del modelo y se encogerán como la v2, a ≈ 50 %. **Estimación: +1 a +1.5 pt de WR y de 0 a +0.1 % de E. Pila v3: WR ≈ 73–79 % y E ≈ +0.6 a +1.2 %.** Como E7 es una regla dentro del episodio, el *holdout* fresco de 20 monedas sí puede confirmarla.

### 11.4 D1: no comprar si el DVOL de BTC está bajo (con reserva)

**La idea.** El DVOL de Deribit es el índice de volatilidad implícita de las opciones de BTC (el "VIX" de BTC). En un pánico de liquidez, las opciones se encarecen: el DVOL salta sobre su media y el miedo sobrepreciado favorece el rebote. Si el precio cae **sin que las opciones paguen miedo**, la caída se parece más a la de un **vendedor informado o estructural**: salidas de GBTC, el hack de Bybit. Esas caídas no rebotan.

**La regla:**

$$
z_{30}(t) = \frac{\text{DVOL}_{h(t)} - \overline{\text{DVOL}}_{720}}{\sigma_{720}},
\qquad
\text{no comprar en } t \iff z_{30}(t) < -1
$$

**Qué es cada símbolo:**

- $h(t)$: la última hora cerrada antes de abrir la vela de señal; se usa la hora con marca $ts$ tal que $ts + 1\text{ h} \le$ apertura de la vela.
- $\text{DVOL}_{h(t)}$: cierre del DVOL de BTC en esa hora. Se usa el de BTC para las 4 monedas, porque no hay DVOL de SOL. Usar el de ETH para ETH da lo mismo.
- $\overline{\text{DVOL}}_{720}$, $\sigma_{720}$: media y desviación de las últimas 720 horas cerradas (30 días).
- **Fuente:** API pública de Deribit, `public/get_volatility_index_data` con `resolution=3600`; horaria desde 2021-03, gratis, sin clave y sin depender de Binance.

> **Ejemplo (números ilustrativos):** si el DVOL vale 45, su media de 30 días es 52 y su desviación es 5, entonces $z_{30} = (45 - 52)/5 = -1.4 < -1$, y la señal **no** se compra aunque tenga co-señal. Con DVOL 50, $z_{30} = -0.4$ y se compra.

**Resultados en diseño.** ENS13 está **contaminado**: el corte −1 se eligió mirando sus operaciones. Los otros tres ensambles no lo están:

| Ensamble | ΔWR / ΔE sobre la pila (288 velas) | ΔWR / ΔE sobre la v3 | v3 + D1: n · WR · E | Vetadas (sobre la v3): n · WR · E | El azar explica (pila / v3) |
|---|---|---|---|---|---|
| ENS13 (contaminado) | +3.9 pt / +0.35 % | +3.3 pt / +0.33 % | 123 · 91.1 % [84.7, 94.9] · +2.35 % | 14 · 64 % · −0.50 % | 101 / 118 % |
| ENS12 | +4.7 pt / +0.43 % | +4.1 pt / +0.41 % | 101 · 91.1 % · +2.32 % | 13 · 62 % · −0.79 % | 78 / 91 % |
| ENS12U | +2.8 pt / +0.21 % | +2.1 pt / +0.20 % | 293 · 84.0 % · +1.30 % | 54 · 69 % · −0.13 % | 91 / 129 % |
| ENS6 (v1) | +2.5 pt / +0.26 % | +2.7 pt / +0.26 % | 130 · 86.2 % · +1.66 % | 11 · 55 % · −1.32 % | 76 / 63 % |

**A favor:**

- **Consistencia:** mejora en los 4 ensambles y con las 2 salidas. Todos los pliegues con vetos mejoran (4 de 4, 4 de 4, 4 de 4 y 3 de 3) y ninguno empeora. P por episodio entre 0.01 y 0.05; Holm, entre 0.04 y 0.16. Las vetadas ganan entre el 54 y el 69 %, con E negativa.
- **No es azar ni volatilidad:** frente a quitar al azar el mismo número de operaciones, D1 queda en el percentil 98–100, y el gradiente se mantiene dentro de los terciles de $s_d$ en 11 de 12 celdas.
- **El modelo no lo ve:** su $\hat p - \theta$ medio apenas baja en las vetadas (+0.004 frente a +0.010). Y se replica en las señales aisladas ($A = 0$, otras operaciones) en 7 de 8 combinaciones de ensamble y salida.
- **Los días vetados** (ENS13) encajan con el mecanismo: 2024-01-22 y 23 (salidas de GBTC), 2024-04-12 y 13, 2024-06-18, **2025-02-21 (hack de Bybit**, una operación de −7.6 %), 2025-04-25, 2025-06-02 y 2025-06-23.

**En contra:**

1. **No pasa el tamiz.** El azar condicionado a la misma regla sube casi lo mismo que el modelo: explica entre el 63 y el 129 % de la ΔWR. D1 aparta **días malos para cualquier compra**, no malas elecciones del modelo.
2. **Es una regla de episodio, con muy pocos episodios.** Los ensambles dan operaciones distintas, pero ENS13, ENS12 y ENS6 vetan los mismos 7–9 días (ENS12U, que opera casi el triple, veta 19 días alrededor de los mismos episodios de 2024 y del 2025-02-21). La evidencia real son **≈ 5–7 episodios**: las "réplicas" no la multiplican.
3. **El corte salió de mirar los datos:** el Investigador A miró 4 cortes y unas 30 variables sobre ENS13 antes de fijarlo.
4. **El *holdout* de 20 monedas no la confirma:** cubre los mismos días.

**Fuera de muestra, si se confirmara.** Encogimiento de 0.3–0.6 sobre el efecto de diseño: **+0.5 a +2 pt de WR y +0.05 a +0.2 % de E**, con un 35–45 % de probabilidad de que el efecto real sea ≈ 0. **v3 + D1 ≈ 74–80 % de WR y +0.65 a +1.4 % de E.** Solo se puede confirmar con episodios nuevos: el estrés de 2022 (LUNA, FTX), para el que ya existe el DVOL, o la prueba prospectiva. Por eso es el **brazo S3** (sección 8.2). La variante D2 (corte en el tercil inferior calculado con entrenamiento y validación, de −0.81 a −1.03) da casi lo mismo, algo más fuerte (Holm 0.02–0.16), y no añade información.

### 11.5 Lo que se rechazó (no repetir)

Cifras de ENS13 en diseño, frente a la pila de la primera iteración (85.5 %, +1.90 %) salvo que se indique otra cosa.

| Ronda | Regla | Número clave | Por qué falla |
|---|---|---|---|
| 1 | Geometría (TP, SL, barrera) elegida en *walk-forward* | +0.0 pt / −0.09 % (guarda de E); −6.7 pt / +0.05 % (máx. E) | Ninguna geometría fija domina a X5: bajar el TP sube el WR y baja la E. Deriva implícita: 0.43 $s_d$/día con compuerta, 0.18 el azar con compuerta y 0.06 sin ella |
| 1 | Re-entrada tras un TP | −3.1 a −4.9 pt / −0.50 a −0.66 % | Las re-entradas ganan solo 77 % |
| 1 | Segunda etapa con regresión logística | −2.5 a −0.2 pt | Los coeficientes cambian de signo entre pliegues |
| 1 | Cortacircuitos tras un SL | −1.4 a 0.0 pt | No sube el WR |
| 1 | Cupo de 2 o 3 posiciones como mejora | −1.4 y −0.5 pt | El cupo de 3 se mantiene como regla de **riesgo** |
| 1 | Co-firma de ENS12U | −0.2 pt | Sin efecto |
| 1 | $\theta$ elegido en validación con la compuerta | −8.0 a −8.4 pt / −0.82 % | Baja $\theta$: no hay que relajarlo con la compuerta |
| 2A | H1, rezagados: no comprar si las otras 3 anclas ya rebotaron | +0.8 pt / −0.04 % (contaminada) | Quita 14 operaciones, no 60: **posterga** la entrada en vez de saltarla. Queda como hipótesis (11.6) |
| 2A | H2, TP anclado a la brecha hasta el máximo de 24 h | +1.1 pt / −0.26 % | Solo redistribuye: en el tercil de brecha baja, 89 → 98 % de WR y +1.83 → +1.11 % de E; en el alto, 82 → 75 % y +1.77 → +2.97 %. No hay anclaje tipo Ornstein-Uhlenbeck |
| 2A | H3, TP reducido por estado (el mercado rebotó y la moneda no) | WR 93.9 %, +8.4 pt / −1.01 % | Se dispara en el ≈ 70 % de las operaciones: es una toma parcial disfrazada |
| 2A | H4, meta-etiquetado bayesiano con pesos por episodio | −1.2 pt / −0.05 % | Las variables salen con el signo contrario al esperado y se eliminan |
| 2A | H6, *funding* de las 24 h previas | −2.4 pt / −0.11 % | Quita un tercio de las operaciones sin mejorar |
| 2A | H7, divergencia de OI y *taker* | −1.4 pt / −0.07 % | No mejora en ningún pliegue |
| 2A | H8, calibración beta y $\theta$ con pesos por episodio | −11.7 a −12.3 pt / −1.26 a −1.40 % | Cambian la selectividad (160–460 operaciones): la cola calibrada con Platt es frágil |
| 2A | H9, Platt recalibrado cada mes | −12.7 pt / −1.40 % | Igual que H8 |
| 2A | H10, co-firma de un modelo con otra etiqueta (G5) | +0.6 pt / 0.00 % | Bajo el umbral |
| 2B | C1, base USDT-USD de Coinbase ($z_{30} \ge -1$) | −0.6 pt / −0.07 % | Mixta: +1.4 a +2.1 pt en otros ensambles, con ΔE ≈ 0 |
| 2B | B1, margen de Bitfinex (dos colas) | −2.5 pt / −0.13 % y −0.6 pt / −0.13 % | Negativa |

**La lección común** es la de la primera iteración: lo que espera o recorta después de la señal pierde los mejores rebotes, y lo que sube el WR sin información nueva lo paga con E. Además, **cualquier cambio en la calibración o en $\theta$** (H8, H9, E14) desplaza la selectividad y pierde entre 8 y 13 pt.

### 11.6 Hipótesis abiertas y la palanca de preferencias

Estas reglas mostraron algo en diseño, pero son inestables por pliegue o no se pueden medir con 4 monedas. Se graban hacia adelante, sin adoptarlas:

| Hipótesis | ENS13: ΔWR / ΔE | Problema | Dónde se puede confirmar |
|---|---|---|---|
| G_BE: la co-señal viene de BTC o ETH | +2.4 pt / +0.26 %; réplica en 3 de 3 | 3 de 6 pliegues; P 0.14 | 2022 o prospectiva (grabar el marcador) |
| F_rank1: la moneda que inicia el episodio | +4.3 pt / +0.22 %; réplica en 3 de 3 | Deja 49 operaciones (−63 %); 3 de 6 pliegues; ninguna de ETH | Prospectiva (grabar el marcador) |
| Episodio que empieza ≥ 3 días después del anterior | +2.8 pt / +0.38 % | n = 60; P 0.23 | 2022 o prospectiva |
| BTC > SMA de 30 días | +4.7 pt / +0.34 % | ENS12U no lo replica; 2 de 6 pliegues; habría apagado la estrategia en el *holdout* bajista | 2022 o prospectiva |
| H1, rezagados | +0.8 pt / −0.04 % | Contaminada; posterga en vez de saltar | 2022 o prospectiva (grabar L4) |
| H5, prioridad por antigüedad bajo cupo | No medible: con 4 monedas, 200 órdenes al azar dan el mismo resultado | — | *Holdout* de 20 monedas |

**Palanca de preferencias (no es una mejora).** Si a las 36 h la operación no tocó el TP, bajar el TP a +0.6 % sobre la entrada; el SL no se mueve. En diseño da 133 operaciones, **90.2 % [84.0, 94.2] y +1.86 %**: +4.7 pt y −0.05 % frente a la pila de 72 h, o **+2.4 pt y −0.16 % frente a la v3**. Se compra WR con E, y es *post hoc*. Queda como brazo opcional **S4**, solo si el usuario prioriza el WR. La geometría (0.6, 1.75, 384) es otra versión de la misma palanca: 89.5 % y +1.82 %.

### 11.7 Fuentes de datos: qué sirvió y qué no

| Fuente | Resultado | Uso |
|---|---|---|
| **DVOL de Deribit** (BTC y ETH, cada hora) | D1, el efecto más consistente | Gratis, sin clave, en vivo, no depende de Binance. **Grabar desde ya** |
| Opciones de Deribit (*skew*, flujo de puts, IV ATM) | La IV ATM repite el DVOL; el *skew* no muestra el gradiente esperado | No añade nada al DVOL |
| Coinbase: prima de BTC y USDT-USD | La "prima de Coinbase" a 15 min es casi toda la base USDT/USD. C1, mixta | Grabar USDT-USD |
| Margen de Bitfinex | B1, negativa | Grabar `…/last` |
| Fear & Greed, oferta de *stablecoins*, prima coreana | Sin gradiente consistente | — |
| Coinalyze | Solo guarda 1 500–2 000 puntos intradía | Inútil en diseño; posible sustituto de `fapi` en vivo (8.3) |
| GDELT (tipo de choque en noticias) | HTTP 429 vía VPN; no verificado | Repetir sin VPN; *prior* de 0 a +2 pt |
| Bybit | Bloqueó el país de salida de la VPN | Redundante con los *metrics* de Binance |

**Sondas para repetir sin VPN** (no tocan Binance). Todas las de la segunda iteración salieron por la VPN, así que conviene confirmar qué responde desde tu ubicación real:

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

### 11.8 Lecciones de método

**1. Un +1 pt real es invisible en diseño.** Si un filtro quita $m$ operaciones con WR $p_r$ y deja otras con WR $p_k$, la ganancia en el WR final es:

$$
\Delta WR = \frac{m}{131}\,(p_k - p_r)
$$

**Qué es cada símbolo:** $m$, las operaciones quitadas; $p_r$, su WR; $p_k$, el WR de las que quedan; 131, las operaciones de la pila.

> **Ejemplo:** con $m = 25$, el error estándar de $p_k - p_r$ es ≈ 0.086 (más con el efecto de diseño). Para detectarla con potencia 0.8 y α = 0.10 unilateral hace falta $p_k - p_r \approx 0.18$, es decir, **ΔWR ≈ +3.5 pt**. Un +1 pt real no se distingue del ruido con 131 operaciones y 24 episodios.

Por eso el tamiz es solo un filtro, y **el veredicto final debe venir de datos nuevos**.

**2. El *bootstrap* se agrupa por episodio, no por día.** Los episodios duran varios días: dentro de un mismo grupo hay hasta 20 operaciones seguidas, y la mediana desde la primera señal del grupo hasta la entrada es de 59 velas. Agrupar por día subestima la varianza.

**3. Cada fuente de datos confirma un tipo de regla:**

| Tipo de regla | Diseño (4 monedas) | *Holdout* fresco de 20 monedas (mismas fechas) | Estrés 2022 | Prospectiva |
|---|---|---|---|---|
| **De episodio** (qué pánico comprar: co-señal, D1, H1, G_BE) | Solo tamiz | **No**: son los mismos pánicos | **Sí** | **Sí** |
| **Dentro del episodio** (qué moneda o qué salida: E7, H5) | Solo tamiz | **Sí**: monedas nuevas | Sí | Sí |

**4. La geometría fija no regala WR.** En teoría (difusión con deriva) y en la rejilla de 30 geometrías, achicar el TP compra WR con E, y ensanchar el SL compra WR con E por unidad de riesgo. Solo una salida que dependa del **estado** podría subir las dos, si existiera un anclaje del precio; H2 mostró que no existe. E7 es la excepción porque no cambia el TP ni el SL: solo da tiempo a que actúe la deriva.

---

> **En una frase:** lo más avanzado de 2025–2026 no rompe el techo; lo que sí lo sube un poco es **comprar solo los pánicos de mercado** (la co-señal) y **darles 96 h para rebotar** (la v3), con un techo realista de **75–78 %** con ganancia, y quizá algo más si el veto por DVOL bajo se confirma en 2022 o en la prueba prospectiva. El 80 % por operación demostrado sigue siendo improbable; un **80 % de meses ganadores** es la meta honesta que sí está al alcance si la prueba prospectiva confirma la ventaja.
