"""riesgo_r2_c1.py - Ronda 2, Gestor de Riesgo: riesgo y dimensionamiento del candidato C1 del Analista
(MR20 z<-2, R>=0.5 %, score ridge h=96 reentrenado mensualmente, compra si score >= Q90), SOLO DISENO.

Periodo evaluable: 2023-10-01 .. 2025-06-30 (los meses previos solo entrenan el ridge). Holdout: no se toca.
Geometrias (las 3 del Analista + UNA variante nueva declarada de antemano):
  T48   : solo salida por tiempo, 48 velas (12 h)
  G2H96 : TP = SMA20, SL = c - 2R, 96 velas
  G3H96 : TP = SMA20, SL = c - 3R, 96 velas
  C48   : (nueva) salida por tiempo a 48 velas + stop de catastrofe SL = c - 3R, sin TP
CRITERIO DE ELECCION (declarado antes de ver resultados): maximizar
  LCB95(E neta con costos 0.30 %) / CVaR95(operacion)
donde LCB95 es el percentil 5 del bootstrap por semanas de E por operacion y CVaR95 la perdida media del 5 %
peor de las operaciones (neto, 0.24 %). Es la ventaja minima creible por unidad de riesgo de cola.
Desempate: menor MDD del Monte Carlo al tamano propuesto.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import harness as Hh
import analista_common as ac
import analista_features as af
import analista_08_candidato as a8
from riesgo_sizing import p_streak

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", "riesgo")
rng = np.random.default_rng(2024)
START, END = Hh.ms(2023, 10, 1), Hh.ms(2025, 7, 1)
WEEK = 7 * 86400000
YEARS = (END - START) / (365.25 * 86400e3)

data = {s: ac.load(s) for s in ac.SYMS}
Fs = {s: af.build(data[s], 20) for s in ac.SYMS}
Fs = af.add_cross(Fs, ac.SYMS)
sc = a8.build_scores(data, Fs, 96)
bars = {s: Hh.load(s) for s in ac.SYMS}

GEOMS = {"T48": (None, 48, False), "G2H96": (2.0, 96, True), "G3H96": (3.0, 96, True), "C48": (3.0, 48, False)}


def run(geom):
    m_sl, H, tpon = GEOMS[geom]
    out = []
    for si, s in enumerate(ac.SYMS):
        b = bars[s]
        msk = sc["S"] == si
        ii, scv, th = sc["I"][msk], sc["score"][msk], sc["thr"][0.9][msk]
        ent = np.zeros(len(b), bool)
        with np.errstate(invalid="ignore"):
            ent[ii[scv >= th]] = True
        mu = Hh.rolling_mean(b.c, 20)
        R = mu - b.c
        tp = mu if tpon else None
        sl = (b.c - m_sl * R) if m_sl else None
        tr = Hh.simulate(b, ent, tp, sl, period=(b.idx(START), b.idx(END)), max_hold=H, risk=None if m_sl else R)
        tr.meta["coin"] = si
        out.append(tr)
    T = Hh.Trades.concat(out)
    coin = np.concatenate([np.full(len(t), i) for i, t in enumerate(out)])
    coin = coin[np.argsort(np.concatenate([t.entry_t for t in out]), kind="stable")]
    return T, coin


def week_boot(x, wk, B=4000, stat="mean"):
    u, inv = np.unique(wk, return_inverse=True)
    groups = [x[inv == k] for k in range(len(u))]
    res = np.empty(B)
    for b in range(B):
        sel = rng.integers(0, len(groups), len(groups))
        v = np.concatenate([groups[k] for k in sel])
        res[b] = v.mean()
    return res


def kelly_w(r):
    from scipy.optimize import minimize_scalar
    hi = -1 / r.min() * 0.999 if r.min() < 0 else 10
    res = minimize_scalar(lambda w: -np.mean(np.log1p(w * r)), bounds=(0, hi), method="bounded")
    return res.x


def mc_portfolio(T, w, n_paths=4000, n_weeks=52):
    """Capital semanal: dentro de una semana las operaciones se SUMAN (simultaneas, tamano fijado con el capital
    del inicio de la semana); entre semanas se compone. Bootstrap de semanas completas (incluye semanas sin operar)."""
    wk = (T.exit_t // WEEK).astype(np.int64)
    weeks = np.arange((START // WEEK), (END // WEEK) + 1)
    wsum = np.array([T.net_ret[wk == k].sum() for k in weeks])
    idx = rng.integers(0, len(weeks), (n_paths, n_weeks))
    eq = np.cumprod(1 + w * wsum[idx], axis=1)
    eq = np.maximum(eq, 1e-9)
    pk = np.maximum.accumulate(np.concatenate([np.ones((n_paths, 1)), eq], 1), axis=1)[:, 1:]
    mdd = (1 - eq / pk).max(1)
    return mdd, eq[:, -1], (eq.min(1) < 0.5), wsum


res = {}
for g in GEOMS:
    T, coin = run(g)
    x = T.net_ret.astype(float)
    gr = T.gross_ret.astype(float)
    x30 = (gr) - 0.0015 * (2 + gr)  # 0.15 % por lado (comision + deslizamiento) => ~0.30 % ida y vuelta
    m = Hh.metrics(T)
    n = len(x)
    wk = (T.entry_t // WEEK).astype(np.int64)
    bs = week_boot(x, wk)
    bs30 = week_boot(x30, wk)
    mon = T.entry_t.astype("datetime64[ms]").astype("datetime64[M]")
    um = np.unique(mon)
    msum = np.array([x[mon == u].sum() for u in um])
    t_mon = msum.mean() / msum.std(ddof=1) * np.sqrt(len(msum))
    q = np.sort(x)
    k5 = max(1, int(round(0.05 * n)))
    cvar95 = -q[:k5].mean()
    q01 = np.quantile(x, 0.01)
    crit = np.quantile(bs30, 0.05) / cvar95
    # concentracion de perdidas: dia UTC de salida
    day = (T.exit_t // 86400000).astype(np.int64)
    ud, dinv = np.unique(day, return_inverse=True)
    dsum = np.bincount(dinv, weights=x)
    dn = np.bincount(dinv)
    worst_days = np.argsort(dsum)[:10]
    loss_total = -x[x < 0].sum()
    # operaciones solapadas de monedas distintas
    o = np.argsort(T.entry_t)
    a_, b_ = [], []
    for i in range(n):
        j = i + 1
        while j < n and T.entry_t[o[j]] < T.exit_t[o[i]]:
            if coin[o[j]] != coin[o[i]]:
                a_.append(x[o[i]]); b_.append(x[o[j]])
            j += 1
    a_, b_ = np.array(a_), np.array(b_)
    rho = np.corrcoef(a_, b_)[0, 1] if len(a_) > 10 else np.nan
    # Kelly en fraccion NOCIONAL w (fraccion del capital invertida por operacion)
    wK = kelly_w(x)
    m2 = np.mean(x ** 2)
    w_lcb = np.quantile(bs, 0.05) / m2
    w_lcb30 = np.quantile(bs30, 0.05) / m2
    risk_med = np.nanmedian(T.risk_pct) if np.isfinite(T.risk_pct).any() else np.nan
    # rachas
    p = (x > 0).mean()
    Ny = int(round(n / YEARS))
    Lseq = x[np.argsort(T.exit_t)] <= 0
    L1 = next(L for L in range(2, 60) if p_streak(L, Ny, 1 - p) < 0.01)
    r = dict(N=n, WR=m["wr"], WR_lo=m["wr_lo"], WR_hi=m["wr_hi"], b_eff=m["b_eff"], E=x.mean() * 100, t=m["t"],
             t_mon=t_mon, months_pos=f"{(msum > 0).sum()}/{len(msum)}", E_R=m["E_R"], R_med=risk_med * 100,
             PF=m["pf"], E30=x30.mean() * 100, t30=x30.mean() / x30.std(ddof=1) * np.sqrt(n),
             LCB=np.quantile(bs, 0.05) * 100, LCB30=np.quantile(bs30, 0.05) * 100, p_le0_30=float(np.mean(bs30 <= 0)),
             q01=q01 * 100, CVaR95=cvar95 * 100, worst=q[0] * 100, crit=crit, E_per_CVaR=x.mean() / cvar95,
             sd=x.std(ddof=1) * 100, Ny=Ny, max_streak=Hh.max_streak(Lseq), L1=L1,
             P5=p_streak(5, Ny, 1 - p), P8=p_streak(8, Ny, 1 - p),
             worst_day=dsum[worst_days[0]] * 100, worst_day_n=int(dn[worst_days[0]]),
             top10_days_loss_share=float(-dsum[worst_days][dsum[worst_days] < 0].sum() / loss_total),
             rho_overlap=rho, both_lose=float(np.mean((a_ < 0) & (b_ < 0))) if len(a_) else np.nan,
             indep_both=float((x <= 0).mean() ** 2), wK=wK, w_lcb=w_lcb, w_lcb30=w_lcb30,
             coins=[float(x[coin == i].mean() * 100) for i in range(4)])
    for w in sorted(set([0.05, 0.10, 0.25, round(wK / 2, 3), round(wK, 3), round(max(w_lcb30, 0) / 4, 3)])):
        if w <= 0:
            continue
        mdd, fin, ruin, wsum = mc_portfolio(T, w)
        r[f"mc_w{w}"] = dict(mdd_med=float(np.median(mdd) * 100), mdd_p95=float(np.percentile(mdd, 95) * 100),
                             p_mdd20=float(np.mean(mdd > 0.2)), ruin=float(ruin.mean()),
                             ret_med=float(np.median(fin) * 100 - 100), ret_p5=float(np.percentile(fin, 5) * 100 - 100))
    r["worst_week_sum"] = float(np.min(wsum) * 100)
    res[g] = r
    print(f"\n=== {g}")
    for k, v in r.items():
        print(f"  {k}: {v if not isinstance(v, float) else round(v, 4)}")

json.dump(res, open(os.path.join(OUT, "r2_c1.json"), "w", encoding="utf-8"), indent=1, default=float)
best = max(res, key=lambda g: res[g]["crit"])
print("\nCriterio LCB95(E @0.30 %)/CVaR95 por geometria:", {g: round(res[g]["crit"], 4) for g in res}, "-> elegida:", best)
Hh.log_trials("riesgo", 1, "R2 C1: variante nueva C48 (tiempo 48 + stop catastrofe c-3R); T48/G2H96/G3H96 ya contadas por el Analista", "design")
