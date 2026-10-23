# Investigador B — Métodos y técnicas para sumar ≥ 1 punto de WR sin bajar la E (ronda 2)

- **Fecha:** 2026-10-16, de 00:43 a 01:06 (hora local de la máquina).
- **Qué hice:**
  - unas 35 búsquedas web y 12 fuentes abiertas para verificar lo que cito;
  - lectura de `be_common.py`, `be_breadth2.py`, `be_events.py`, `nn_common.py`, `nn_report.py`, `nn_v2_report.py`, `HARNESS.md` y `be2_common.py`;
  - conteos **estructurales** de la pila sin mirar resultados (sección 1.2);
  - dos simulaciones teóricas propias, de difusión con deriva y de Ornstein-Uhlenbeck (sección 1.3).
- **Transparencia:** mientras trabajaba, el laboratorio publicó en esta carpeta sus experimentos `be2_*` (R2-E1 a E12 y v3). Los leí **después** de formular la primera lista. Mi idea H1 cambió de dirección por un descriptivo de `be2_stage2.md`, y la marco como **contaminada**. Siete ideas mías ya estaban cubiertas por el laboratorio y van a la sección 3, no a la lista. Esa sección incluye también dos experimentos del laboratorio que sirven de control.
- **No ejecuté** experimentos con resultados de la prueba ni consulté dominios de Binance. Los scripts de los conteos y las simulaciones están en el *scratchpad* de la sesión (`struct.py`, `bm.py`, `ou.py`, `ou2.py`) y no tocan el proyecto.

---

## Resumen

**Tres hechos condicionan cualquier receta:**

1. **Con 131 operaciones y 24 episodios, un +1 pt real de WR no se puede demostrar en diseño.**
   - Un filtro que quite 25 operaciones solo se distingue del ruido si las quitadas ganan ≈ 18 pt menos que las que quedan. Eso equivale a ≈ +3.5 pt en el WR final.
   - Las decisiones de esta ronda deben apoyarse en el **mecanismo**, la **pre-especificación** y la **réplica en 3 ensambles**, y después confirmarse con datos nuevos.
2. **La geometría sola no da WR gratis.**
   - Bajo difusión con deriva, achicar el TP sube el WR y baja la E. Ensanchar el SL sube ≈ 1 pt el WR y baja la E_R entre un 10 y un 20 %.
   - El laboratorio lo confirmó con 30 geometrías (R2-E1). La única geometría que puede subir las dos a la vez es una que dependa del **estado**: un TP anclado a la distancia al precio de equilibrio, como en los modelos de Ornstein-Uhlenbeck (H2).
3. **No todos los datos nuevos prueban lo mismo:**
   - El *holdout* fresco de 20 monedas (fase 2 del doc) cubre **las mismas fechas** que el diseño, así que contiene **los mismos episodios de pánico**. Sirve para reglas **dentro del episodio** (qué moneda y qué salida), pero **no** para reglas **de episodio** (qué pánico comprar).
   - Para las reglas de episodio solo sirven el estrés de 2022 (episodios nuevos, si existen *metrics* de 2022) y la prueba prospectiva.

**El hilo nuevo más coherente es "comprar al líder, no al rezagado".** Varias piezas independientes apuntan en la misma dirección:

- los descriptivos del laboratorio: F_rank1 +4.3 pt, F_tsf ≤ 12 h +2.6 pt y "rebote de 18 monedas" bajo 97 % frente a alto 79 %;
- la teoría de Llorente, Michaely, Saar y Wang (2002): los movimientos de liquidez revierten y los informados continúan.

Una moneda que capitula **cuando el mercado ya rebotó** se parece más a un vendedor informado que a un pánico de liquidez.

### TOP 5 para el laboratorio

| # | Hipótesis | Tema | Configs. | Prior ΔWR / ΔE (fuera de muestra) | P(≥ +1 pt y ΔE ≥ 0) | Limpieza |
|---|---|---|---|---|---|---|
| 1 | **H1. Filtro de rezagados** (las otras 3 anclas ya rebotaron) | b, d, e | 1 | +1 a +2 pt / +0.1 a +0.3 % | ≈ 35 % | **Contaminada** por el descriptivo de R2-E6. Prueba válida: 2022 y prospectiva |
| 2 | **H2. TP anclado a la brecha** hasta el máximo de 24 h (Ornstein-Uhlenbeck) | a | 2 | +0.5 a +2.5 pt / −0.10 a +0.20 % | ≈ 25 % | Limpia |
| 3 | **H3. TP reducido por estado**: el mercado ya rebotó y la moneda no; se compara con D2 (por tiempo) | a, b | 1 | +2 a +4 pt / −0.05 a +0.10 % | ≈ 25 % | Casi limpia (la dirección la sugiere H1) |
| 4 | **H4. Meta-etiquetado bayesiano parsimonioso** con pesos por episodio | c, f | 1 | 0 a +1.5 pt / 0 a +0.15 % | ≈ 15 % | Limpia (difiere de LR5/LR6) |
| 5 | **H5. Prioridad por antigüedad bajo cupo** (líder primero) | d | 1 | +0.5 a +2 pt frente al orden por p̂ (solo con cupo) | ≈ 20 % | Limpia |

Le siguen H6 a H10 (sección 2), con prior menor. En total son **12 configuraciones nuevas** que hay que registrar con `log_trials`, más 2 que no deciden (un control al revés y una sensibilidad).

---

## 1. Tres hechos que condicionan las recetas

### 1.1 Potencia: qué se puede detectar en diseño

