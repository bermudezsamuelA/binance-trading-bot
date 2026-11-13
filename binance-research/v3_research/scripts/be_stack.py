"""Pila combinada en DISENO + % de semanas y meses ganadores + insumos del techo honesto (sigma por operacion, DEFF).
S0 v2 (taker 0.24 %), S1 v2 con BNB (0.075 % + 0.02 % por lado = 0.19 %), S2 v2 + A_model(W=48) >= 1,
S3 = S2 con BNB; todas tambien con estres de 0.30 %."""
import os, sys, json, math
import numpy as np
from scipy.stats import norm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H

D = B.load_ens()
tg = D["cache"]["BTCUSDT"]["t"].astype(np.int64)
jrow = np.searchsorted(tg, D["t"])
sig = D["p"] >= D["thr"]
per = []
for ci_ in range(4):
    m = D["ci"] == ci_
    v = np.zeros(len(tg), bool); v[jrow[m][sig[m]]] = True
    per.append(H.rolling_max(v.astype(float), 48) > 0)
per = np.array(per)
A48 = per.sum(0)[jrow] - per[D["ci"], jrow]


def deff(x, g):
    r = x - x.mean()
    u, inv = np.unique(g, return_inverse=True)
    s = np.bincount(inv, weights=r)
    return float(np.sum(s ** 2) / np.sum(r ** 2))


def period_stats(T, key):
    k = key(T.entry_t)
    u, inv = np.unique(k, return_inverse=True)
    pnl = np.bincount(inv, weights=T.net_ret)
    return int(np.sum(pnl > 0)), len(u)


months_total = len(np.unique(B.month_of(D["t"])))
weeks_total = len(np.unique(D["t"] // (7 * B.DAY)))
lines = ["# Pila combinada en diseno y metricas por periodo\n",
         "| Pila | c ida y vuelta | n | WR % [Wilson] | E % | E_R | t día | σ por op % | DEFF (día) | meses + / con op / total | semanas + / con op | P(mes>0) predicha |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
res = {}
for lab, mask in (("S0 v2", sig), ("S2 v2 + A_model≥1", sig & (A48 >= 1))):
    for cl, fee, slip in (("0.24 %", 0.001, 0.0002), ("0.19 % (BNB)", 0.00075, 0.0002), ("0.30 % (estrés)", 0.0013, 0.0002)):
        T, s = B.simulate_entries(D, mask, fee=fee, slip=slip)
        x = T.net_ret
        m = H.metrics(T)
        day = T.entry_t // B.DAY
        dfx = deff(x, day)
        mp, mt = period_stats(T, lambda t: B.month_of(t))
        wp, wt = period_stats(T, lambda t: t // (7 * B.DAY))
        n_m = len(x) / months_total
        mu, sd = x.mean(), x.std(ddof=1)
        p_month = norm.cdf(mu * n_m / (sd * math.sqrt(n_m * dfx)))
        lines.append(f"| {lab} | {cl} | {len(x)} | {m['wr']*100:.1f} [{m['wr_lo']*100:.1f}, {m['wr_hi']*100:.1f}] | {mu*100:+.2f} | "
                     f"{m['E_R']:+.3f} | {B.cluster_t(x, day):.2f} | {sd*100:.2f} | {dfx:.2f} | {mp} / {mt} / {months_total} | "
                     f"{wp} / {wt} | {p_month*100:.0f} % |")
        res[f"{lab} {cl}"] = dict(n=len(x), wr=m["wr"], E=mu * 100, sd=sd * 100, deff=dfx, months_pos=mp, months_act=mt,
                                  weeks_pos=wp, weeks_act=wt, p_month=p_month, avg_win=float(x[x > 0].mean() * 100),
                                  avg_loss=float(-x[x <= 0].mean() * 100), R_med=m["risk_med_pct"])
        print(lines[-1])
B.log_once("stack", 2, "Pila: BNB 0.19 % y A_model>=1 combinados (diseno; sin parametros nuevos)")
with open(os.path.join(B.OUT, "be_stack.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_stack.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
