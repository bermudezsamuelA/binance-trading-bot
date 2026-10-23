"""Pruebas sinteticas del arnes. Ejecutar: PYTHONIOENCODING=utf-8 python -I test_harness.py
Cada prueba construye una serie donde se sabe de antemano que barrera se toca."""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

C = H.FEE + H.SLIP
FAILS = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  ({info})" if info else ""))
    if not cond:
        FAILS.append(name)


def mk(ohlc, t0=H.ms(2024, 1, 1)):
    """ohlc: lista de (o,h,l,c). Devuelve Bars 15m sinteticas."""
    a = np.array(ohlc, float)
    n = len(a)
    t = t0 + np.arange(n) * 900_000
    arr = np.column_stack([t, a[:, 0], a[:, 1], a[:, 2], a[:, 3], np.ones(n), np.ones(n) * 0.5])
    return H.Bars(arr, "TEST", "15m")


def sig_at(n, *idx):
    s = np.zeros(n, bool)
    s[list(idx)] = True
    return s


# 1. TP tocado primero ------------------------------------------------------------------------
b = mk([(100, 100, 100, 100), (100, 101, 99.5, 100.5), (100.5, 102.5, 100, 102), (102, 103, 101, 102)])
tr = H.simulate(b, sig_at(4, 0), tp=102.0, sl=98.0)
check("TP primero: 1 operacion", len(tr) == 1)
check("TP primero: motivo TP en vela 2", tr.reason[0] == H.TP and tr.exit_idx[0] == 2, f"{tr.reason}, {tr.exit_idx}")
check("TP primero: precio de salida = TP", tr.exit_px[0] == 102.0)
exp_net = 0.02 - C * (1 + 1.02)
check("TP primero: retorno neto con costos", abs(tr.net_ret[0] - exp_net) < 1e-12, f"{tr.net_ret[0]} vs {exp_net}")
check("TP primero: r_mult = net / 2 %", abs(tr.r_mult[0] - exp_net / 0.02) < 1e-12)

# 2. SL tocado primero ------------------------------------------------------------------------
b = mk([(100, 100, 100, 100), (100, 100.5, 97.5, 98), (98, 103, 97, 102)])
tr = H.simulate(b, sig_at(3, 0), tp=102.0, sl=98.0)
check("SL primero", tr.reason[0] == H.SL and tr.exit_idx[0] == 1 and tr.exit_px[0] == 98.0)

# 3. TP y SL en la misma vela -> SL --------------------------------------------------------------
b = mk([(100, 100, 100, 100), (100, 103, 97, 101), (101, 101, 101, 101)])
tr = H.simulate(b, sig_at(3, 0), tp=102.0, sl=98.0)
check("Misma vela TP y SL -> SL", tr.reason[0] == H.SL and tr.exit_px[0] == 98.0)

# 4. Hueco bajista por debajo del SL -> sale al open ----------------------------------------------
b = mk([(100, 100, 100, 100), (100, 100.5, 99, 99.5), (96, 97, 95, 96.5)])
tr = H.simulate(b, sig_at(3, 0), tp=102.0, sl=98.0)
check("Hueco bajo SL -> sale al open", tr.reason[0] == H.SL and tr.exit_px[0] == 96.0 and tr.exit_idx[0] == 2)

# 5. Barrera de tiempo -----------------------------------------------------------------------------
b = mk([(100, 100, 100, 100)] + [(100, 100.5, 99.5, 100.2)] * 10)
tr = H.simulate(b, sig_at(11, 0), tp=102.0, sl=98.0, max_hold=3)
check("Tiempo: sale al cierre de la vela 3", tr.reason[0] == H.TIME and tr.exit_idx[0] == 3 and tr.exit_px[0] == 100.2)

# 6. Fin del periodo ---------------------------------------------------------------------------------
tr = H.simulate(b, sig_at(11, 0), tp=102.0, sl=98.0, period=(0, 6))
check("Fin de periodo: sale en la vela 5 con motivo END", tr.reason[0] == H.END and tr.exit_idx[0] == 5)

