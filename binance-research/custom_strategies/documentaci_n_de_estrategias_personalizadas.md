# Custom Strategies (`custom_strategies`)

## Descripción del Directorio

Este directorio contiene la documentación técnica, reglas lógicas, fórmulas de gestión de riesgo y los módulos de ejecución para las estrategias personalizadas del bot de trading en **Binance Futures**.

El objetivo de este documento es centralizar el conocimiento extraído de diferentes análisis y vídeos operativos, traduciendo conceptos discrecionales a reglas algorítmicas cuantificables (cuándo operar, cuándo filtrar el mercado, cómo dimensionar posiciones y cómo gestionar salidas).

---

## Módulo 1: Gestión Monetaria, Apalancamiento y Cierres Parciales

*(Extraído del Vídeo 1: Filosofía de escalado de cuentas, cálculo de posición y gestión dinámica con EMA 50)*

### 1. Filosofía Operativa y Apalancamiento

* **Futuros vs. Fondeo:** Se descartan las cuentas de fondeo por sus reglas restrictivas de *drawdown*. Se opera directamente en **Futuros (Binance Futures)** utilizando margen **Aislado (Isolated)**.
* **Rol del Apalancamiento:** El apalancamiento no se usa para arriesgar más dinero por operación, sino para **reducir el margen retenido (colateral)** de la cuenta necesario para abrir una posición cuyo riesgo en dólares ya está estrictamente definido por el *Stop Loss*.
* **Normalización de Precios:** Al definir niveles de entrada, *Take Profit* (TP) y *Stop Loss* (SL), se recomienda redondear los precios a números planos (terminados en `.00` o `.50`) para facilitar el cálculo y evitar ruido de micro-ticks.

### 2. Fórmulas de Dimensionamiento de Posición (Position Sizing)

Para que el bot calcule automáticamente el tamaño de la orden en USDT (Valor Nocional) sin importar la distancia del *Stop Loss*:

1. **Riesgo Monetario ($R_{USD}$):**
   $$R_{USD} = \text{Balance Total} \times \text{Porcentaje de Riesgo}$$
   *(Ejemplo conservador: $1\%$ de $\$6,576 = \$66\text{ USD}$. Ejemplo en vivo con cuenta de $\$5,000$: $5\%$ de riesgo = $\$250\text{ USD}$ por trade).*

2. **Distancia al Stop Loss ($D_{SL}$):**
   $$D_{SL} = \frac{\lvert\text{Precio Entrada} - \text{Precio SL}\rvert}{\text{Precio Entrada}} \times 100$$

3. **Tamaño de la Posición Nocional ($P_{USDT}$):**
   $$P_{USDT} = \frac{R_{USD}}{D_{SL}} \times 100$$
   *(Ejemplo 1: Para arriesgar $\$66\text{ USD}$ con un SL a $1.94\%$ de distancia: $\frac{66}{1.94} \times 100 = \$3,402\text{ USDT}$. Ejemplo 2 en BCH: Para arriesgar $\$250\text{ USD}$ con un SL a $2.50\%$ de distancia: $\frac{250}{2.50} \times 100 = \$10,000\text{ USDT}$ de posición).*

4. **Margen Requerido en Binance ($M_{USDT}$):**
   $$M_{USDT} = \frac{P_{USDT}}{\text{Apalancamiento}}$$
   *(Con apalancamiento $10\text{x}$ en una posición de $\$10,000\text{ USDT}$, el exchange solo retiene $\$1,000\text{ USDT}$ de margen; con $20\text{x}$ retiene $\$500\text{ USDT}$, manteniendo el riesgo fijo en $\$250\text{ USD}$).*

### 3. Reglas de Gestión de Riesgo y Escalado (Interés Compuesto Dinámico)

#### A. Perfil de Riesgo del $10\%$ (Escalado Rápido)
* Solo aplicable si la estrategia validada (backtesting/journaling) demuestra una racha máxima de pérdidas (*max losing streak*) inferior a $10$ trades consecutivos.
* Límite de exposición simultánea: Máximo **4 setups abiertos a la vez** (Riesgo total en mercado = $40\%$ en Nivel 1).

