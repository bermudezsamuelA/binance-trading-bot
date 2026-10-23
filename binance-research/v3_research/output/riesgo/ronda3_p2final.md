# Gestor de Riesgo — voto P2-final

**Voto: NO al tope de cola del 6 %.** Contrapropongo el mismo P2-final con **Σ w_i·Q_TAIL_i ≤ 10 %**. Todo lo demás queda igual:

- F_RISK = 3 % en G3H96 y 1.5 % en T48.
- Q_TAIL_i = max(lossU_i/P_i + 0.02, 0.15).
- Nocional total ≤ 0.40.
- Sin reducción por número de posiciones abiertas.
- Dinero real: w = 0 hasta aprobar el holdout, sumar ≥ 200 operaciones en testnet con E > 0 y no disparar el CUSUM; después, w = 0.05.

## Monte Carlo de diseño (G3H96)

- 467 operaciones, bootstrap por semanas, 20 000 años simulados.
- Los topes se aplican en orden cronológico; las entradas que ocurren en la misma vela cuentan como simultáneas.
- Script: `scripts/riesgo_r3_p2final.py`. Resultados: `output/riesgo/r3_p2final_log.txt`.

| Regla | Recortadas / omitidas | E por nocional | MDD p50 / p95 / p99 | Peor día | Retorno 1 año, mediana [p5] |
|---|---|---|---|---|---|
| F 3 %, sin tope de cola | 0 / 0 | +0.503 % | 3.5 / 7.6 / 9.9 % | −4.09 % | +14.0 % [+1.3] |
| **P2-final (tope 6 %)** | 34 / 6 | +0.424 % | **4.3 / 9.5 / 12.6 %** | −3.95 % | **+11.2 % [−1.7]** |
| P2-final con F 1.5 % | 33 / 0 | +0.380 % | 4.3 / 9.5 / 12.9 % | −3.59 % | +10.0 % [−2.9] |
| Tope 8 % | 5 / 1 | +0.473 % | 3.9 / 8.7 / 11.6 % | −4.09 % | +12.9 % [−0.2] |
| **Tope 10 % (contrapropuesta)** | 4 / 0 | +0.495 % | **3.6 / 7.8 / 10.4 %** | −4.09 % | **+13.6 % [+1.1]** |

## Por qué el 6 % no sirve

**El 6 % se llena con posiciones normales.** El 80 % de las operaciones tiene Q en el piso de 0.15, así que cuatro posiciones normales (4 × 0.10 × 0.15) ya ocupan el 6 %. Cualquier grupo de entradas con un SL profundo queda recortado.

**Recorta justo las mejores entradas.** Esos grupos son las entradas de C1 con más E: en T48, la E sube de +0.44 % a +2.23 % según el número de posiciones abiertas.

**Su costo supera su beneficio:**

| Efecto del tope del 6 % | Cambio |
|---|---|
| Peor día | mejora 0.14 pp |
| MDD p99 | empeora 2.2 pp |
| Retorno p5 | pasa a negativo (−1.7 %) |

**El 10 % sigue acotando el peor caso.** Con todos los SL tocados a la vez, la pérdida queda en ≤ 10 % del capital; sin tope, el máximo observado fue 11.1 %.

**En T48 no cambia nada.** Allí Q = 0.15, así que el tope nunca se activa.

## Interruptores

- Caída máxima con tope del 10 %: el umbral se queda en 12 %.
- Si el equipo mantiene el 6 %, el umbral sube a 14 %, porque el MDD p99 pasa a 12.6 %.

Quedo a la espera del resultado del holdout.