- La pila tiene **131 operaciones** (WR 85.5 %), **24 episodios** con la definición del doc y **26 grupos** con la mía (velas con señal de cualquier moneda, unidas si distan ≤ 48 velas).
- Supón un filtro que quita $m$ operaciones con WR $p_r$ y deja $n_k$ con WR $p_k$. La ganancia en el WR final es:

$$
\Delta WR = p_k - 0.855 = \frac{m}{131}\,(p_k - p_r)
$$

**Qué es cada símbolo:** $m$ es el número de operaciones quitadas; $p_r$, su WR; $n_k$ y $p_k$, el número y el WR de las que quedan; 0.855 es el WR actual de la pila.

> **Ejemplo:** con $m = 25$, el error estándar de $p_k - p_r$ es ≈ 0.086 (más con DEFF). Para detectar la diferencia con potencia de 0.8 y α = 0.10 unilateral hace falta $p_k - p_r \approx 0.18$, es decir, **ΔWR ≈ +3.5 pt**. Un +1 pt real es invisible en diseño.

**Consecuencias:**

- **(i)** El criterio del laboratorio (ΔWR ≥ +1, ΔE ≥ 0, ≥ 4/6 pliegues, P(ΔWR ≤ 0) ≤ 0.20 y réplica en 2/3 ensambles) es un **tamiz**, no una prueba. Hay que mantenerlo, pero el veredicto final debe venir de datos nuevos.
- **(ii)** El *bootstrap* debe agruparse por **episodio**, no por día. Los episodios duran varios días: la operación $k$-ésima dentro de un grupo llega a $k = 20$, y la mediana desde el inicio del grupo es de 59 velas. Agrupar por día subestima la varianza.

### 1.2 Estructura de la muestra (conteos sin resultados)

| Medida | Valor |
|---|---|
| Velas de prueba con $\hat p \ge \theta$ | 3 581 |
| … de ellas con $A \ge 1$ | 2 703 |
| Operaciones de la pila (una posición por moneda) | 131 |
| Velas con compuerta en las que la misma moneda ya dio señal en las 48 velas previas | 2 645 de 2 703 |
| Señales simultáneas (de las 4 monedas) en la vela de entrada | 1 → 27 operaciones; 2 → 64; 3 → 20; 4 → 20 |
| Orden de la operación dentro de su grupo ($k$ = 1, 2, 3, …) | 26, 22, 15, 14, 9, 7, … (cola hasta $k$ = 20) |
| Velas desde la primera señal del grupo hasta la entrada (cuantiles 10/25/50/75/90 %) | 2 / 13 / 59 / 108 / 162 |
| Brecha hasta el máximo de 24 h en la entrada, en $s_d$ (cuantiles 10/25/50/75/90 %) | 0.26 / 0.65 / 1.33 / 2.06 / 3.07; el 29 % está por debajo de 0.7 |
| Fracción de las **otras 3 anclas** ya rebotadas en la entrada (≥ 1 σ de 4 h sobre su mínimo de 16 velas) | 0 → 46; 1/3 → 14; 2/3 → 11; 1 → 60 |

**Lectura.** Casi toda entrada ocurre en medio de una racha de señales: la moneda queda libre al cerrar su operación anterior y vuelve a entrar mientras sigue "en pánico". La "primera señal de la cascada" casi nunca se opera: la compuerta la bloquea, porque $A = 0$ en ese momento. Así, la pregunta útil del tema (b) no es "¿la primera es peor?", sino **"¿las tardías son peores?"**.

### 1.3 Geometría: lo que dice la teoría (simulación propia, no datos)

**Difusión con deriva constante $\nu$ calibrada al WR de la pila** ($\nu \approx 0.45\,s_d$ por día ⇒ 86 % con X5). Costo de 0.24 % ($0.056\,s_d$), $H$ = 3 días, $s_d = 4.3\,\%$ y 20 000 trayectorias:

| Geometría | WR | E % | E_R |
|---|---|---|---|
| X5 (0.7, 1.75) | 86.2 | +1.52 | +0.202 |
| TP 0.6 | 87.3 | +1.24 | +0.164 |
| TP 0.5 | 89.2 | +1.00 | +0.133 |
| SL 2.0 | 87.0 | +1.60 | +0.186 |
| SL 2.25 | 87.5 | +1.66 | +0.171 |

**Deriva que decae** (rebote impulsivo, $\nu_0 = 3$, vida media ≈ 4 h): X5 da 89.3 / +1.79; TP 0.6 da 91.5 / +1.59; SL 2.25 da 90.0 / +1.82 con una E_R 21 % menor.

**Conclusión:**

- **Achicar el TP compra WR con E.** La rejilla R2-E1 lo confirma: TP 0.6 da 88.9 % y +1.78 %, frente a 85.5 % y +1.90 %.
- **Ensanchar el SL compra WR con E_R.** En R2-E1, el SL de 2.25 dio 85.6 % y +1.76 %.
- **Ninguna geometría fija cumple "+1 pt sin bajar la E".**

**Mezcla con anclaje (Ornstein-Uhlenbeck hacia un nivel de equilibrio).** Una fracción $f$ de las operaciones revierte hacia la mitad de la brecha hasta el máximo de 24 h; el resto es difusión sin deriva. La brecha se sorteó con su distribución empírica (sección 1.2):

| $f$, $\kappa$ | X5: WR / E | TP $=\min(0.7,\max(0.35, g))$ | **TP $=\text{clip}(0.5\,g,\ 0.35,\ 1.2)$** |
|---|---|---|---|
| 0.5, 2.8 | 82.2 / +1.14 | 84.6 / +1.05 | **84.0 / +1.26** |
| 0.7, 0.7 | 83.1 / +1.31 | 85.5 / +1.22 | **85.5 / +1.51** |
| 0.3, 2.8 | 76.2 / +0.55 | 78.6 / +0.49 | **77.6 / +0.61** |

