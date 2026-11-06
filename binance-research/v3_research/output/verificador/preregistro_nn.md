# Pre-registro: criterios de aceptación de la red neuronal (Constructor)

Lo redactó el Verificador el **2026-10-14, antes de ver ningún modelo ni ningún resultado**. Este documento no se modifica después de la primera ejecución. Si hace falta corregir algo antes, el cambio se anota al final con su fecha y su motivo.

## 1. Qué se prueba

- **Una sola candidata congelada:**
  - Pesos con su hash.
  - Lista de *features* y código para generarlas.
  - Umbral de decisión.
  - Geometría TP/SL/H.
  - Modo de entrada.
  - Regla de una posición por moneda.

  El Constructor la entrega **antes** de que se ejecute nada. Si envía K > 1 variantes, se aplica Holm con α = 0.05 a (a) y (c), y (b) se evalúa con Wilson al nivel 1 − 0.05/K. Lo recomendado es K = 1.
- **Reentrenamiento:** solo si está especificado de antemano y es automático (por ejemplo, un reajuste mensual con datos pasados). Ningún parámetro puede elegirse mirando el periodo de prueba.
- **Datos prohibidos** para el entrenamiento, la selección, la parada temprana y el umbral:
  - Todo lo que sea ≥ 2025-07-01, en cualquier moneda.
  - Cualquier dato de XRP, BNB, ADA, LINK, AVAX y LTC.

## 2. Pruebas (cada una se ejecuta una vez y queda registrada)

| Prueba | Monedas | Entradas | Carácter |
|---|---|---|---|
| **Primaria** | XRPUSDT, BNBUSDT, ADAUSDT, LINKUSDT, AVAXUSDT, LTCUSDT | 2025-07-01 .. 2026-10-01 (semiabierto) | Limpia; **decide** |
| Secundaria | BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT | La misma | Contaminada (holdout gastado); solo de apoyo |

- Se permite usar historia de calentamiento desde 2023-01, solo con datos pasados.
- Datos de la primaria: `research/verificador/data/` (la custodia es del Verificador; los SHA256 están en `manifest.json`).
- Se ejecuta con `verify.py --final primaria|secundaria --reason ...`, que se niega a repetir una prueba ya registrada en `research/output/verificador/ejecuciones_log.csv`. El registro guarda la fecha, el motivo, el SHA256 de las operaciones, el de `verify.py` y el de los datos.
- Código de verificación congelado: `research/verificador/verify.py`, SHA256 `0aeb80997c89e09bccfd4da0216b9b57ab0fc56f6bdf2575c5e504082ddb3d7b`.

## 3. Reglas de simulación (independientes del Constructor)

- **Salidas:**
  - Se usan el high y el low de cada vela.
  - Si TP y SL caen en la misma vela, cuenta como **SL**.
  - Si el precio abre por debajo del stop, se sale al open.
  - El TP se llena exactamente en su precio.
  - La barrera de tiempo H sale al cierre.
  - Ninguna salida usa velas posteriores al final del periodo.
- **Costos:** 0.10 % de comisión + 0.02 % de deslizamiento por lado (≈ 0.24 % ida y vuelta). El escenario de estrés es 0.15 % por lado (≈ 0.30 %).
- **Réplica:** `verify.py` vuelve a simular cada operación con los datos de custodia. Si una salida o un precio de entrada no coinciden, la operación cuenta como discrepancia, y cualquier discrepancia sin explicar es motivo de auditoría.

## 4. Criterios de aceptación (prueba primaria; se exigen los cuatro)

| | Criterio | Cómo se mide |
|---|---|---|
| **(a)** | E neta > 0 **y** t agrupado por día > 1.645 **y** E neta > 0 con costos de 0.30 % | Media del retorno neto por operación. Error estándar robusto por conglomerados (CR1) con el día UTC de entrada como conglomerado, juntando las 6 monedas. |
| **(b)** | Límite inferior de Wilson al 95 % del WR (P(neto > 0)) **≥ 0.70** | Wilson con el n bruto. Como dato informativo también se reporta con n_efectivo = n/DEFF del agrupamiento diario. |
| **(c)** | ΔE frente al azar > 0 con significancia | Control emparejado: misma moneda, mismo mes, misma geometría relativa (TP/entrada, SL/entrada, H, modo), entradas al azar y 200 repeticiones (como mínimo 20). Se exigen p < 0.05 en la prueba pareada agrupada por día sobre d_k = neto_k − media del control de k, **y** p < 0.05 en la distribución de las repeticiones. |
| **(d)** | Sin fugas | La auditoría de la fase 2 sale limpia (ver §6). |