#### B. Escalado de Nivel por Condición de Drawdown
En lugar de subir el riesgo arbitrariamente, se utiliza una tabla de niveles basada en el **Drawdown Máximo Histórico ($DD_{max}$)** de la estrategia y un **Multiplicador ($M$)**:

$$\text{Condición de Avance (\% Beneficio requerido)} = DD_{max} \times M$$

* **Parámetros recomendados:**
  * Si arriesgamos $10\%$ por trade y nuestra peor racha histórica es de $7$ pérdidas seguidas, el $DD_{max} = 70\%$.
  * **Multiplicador Conservador ($M = 0.60$):** $70\% \times 0.60 = 42\%$ de beneficio acumulado necesario sobre el capital inicial para duplicar el riesgo en dólares (pasar de Nivel 1 a Nivel 2). Equivale a unos $\sim 4$ trades ganadores netos (a ratio 1:1).
  * **Multiplicador Agresivo ($M = 0.30$):** $70\% \times 0.30 = 21\%$ de beneficio requerido (aprox. $2$ trades ganadores netos para subir de nivel).

### 4. Gestión de Salidas: Parciales + Trailing Stop con EMA 50

El mercado cripto tiende a tener impulsos agresivos seguidos de manipulaciones o *pullbacks* profundos. Para asegurar ganancias sin cortar una tendencia larga, toda posición abierta se divide en **3 tramos de salida**:

1. **Take Profit 1 ($50\%$ de la posición) — Asegurar:**
   * **Condición:** Precio alcanza el mínimo anterior (en *Short*) o máximo anterior (en *Long*), buscando una relación Riesgo/Beneficio cercana al $1:1$.
   * **Impacto:** Asegura inmediatamente una ganancia equivalente a la mitad del riesgo asumido (si arriesgaste el $10\%$ de la cuenta, aseguras un $+5\%$ directo al balance).

2. **Take Profit 2 ($25\%$ de la posición) — Tendencia Corta:**
   * **Condición:** Gestión dinámica mediante la **EMA de 50 periodos en temporalidad de 1 Hora ($\text{EMA}_{50, 1\text{H}}$)**.
   * **Gatillo:** Se cierra este $25\%$ únicamente cuando una vela de $1\text{H}$ rompe, cierra y confirma en contra de nuestra dirección al cruzar la $\text{EMA}_{50, 1\text{H}}$.

3. **Take Profit 3 ($25\%$ restante) — Tendencia Macro (Home Run):**
   * **Condición:** Gestión dinámica mediante la **EMA de 50 periodos en temporalidad de 4 Horas ($\text{EMA}_{50, 4\text{H}}$)**.
   * **Gatillo:** Se mantiene abierta durante toda la tendencia macro (soportando *pullbacks* de $1\text{H}$) y se cierra solo cuando el precio rompe y confirma cierre en contra de la $\text{EMA}_{50, 4\text{H}}$.

### 5. Esperanza Matemática y Ratios (Cuándo una estrategia es viable)

Una estrategia se evalúa por 3 variables: **Número de ejecuciones**, **Ratio de Acierto ($WR$)** y **Relación Beneficio/Riesgo ($R/R$)**.

$$\text{Rentabilidad Esperada} = (N_{\text{ganadoras}} \times \text{Ganancia Media}) - (N_{\text{perdedoras}} \times \text{Pérdida Media})$$

**Umbrales mínimos de rentabilidad para filtros de Backtesting:**

| Ratio Beneficio/Riesgo ($R/R$) | Win Rate ($WR$) Mínimo para Break Even | Win Rate ($WR$) Mínimo para ser Rentable |
| ----- | ----- | ----- |
| **1:1** | $50\%$ | $\ge 60\%$ |
| **2:1** | $\sim 33.3\%$ | $\ge 40\%$ |
| **3:1** | $25\%$ | $\ge 30\%$ |
| **4:1** | $20\%$ | $\ge 30\%$ |
| **5:1** | $\sim 16.6\%$ | $\ge 20\%$ |

---

## Módulo 2: Estrategia Multitemporal de Continuación Fractal (1D - 4H - 1H - 5M)