**Qué es cada símbolo:** $f$ es la fracción de operaciones con anclaje; $\kappa$, la velocidad de reversión (0.7 equivale a una vida media de ≈ 1 día y 2.8, a ≈ 6 h); $g$, la brecha hasta el máximo de 24 h en $s_d$.

> **Lectura:** solo si **existe** anclaje, escalar el TP con la brecha sube el WR (+1.4 a +2.4 pt) y la E a la vez. Si no existe, el efecto es ≈ 0. H2 es una prueba directa de esa estructura.

### 1.4 Qué datos sirven para qué

| Tipo de regla | Diseño (4 monedas) | *Holdout* fresco de 20 monedas, mismas fechas | Estrés 2022 (LUNA, FTX) | Prospectiva |
|---|---|---|---|---|
| **De episodio** (qué pánico comprar: H1, H6) | Tamiz | **No** independiente: mismos pánicos | **Sí** | **Sí** |
| **Dentro del episodio** (qué moneda, qué salida: H2, H3, H5, H7) | Tamiz | **Sí**: monedas nuevas | Sí | Sí |

Para todo lo que sobreviva al tamiz, recomiendo **pre-registrarlo con *hash*** como brazo secundario del doc (sección 8.2) **antes** de abrir cualquier dato posterior al 2026-09-30, y también como prueba del estrés de 2022.

---

## 2. Hipótesis, ordenadas por valor esperado

Convenciones de todas las recetas:

- Se usa `be2_common` (`E.load(ens)`, `D["stack"]`, `D["A"]`, `D["jrow"]`, `E.trade_table`, `E.summ`). Las variables salen de `D["cache"][sym]["X"]` con `names`.
- Cada regla se compara con:
  - **(a)** la pila: 131 operaciones, 85.5 % y +1.90 %;
  - **(b)** el azar condicionado **a la misma regla nueva** y con la misma salida;
  - **(c)** el complemento (las operaciones que la regla quita).
- Las réplicas usan ENS13, ENS12 y ENS12U.

### H1. Filtro de rezagados: no comprar cuando las otras anclas ya rebotaron (temas b, d, e) — **TOP 1, contaminada**

**Mecanismo.** En un pánico de **liquidez** (ventas forzadas en todo el mercado), las monedas tocan fondo casi a la vez. Una moneda que sigue capitulando **después** de que el resto rebotó tiene un vendedor propio: noticia, desbloqueo, flujo informado.

**Fuentes:**