- **Veredicto.** ACEPTA si (a), (b), (c) y (d) se cumplen en la primaria. En cualquier otro caso, RECHAZA.
- **Peso de la secundaria.** Si la primaria acepta pero la secundaria da E < 0 con t por día < −1.645, el veredicto pasa a **NO CONCLUYENTE**.
- **Información sin carácter de criterio:**
  - ΔWR y su p.
  - b efectivo y WR de equilibrio.
  - PF y MDD.
  - Resultado por moneda y por mes.
  - **DSR** con N = 12 268 configuraciones (`trials_log.csv` al 2026-10-14) más las que registre el Constructor.

  Una sola prueba pre-registrada en datos vírgenes no hereda la multiplicidad del diseño, pero un DSR bajo indica que la evidencia de diseño era débil.

## 5. Tamaño de muestra (`research/verificador/power.py`)

**(b) Wilson con límite inferior ≥ 0.70:**

| WR | n si el WR observado es ese | n para potencia del 80 % si el WR verdadero es ese |
|---|---|---|
| 0.72 | 2 025 | 4 100 |
| 0.73 | 900 | 1 780 |
| **0.75** | **324** | **625** |
| 0.78 | 131 | 240 |
| 0.80 | 85 | 155 |

**(a) E > 0 con t por día > 1.645.** Se usa un modelo de dos resultados con WR p y b elegido de forma que el azar de la misma geometría dé p − Δp; μ = R·Δp/(p − Δp) − c y σ = R(1+b)√(p(1−p)), con DEFF = 1.5. Para WR = 0.75:

| Δp sobre el azar | R | n (80 %) con c = 0.24 % | n (80 %) con c = 0.30 % |
|---|---|---|---|
| 5 pts | 2 % | E ≤ 0 | E ≤ 0 |
| 5 pts | 6.5 % (como C1) | 2 981 | 5 556 |
| 10 pts | 2 % | 3 593 | 278 243 |
| 10 pts | 4 % | 467 | 662 |
| 15 pts | 2 % | 286 | 483 |
| 15 pts | 4 % | 134 | 158 |

Para WR = 0.80 las cifras son parecidas (ver la salida de `power.py`). El equipo anterior midió ventajas de entre −1.5 y +6 puntos.

**¿Puede darlas el periodo primario?** Son 457 días × 6 monedas = 263 232 velas de 15 m. Según la frecuencia:

- A la de C1 (≈ 30 operaciones por moneda y año) salen **≈ 225 operaciones**: no alcanzan para (b) salvo que el WR observado sea ≥ 0.78. Con WR 0.75 hacen falta ≥ 324 operaciones (≥ 43 por moneda y año) y ≈ 625 para tener una potencia razonable (≥ 83 por moneda y año).
- (a) solo es alcanzable si la red supera al azar de su propia geometría en **≥ 10 puntos con R ≥ 4 %**, o en ≥ 15 puntos con R ≈ 2 %.

**Requisito.** El Constructor debe declarar su frecuencia esperada, medida en el OOS del diseño. Si implica menos de ~600 operaciones en la primaria, la prueba tendrá poca potencia; se ejecutará igual y el resultado se reportará como tal.

## 6. Auditoría de fugas (criterio d, fase 2)

1. **Truncamiento.** Para ≥ 500 velas al azar, las *features* y la predicción calculadas con datos truncados al cierre de la vela *i* deben ser iguales (con un error < 1e-9) a las calculadas con la serie completa.
2. **Perturbación del futuro.** Alterar todos los datos posteriores a `t_i + 15 m` no debe cambiar la predicción en *i*.
3. **Metrics de futuros.** Se cumple la regla de `regla_metrics.md` (T ≤ t_i + 10 min; nunca T = t_i + 15 m).
4. **Normalización y escaladores.** Se ajustan solo con datos de entrenamiento. Debe haber purga y embargo de ≥ H velas entre entrenamiento y validación.
5. **Etiquetas.** Las etiquetas no aparecen entre las *features*.
6. **Etiquetas permutadas.** Con las etiquetas permutadas, el AUC en el OOS debe ser ≈ 0.5.
7. **Datos prohibidos.** No se usan datos posteriores a 2025-07-01 ni de las monedas reservadas: se revisan el código y los hashes de entrada.
8. **Reproducción independiente.** El Verificador vuelve a generar las señales desde los pesos y el código congelados y obtiene las mismas operaciones.