*(Extraído del Vídeo 2: Reglas paso a paso de entrada y salida en Largo y Corto con confluencia de Fibonacci + EMA 50)*

### 1. Fundamentos de la Estrategia

* **Los 4 Pilares de una Estrategia:**
  1. **Patrón ($P$):** Movimiento específico del precio (Impulso + Pullback corto o profundo + Continuación).
  2. **Repetición ($R$):** Que ocurra constantemente en el tiempo (alta frecuencia en cripto debido a la volatilidad/no regulación).
  3. **Normas ($N$):** Reglas objetivas de entrada, *Stop Loss* y *Take Profit*.
  4. **Ventaja a Largo Plazo ($LP$):** Esperanza matemática positiva.
* **Fractalidad y Estilos:** El mismo patrón ocurre en todas las temporalidades. Buscar el patrón principal en `1D` = *Swing Trading*; en `1H` = *Day Trading*; en `5M` = *Scalping*. En esta estrategia se combinan las **4 temporalidades de forma simultánea** para alinear la dirección macro con una entrada de alta precisión (reduciendo la distancia del *Stop Loss* y maximizando el ratio $R/R$).
* **Indicador Único de Referencia:** Media Móvil Exponencial de 50 sesiones ($\text{EMA}_{50}$) activa en todos los gráficos (`1D`, `4H`, `1H`, `5M`).
* **Selectividad Operativa (Cuándo NO operar):** No operar por impulso ni por volumen de operaciones; si las 4 temporalidades no están alineadas o si el retroceso rompe el nivel máximo permitido de Fibonacci ($0.75$), se descarta el *trade*.

### 2. Los 6 Pasos de Ejecución (Reglas Algorítmicas Long / Short)

#### Paso 1: Contexto Macro en Gráfico Diario (`1D`) — Soporte / Resistencia
* **En Largo (Long):** El precio debe encontrarse sobre una **zona de Soporte histórico relevante en `1D`** (nivel que haya actuado múltiples veces como soporte y resistencia en el pasado).
* **En Corto (Short):** El precio debe encontrarse chocando contra una **zona de Resistencia histórica relevante en `1D`**.

#### Paso 2: Acción del Precio en Gráfico Diario (`1D`) — Desaceleración y Giro
* **En Largo (Long):** Tras tocar el soporte en `1D`, el precio muestra desaceleración en la caída y confirma un **arranque o giro alcista** (ej. vela diaria alcista con fuerza). Esto proyecta una dirección alcista para los próximos $2\text{ a }3\text{ días}$.
* **En Corto (Short):** Al llegar a la resistencia en `1D`, el movimiento alcista se desacelera (rechazo/mechas superiores) y muestra una **vela de giro bajista**.

#### Paso 3: Confirmación de Estructura en 4 Horas (`4H`) — Ruptura (BOS)
* **En Largo (Long):** Bajamos a `4H` y exigimos ver una estructura de **máximos y mínimos crecientes**, confirmada por la **ruptura clara del último máximo anterior** (que además suele coincidir con una zona de soporte/resistencia intermedia en `4H`) y situándose por encima de la $\text{EMA}_{50, 4\text{H}}$.
* **En Corto (Short):** En `4H` el precio forma un máximo decreciente y **rompe el mínimo relevante anterior**, iniciando una sucesión de máximos y mínimos decrecientes y cruzando a la baja la $\text{EMA}_{50, 4\text{H}}$.

#### Paso 4: Zona de Espera y Patrón en 1 Hora (`1H`) — Fibonacci + EMA 50 + Figura Correctiva
Una vez confirmado el impulso en `4H`/`1H` y detectado que el precio detiene su avance para iniciar el *pullback*:

1. **Trazado de Fibonacci:** Se traza el retroceso de Fibonacci desde el inicio hasta el final del impulso en `1H`.
2. **Zona de Caza (Golden Zone ampliada):** Esperamos a que el precio retroceda específicamente a la franja comprendida entre el **nivel $0.50$ (mínimo requerido) y el nivel $0.75$ (máximo permitido)** de Fibonacci (incluyendo el $0.618$), buscando confluencia con la $\text{EMA}_{50, 1\text{H}}$.
3. **Filtro de Patrón Correctivo:** El retroceso hacia la zona $0.50 - 0.75$ **NO** puede ser una caída libre vertical; debe comprimir el precio formando un **patrón chartista de continuación** claro (cuña descendente/ascendente, triángulo o canal correctivo) delimitado por líneas de tendencia (diagonales).
4. **Regla de Invalidación Estricta:** Si el precio en `1H` rompe con fuerza más allá del nivel $0.75$ **de Fibonacci**, **se cancela completamente el setup**.

#### Paso 5: Gatillo de Entrada en 5 Minutos (`5M`) — Cambio de Estructura + EMA 50
Cuando el precio en `1H` ya está dentro de la caja $0.50 - 0.75$ de Fibonacci y tocando la base/techo del patrón correctivo, bajamos a **`5M`** para disparar:

* **En Largo (Long):** El precio en `5M` (que venía cayendo en el *pullback*) deja de hacer mínimos decrecientes, **empieza a formar máximos y mínimos crecientes**, y **rompe, cierra y confirma por encima de la $\text{EMA}_{50, 5\text{M}}$** (y de la diagonal del patrón). Se ejecuta compra a mercado (`MARKET`).
* **En Corto (Short):** El precio en `5M` (que venía subiendo en el *pullback*) deja de hacer máximos crecientes, **forma máximos y mínimos decrecientes**, y **rompe, cierra y confirma por debajo de la $\text{EMA}_{50, 5\text{M}}$**. Se ejecuta venta en corto a mercado (`MARKET`).

#### Paso 6: Colocación de Stop Loss (SL) y Take Profit (TP)
* **Regla de Stop Loss (Protección por Nivel de Fibonacci en `1H`):**
  * El *Stop Loss* se coloca siempre **inmediatamente por detrás del siguiente nivel de Fibonacci válido en `1H`** que no haya sido perforado:
    * Si el precio rebotó entre el $0.50$ y el $0.618$, el SL se sitúa justo por debajo (en Long) o por encima (en Short) del nivel $0.618$ (o protegiendo el $0.75$ si se acercó mucho al $0.618$).
    * Si el precio corrigió hasta tocar la zona entre $0.618$ y $0.75$, el SL se coloca justo por detrás del nivel $0.75$.
* **Regla de Take Profit:**
  * **Opción Estática / Conservadora (Salida rápida o TP1):** En el **máximo anterior** (para *Long*) o **mínimo anterior** (para *Short*) del impulso de `1H`/`4H`.
  * **Opción Dinámica (Maximizar tendencia):** Acompañar el precio moviendo el *Stop Loss* dinámicamente (*Trailing Stop* tras los nuevos mínimos crecientes en Long o máximos decrecientes en Short, o aplicando la regla de cierres parciales con $\text{EMA}_{50}$ de `1H` y `4H` descrita en el Módulo 1).

### 3. Tabla Resumen de la Lógica Multitemporal (Estándar)

| Temporalidad | Función en el Algoritmo | Condición para LONG | Condición para SHORT |
| ----- | ----- | ----- | ----- |
| **`1D` (Diario)** | Dirección y Sesgo Macro ($2-3$ días) | Rebote en Soporte histórico + Vela de desaceleración y arranque alcista. | Rechazo en Resistencia histórica + Vela de desaceleración y giro bajista. |
| **`4H` (4 Horas)** | Confirmación de Tendencia | Ruptura de máximo anterior (HH/HL) + Precio sobre $\text{EMA}_{50, 4\text{H}}$. | Ruptura de mínimo anterior (LH/LL) + Precio bajo $\text{EMA}_{50, 4\text{H}}$. |
| **`1H` (1 Hora)** | Zona de Valor y Patrón | Pullback en canal/cuña/triángulo hacia Fibo $[0.50 - 0.75]$ + $\text{EMA}_{50, 1\text{H}}$. *(Invalidar si $> 0.75$).* | Pullback en canal/cuña/triángulo hacia Fibo $[0.50 - 0.75]$ + $\text{EMA}_{50, 1\text{H}}$. *(Invalidar si $> 0.75$).* |
| **`5M` (5 Minutos)** | Gatillo de Ejecución (Trigger) | Cambio a estructura alcista (HH/HL) + Ruptura y cierre sobre $\text{EMA}_{50, 5\text{M}}$. | Cambio a estructura bajista (LH/LL) + Ruptura y cierre bajo $\text{EMA}_{50, 5\text{M}}$. |