- Llorente, Michaely, Saar y Wang (2002), *RFS*: los movimientos con volumen alto revierten cuando dominan las operaciones de cobertura o liquidez, y continúan cuando dominan las especulativas o informadas ([NBER w8312](https://img.nber.org/papers/w8312); [PDF](https://www.johnhcochrane.com/s/llorente_michaely_saar_wang_volume_rfs.pdf)).
- Chan (2003) y Savor (2012), ya en el doc: los choques con noticia continúan.
- Petersen, Wang, Havlin y Stanley (2010): las acciones más activas reaccionan antes y con más fuerza a los choques de mercado ([arXiv 1006.1882](https://arxiv.org/abs/1006.1882)).
- La literatura de saltos conjuntos ("co-saltos") separa los sistemáticos de los idiosincráticos ([PMC7857619](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7857619/)).

**Evidencia en diseño, ya vista (por eso está contaminada):**

- `be2_stage2.md`, operaciones de la pila según la fracción de 18 monedas rebotadas: 0–0.1 → 37 op · 97 % · +2.64 %; 0.5–1 → 68 op · 79 % · +1.49 %.
- `be2_gatevar`: F_rank1 (primera moneda del episodio) 89.8 %, +2.12 %; F_tsf ≤ 12 h +2.6 pt, en 4/6 pliegues; F_nprev0 −8.9 pt.

**Receta (pre-especificada antes de ver el resultado con las anclas; nadie lo ha medido con 4 anclas):**

```python
D = E.load("ENS13")                                    # D["stack"], D["jrow"], D["tg"], D["ci"]
reb = []
for s in H.SYMBOLS:                                     # solo las 4 anclas (lo mismo se calcula en vivo con 18 monedas)
    z = D["cache"][s]; bars = R.coin_bars(s, len(z["c"]))
    up = (bars.c - H.rolling_min(bars.l, 16)) / (bars.c * z["s15"] * 4) >= 1   # ≥ 1 σ de 4 h sobre su mínimo de 4 h
    j = np.searchsorted(z["t"].astype(np.int64), D["tg"]); reb.append(up[np.minimum(j, len(up) - 1)])
reb = np.array(reb, float)
L = (reb.sum(0)[D["jrow"]] - reb[D["ci"], D["jrow"]]) / 3.0  # fracción de las OTRAS 3 anclas ya rebotadas
mask = D["stack"] & (L < 1.0)                           # regla única: saltar si las 3 otras ya rebotaron
```

- Es causal: usa el cierre de la vela de señal y mínimos hasta esa vela.
- Quita ≈ 60 de las 131 operaciones (sección 1.2). Es un recorte grande: queda $n \approx 71$.

**Cómo leer el resultado:**

- **(i)** ΔWR y ΔE frente a la pila, junto con el WR y la E del complemento.
- **(ii)** Azar condicionado a $A \ge 1$ y $L < 1$. Si el azar condicionado sube tanto como el modelo, la regla es "día bueno", no selección.
- **(iii)** Por pliegue y por episodio.
- **(iv)** **Versión al revés como control:** saltar si $L = 0$. Debe empeorar.

| Concepto | Valor |
|---|---|
| Configuraciones | 1, más 1 control al revés que no decide |
| Prior en diseño (inflado) | +3 a +6 pt |
| Prior real | +1 a +2 pt de WR y +0.1 a +0.3 % de E por operación. Baja el número de operaciones casi a la mitad, así que la E total cae |
| Riesgo de sobreajuste | **Alto**: la dirección se eligió después de ver el descriptivo de 18 monedas |
| Prueba válida | 2022 y prospectiva (es una regla de episodio). En la prospectiva, como brazo **S3 = P1 + $L_4 < 1$**, pre-registrado con *hash* antes del primer vistazo |

**Argumento más fuerte en contra.** Nagel (2012, [NBER w17653](https://nber.org/papers/w17653)) muestra que el rendimiento de proveer liquidez es **mayor** cuanto más dura el estrés. Una segunda pierna del pánico (doble suelo) puede ser justo la mejor compra, y este filtro la salta. Además, con 24 episodios, el patrón puede deberse a 2 o 3 episodios con segunda pierna fallida.

### H2. TP anclado a la brecha: el objetivo depende de cuánto cayó el precio (tema a) — **TOP 2, limpia**

**Mecanismo.** En un proceso de Ornstein-Uhlenbeck, el TP óptimo depende de la distancia al nivel de equilibrio, no de un múltiplo fijo de la volatilidad:

- Bertram (2010, *Physica A* 389: 2234–2243; implementación descrita en [Hudson & Thames](https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/time_series_approach/ou_optimal_threshold_bertram.html)).
- Lipton y López de Prado (2020), solución cerrada de los umbrales de toma de ganancia y *stop-loss* para Ornstein-Uhlenbeck ([arXiv 2003.10502](https://arxiv.org/abs/2003.10502)).
- Leung y Li (2015): con *stop-loss*, el TP óptimo es menor cuanto más alto está el SL ([arXiv 1411.5062](https://arxiv.org/abs/1411.5062)).
- Carr y López de Prado (2014), "reglas óptimas sin *backtest*": calibrar el proceso y derivar la regla, en vez de buscar en una rejilla ([arXiv 1408.1159](https://arxiv.org/abs/1408.1159)).

Hoy el TP es $0.7\,s_d$ para todas las operaciones. En el 29 % de ellas eso exige un **máximo nuevo de 24 h**, más allá del anclaje.

**Receta (pre-especificada por la teoría; no salió de una rejilla):**

- Brecha: $g_i = -\text{dd\_96}_i$, que ya está en $s_d$ porque $\text{dd\_96} = \ln(c/\max h_{96})/(\sigma_{15}\sqrt{96})$.
- **Regla principal:** $a_i = \text{clip}(0.5\,g_i,\ 0.35,\ 1.2)$, con $TP_i = c_i\,(1 + a_i\,s_{d,i})$. El SL de X5 ($1.75\,s_d$) y $H$ (288, o 384 si la pila adopta R2-E7) no cambian.
- **Sensibilidad** (no decide): un factor de 0.6 en lugar de 0.5.
- **Implementación:**
  1. Copiar `nn_common.label_all` cambiando `tp` por `c*(1 + a_arr*sd)`. Con eso se obtienen las etiquetas por vela con la nueva salida, para el azar condicionado con la misma salida.
  2. Simular las operaciones con `H.simulate(bars, ent, tp_arr, sl_arr, ...)`, como en `R.simulate_rows`.
- **θ** se mantiene en el de cada pliegue. En una variante, se re-elige solo en validación con la nueva etiqueta.
- **Comparar:**
  - con X5 sobre las **mismas** entradas;
  - con el azar condicionado con la **misma** salida anclada. Si el azar también mejora, es anclaje del mercado, que igual vale;
  - con la geometría fija de mismo $a$ medio (≈ 0.67), para separar "anclaje" de "TP más chico".
- **Diagnóstico del mecanismo:** el WR por tercil de $g$ con X5 y con la regla. Con anclaje, la regla gana sobre todo en el tercil bajo de $g$.

| Concepto | Valor |
|---|---|
| Configuraciones | 2 (principal y re-elección de θ), más 1 de sensibilidad |
| Prior | +0.5 a +2.5 pt; ΔE de −0.10 a +0.20 % |
| Riesgo de sobreajuste | Bajo a medio: 1 regla fijada por la teoría y una variable que ya existe |

**Argumento más fuerte en contra.** Si el rebote es difusión con deriva sin un nivel de equilibrio, la regla es solo una redistribución del TP: más WR en las brechas chicas y menos en las grandes, con efecto neto ≈ 0 (sección 1.3). Además, el "equilibrio" correcto puede no ser el máximo de 24 h: puede ser el VWAP o la media.

### H3. TP reducido por estado: el mercado ya rebotó y la moneda no (temas a, b) — **TOP 3**

**Mecanismo.** Tras el choque, la deriva favorable se agota según una ley de decaimiento (Omori):

- Lillo y Mantegna (2003), *PRE* 68, 016119 ([DOI](https://link.aps.org/doi/10.1103/PhysRevE.68.016119));
- Weber et al., la ley de Omori también vale tras choques intermedios, con exponente ≈ 1 ([arXiv physics/0611093](https://arxiv.org/abs/physics/0611093));
- Petersen et al. (2010).

Cuando **el mercado ya rebotó** y la posición propia sigue lejos del TP, la deriva que queda es baja, y la moneda es un rezagado (H1). Bajar el objetivo de **esas** operaciones convierte salidas por tiempo o por SL en ganancias pequeñas, sin recortar a las que van bien.

El laboratorio ya probó la versión **por tiempo** (R2-E12, D2: TP2 = +0.6 % desde las 36 h): +4.7 pt de WR y −0.05 % de E. Esta hipótesis cambia solo **el disparador**.

**Receta:**

- Partir de `be2_tpdecay.sim`. Reemplazar `decay_at` por un disparador por vela $j$ ≥ entrada + 8 (2 h) que se cumple si:
  - **(i)** las otras 3 anclas están rebotadas (la misma `reb` de H1, $L_j = 1$); y
  - **(ii)** $c_j < \text{entrada}\cdot(1 + 0.35\,s_d)$, es decir, la posición no llegó a la mitad del TP.
- Desde ese momento, $TP2 = \text{entrada}\times 1.006$, el **mismo** TP2 de D2. El SL y $H$ no cambian.
- Comparar con D2 (mismo TP2, disparador por tiempo) y con X5. Si el disparador por estado logra el WR de D2 con ΔE ≥ 0, se queda con la ventaja.
- Registrar también qué fracción de las operaciones se dispara: menos que D2 sería lo esperado.

| Concepto | Valor |
|---|---|
| Configuraciones | 1 |
| Prior | +2 a +4 pt; ΔE de −0.05 a +0.10 % |
| Riesgo de sobreajuste | Medio: hereda la dirección de H1 |

**Argumento más fuerte en contra.** Es pariente de la toma parcial y de la salida por "tesis rota", que se rechazaron: todo lo que recorta a una operación que todavía va a llegar al TP pierde E. Y el estado "mercado rebotado" se cumple en casi todos los pánicos tarde o temprano. Si se dispara en > 60 % de las operaciones, es una toma parcial disfrazada.

### H4. Meta-etiquetado bayesiano parsimonioso con pesos por episodio (temas c, f) — **TOP 4**

**Mecanismo.** Una segunda etapa (meta-etiquetado) filtra los falsos positivos del modelo primario:

- López de Prado (2018);
- "Meta-Labeling: Calibration and Position Sizing", *JFDS*: la calibración ayuda a las reglas fijas ([listado de Hudson & Thames](https://hudsonthames.org/tag/meta-labeling/)).

Con pocas muestras, hacen falta *priors* débilmente informativos:

- Gelman, Jakulin, Pittau y Su (2008), *AoAS*: Cauchy(0, 2.5) con variables escaladas a desviación estándar de 0.5 ([Project Euclid](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-2/issue-4/A-weakly-informative-default-prior-distribution/10.1214/08-AOAS191.short));
- King y Zeng (2001): la regresión logística subestima la probabilidad de los eventos raros ([Harvard](https://gking.harvard.edu/publication/logistic-regression-in-rare-events-data/)).

**Qué cambia frente a LR5/LR6 del laboratorio** (que dieron −0.2 pt y +0.01 %, con coeficientes que cambian de signo entre pliegues):

- **(1)** Los pesos suman 1 por (episodio, moneda), así que el tamaño efectivo es el número de episodios, no el de velas. Hoy unas 2 000 velas solapadas fingen ser datos independientes.
- **(2)** Un *prior* N(0, 0.5²) sobre los coeficientes estandarizados: el estimador MAP equivale a una penalización L2 con λ = 2 sobre la log-verosimilitud ponderada.
- **(3)** **Solo 3 variables, con el signo esperado declarado:**
  - brecha $g$ (+, por H2);
  - dispersión de los 13 miembros calibrados (+; `be_disagree.py` encontró que más desacuerdo es mejor);
  - *funding* z antes del choque, $\text{funding\_z\_2016}$ en $t - 96$ (+, por H6).
- **(4)** Solo se descarta el **20 % inferior**, para no recortar media muestra.

**Receta:** el entrenamiento del pliegue $k$ usa las velas `D["stack"]` de los pliegues < $k$ con purga (como `be2_stage2.stage2_mask`). El pliegue 0 pasa sin filtro. La regla es saltar si $\hat p_{\text{meta}} < q_{0.20}$ de entrenamiento. Se compara con la pila, con LR5 q25 y con el azar condicionado.

| Concepto | Valor |
|---|---|
| Configuraciones | 1 |
| Prior | 0 a +1.5 pt; ΔE de 0 a +0.15 % |
| Riesgo de sobreajuste | Medio a bajo, por la contracción del *prior* |

**Argumento más fuerte en contra.** El modelo primario ya ve casi la misma información (74 variables, incluido el *funding*). El meta-etiquetado rinde sobre todo cuando el primario es una regla simple, y aquí el primario es un ensamble de ML con los mismos datos. La prueba LR5/LR6 ya salió nula.

### H5. Prioridad por antigüedad bajo cupo: el líder primero (tema d) — **TOP 5**

**Mecanismo.**

- El doc recomienda un tope de 3 posiciones y operar 18 monedas, así que el cupo **va a mandar**.
- El laboratorio probó MAX2 y MAX3 ordenando por $\hat p$ (R2-E8): −1.4 pt y −0.5 pt. Ordenar por la confianza del modelo no ayuda, igual que el desacuerdo alto resultó mejor en `be_disagree`.
- La literatura de *learning to rank* muestra que el criterio de orden importa más que el modelo de puntaje (Poh, Lim, Zohren y Roberts, [arXiv 2012.07149](https://arxiv.org/abs/2012.07149)).
- Por H1, el orden natural es **temporal**: primero la moneda que capituló primero en el episodio.

**Receta:**

- En el simulador conjunto de `be2_joint` (MAX2 como principal, MAX3 informativo), cuando hay más candidatas que cupos en la misma vela, ordenar por la vela de la **primera señal propia dentro del grupo** (antes = primero). Los empates se rompen por $\hat p$.
- Comparar con: orden por $\hat p$ (lo de R2-E8), orden al azar (200 permutaciones, para obtener la distribución) y sin cupo.

| Concepto | Valor |
|---|---|
| Configuraciones | 1 |
| Prior | +0.5 a +2 pt frente al orden por $\hat p$. Con 4 monedas el cupo casi no muerde (MAX3 cambia 4 operaciones), así que el efecto en diseño será pequeño; importa con 18 monedas |
| Riesgo de sobreajuste | Bajo |

**Argumento más fuerte en contra.** Bianchi, Babiak y Dickerson (2022, *JBF* 142: 106547, [IDEAS](https://ideas.repec.org/a/eee/jbfina/v142y2022ics0378426622001418.html)) y Zaremba et al. (2021, *IRFA* 78: 101908, [IDEAS](https://ideas.repec.org/a/eee/finana/v78y2021ics1057521921002349.html)) encuentran que la reversión paga más en los pares **menos** líquidos. Si eso domina, conviene priorizar la moneda menos líquida, no la primera. En diseño, el desglose por moneda (BTC el mejor) contradice esa idea, pero está contaminado.

### H6. Apalancamiento previo al choque: pánico de liquidación o pánico informativo (tema e)

**Mecanismo.**

- Schmeling, Schrimpf y Todorov, "Crypto carry" (BIS WP 1087, revisado en 2025): "un *carry* cripto alto predice caídas futuras" ([BIS](https://www.bis.org/publ/work1087.htm)). Si había largos apalancados antes del choque, la caída es mecánica (liquidaciones) y debería revertir.
- Khandani y Lo (2007/2011): las liquidaciones forzadas causan presión de precio **temporal** ([NBER w14465](https://nber.org/system/files/working_papers/w14465/w14465.pdf)).
- Si **no** había apalancamiento largo, la caída es informativa y continúa, como en FTX, con *funding* negativo durante la caída.

**Receta:**

- $f_{\text{pre}} = \text{funding\_z\_2016}$ en la vela $ii - 96$ (24 h antes de la señal), leído de `cache[sym]["X"]`.
- Saltar si $f_{\text{pre}}$ está en el **tercil inferior**, con los cortes fijados en las velas `stack` de **validación** de cada pliegue.
- Comparar con la pila, el complemento y el azar condicionado.

| Concepto | Valor |
|---|---|
| Configuraciones | 1 |
| Prior | 0 a +1 pt; ΔE de 0 a +0.1 % |
| Riesgo de sobreajuste | Bajo |

**Argumento más fuerte en contra.** El *funding* cambia cada 8 h, así que el de 24 h antes se parece mucho al actual, que ya está en el modelo. Además, por tercil del *funding* actual no hubo gradiente de WR (79.6 / 74.6 / 80.5 % en `be_liqproxy`). La señal puede tener el signo contrario: un *funding* negativo trae compresiones de cortos.

### H7. Divergencia idiosincrática en futuros dentro del pánico (temas d, e)

**Mecanismo.**

- Llorente et al. (2002): un flujo propio de la moneda es informativo.
- Jacod, Lin y Todorov (2024) separan los saltos sistemáticos de los idiosincráticos con paneles de alta frecuencia (citado en la búsqueda; no lo verifiqué en el texto completo).
- Si el OI y el lado agresor de **una** moneda divergen del de las otras anclas en el mismo pánico, hay un vendedor específico.
- El "rezago relativo" en **precio** ya se probó sin gradiente. En **futuros**, no.

**Receta:**

- En cada vela con compuerta, calcular el z transversal entre las 4 anclas de `oi_chg_16` y `fut_taker_4`.
- $D_i = |z_{\text{oi}}| + |z_{\text{taker}}|$. Saltar si $D_i$ supera el percentil 80 de validación.

| Concepto | Valor |
|---|---|
| Configuraciones | 1 |
| Prior | 0 a +1.5 pt |
| Riesgo de sobreajuste | Bajo a medio |

**Argumento más fuerte en contra.** Con 4 monedas, el z transversal es muy ruidoso, y DOGE diverge siempre por naturaleza. Los *proxies* de flujo forzado a nivel de moneda ya fallaron ("*OI flush*" bajó el WR).

### H8. Calibración beta en la cola y θ con pesos por episodio (tema f)

**Mecanismo.**

- Kull, Silva Filho y Flach (2017, AISTATS) proponen la calibración beta: 3 parámetros, contiene la identidad, y es mejor que Platt con puntajes asimétricos y menos sobreajustada que la isotónica ([PMLR v54](https://proceedings.mlr.press/v54/kull17a.html)).
- La isotónica sobreajustó la cola (`be_disagree`).

**Receta:**

- **(1)** En `load_ens`, reemplazar `platt_fit`/`platt_apply` por una regresión logística sobre $[\ln \sigma(s),\ -\ln(1-\sigma(s))]$, donde $\sigma(s)$ es la sigmoide del puntaje crudo estandarizado (los puntajes crudos no están en (0, 1)).
- **(2)** Elegir θ con la misma regla v2, pero con cada vela de validación pesada por $1/n$ de su episodio.
- Comparar la pila con cada cambio por separado.

| Concepto | Valor |
|---|---|
| Configuraciones | 2 |
| Prior | 0 a +1 pt |
| Riesgo de sobreajuste | Bajo |

**Argumento más fuerte en contra.** Con un promedio de 13 modelos, la forma de la calibración casi no cambia el orden de las velas, y el umbral se re-elige igual. El efecto esperado está dentro del ruido.

### H9. Recalibración mensual de Platt con las etiquetas más recientes (aprendizaje en línea, tema g)

**Mecanismo.**

- La v2 cayó a 60–63 % en 2026-T1 y T2: hay deriva entre trimestres.
- La competición de Jane Street de 2024 incluyó un *responder* retrasado precisamente para el aprendizaje en línea, según la [página de Jane Street](https://janestreet.com/machine-learning) citada por el buscador. **No pude confirmarlo al abrirla**, y no encontré el informe de la solución ganadora.

**Receta:**

- Para los meses 2 y 3 de cada trimestre de prueba, re-ajustar Platt de cada miembro con la validación del pliegue más las velas de prueba del **mismo** modelo cuyas etiquetas ya cerraron (salida ≤ inicio del mes − 289 velas).
- θ queda fijo.

| Concepto | Valor |
|---|---|
| Configuraciones | 1 |
| Prior | 0 a +1 pt |
| Riesgo de sobreajuste | Bajo |

**Argumento más fuerte en contra.** ACI, que ajusta θ con los aciertos recientes, falló justamente por perseguir ruido con ≈ 30 operaciones por trimestre. Platt tiene más datos (todas las velas, no solo las operaciones), pero la deriva relevante está en la cola.

### H10. Co-firma de un modelo entrenado con **otra etiqueta** (tema c)

**Mecanismo.** La co-firma con ENS12U (misma etiqueta G3, R2-E10) fue neutra (−0.2 pt y +0.15 %): los miembros con la misma etiqueta se equivocan juntos. Un modelo entrenado con otra geometría ya existe en `tmp/nn_preds/` (`lgbv4_G5_f1_s0`, `mlpv4_G5_f1_s0`, con etiqueta G5 = 0.6, 1.5, 192). Aporta otra forma de error, al estilo del meta-etiquetado con ensambles diversos (Thumm, Barucca y Joubert, "Ensemble Meta-Labeling", *JFDS*; no verifiqué el texto completo).

**Receta:**

- Ensamble G5 de 2 miembros, con Platt en validación contra la etiqueta G5 y su propio θ elegido con la regla v2.
- Exigir pila **y** $\hat p_{G5} \ge \theta_{G5}$ en la vela de entrada.

| Concepto | Valor |
|---|---|
| Configuraciones | 1 |
| Prior | 0 a +1 pt |
| Riesgo de sobreajuste | Bajo |

**Argumento más fuerte en contra.** Dos miembros dan mucho ruido, y G5 está muy correlacionada con G3. Lo más probable es que repita lo de R2-E10: menos operaciones con el mismo WR.

---

## 3. Ideas mías que el laboratorio ya cubrió (no repetir)

| Mi idea original | Experimento del laboratorio | Resultado (ENS13) | Lectura |
|---|---|---|---|
| TP menor cuando hay co-señal (geometría por fuerza de la señal) | R2-E1, 30 geometrías y 2 selectores en *walk-forward* | TP 0.6: 88.9 % y +1.78 %. WF wr_guard: +0.0 pt y −0.09 % | Coincide con la teoría de 1.3: el WR se compra con E. No insistir con multiplicadores fijos |
| SL ancho solo con compuerta | R2-E1, g0.70_2.25_288 | 85.6 % y +1.76 % | Rechazada |
| Primera señal frente a las siguientes; tiempo desde el choque (Hawkes u Omori) | R2-E2: F_rank, F_tsf y F_nprev | F_rank1 +4.3 pt (3/6); F_tsf ≤ 12 h +2.6 pt (4/6); F_nprev0 −8.9 pt | Es la base de H1. Una intensidad de Hawkes de las señales sería otra medida de lo mismo: no la propongo aparte |
| Co-señal con BTC como ancla | R2-E3, G_BE | +2.4 pt y +0.26 % (3/6 pliegues, réplica 3/3) | Prometedora, ya está en manos del laboratorio |
| Cortacircuito tras un SL (misma moneda o mercado) | R2-E8, CB_coin96 y CB_mkt48 | −1.4 pt y −0.17 %; 0 y 0 | Rechazada |
| Cupo ordenado por $\hat p$ | R2-E8, MAX2 y MAX3 | −1.4 pt; −0.5 pt | Motiva H5 (orden por antigüedad) |
| Meta-etiquetado logístico simple | R2-E5 y E6, LR5 y LR6 | −0.2 pt y +0.01 % | H4 dice qué cambiar |
| Barrera de tiempo más larga | R2-E7, H = 384 | +2.3 pt y +0.12 % (3/6) | Coincide con una deriva residual positiva: el tiempo extra convierte salidas por tiempo en TP |
| TP que baja con el tiempo | R2-E12, D1 y D2 | +3.2 pt y −0.05 %; +4.7 pt y −0.05 % | Sirve de control de H3 |

**Pista ya contaminada que conviene registrar.** En `be_liqproxy.md`, por vela, el tercil bajo de `oi_to_vol` (open interest bajo frente al volumen) dio 90.1 % y +3.41 %, frente a 72–75 % en los otros terciles. Su azar también sube: 70.5 % y +0.84 %. Ya se vio en diseño, así que no debe "descubrirse" ahí otra vez. Solo vale como variable pre-registrada para la prospectiva o 2022.

---

## 4. Protocolo común propuesto

1. **Registrar antes de correr:**
   - con `E.log_once(tag, n, desc)`: H1 1 configuración más 1 control; H2 2 más 1 de sensibilidad; H3 a H7 1 cada una; H8 2; H9 y H10 1 cada una;
   - el texto de la regla, en el *docstring* (como hizo `be2_tpdecay.py`).
2. **Comparadores fijos:**
   - la pila (131 · 85.5 · +1.90), o la pila con $H$ = 384 si el laboratorio la adopta;
   - el azar condicionado a la **regla nueva** y con la **misma salida**;
   - el complemento;
   - los 3 ensambles.
3. **Bootstrap por episodio,** no por día: grupos de velas con señal unidas si distan ≤ 48 velas, o la definición de 2 días de `be_events`. Reportar también un IC del WR con efectos aleatorios por episodio (beta-binomial), que es el IC honesto con 24 episodios.
4. **Tamiz para pasar:**
   - el del laboratorio: ΔWR ≥ +1, ΔE ≥ 0, ≥ 4/6 pliegues, P(ΔWR ≤ 0) ≤ 0.20 y réplica en 2/3;
   - **y además**: el azar condicionado no explica más de la mitad de la mejora.
5. **Combinación:** solo una, pre-especificada. La mejor regla de selección (H1, H4, H6 o H7) más la mejor de salida (H2 o H3), sin buscar combinaciones.
6. **Confirmación:**
   - todo lo que pase se congela con *hash* y entra como brazo secundario de la prospectiva antes del primer vistazo a datos posteriores al 2026-09-30;
   - las reglas de episodio (H1, H6) se prueban además en el estrés de 2022, si existen *metrics*;
   - las reglas dentro del episodio (H2, H3, H5, H7), en el *holdout* de 20 monedas.

---

## 5. Fuentes

**Verificadas al abrirlas o en su resumen:**

- Carr y López de Prado (2014), *Determining Optimal Trading Rules without Backtesting*: <https://arxiv.org/abs/1408.1159>
- Lipton y López de Prado (2020), *A closed-form solution for optimal mean-reverting trading strategies*, *IJTAF* 23(08): <https://arxiv.org/abs/2003.10502>
- Leung y Li (2015), *Optimal Mean Reversion Trading with Transaction Costs and Stop-Loss Exit*, *IJTAF*: <https://arxiv.org/abs/1411.5062>
- Bertram (2010), *Physica A* 389(11): 2234–2243 (vía la documentación de Hudson & Thames): <https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/time_series_approach/ou_optimal_threshold_bertram.html>
- Petersen, Wang, Havlin y Stanley (2010), ley de Omori en los choques de mercado: <https://arxiv.org/abs/1006.1882>
- Lillo y Mantegna (2003): <https://link.aps.org/doi/10.1103/PhysRevE.68.016119>
- Weber et al. (2007), procesos de Omori a todas las escalas: <https://arxiv.org/abs/physics/0611093>
- Bacry, Mastromatteo y Muzy (2015), *Hawkes processes in finance*: <https://arxiv.org/abs/1502.04592>
- Llorente, Michaely, Saar y Wang (2002), *RFS*: <https://img.nber.org/papers/w8312>
- Nagel (2012), *Evaporating Liquidity*, *RFS*: <https://nber.org/papers/w17653>
- Khandani y Lo, *What Happened to the Quants in August 2007?*: <https://nber.org/system/files/working_papers/w14465/w14465.pdf>
- Schmeling, Schrimpf y Todorov, *Crypto carry*, BIS WP 1087: <https://www.bis.org/publ/work1087.htm>
- Bianchi, Babiak y Dickerson (2022), *JBF* 142: <https://ideas.repec.org/a/eee/jbfina/v142y2022ics0378426622001418.html>
- Zaremba et al. (2021), *IRFA* 78: <https://ideas.repec.org/a/eee/finana/v78y2021ics1057521921002349.html>
- Poh, Lim, Zohren y Roberts, *learning to rank* para estrategias transversales: <https://arxiv.org/abs/2012.07149>
- Kull, Silva Filho y Flach (2017), calibración beta: <https://proceedings.mlr.press/v54/kull17a.html>
- Gelman, Jakulin, Pittau y Su (2008), *prior* débilmente informativo: <https://projecteuclid.org/journals/annals-of-applied-statistics/volume-2/issue-4/A-weakly-informative-default-prior-distribution/10.1214/08-AOAS191.short>
- King y Zeng (2001), eventos raros: <https://gking.harvard.edu/publication/logistic-regression-in-rare-events-data/>
- G-Research Crypto Forecasting, cierre: los 3 primeros usaron LightGBM, y la ingeniería de variables pesó más que el modelo: <https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/>
- Anomalías de "no recuperación" en ETP cripto (2026): AUC fuera de muestra de hasta 0.82, con la volatilidad de corto plazo y el *drawdown* por encima de la microestructura: <https://arxiv.org/abs/2608.09576>
- Garcia Seuma (2026): las señales de alerta temprana varían de un episodio a otro en 7 cascadas: <https://arxiv.org/abs/2607.27070>

**No verificadas o no encontradas (no usar como evidencia):**

- La solución ganadora de **DRW Crypto Market Prediction 2025**: no encontré un informe verificable. Un hilo de participante ([fast.ai](https://forums.fast.ai/t/95-accuracy-notebooks-in-the-recent-drw-crypto-market-prediction-kaggle-comptetition/121591)) reporta que el anfitrión invalidó envíos por fuga de datos del futuro.
- La ganadora de **Jane Street 2024**: no la encontré. Que el *responder* retrasado fuera pensado para el aprendizaje en línea lo dice el buscador citando a Jane Street; no lo vi en la página abierta.
- Los autores exactos de "Meta-Labeling: Calibration and Position Sizing" y de "Ensemble Meta-Labeling" (*JFDS*): solo vi listados.
- Jacod, Lin y Todorov (2024): solo aparece mencionado en un resultado de búsqueda.
- No encontré ningún estudio académico de 2024–2026 que mida, con costos y fuera de muestra, **qué moneda rebota más** tras un pánico cripto. La evidencia del tema (d) es indirecta: liquidez y reversión en cripto, y *learning to rank* en otros activos.
