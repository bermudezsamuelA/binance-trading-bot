"""riesgo_r3_p2final.py - Ronda 3: Monte Carlo de DISENO (bootstrap por semanas) de la regla P2-final en G3H96:
w_i = min(0.10, 0.03/(lossU_i/P_i)); Q_i = max(lossU_i/P_i + 0.02, 0.15); nocional total <= 0.40; sum w*Q <= 6 %
(los topes se aplican en orden cronologico reduciendo w al presupuesto restante; si queda < 0.01 se omite)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import harness as Hh
import analista_common as ac
import analista_features as af
import analista_08_candidato as a8

rng = np.random.default_rng(7)
START, END = Hh.ms(2023, 10, 1), Hh.ms(2025, 7, 1)
WEEK, DAY = 7 * 86400000, 86400000
data = {s: ac.load(s) for s in ac.SYMS}
Fs = af.add_cross({s: af.build(data[s], 20) for s in ac.SYMS}, ac.SYMS)
sc = a8.build_scores(data, Fs, 96)
xs, Ps, SLs, tis, tes = [], [], [], [], []
for si, s in enumerate(ac.SYMS):
    b = Hh.load(s); msk = sc["S"] == si
    ii, scv, th = sc["I"][msk], sc["score"][msk], sc["thr"][0.9][msk]
    ent = np.zeros(len(b), bool)
    with np.errstate(invalid="ignore"):
        ent[ii[scv >= th]] = True
    mu = Hh.rolling_mean(b.c, 20); R = mu - b.c
    tr = Hh.simulate(b, ent, mu, b.c - 3.0 * R, period=(b.idx(START), b.idx(END)), max_hold=96)
    xs.append(tr.net_ret); Ps.append(tr.entry_px); SLs.append(tr.sl); tis.append(tr.entry_t); tes.append(tr.exit_t)
x, P, SL, ti, te = map(np.concatenate, (xs, Ps, SLs, tis, tes))
o = np.argsort(ti, kind="stable"); x, P, SL, ti, te = x[o], P[o], SL[o], ti[o], te[o]
s = 0.0012
lu = ((P - SL) + s * (P + SL)) / P
Q = np.maximum(lu + 0.02, 0.15)

def sizing(F, caps, TC=0.06):
    w = np.minimum(0.10, F / lu)
    if not caps:
        return w, 0, 0
    wf = np.zeros(len(w)); cut = skip = 0
    for i in range(len(w)):
        op = (np.arange(len(w)) < i) & (te > ti[i]) & (wf > 0)
        not_left = 0.40 - wf[op].sum(); tail_left = TC - (wf[op] * Q[op]).sum()
        wi = min(w[i], not_left, tail_left / Q[i])
        if wi < 0.01:
            skip += 1; continue
        cut += wi < w[i] - 1e-12
        wf[i] = wi
    return wf, cut, skip

def mc(wv, n_paths=20000):
    wk = te // WEEK; weeks = np.arange(START // WEEK, END // WEEK + 1)
    ws = np.array([(wv * x)[wk == k].sum() for k in weeks])
    idx = rng.integers(0, len(weeks), (n_paths, 52))
    eq = np.cumprod(1 + ws[idx], 1)
    pk = np.maximum.accumulate(np.concatenate([np.ones((n_paths, 1)), eq], 1), 1)[:, 1:]
    mdd = (1 - eq / pk).max(1)
    dsum = np.bincount(np.unique(te // DAY, return_inverse=True)[1], weights=wv * x)
    return mdd, eq[:, -1], dsum.min()

print(f"G3H96 N={len(x)}; Q_i: mediana {np.median(Q):.3f}, fraccion en el piso 0.15: {np.mean(Q==0.15):.3f}")
for lab, F, caps in (("F_RISK 3 % sin topes", 0.03, False), ("P2-final (F 3 %, Q=max(lu+0.02,0.15), topes 0.40 y 6 %)", 0.03, True),
                     ("F_RISK 1.5 % con los mismos topes", 0.015, True), ("F 3 %, tope de cola 8 %", 0.03, 0.08), ("F 3 %, tope de cola 10 %", 0.03, 0.10)):
    wv, cut, skip = sizing(F, bool(caps), caps if isinstance(caps, float) else 0.06)
    mdd, fin, wd = mc(wv)
    tail = np.array([(wv[:i+1][te[:i+1] > ti[i]] * Q[:i+1][te[:i+1] > ti[i]]).sum() for i in range(len(x))])
    print(f"{lab}: recortadas {cut}, omitidas {skip}; nocional medio {wv[wv>0].mean():.3f}; E por nocional {np.sum(wv*x)/np.sum(wv)*100:+.3f}%; "
          f"riesgo de cola abierto max {tail.max()*100:.2f}%; MDD p50 {np.median(mdd)*100:.1f}% p95 {np.percentile(mdd,95)*100:.1f}% "
          f"p99 {np.percentile(mdd,99)*100:.1f}%; peor dia {wd*100:.2f}%; ret 1 ano mediana {np.median(fin)*100-100:+.1f}% [p5 {np.percentile(fin,5)*100-100:+.1f}%]")
