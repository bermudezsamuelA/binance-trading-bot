# HARNESS.md — API del arnés de backtest compartido

Custodio: Agente 3 (Validador). Archivos: `harness.py` (núcleo), `bot_replica.py` (réplicas del bot), `test_harness.py` (pruebas sintéticas: `PYTHONIOENCODING=utf-8 python -I test_harness.py` → "TODAS LAS PRUEBAS OK").

```python
import harness as H                      # ejecutar desde research/scripts
bars = H.load("ETHUSDT")                 # Bars: t(ms) o h l c v tbv, 131 419 velas de 15m
i0, i1 = H.bounds(bars, "design")        # DISEÑO 2023-01-01 .. 2025-06-30
mu, sd = H.rolling_mean(bars.c, 20), H.rolling_std(bars.c, 20)
sig = bars.c < mu - 2 * sd
tr = H.simulate(bars, sig, tp=mu, sl=bars.c - (mu - bars.c), period=(i0, i1), max_hold=96)
m = H.metrics(tr, n_configs=40, boot=2000)
print(H.fmt(m, "MR 20/2"))
H.log_trials("analista", 40, "rejilla MR n∈{..} k∈{..}")   # registrar SIEMPRE cuántas configuraciones probaste
```

## 1. Datos y particiones

| Función | Qué hace |
|---|---|
| `load(symbol, tf="15m") -> Bars` | Lee `klines/{symbol}_{tf}.npy` (N×7: open_time_ms, open, high, low, close, volume, taker_buy_base). Cachea. |
| `Bars.t/o/h/l/c/v/tbv` | Arrays numpy. `bars.month` (AAAAMM), `bars.hour` (UTC), `bars.weekday` (0 = lunes), `bars.idx(ts_ms)`, `bars.slice(i0, i1)`. |
| `DESIGN`, `HOLDOUT` | `(ms_inicio, ms_fin)` semiabiertos: DISEÑO 2023-01-01→2025-07-01; HOLDOUT 2025-07-01→2026-10-01. |
| `bounds(bars, part, reason=None)` | Índices `[i0, i1)`. `part` = `"design"`, `"holdout"`, `"all"` o `(ms0, ms1)`. **Cualquier rango que toque el holdout exige `reason="..."` y queda registrado** en `output/validador/holdout_log.csv`. Sin `reason` lanza `PermissionError`. |
| `walk_forward(bars, "design", train_months=12, test_months=3, step_months=3, embargo_bars=0)` | Lista de pliegues `{train:(i0,i1), test:(j0,j1), train_months, test_months}` por meses calendario. 12/3/3 en DISEÑO da 6 pliegues (tests 2024-01 … 2025-06). |
| `log_trials(agent, n_configs, description)` | Registro obligatorio de configuraciones probadas → `output/validador/trials_log.csv` (base para Bonferroni y Deflated Sharpe). |

**Regla de oro:** calcula los indicadores sobre la serie completa (así el holdout tiene calentamiento con datos pasados legítimos) y restringe las operaciones con `period=(i0, i1)`. No uses `bars.slice` para indicadores (pierde el calentamiento).

## 2. Indicadores (vectorizados, sin mirar al futuro: el valor en `i` usa datos ≤ `i`)

`shift(x, k)`, `rolling_mean(x, n)`, `rolling_std(x, n, ddof=1)` (igual que pandas `.std()`; exacta, dos pasadas), `rolling_max/min/sum(x, n)`, `log_returns(c)`, `simple_returns(c)`, `rolling_std_returns(c, n)` (σ por vela de los retornos, fracción), `ewma_vol(c, lam=0.94)`, `ema(x, span=…)`/`ema(x, alpha=…)`, `true_range(h,l,c)`, `atr(h,l,c,n, method="wilder"|"sma")`, `zscore(x, n)` (ventana que incluye `x_i`, como las bandas del bot), `rolling_vwap(c, v, n)`. Los primeros `n−1` valores son NaN.

## 3. Simulador

```python
simulate(bars, entries, tp=None, sl=None, *, period=None, entry_mode="close", levels="absolute",
         max_hold=None, trail=None, fee=0.001, slip=0.0002, invalid="skip", cooldown=0, risk=None) -> Trades
```

