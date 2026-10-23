# Gestor de Riesgo — Ronda 3: voto

- Todo se calculó con datos de diseño (2023-10 a 2025-06). No hubo consultas al holdout.
- Script: `scripts/riesgo_r3.py`. Resultados: `output/riesgo/r3_log.txt`.
- No es una configuración nueva de señal: el tamaño no cambia la E por operación que se prueba en el holdout.

## P1 (prueba con Holm): SÍ

Medí la correlación entre las E de T48 y de G3H96 con un bootstrap por día: ρ = 0.65. Con esa correlación simulé las tres reglas, con n = 300 y las no-centralidades del preregistro (1.84 y 1.77).

**Probabilidad de aprobar, según la E real:**

| Regla | P(aprueba G3), E de diseño | P(aprueba G3), E = ½ | P(aprueba alguna), E de diseño |
|---|---|---|---|
| Secuencia T48 → G3 | 0.43 | 0.13 | 0.58 |
| Secuencia G3 → T48 | 0.55 | 0.22 | 0.55 |
| **Holm** | **0.48** | 0.16 | **0.575** |

- **Error de familia:** con Holm es 0.043 bajo H0 global (≤ 0.05).
- **Por qué Holm:** conserva casi toda la potencia de aprobar alguna de las dos (0.575 frente a 0.577), le da a G3 más potencia que poner T48 primero y no impone un orden.
- **La prueba terciaria del WR es válida tal como está.** El límite inferior de Wilson al 95 % (bilateral) es una prueba unilateral con α = 0.025. Eso es lo que Holm le deja como mínimo a G3, así que el error de familia sigue ≤ 0.05.
- **Probabilidad de demostrar WR ≥ 70 %:** ≈ 17 % si el WR real es 72.4 %.
- **Advertencia para el usuario:** si aprueban las dos y se implementa G3, se renuncia a ≈ 0.19 pp de E por operación (0.73 % frente a 0.54 %). Además, su cota creíble con costos de 0.30 % es la mitad: +0.16 % frente a +0.32 %. Lo acepto, porque G3 cumpliría E > 0 demostrada y la supervivencia (ver P2).

## P2 (tamaño): SÍ, con una enmienda solo para G3H96

Para T48, P2 funciona tal como está: Q_TAIL = 0.15 y F_RISK = 1.5 % dan w = 0.10.

Para G3 hay un problema. Su lossU/P (pérdida por unidad al tocar el SL) tiene mediana de 8.9 %, p95 de 21.5 % y máximo de 49 %. Con F_RISK = 1.5 %, el 15 % de las operaciones queda con w < 0.10, y son justamente las caídas más profundas, que tienen la E más alta.

**Monte Carlo de G3 a 1 año** (bootstrap por semanas, 20 000 trayectorias):

| Tamaño | E por nocional | MDD p50 / p95 / p99 | Peor día | Retorno mediano [p5] |
|---|---|---|---|---|
| P2, F_RISK 1.5 % | +0.40 % | 4.2 / 9.3 / 12.4 % | −3.65 % | +10.6 % [−2.0] |
| P2 + f/(1 + 0.4k) | +0.35 % | 3.8 / 8.5 / 11.4 % | −2.74 % | +7.6 % [−2.9] |
| **P2, F_RISK 3 %** | **+0.50 %** | **3.5 / 7.5 / 10.1 %** | −4.09 % | **+13.8 % [+1.3]** |
| w = 0.10 fijo | +0.54 % | 3.2 / 6.7 / 8.8 % | −4.09 % | +15.1 % [+3.1] |

**Contrapropuesta para G3:** F_RISK = 3 % y Q_TAIL_i = lossU_i/P_i + 0.02 (margen por hueco). El resto de P2 no cambia: w ≤ 0.10, nocional total ≤ 0.40, Σ w·Q_TAIL ≤ 6 % y sin reducción por posiciones abiertas.

- Así, la pérdida máxima de una operación al tocar el SL queda en ≤ 3 % del capital.
- La reducción f/(1 + 0.4k) baja la E por nocional y el retorno p5 tanto en G3 como en T48.
- Dinero real: w = 0 hasta que se cumplan las dos condiciones (holdout aprobado y 200 operaciones o más en testnet con E > 0). Después, w = 0.05.

## (i) Stop en el exchange para G3H96

- Ninguna de las 467 operaciones perdió más que el SL más los costos: el SL duro no se perforó por huecos en diseño.
- Por eso **no hace falta un stop de catástrofe aparte**. El propio SL se coloca en el exchange como orden OCO, apenas se confirma el llenado.
  - Rama de ganancia: TP límite en la SMA20 de la entrada.
  - Rama de pérdida: orden STOP_LOSS de mercado. Si solo hay STOP_LOSS_LIMIT, el límite va un 2 % debajo del stop y Node vende a mercado si el precio cae por debajo de ese límite.
- La barrera de 96 velas la ejecuta Node: cancela la OCO y vende a mercado.

## (ii) Interruptores para G3H96 (con F_RISK 3 %)

1. **Caída desde el máximo ≥ 12 %** (p99 del Monte Carlo = 10.1 %): detener y revisar. Si queda F_RISK 1.5 %: 14 %.
2. **Pérdida del día UTC ≥ 5 %**, sumando abiertas y cerradas (peor caso en diseño: −4.09 %): sin entradas por 24 h.
3. **Racha de 8 pérdidas o más**: P = 0.64 % al año, con p = 0.724 y 267 operaciones/año. Detener.
4. **CUSUM a partir de n ≥ 30:** detener si Σr < n·0.0016 − 2·0.0438·√n. Aquí 0.0016 es la cota inferior al 95 % de la E con costos de 0.30 %. La falsa alarma es del 3.5 % al año si la E real es la de diseño.

Los de T48 se mantienen: 10 %, 6 %, 11 y Σr < n·0.0032 − 2·0.048·√n (falsa alarma: 2.5 % al año).