# 7. Entrada a la apertura siguiente ----------------------------------------------------------------
b = mk([(100, 100, 100, 100), (101, 101.5, 100.5, 101), (101, 102.2, 100.8, 102), (102, 102, 102, 102)])
tr = H.simulate(b, sig_at(4, 0), tp=102.0, sl=98.0, entry_mode="next_open")
check("next_open absoluto: entra a 101 en vela 1", tr.entry_px[0] == 101 and tr.entry_idx[0] == 1)
check("next_open absoluto: TP 102 en vela 2", tr.reason[0] == H.TP and tr.exit_idx[0] == 2)
tr = H.simulate(b, sig_at(4, 0), tp=102.0, sl=98.0, entry_mode="next_open", levels="relative")
check("next_open relativo: TP re-anclado a 103.02 (no tocado)", abs(tr.tp[0] - 103.02) < 1e-9 and tr.reason[0] == H.END)

# 8. Una posicion a la vez -------------------------------------------------------------------------
b = mk([(100, 100, 100, 100), (100, 100.5, 99.5, 100), (100, 102.5, 99.5, 102), (102, 102, 101, 101.5),
        (101.5, 101.6, 101.4, 101.5), (101.5, 104, 101.4, 103.6)])
tp = np.array([102, 102, 102, 103.5, 103.5, 105.0])
sl = np.array([98, 98, 98, 99.5, 99.5, 101.0])
tr = H.simulate(b, sig_at(6, 0, 1, 2, 3), tp=tp, sl=sl)
check("Una posicion: senales 1 y 2 ignoradas (2 = vela de salida)", list(tr.sig_idx) == [0, 3], f"{tr.sig_idx}")
check("Una posicion: 2a operacion toca TP 103.5 en vela 5", tr.reason[1] == H.TP and tr.exit_idx[1] == 5)
check("meta: senales ocupadas contadas", tr.meta["n_skipped_busy"] == 2)

# 9. Niveles invalidos (TP <= entrada) ------------------------------------------------------------
b = mk([(100, 100, 100, 100), (100, 100.5, 99.5, 100)])
tr = H.simulate(b, sig_at(2, 0), tp=99.0, sl=98.0)
check("Invalido skip: no opera", len(tr) == 0 and tr.meta["n_invalid"] == 1)
tr = H.simulate(b, sig_at(2, 0), tp=99.0, sl=98.0, invalid="immediate")
check("Invalido immediate: pierde solo costos", tr.reason[0] == H.INVALID and abs(tr.net_ret[0] + 2 * C) < 1e-12)

# 10. Trailing stop --------------------------------------------------------------------------------
b = mk([(100, 100, 100, 100), (100, 103, 99.8, 102.5), (102.5, 105, 102, 104.5), (104.5, 104.6, 102.9, 103)])
tr = H.simulate(b, sig_at(4, 0), tp=np.nan, sl=95.0, trail=2.0)
# stop vela1 = max(95, 100-2)=98 (no toca); vela2 = 103-2 = 101 (low 102 no toca); vela3 = 105-2 = 103 -> low 102.9 toca
check("Trailing: sale en vela 3 a 103", tr.reason[0] == H.TRAIL and tr.exit_idx[0] == 3 and tr.exit_px[0] == 103.0,
      f"{tr.reason} {tr.exit_idx} {tr.exit_px}")

# 11. Busqueda larga (mas de 64 velas, bloques crecientes) -----------------------------------------
n = 5000
ohlc = [(100, 100, 100, 100)] + [(100, 100.4, 99.6, 100)] * (n - 2) + [(100, 110, 99.9, 109)]
b = mk(ohlc)
tr = H.simulate(b, sig_at(n, 0), tp=105.0, sl=95.0)
check("Busqueda larga: TP en la ultima vela", tr.exit_idx[0] == n - 1 and tr.reason[0] == H.TP)