- `entries`: bool (N,) — señal al **cierre** de la vela `i`.
- `tp`, `sl`: precios absolutos (array (N,) o escalar) fijados en la vela de señal; NaN = sin barrera.
- `entry_mode="close"`: entra a `c[i]`, barreras desde la vela `i+1`. `"next_open"`: entra a `o[i+1]`, barreras desde la vela `i+1` (incluida). Con `levels="relative"` TP/SL se re-anclan al precio real de entrada (`tp·o[i+1]/c[i]`).
- Barreras con **high/low**. Si en la misma vela se tocan TP y SL ⇒ **SL**. Stop con hueco (open ≤ SL) se llena al open; TP se llena exactamente al TP. `max_hold` = barrera de tiempo (sale al cierre de la vela `entrada + max_hold`). `trail` = distancia absoluta del trailing stop (Chandelier: stop_j = max(SL, máx(entrada, H hasta j−1) − trail)).
- **Una posición a la vez**: una señal solo se toma si su vela es posterior a la vela de salida (+`cooldown`).
- `period=(i0, i1)`: solo señales en `[i0, i1)`; la salida nunca usa velas ≥ `i1` (se cierra en `i1−1`, motivo END).
- Costos: `net = (exit/entry − 1) − (fee+slip)·(1 + exit/entry)` ≈ bruto − 0.24 %.
- `invalid="skip"` descarta señales con entrada fuera de (SL, TP); `"immediate"` las abre y cierra al mismo precio (pierden solo costos: así se comporta el bot en vivo cuando el redondeo deja TP ≤ entrada).
- `resolve_exit(o,h,l,c,j0,j_end,entry,tp,sl,trail,max_hold)` es la función de bajo nivel (para simuladores por eventos).

`Trades`: arrays `sig_idx, entry_idx, exit_idx, entry_px, exit_px, tp, sl, reason (0 tp,1 sl,2 time,3 end,4 trail,5 invalid), gross_ret, net_ret, risk_pct, r_mult, entry_t, exit_t`; `.hold`, `.subset(mask)`, `.between(ts0, ts1)`, `.to_csv(path)`, `Trades.concat(lista)`, `.meta` (señales, ocupadas, inválidas…). R = entrada − SL (o `risk=` si no hay SL); `r_mult = net_ret / risk_pct`.

## 4. Métricas y estadística

`metrics(tr, n_configs=1, frac=1.0, boot=0, block=1)` devuelve, entre otras: `n`, `wr` (= P(neto > 0)), `wr_lo/wr_hi` (Wilson 95 %), `tp_rate`, `b_eff` (ganancia media neta / pérdida media neta), `wr_breakeven` (= pérdida/(ganancia+pérdida), el WR que deja E = 0 con ese b_eff), `E_pct` y `E_R` (netas), `E_gross_pct`, `wr_gross`, `pf`, `mdd_pct` (curva compuesta con `frac` del capital por operación), `mdd_R`, `max_loss_streak`, `t`, `p_value` (unilateral H0: E ≤ 0), `p_bonf` (= p·n_configs), `risk_med_pct`, `trades_per_year`, `sharpe_trade` y, con `boot>0`, `E_boot_lo_pct/E_boot_hi_pct/E_boot_p_le0`. `fmt(m, label)` imprime una línea; `md_header()` y `md_row(label, m)` arman tablas Markdown.

| Función | Uso |
|---|---|
| `wilson(k, n)` | (p, lo, hi) |
| `min_n_wilson(p_obs, p0)` | n mínimo para que el límite inferior de Wilson supere `p0` |
| `two_outcome_moments(p, b, R, c)` / `breakeven_p(b, R, c)` | μ y σ por operación; p* = (1 + c/R)/(1 + b) |
| `min_n_mean(mu, sd, alpha, power, n_tests)` | n = ((z₁₋α/N + z_potencia)·σ/μ)² |
| `bootstrap(x, B, block)` | IC y P(E ≤ 0) (bloques móviles si `block>1`) |
| `psr`, `deflated_sharpe(x, n_trials, sr_trials=…)` | PSR y DSR (Bailey y López de Prado) |
| `pbo_cscv(M, S=16)` | PBO por CSCV sobre una matriz meses × configuraciones (`monthly_matrix(lista_trades, meses)`) |
| `equity_curve`, `max_drawdown`, `max_streak` | Curvas y rachas |

## 5. Réplicas del bot (`bot_replica.py`)

- `original_optimizer(closes, code, n, k)`: copia literal de `optimize.py` (reproduce 15 de las 16 entradas de `ml_results.json` sobre sep-2026).
- `run_frozen(bars, code, n, k, period, rounding=True)`: el bot fiel (ventana congelada mientras hay posición, TP/SL redondeados a 2 decimales) con salidas honestas.
- `signals(bars, code, n, k, rounding=False)`: señales vectorizadas con ventana continua → `(entries, tp, sl)` para `simulate`.
- Códigos: `"MR"` (MeanReversion, b = 1), `"TF"` (TrendFollowing, b = 2), `"SQ"` (Squeeze, b = 2.5), `"VWAP"` (= MR en el bot).

## 6. Protocolo obligatorio (resumen; detalle en `output/validador/ronda1.md`)

1. Ajustes **solo en DISEÑO**, con walk-forward 12/3/3 (`walk_forward`). Reporta el resultado OOS concatenado de los pliegues, no el IS.
2. Registra con `log_trials` cada rejilla o variante probada; reporta `n_configs` en `metrics`.
3. Una candidata se acepta si en el OOS del walk-forward: E neta > 0 con p_Bonferroni < 0.05 (o DSR > 0.95), PBO < 0.2 en CSCV y n suficiente (ver la tabla de tamaños mínimos).
4. El holdout se abre **una sola vez por candidata final**, con `bounds(..., reason=...)`, y lo ejecuta o audita el Validador.