---

## Módulo 3: Operativa en Vivo — Mix Day Trading + Scalping, Filtro SMA 200 y Gestión de Watchlist

*(Extraído del Vídeo 3: Operativa real en vivo ganando $+14.77\%$ en 24h, reglas de filtrado de mercado, uso de la SMA 200 y gestión de múltiples setups)*

### 1. Arquitectura de Temporalidades e Indicadores (Mix Day Trading + Scalping)

Cuando se busca operar intradía sin que las posiciones se alarguen durante $4\text{ días}$ (evitando depender del gráfico `1D`), se ajusta el *layout* multitemporal reduciendo un escalón las temporalidades:

* **Temporalidades de Contexto y Estructura:** `4H` (marco mayor), `1H` y `15M`.
* **Temporalidades de Ejecución y Gestión Micro:** `5M`, `2M`, `1M` (y `30S` para lectura de volumen/microestructura).
* **Configuración Exacta de Indicadores:**
  1. **$\text{EMA}_{50}$ (Media Móvil Exponencial de 50 periodos — Línea Roja):** Activa en **TODAS** las temporalidades (`4H`, `1H`, `15M`, `5M`, `2M`, `1M`). Define la tendencia dinámica y el *Trailing Stop*.
  2. **$\text{SMA}_{200}$ (Media Móvil Simple de 200 periodos — Línea Morada/Azul):** Activa específicamente en **`1H` y `5M`**. *(Nota crítica del vídeo: El autor corrige explícitamente que la media de 200 periodos es **Simple (SMA)** y NO Exponencial).* Actúa como soporte/resistencia dinámico mayor y como filtro contra falsas rupturas.
  3. **MACD:** Activo en `15M` y `5M` únicamente como confirmación secundaria de momentum/divergencia.
  4. **Volumen:** Monitoreado en las temporalidades más bajas (`1M`, `2M`) para validar la fuerza en las rupturas.

### 2. Escaneo de Mercado y Sistema de Prioridades (Watchlist Top 50)

El bot no debe operar cientos de monedas sin liquidez, sino escanear periódicamente el **Top 50 de criptomonedas por capitalización/volumen** en dos horarios clave de liquidez: **Apertura de Londres (~07:30 - 09:00 CET)** y **Apertura de Nueva York (~14:30 - 16:00 CET)**, limpiando la lista entre sesiones para eliminar ruido.

#### Clasificación de Activos (Listas `CRYPTO L` y `CRYPTO S`)
Al escanear el Top 50, los pares en rango lateral se descartan inmediatamente. Los pares en tendencia se dividen según dos escenarios operativos:

1. **Escenario A — Continuación tras Ruptura de $\text{EMA}_{50}$ (Ej. `ATOM`):**
   * El activo acaba de romper con fuerza la $\text{EMA}_{50, 1\text{H}}$, cambiando su estructura (ej. formando máximos y mínimos decrecientes).
   * **Acción:** Se espera un *pullback* hacia la $\text{EMA}_{50, 1\text{H}}$ para operar a favor de la nueva dirección.

2. **Escenario B — Rebote o Continuación en Activos "Muy Tocados" / Sobreextendidos en $\text{SMA}_{200}$ (Ej. `BGB`, `BCH`):**
   * El activo ha caído de forma mucho más agresiva y vertical que el resto del mercado, llegando directamente a chocar contra una zona de soporte mayor: la **$\text{SMA}_{200}$ en `1H`** o la **$\text{EMA}_{50}$ en `4H`** con evidente desaceleración (velas cada vez más pequeñas).
   * **Acción:** Se busca operar en *Long* dentro del movimiento correctivo/rebote bajando a temporalidades menores (`5M` / `2M`), o esperando que rompa el patrón de agotamiento para subirse a los sub-impulsos fractales.

