# Regla de alineación sin fuga: `futures/um/daily/metrics` con velas de 15 m

Verificador, fase 1 (2026-10-14). Medido con **BTCUSDT**, del 2023-01-01 al 2026-09-30 (1 369 archivos diarios). Scripts: `research/verificador/probe_metrics*.py`.

## 1. Qué describe un registro con `create_time = T`

Comparé cada registro con las velas de futuros UM de 1 m y 5 m de ese mismo instante:

- **Taker ratio.** `sum_taker_long_short_vol_ratio` frente a taker_buy/(volumen − taker_buy) de la vela de 5 m.
- **Open interest.** El precio implícito (`sum_open_interest_value / sum_open_interest`) frente al precio de cada minuto.

**La convención cambia a mitad de la serie** (lo comprobé día por día, sin excepciones):

| Días | Taker ratio de la ventana | OI tomado en | El registro se conoce en |
|---|---|---|---|
| 2023-01-01 .. 2024-03-03 (428 días) | [T − 5 m, T) | T | **T** |
| 2024-03-04 .. 2026-09-30 (941 días) | **[T, T + 5 m)** | **T + 5 m** | **T + 5 m** |

Las coincidencias son claras: un error mediano de 0.0000–0.0008 en log en el taker ratio y de 0.15–2 pb en el precio implícito, frente a 0.3–0.7 en log y 5–27 pb en los instantes vecinos. Desde 2024-03-04, `create_time` marca el **inicio** del intervalo y no su final. Los archivos de esas fechas se regeneraron en 2026 (su fecha de modificación en el zip es de 2026-07/08), así que los valores también pueden haberse revisado.

## 2. Regla (obligatoria)

Una vela *i* abre en `t_i` y la decisión se toma a su cierre, en `t_i + 15 m`.

- **Instante en que se conoce cada registro:** τ(T) = T + 5 min, para todas las fechas. Es exacto desde 2024-03-04 y conservador en 5 min antes de esa fecha.
- **Un registro puede usarse en la vela *i* solo si τ(T) ≤ t_i + 15 m**, es decir, **T ≤ t_i + 10 min**. La unión se hace hacia atrás (*as-of backward*) con ese límite.
- **Margen recomendado para que el backtest coincida con el bot en vivo** (latencia de publicación de `/futures/data/*`): T ≤ t_i + 5 min.
- **Agregados de la vela de 15 m** (por ejemplo, el taker ratio de la vela): solo T ∈ {t_i, t_i + 5, t_i + 10}. **Nunca T = t_i + 15 m.**
- **Errores típicos que SÍ filtran el futuro:**
  - Un `merge_asof` sobre `close_time` + 1 ms, o sobre el `open_time` de la vela siguiente.
  - `resample('15min', closed='right', label='right')` sobre `create_time`.
  - Tratar `create_time` como el final del intervalo después de 2024-03-04.

  En los tres casos entra el registro T = t_i + 15 m. Ese registro describe [t_i + 15, t_i + 20) y el OI en t_i + 20, que son los primeros 5 minutos de la operación.
- **Normalizaciones** (z-scores, escaladores): solo con ventanas pasadas, o ajustadas únicamente en el tramo de entrenamiento de cada pliegue.

## 3. Huecos (BTCUSDT, del 2023-01 al 2026-09)

- Faltan 0 de 1 369 días.
- Faltan 133 de 394 272 intervalos de 5 m (0.034 %), en 4 rachas: la mayor es de 125 intervalos (≈ 10.4 h) desde el 2024-02-16 13:35 UTC; las demás son de 3, 3 y 2.
- Hay 168 celdas vacías: 82 en el ratio de cuentas top, 48 en el de posiciones top y 38 en el de cuentas globales. El OI y el taker ratio están completos.
- 143 archivos diarios traen las filas **desordenadas**, así que hay que ordenarlas por `create_time`. No hay duplicados ni marcas fuera de la rejilla de 5 m.
- **Tratamiento:**
  - Rellenar hacia adelante desde el último registro válido con T ≤ t_i + 10 m, con una antigüedad máxima de 30 min. Si se supera, se deja NaN y se añade un indicador de dato faltante.
  - Nunca rellenar hacia atrás ni interpolar con valores futuros.

## 4. Pendiente

- La fecha del cambio de convención se confirmará moneda por moneda en la auditoría.
- `fundingRate` (se conoce en `calc_time`) y `premiumIndexKlines` (como cualquier vela: se conocen al cierre) siguen la misma regla de "solo lo cerrado a `t_i + 15 m`", pero todavía no las he verificado empíricamente.
