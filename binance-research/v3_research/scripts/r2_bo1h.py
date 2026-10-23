"""Ronda 2 (Validador): reproduccion y protocolo del candidato del Gestor de Riesgo (solo DISENO).

BO 1h = velas de 1h (agregadas de 15m, alineadas a la hora UTC); senal z96 = (C - SMA96)/sd96 > 2.5 (sd de
precios, ddof=1); salida chandelier: stop = max(entrada, maximos posteriores) - 3*ATR14(SMA de TR) fijado en la
entrada; sin TP; barrera de tiempo H = 192 velas (8 dias); R = 3*ATR. Una posicion por moneda.
Pruebas: reproduccion con harness.simulate, pliegues 3m (>= 4/6), por ano y moneda, costos 0.30 %, retraso de
1 vela, linea base de entradas al azar con la misma salida (mismo mes y moneda), WF 12/3/3 con seleccion dentro
de una familia declarada de 16 variantes, PBO (CSCV) y DSR con el conteo total del equipo.
Salida: output/validador/r2_bo1h.txt / .json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

OUT, RES = [], {}


def P(s=""):
    print(s, flush=True)
    OUT.append(s)


def to_1h(b15):
    key = b15.t // 3_600_000
    st = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    en = np.r_[st[1:] - 1, len(b15) - 1]
    arr = np.column_stack([b15.t[st].astype(float), b15.o[st], np.maximum.reduceat(b15.h, st),
                           np.minimum.reduceat(b15.l, st), b15.c[en], np.add.reduceat(b15.v, st),
                           np.add.reduceat(b15.tbv, st)])
    return H.Bars(arr, b15.symbol, "1h")


B = {s: to_1h(H.load(s)) for s in H.SYMBOLS}
IND = {}


def ind(s, n):
    k = (s, n)
    if k not in IND:
        b = B[s]
        IND[k] = (H.rolling_mean(b.c, n), H.rolling_std(b.c, n), H.atr(b.h, b.l, b.c, 14, method="sma"))
    return IND[k]


def run(n=96, k=2.5, m=3.0, Hh=192, period="design", fee=H.FEE, slip=H.SLIP, delay=0, sig_override=None):
    out = []
    for s in H.SYMBOLS:
        b = B[s]
        mu, sd, A = ind(s, n)
        with np.errstate(invalid="ignore"):
            sig = (b.c - mu) / sd > k
        sig &= np.isfinite(A)
        if sig_override is not None:
            sig = sig_override[s]
        trail, risk = m * A, m * A
        if delay:
            sig = np.r_[np.zeros(delay, bool), sig[:-delay]]
            trail = np.r_[np.full(delay, np.nan), trail[:-delay]]
            risk = trail
        i0, i1 = H.bounds(b, period) if isinstance(period, str) else (b.idx(period[0]), b.idx(period[1]))
        out.append(H.simulate(b, sig, None, None, period=(i0, i1), max_hold=Hh, trail=trail, risk=risk, fee=fee, slip=slip))
    return H.Trades.concat(out)


def line(m):
    return (f"n={m['n']:4d} WR={m['wr']*100:5.1f}% [{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}] b={m['b_eff']:.2f} "
            f"E={m['E_pct']:+.3f}% E_R={m['E_R']:+.3f} t={m['t']:+.2f} PF={m['pf']:.2f} MDD_R={m['mdd_R']:.1f}")


def month_sums(T):
    mon = T.entry_t.astype("datetime64[ms]").astype("datetime64[M]")
    u = np.unique(mon)
    return np.array([np.nansum(T.r_mult[mon == x]) for x in u]), np.array([T.net_ret[mon == x].sum() for x in u])


def folds(T):
    res = []
    for kf in range(6):
        y, mth = 2024 + kf // 4, 1 + 3 * (kf % 4)
        a, b = H.ms(y, mth), H.ms(y + (mth + 3 > 12), (mth + 3 - 1) % 12 + 1)
        sub = T.between(a, b)
        res.append((f"{y}-{mth:02d}", len(sub), float(np.nanmean(sub.r_mult)) if len(sub) else float("nan")))
    return res


P("=== 1. Reproduccion BO(96, 2.5) 1h + chandelier 3 ATR, H 192 (Gestor: N 486, WR 42.0 %, E +0.446 %, E_R +0.130, t_mes 2.05) ===")
T = run()
m = H.metrics(T)
rs, _ = month_sums(T)
tmes = rs.mean() / rs.std(ddof=1) * np.sqrt(len(rs))
P(f"  arnes: {line(m)} t_mes(R)={tmes:+.2f}")
RES["base"] = {"metrics": m, "t_mes": tmes}
fe = folds(T)
P(f"  pliegues 3m 2024-01..2025-06 con E_R>0: {sum(f[2] > 0 for f in fe)}/6: " + " ".join(f"{f[0]}:{f[2]:+.3f}R({f[1]})" for f in fe))
for y in (2023, 2024, 2025):
    sub = T.between(H.ms(y, 1), H.ms(y + 1, 1))
    P(f"  {y}: n={len(sub)} E_R={np.nanmean(sub.r_mult):+.3f} E={sub.net_ret.mean()*100:+.3f}% WR={(sub.net_ret > 0).mean()*100:.1f}%")
for s in H.SYMBOLS:
    sub = T.subset(np.isin(T.entry_t, B[s].t) & (np.array([True] * len(T))))
P("  por moneda: " + "; ".join(
    f"{s[:4]} " + line(H.metrics(run_s)).split(' t=')[0] for s, run_s in
    ((s, H.simulate(B[s], ((B[s].c - ind(s, 96)[0]) / ind(s, 96)[1] > 2.5) & np.isfinite(ind(s, 96)[2]), None, None,
                    period=H.bounds(B[s], "design"), max_hold=192, trail=3 * ind(s, 96)[2], risk=3 * ind(s, 96)[2]))
     for s in H.SYMBOLS)))

P("\n=== 2. Costos 0.30 % y retraso de 1 vela (1 h) ===")
P(f"  costo 0.30 %: {line(H.metrics(run(fee=0.0013)))}")
P(f"  retraso 1 vela: {line(H.metrics(run(delay=1)))}")

P("\n=== 3. Linea base: entradas al azar (mismo mes y moneda) con la MISMA salida chandelier 3 ATR / H 192 ===")
rng = np.random.default_rng(3)
Er, Wr = [], []
for rep in range(10):
    ov = {}
    for s in H.SYMBOLS:
        b = B[s]
        mu, sd, A = ind(s, 96)
        with np.errstate(invalid="ignore"):
            sig = ((b.c - mu) / sd > 2.5) & np.isfinite(A)
        i0, i1 = H.bounds(b, "design")
        mon = b.month
        rnd = np.zeros(len(b), bool)
        for i in np.flatnonzero(sig[i0:i1]) + i0:  # reemplaza cada senal por una vela al azar del mismo mes
            cand = np.flatnonzero(mon[i0:i1] == mon[i]) + i0
            rnd[rng.choice(cand)] = True
        ov[s] = rnd & np.isfinite(A)
    Tr = run(sig_override=ov)
    mr = H.metrics(Tr)
    Er.append(mr["E_R"]); Wr.append(mr["E_pct"])
P(f"  azar (10 repeticiones): E_R medio {np.mean(Er):+.3f} (min {np.min(Er):+.3f}, max {np.max(Er):+.3f}); "
  f"E % medio {np.mean(Wr):+.3f}% | senal BO: E_R {m['E_R']:+.3f}, E {m['E_pct']:+.3f}%")
RES["random_baseline"] = {"E_R": Er, "E_pct": Wr}
# comprar y mantener del diseno (deriva)
bh = [B[s].c[H.bounds(B[s], 'design')[1] - 1] / B[s].c[H.bounds(B[s], 'design')[0]] - 1 for s in H.SYMBOLS]
P("  comprar y mantener en DISENO: " + ", ".join(f"{s[:4]} {x*100:+.0f}%" for s, x in zip(H.SYMBOLS, bh)))

P("\n=== 4. Walk-forward 12/3/3 con seleccion en una familia declarada (n{48,96} x k{2,2.5} x m{2,3} x H{96,192}) ===")
FAM = [(n, k, mm, hh) for n in (48, 96) for k in (2.0, 2.5) for mm in (2.0, 3.0) for hh in (96, 192)]
TRS = [run(n, k, mm, hh) for (n, k, mm, hh) in FAM]
months = np.unique(B["BTCUSDT"].month[slice(*H.bounds(B["BTCUSDT"], "design"))])
M = H.monthly_matrix(TRS, months, "r_mult")
Mc = H.monthly_matrix([type(t)({**{f: getattr(t, f) for f in H.Trades.FIELDS}, "r_mult": np.ones(len(t))}, {}) for t in TRS], months, "r_mult")
oos = []
picks = []
for f in range(6):
    te_start = 12 + 3 * f
    tr_rows = slice(te_start - 12, te_start)
    perf = M[tr_rows].sum(0) / np.maximum(Mc[tr_rows].sum(0), 1)
    perf[Mc[tr_rows].sum(0) < 20] = -np.inf
    j = int(np.argmax(perf))
    picks.append(FAM[j])
    te_m = months[te_start:te_start + 3]
    t = TRS[j]
    mm_ = t.entry_t.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)
    mm_ = (1970 + mm_ // 12) * 100 + mm_ % 12 + 1
    oos.append(t.subset(np.isin(mm_, te_m)))
To = H.Trades.concat(oos)
mo = H.metrics(To)
P(f"  elegidos por pliegue: {picks}")
P(f"  OOS concatenado 2024-01..2025-06: {line(mo)}")
RES["wf"] = {"metrics": mo, "picks": picks}
for S in (6, 10):
    pb = H.pbo_cscv(M, S=S)
    P(f"  PBO familia de {len(FAM)} (S={S}): {pb['pbo']:.2f}; P(el elegido pierde OOS) = {pb['p_oos_loss']:.2f}; pendiente {pb['slope_oos_on_is']:+.2f}")
    RES[f"pbo_S{S}"] = pb

P("\n=== 5. DSR / Bonferroni con el conteo total del equipo ===")
from scipy import stats  # noqa: E402
for lab, n in (("Gestor 1h (3 447)", 3447), ("Gestor (6 894)", 6894), ("equipo (12 164)", 12164)):
    d_tr = H.deflated_sharpe(np.nan_to_num(T.r_mult), n_trials=n)
    d_mo = H.deflated_sharpe(rs, n_trials=n)
    p_mo = 1 - stats.t.cdf(tmes, len(rs) - 1)
    P(f"  N={n:6d} ({lab}): por operacion DSR={d_tr['dsr']:.3f} (SR {d_tr['sr']:.3f} vs SR0 {d_tr['sr0']:.3f}); "
      f"por mes DSR={d_mo['dsr']:.3f}; Bonferroni t_mes: p={H.bonferroni(p_mo, n):.3g}")
H.log_trials("validador", 1 + 2 + 10 + len(FAM), "R2 auditoria BO 1h del Gestor: reproduccion, costos/retraso, azar x10, familia WF/PBO 16", "design")
open(os.path.join(H.VALIDADOR_DIR, "r2_bo1h.txt"), "w", encoding="utf-8").write("\n".join(OUT))
json.dump(RES, open(os.path.join(H.VALIDADOR_DIR, "r2_bo1h.json"), "w"), indent=1, default=float)