3. **Variante C — Ruptura de Patrón Feo + Sub-impulso Fractal (Ej. `ALGO`):**
   * Si en `1H` el patrón correctivo es sucio o poco claro, **no se opera el borde del patrón**. Se espera a que el precio rompa primero el patrón en `1H`, inicie el nuevo brazo alcista, y dentro de ese brazo se buscan pequeños *pullbacks* en `5M` y `15M`.

#### Sistema de Semáforo (Prioridad de Monitoreo)
* **Color Rojo (Inminente):** El activo ya está en la zona clave de `1H`/`4H`, ha formado el patrón y está a punto de romper en `5M`. Monitoreo tick a tick.
* **Color Naranja/Rosa (Intermedio):** El activo está llegando al soporte/resistencia y comprimiendo, falta confirmación final.
* **Color Amarillo (En desarrollo):** Tiene buena estructura macro, pero aún le falta recorrido en el *pullback*.
* **Color Verde (En Ejecución / Finalizado):** Posición ya abierta en el mercado o cerrada en ganancias.

### 3. Cuándo Operar y Cuándo NO Operar (Filtros Algorítmicos Críticos)

Este vídeo revela tres reglas esenciales de filtrado para evitar pérdidas por entradas prematuras (*FOMO* o falsas rupturas):

1. **Filtro de Bloqueo por $\text{SMA}_{200}$ en `5M` (Evitar Falsas Rupturas):**
   * **Regla:** Si en `5M` el precio rompe la línea diagonal del patrón correctivo (y la $\text{EMA}_{50, 5\text{M}}$), pero la **$\text{SMA}_{200, 5\text{M}}$ pasa muy cerca por encima** (en un *Long*) o por debajo (en un *Short*), **NO se ejecuta la orden todavía**.
   * **Por qué:** Como se demostró en vivo con `BCH` y `BTC`, entrar antes de superar la $\text{SMA}_{200, 5\text{M}}$ suele comerse un rechazo inmediato (*fakeout*). Es obligatorio exigir que la vela de `5M` **rompa, cierre y confirme también por encima de la $\text{SMA}_{200, 5\text{M}}$**.

2. **Filtro de Profundidad de Pullback en Cripto (`15M` / `4H` vs `5M` / `1H`):**
   * **Regla (Casos `DOT` e `ICP`):** En criptomonedas, los *pullbacks* suelen ser cortos en tiempo pero profundos/incisivos en precio.
   * Si un activo en tendencia bajista hace un *pullback* débil que solo toca la $\text{EMA}_{50, 5\text{M}}$ (como en `DOT`) o se queda a mitad de camino entre la $\text{EMA}_{50}$ de `5M` y la de `15M` sin tocar niveles de Fibonacci, diagonales ni *Fair Value Gaps* (como en `ICP`), **NO SE OPERA**.
   * **Nivel requerido:** En cripto, para que un *pullback* sea operable con alta probabilidad, debe atacar la media móvil más larga del par de trabajo: la **$\text{EMA}_{50}$ de `15M`** (en *scalping*) o la **$\text{EMA}_{50}$ de `4H` / $\text{SMA}_{200}$ de `1H`** (en *day trading*).

3. **Filtro de Límite de Tiempo / Estancamiento (Time-Stop):**
   * **Regla:** Si tras abrir una posición el precio no arranca en las siguientes **$4\text{ a }5\text{ horas}$** y entra en una consolidación horizontal prolongada al borde del patrón, aumenta drásticamente la probabilidad de caída.
   * **Acción:** Nunca irse a dormir con riesgo abierto; si la operación se estanca al final del día, se mueve el *Stop Loss* a **Break Even (BE)** o se cierra manualmente a primera hora de la mañana siguiente.

### 4. Reglas Avanzadas de Ejecución y Gestión Dinámica (Plan B y Trailing Stop)

* **Confluencia Triple de Entrada (El Setup Perfecto — Ej. `BTC`):**
  1. Tendencia macro alcista en `4H`.
  2. Patrón grande de continuación en `1H` (Triángulo / Cuña).
  3. **Micro-patrón de reversión** al final del patrón de `1H` sobre soporte: formación de un **Doble Suelo** o **Triple Suelo** (ej. `ADA`, `BTC`, `BCH`) acompañado de una **Vela Envolvente Alcista** (*Bullish Engulfing*).
  4. Disparo en `5M` al romper la $\text{SMA}_{200, 5\text{M}}$.