# 12. Indicadores contra implementaciones ingenuas --------------------------------------------------
rng = np.random.default_rng(1)
x = 60000 * np.exp(np.cumsum(rng.normal(0, 0.003, 3000)))
for nwin in (2, 8, 20, 88):
    rm, rs = H.rolling_mean(x, nwin), H.rolling_std(x, nwin)
    i = 1500
    w = x[i - nwin + 1:i + 1]
    check(f"rolling_mean/std n={nwin}", abs(rm[i] - w.mean()) < 1e-6 and abs(rs[i] - w.std(ddof=1)) < 1e-6
          and np.isnan(rm[nwin - 2]) and np.isfinite(rm[nwin - 1]))
check("rolling_max/min", H.rolling_max(x, 10)[100] == x[91:101].max() and H.rolling_min(x, 10)[100] == x[91:101].min())
e = H.ema(x, span=9)
a = 2 / 10
ref = [x[0]]
for v in x[1:]:
    ref.append(a * v + (1 - a) * ref[-1])
check("EMA recursiva", np.allclose(e, ref))
hh, ll = x * 1.002, x * 0.998
at = H.atr(hh, ll, x, 14)
tr_ = np.maximum(hh - ll, np.maximum(np.abs(hh - np.r_[np.nan, x[:-1]]), np.abs(ll - np.r_[np.nan, x[:-1]])))
tr_[0] = hh[0] - ll[0]
ref = [np.nan] * 13 + [tr_[:14].mean()]
for v in tr_[14:]:
    ref.append(ref[-1] + (v - ref[-1]) / 14)
check("ATR Wilder", np.allclose(at[13:], ref[13:]))
rsr = H.rolling_std_returns(x, 20)
r = np.diff(np.log(x))
check("sigma de retornos", abs(rsr[100] - r[80:100].std(ddof=1)) < 1e-12)
z = H.zscore(x, 20)
check("z-score", abs(z[500] - (x[500] - x[481:501].mean()) / x[481:501].std(ddof=1)) < 1e-9)

# 13. Estadistica ----------------------------------------------------------------------------------
p, lo, hi = H.wilson(8, 10)
check("Wilson 8/10 = [0.490, 0.943]", abs(lo - 0.4902) < 1e-3 and abs(hi - 0.9433) < 1e-3, f"{lo:.4f},{hi:.4f}")
n72 = H.min_n_wilson(0.72, 0.70)
check("min_n_wilson consistente", H.wilson(0.72 * n72, n72)[1] > 0.70 >= H.wilson(0.72 * (n72 - 1), n72 - 1)[1], f"n={n72}")
mu, sd = H.two_outcome_moments(0.6, 1.0, 1.0, 0.0)
check("Momentos dos resultados", abs(mu - 0.2) < 1e-12 and abs(sd - 2 * math.sqrt(0.24)) < 1e-12)
check("p* con costos (b=1, c/R=0.4 -> 70 %)", abs(H.breakeven_p(1, 0.5, 0.2) - 0.7) < 1e-12)

# 14. Metricas sobre una secuencia conocida ---------------------------------------------------------
class _T:  # objeto Trades minimo
    pass


rows = {f: np.zeros(4) for f in H.Trades.FIELDS}
rows["net_ret"] = np.array([0.02, -0.01, -0.01, 0.02])
rows["r_mult"] = np.array([2.0, -1.0, -1.0, 2.0])
rows["reason"] = np.array([H.TP, H.SL, H.SL, H.TP])
rows["entry_px"], rows["tp"], rows["sl"] = np.full(4, 100.0), np.full(4, 102.0), np.full(4, 99.0)
rows["risk_pct"] = np.full(4, 0.01)
rows["exit_idx"], rows["entry_idx"] = np.arange(4) + 1, np.arange(4)
T = H.Trades(rows, {})
m = H.metrics(T)
check("Metricas: WR 50 %, b_eff 2, PF 2", abs(m["wr"] - 0.5) < 1e-12 and abs(m["b_eff"] - 2) < 1e-12 and abs(m["pf"] - 2) < 1e-12)
check("Metricas: MDD_R = 2R, racha perdedora 2", abs(m["mdd_R"] - 2) < 1e-12 and m["max_loss_streak"] == 2)
eq = H.equity_curve(rows["net_ret"])
check("Metricas: MDD compuesto", abs(m["mdd_pct"] / 100 - (1 - 0.99 * 0.99)) < 1e-12)
check("Metricas: b de diseno = 2", abs(m["b_design_med"] - 2) < 1e-12)

