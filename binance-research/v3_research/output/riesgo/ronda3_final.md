# Gestor de Riesgo — Veredicto final

## 1. Veredicto: acepto el rechazo de C1

C1 se descarta con su familia, tal como estaba pre-registrado.

**Consulta extra al holdout:** el Validador no guardó las operaciones del holdout, así que las regeneré con el código congelado `C1_eval.py`. La consulta quedó registrada en `holdout_log.csv` (04:49:06) y coincide con la del Validador: n 148 / −0.498 % y n 150 / +0.056 %. Solo sirve para evaluar el paquete de riesgo y **no cambia ninguna decisión**.

**El paquete de riesgo aplicado al holdout** (`riesgo_r3_final.py`):

| Caso | Capital final, sin detenerse | MDD | Peor día | Interruptor que salta |
|---|---|---|---|---|
| **G3H96** (F_RISK 3 %, tope de cola 6 %) | −7.42 % | 9.0 % | −2.05 % | **CUSUM en la operación 34 (2025-10-17)**, con el capital en −4.33 % |
| **T48** (w = 0.10) | +0.62 % | 5.65 % | −2.95 % | Ninguno (racha máxima 10; el umbral era 11) |

- **G3H96:** el CUSUM la detiene y ahorra ≈ 3.1 pp. El umbral de caída (12 %) no se alcanza. Con tope de cola del 10 % el resultado es casi idéntico (−7.32 %).
- **T48:** el CUSUM no detecta una E ≈ 0 con 150 operaciones.

**Lección sobre mis Monte Carlo de diseño:**

- Con la E de diseño, P(15 meses ≤ −7.42 %) = 0.6 %.
- Con E = 0, esa probabilidad es del 33 %.
- El Monte Carlo solo mide el ruido de muestreo alrededor de una E que estaba inflada por la selección (DSR de 0.13 a 0.27).
- **Los umbrales deben calibrarse con la E desplazada a 0** (o a su cota inferior deflactada), nunca con la E puntual de diseño.

## 2. Tope de cola por defecto del 6 %, recalibrable: SÍ

En el holdout, la diferencia entre 6 % y 10 % fue de 0.1 pp. Mi argumento a favor del 10 % dependía de una ventaja de diseño que no se replicó. Lo prudente es el 6 % por defecto.

## 3. Paquete de riesgo definitivo (aunque no haya estrategia ganadora)

**Tamaño en Node, en `evaluateNewTrade`:**

```
s = 0.0012                                   // 0.10 % comisión + 0.02 % deslizamiento, por lado
lossU = SL ? (P−SL) + s·(P+SL) : Q0·P        // Q0 = cola declarada por la estrategia (por defecto 0.15)
gainU = TP ? (TP−P) − s·(P+TP) : ∞ ;  si gainU ≤ 0 → no operar
Q_i   = max(lossU/P + 0.02, 0.15)
w_i   = min(0.10, F_RISK·P/lossU, 0.40 − Σw_abiertas, (0.06 − Σw_j·Q_j)/Q_i) ;  si w_i < 0.01 → no operar
q     = floor(w_i·capital / (P·(1+s)) / stepSize)·stepSize ;  exigir q ≥ minQty y q·P ≥ minNotional
```

- F_RISK = 1.5 % por defecto.
- Con dinero real, **w = 0** hasta que una estrategia pase todo esto:
  - el protocolo del Validador;
  - un holdout nuevo o una prueba prospectiva pre-registrada;
  - 200 operaciones o más en testnet con E > 0 y sin disparo del CUSUM.

  Después se empieza con w = 0.05.

**Exchange:**

- Confirmar `executedQty` y el precio medio antes de registrar la posición.
- Precios redondeados al `tickSize`.
- Inmediatamente después, una OCO: TP límite + STOP_LOSS de mercado. Si solo hay STOP_LOSS_LIMIT, el límite va 2 % por debajo y Node actúa como vigilante.
- Si la estrategia no tiene SL, stop de catástrofe en P·(1 − max(Q0, 1.2·peor excursión adversa de diseño)).

**Barrera de tiempo:** `time_stop_ts` guardado en el ledger. Al vencer, se cancela la OCO y se vende a mercado.

**Interruptores por defecto:**

1. Caída ≥ 10 % desde el máximo.
2. Pérdida en el día UTC ≥ 5 %: sin entradas durante 24 h.
3. Racha ≥ L, con P(racha ≥ L) < 1 % al año (cadena de Markov con p y operaciones/año). Por defecto, L = 8.
4. CUSUM desde n ≥ 30: Σr < n·E_lcb − 2·σ·√n.
5. **Revisión obligatoria a las 150 operaciones:** detener si el t de E (agrupado por día) es < 1. T48 habría parado con t = 0.13.
6. Fallos operativos: deslizamiento > 0.10 % por lado en 50 operaciones, datos con más de 2 velas de atraso, o modelo sin reajustar en más de 35 días.

**Recalibración por estrategia:** se hace con su Monte Carlo de diseño, desplazando la E a 0.

- Caída = 1.2 × p99.
- Pérdida diaria = 1.25 × peor día.
- L con la fórmula de Markov.
- CUSUM con E_lcb (bootstrap semanal al 95 %, costos de 0.30 %) y σ.

## Qué NO hacer

- **Subir el WR achicando b.** Sin ventaja, P(TP antes que SL) = 1/(1+b). Entonces p(1+b) = 1 y E = −c para cualquier geometría.
  - Para WR 75 % con E > 0 hace falta R/c > 1/(p(1+b) − 1): 8 si b = 0.5, ∞ si b ≤ 1/3.
  - Medido: 0 de 3 447 configuraciones de 15m con E > 0.
  - En el holdout, G3H96 dio WR 60 % y E −0.50 %.
- **TP por debajo de los costos.** Un TP de 0.25 ATR se toca el 75 % de las veces, pero el WR neto es del 7 %.
- **Kelly con la E de diseño.** El Kelly completo arruinaba entre el 31 % y el 55 % de los años simulados, y esa E no se replicó.
- **Optimizar con un mes o quedarse con la mejor entre miles de configuraciones.** El 94.74 % de DOGE fue un artefacto del redondeo.
- **Operar sin filtro de costos.** Con 15 USDT fijos, se pierden ≈ 80 USDT al año.

## Win rate realista

**Ninguna estrategia mostró E neta > 0 fuera de muestra.** Sin ventaja, el WR lo fija la geometría (≈ 1/(1+b), menos el arrastre de los costos) y E ≈ −c. Con E > 0 demostrada, el WR realista es **«no determinado»**. Las únicas candidatas positivas en diseño tenían WR de 42–62 % y no se sostuvieron.