* **Plan B de Entrada en `2M` (Cuando se escapa la ruptura en `5M` — Ej. `HBAR`):**
  * Si el precio rompe la diagonal en `5M` demasiado rápido y no dio punto de entrada limpio, **no se persigue el precio**.
  * Se baja al gráfico de **2 Minutos (`2M`)**, se espera a que se forme un pequeño nivel de resistencia/consolidación horizontal tras la primera subida, y se entra en la **ruptura confirmada de esa resistencia horizontal en `2M`**.
  * **Ajuste de SL en Plan B:** Como se entra más arriba (más tarde), el *Stop Loss* ya no se pone en el mínimo absoluto de `5M`/`1H`, sino **justo por debajo del último mínimo local formado en `2M`** (apoyado en la $\text{EMA}_{50, 2\text{M}}$).

* **Gestión Activa del Trade (Trailing Stop con Fibonacci + $\text{EMA}_{50}$ en `2M`/`5M`):**
  * **Método 1 (Fibonacci Progresivo):** Cuando el trade entra en beneficios, hace un primer impulso, corrige (*pullback*) y vuelve a romper el máximo anterior, se traza Fibonacci sobre el nuevo impulso para ir subiendo el *Stop Loss* detrás de los niveles de retroceso.
  * **Método 2 ($\text{EMA}_{50}$ en `2M` y `5M`):** En movimientos rápidos (como el *trade* de `BTC`), se persigue el precio subiendo el *Stop Loss* detrás de la **$\text{EMA}_{50}$ en `2M` o `5M`**. En cuanto el precio pierde fuerza y rompe la $\text{EMA}_{50, 2\text{M}}$ / `1M` a la baja, se cierra la posición asegurando todo el tramo.

### 5. Registro de Auditoría: Los 4 Trades Ejecutados en Vivo

*(Capital operativo asignado: $\$5,000\text{ USDT}$ | Riesgo fijo por operación: $\$250\text{ USDT}$ ($5\%$) | Resultado en 24h: $+\$738.29\text{ USDT}$ / $+14.77\%$)*

| # | Activo | Dirección | Contexto (`4H` / `1H`) | Gatillo de Entrada (`5M` / `2M` / `1M`) | Ubicación Stop Loss (SL) | Gestión de Salida / TP | Resultado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **1** | **BTCUSDT** | `LONG` | Tendencia alcista `4H` + Triángulo/Cuña en `1H` + Doble Suelo con envolvente alcista en la base. | Ruptura y confirmación por encima de la **$\text{SMA}_{200}$ en `5M`**. | Por debajo del doble suelo / mínimo previo en `5M`. | *Trailing Stop* dinámico siguiendo la **$\text{EMA}_{50}$ en `2M`**. Cerrado al romper en `2M`/`1M`. | **+$271.25** |
| **2** | **BCHUSDT** | `LONG` | Caída acelerada tras triple techo en `4H` directo a soporte de $\text{EMA}_{50, 4\text{H}}$ y $\text{SMA}_{200, 1\text{H}}$ con velas de desaceleración + Cuña y Doble Suelo en `1H`. | Ruptura de la diagonal de la cuña + ruptura de la **$\text{SMA}_{200}$ en `5M`** (Entrada: $\$522.2$, Posición: $\$10,000\text{ USDT}$ a $10\text{x}$). | En $\$509.0$ ($2.50\%$ de distancia), protegiendo por debajo de la zona de doble suelo en `1H`. | TP objetivo en $\$552.0$ (máximos anteriores). Se movió a *Break Even* por la noche y se cerró manualmente por la mañana tras romper al alza. | **+$89.37** *(+107.71 bruto)* |
| **3** | **PENGUUSDT** | `LONG` | Tendencia alcista clara en `4H` con pequeña acumulación que forma un Triángulo simétrico perfecto en `1H`. | Entrada anticipada/agresiva en `1M`/`5M` al romper un nivel de resistencia horizontal interna antes de romper la cuña/triángulo completo. | Por debajo de los últimos mínimos de la estructura en `5M`. | TP estático/conservador en la zona de máximos anteriores (salida rápida para rotar capital). | **+$253.78** |
| **4** | **HBARUSDT** | `LONG` | Cuña descendente clara en `1H` apoyándose sobre la $\text{SMA}_{200, 1\text{H}}$ y $\text{EMA}_{50}$. | **Plan B en `2M`:** Se escapó la ruptura de la diagonal en `5M`; se entró al romper la resistencia horizontal de consolidación en `2M` sobre la $\text{EMA}_{50, 2\text{M}}$. | Ajustado por debajo de los mínimos locales de **`2M`** (no en la base de `5M`). | Ajuste manual agresivo del *Stop Loss* (Trailing muy pegado al precio) para asegurar ganancias rápido. | **+$123.89** |