# 15. PBO: ruido puro ~ 0.5; una configuracion dominante ~ 0 --------------------------------------
pbos = [H.pbo_cscv(rng.normal(0, 1, (48, 100)), S=8)["pbo"] for _ in range(20)]
check("PBO ruido: media de 20 matrices ~ 0.5", 0.35 < np.mean(pbos) < 0.65, f"{np.mean(pbos):.2f}")
noise = rng.normal(0, 1, (48, 100))
good = noise.copy()
good[:, 7] += 1.5
pb2 = H.pbo_cscv(good, S=8)
check("PBO senal real ~ 0", pb2["pbo"] < 0.05, f"{pb2['pbo']:.2f}")

# 16. Deflated Sharpe: el mejor de 1000 ruidos no es significativo ----------------------------------
series = rng.normal(0, 1, (1000, 200))
srs = series.mean(1) / series.std(1, ddof=1)
best = series[int(np.argmax(srs))]
d = H.deflated_sharpe(best, n_trials=1000, sr_trials=srs)
check("DSR: el mejor de 1000 ruidos parece significativo sin corregir (PSR>0.99) pero no con DSR (<0.95)",
      d["psr0"] > 0.99 and d["dsr"] < 0.95, f"sr={d['sr']:.3f} sr0={d['sr0']:.3f} psr0={d['psr0']:.3f} dsr={d['dsr']:.2f}")

# 17. Particiones y custodia del holdout ------------------------------------------------------------
real = H.load("BTCUSDT")
i0, i1 = H.bounds(real, "design")
check("DISENO empieza 2023-01-01 y termina antes de 2025-07-01",
      H.iso(real.t[i0]) == "2023-01-01 00:00" and H.iso(real.t[i1 - 1]) == "2025-06-30 23:45")
try:
    H.bounds(real, "holdout")
    check("Holdout sin reason -> error", False)
except PermissionError:
    check("Holdout sin reason -> error", True)
wf = H.walk_forward(real, "design", 12, 3, 3)
check("Walk-forward 12/3/3 en DISENO: 6 pliegues, primer test 2024-01",
      len(wf) == 6 and wf[0]["test_months"] == (202401, 202403) and wf[-1]["test_months"] == (202504, 202506),
      f"{len(wf)} {[f['test_months'] for f in wf]}")
mon = real.month
check("Mes AAAAMM", mon[0] == 202301 and mon[-1] == 202609)
check("Dia de la semana (2023-01-01 fue domingo=6)", real.weekday[0] == 6)

# 18. monthly_matrix ------------------------------------------------------------------------------------
rows2 = {f: np.zeros(2) for f in H.Trades.FIELDS}
rows2["entry_t"] = np.array([H.ms(2024, 1, 5), H.ms(2024, 3, 2)], dtype=np.int64)
rows2["r_mult"] = np.array([1.0, -1.0])
Mx = H.monthly_matrix([H.Trades(rows2, {})], np.array([202401, 202402, 202403]))
check("monthly_matrix", list(Mx[:, 0]) == [1.0, 0.0, -1.0])

print("\nRESULTADO:", "TODAS LAS PRUEBAS OK" if not FAILS else f"{len(FAILS)} FALLAS: {FAILS}")
sys.exit(1 if FAILS else 0)