---

## Siguientes Pasos para el Repositorio (Roadmap Técnico Integrado)

1. **Módulo de Cálculo de Órdenes (`risk_manager.py`):**
   * Implementar la función que reciba `entry_price`, `stop_loss_price` y `risk_percentage` (o monto fijo en USD como $\$250$), redondee los precios, y calcule el tamaño nocional exacto ($P_{USDT} = \frac{R_{USD}}{D_{SL}} \times 100$) configurando el apalancamiento en modo `ISOLATED` ($10\text{x}$ o $20\text{x}$).

2. **Escáner del Top 50 y Clasificador de Watchlist (`market_scanner.py`):**
   * Obtener los 50 pares con mayor volumen/capitalización en Binance Futures.
   * Programar rutinas de escaneo en los inicios de sesión (Londres y Nueva York).
   * Clasificar automáticamente los activos en:
     * `ESCENARIO_1_CONTINUACION`: Ruptura reciente de $\text{EMA}_{50, 1\text{H}}$ esperando *pullback* a la $\text{EMA}_{50}$ de `15M` o `4H`.
     * `ESCENARIO_2_SOBREEXTENSION`: Caída/subida vertical chocando con $\text{SMA}_{200, 1\text{H}}$ o $\text{EMA}_{50, 4\text{H}}$ + reducción del cuerpo de las velas (desaceleración).

3. **Filtros de Seguridad Pre-Trade (`trade_filters.py`):**
   * **Filtro $\text{SMA}_{200}$ en `5M`:** Bloquear cualquier orden `LONG` si $\text{Precio Actual} < \text{SMA}_{200, 5\text{M}}$ pero la distancia a la $\text{SMA}_{200, 5\text{M}}$ es menor al $0.5\%$, exigiendo el cierre de vela por encima de dicha media.
   * **Filtro de Profundidad de Pullback:** Descartar señales donde el retroceso solo haya tocado la $\text{EMA}_{50, 5\text{M}}$ sin haber alcanzado la $\text{EMA}_{50, 15\text{M}}$, la zona Fibo $[0.50 - 0.75]$ o la $\text{SMA}_{200, 1\text{H}}$.

4. **Motor de Ejecución Dual (`entry_trigger.py`):**
   * **Modo A (`5M`):** Entrada por ruptura de diagonal + cierre sobre $\text{EMA}_{50, 5\text{M}}$ y $\text{SMA}_{200, 5\text{M}}$ (con detección de Doble/Triple Suelo + vela envolvente).
   * **Modo Plan B (`2M`):** Si la ruptura en `5M` ocurrió hace $N$ velas sin entrada, detectar rango horizontal corto en `2M` y disparar al romper el techo del rango con SL en el mínimo de `2M`.

5. **Gestor Dinámico de Salidas y Time-Stop (`position_manager.py`):**
   * Soporte para TP estático en el máximo/mínimo anterior (estilo *scalping* rápido para liberar margen), *Trailing Stop* por cierre contra la $\text{EMA}_{50}$ en `2M`/`5M` o `1H`/`4H`, y regla de **Time-Stop** (mover a *Break Even* automáticamente si transcurren $5\text{ horas}$ sin romper estructura a favor o antes del cierre diario).