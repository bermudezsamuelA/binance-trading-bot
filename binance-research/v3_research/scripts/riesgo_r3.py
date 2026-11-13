"""riesgo_r3.py - Ronda 3 (solo DISENO): (1) potencia de las reglas de prueba (secuencia T48->G3, G3->T48, Holm)
con la correlacion medida entre los estadisticos de T48 y G3H96; (2) G3H96 con el tamano P2
w = min(0.10, 0.015/(lossU/P)): MDD p99, peor dia, rachas, CUSUM; (3) efecto de reducir por k abiertas en G3H96.
No es una configuracion nueva de senal ni de salida (no se registra en trials_log)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import harness as Hh
import analista_common as ac
import analista_features as af
import analista_08_candidato as a8
from riesgo_sizing import p_streak

rng = np.random.default_rng(7)
START, END = Hh.ms(2023, 10, 1), Hh.ms(2025, 7, 1)
WEEK, DAY = 7 * 86400000, 86400000
data = {s: ac.load(s) for s in ac.SYMS}
Fs = af.add_cross({s: af.build(data[s], 20) for s in ac.SYMS}, ac.SYMS)
sc = a8.build_scores(data, Fs, 96)
bars = {s: Hh.load(s) for s in ac.SYMS}
G = {"T48": (None, 48, False), "G3H96": (3.0, 96, True)}

def run(g):
    m_sl, H, tpon = G[g]; out = []
    for si, s in enumerate(ac.SYMS):
        b = bars[s]; msk = sc["S"] == si
        ii, scv, th = sc["I"][msk], sc["score"][msk], sc["thr"][0.9][msk]
        ent = np.zeros(len(b), bool)
        with np.errstate(invalid="ignore"):
            ent[ii[scv >= th]] = True
        mu = Hh.rolling_mean(b.c, 20); R = mu - b.c
        tr = Hh.simulate(b, ent, mu if tpon else None, (b.c - m_sl * R) if m_sl else None,
                         period=(b.idx(START), b.idx(END)), max_hold=H, risk=None if m_sl else R)
        out.append((si, tr))
    return out

res = {g: run(g) for g in G}
# (1) correlacion de los estadisticos: medias diarias de E (por dia UTC de entrada) de ambas geometrias
def daily(trs):
    t = np.concatenate([tr.entry_t for _, tr in trs]); x = np.concatenate([tr.net_ret for _, tr in trs])
    return t // DAY, x
dT, xT = daily(res["T48"]); dG, xG = daily(res["G3H96"])
days = np.union1d(dT, dG)
sT = np.array([xT[dT == d].sum() for d in days]); nT = np.array([(dT == d).sum() for d in days])
sG = np.array([xG[dG == d].sum() for d in days]); nG = np.array([(dG == d).sum() for d in days])
B = 4000; eT = np.empty(B); eG = np.empty(B)
for b in range(B):
    k = rng.integers(0, len(days), len(days))
    eT[b] = sT[k].sum() / nT[k].sum(); eG[b] = sG[k].sum() / nG[k].sum()
rho = np.corrcoef(eT, eG)[0, 1]
print(f"(1) correlacion bootstrap (por dia) entre E_T48 y E_G3: rho = {rho:.3f}")
# potencia con n = 300 en holdout: no-centralidades de preregistro (T48 1.84, G3 1.77) y escenarios 2/3 y 1/2
z = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], 400000)
for frac in (1.0, 2 / 3, 0.5):
    zT = z[:, 0] + 1.84 * frac; zG = z[:, 1] + 1.77 * frac
    seqTG_G = (zT > 1.645) & (zG > 1.645); seqTG_any = zT > 1.645
    seqGT_G = zG > 1.645; seqGT_any = seqGT_G
    zmax = np.maximum(zT, zG)
    holm_any = zmax > 1.96
    holm_G = ((zG > 1.96)) | ((zG > 1.645) & (zT > 1.96))
    holm_T = ((zT > 1.96)) | ((zT > 1.645) & (zG > 1.96))
    print(f"   E real = {frac:.2f}xdiseno: P(aprueba G3) secuencia T48->G3 {seqTG_G.mean():.3f}, G3->T48 {seqGT_G.mean():.3f}, Holm {holm_G.mean():.3f} | "
          f"P(aprueba alguna) {seqTG_any.mean():.3f} / {seqGT_any.mean():.3f} / {(holm_G | holm_T).mean():.3f}")
z0 = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], 400000)
fw = ((np.maximum(z0[:, 0], z0[:, 1]) > 1.96) | ((z0[:, 1] > 1.645) & (z0[:, 0] > 1.96)) | ((z0[:, 0] > 1.645) & (z0[:, 1] > 1.96))).mean()
print(f"   FWER Holm bajo H0 global: {fw:.4f}")

# (2) G3H96 con tamano P2
s = 0.0012
trs = res["G3H96"]
x = np.concatenate([tr.net_ret for _, tr in trs]); P = np.concatenate([tr.entry_px for _, tr in trs])
SL = np.concatenate([tr.sl for _, tr in trs]); te = np.concatenate([tr.exit_t for _, tr in trs])
ti = np.concatenate([tr.entry_t for _, tr in trs])
lossU = (P - SL) + s * (P + SL)
w = np.minimum(0.10, 0.015 / (lossU / P))
print(f"(2) G3H96: lossU/P mediana {np.median(lossU/P)*100:.2f}% p95 {np.percentile(lossU/P,95)*100:.2f}% max {np.max(lossU/P)*100:.2f}%; "
      f"w P2: mediana {np.median(w):.3f}, fraccion con w<0.10: {np.mean(w<0.10):.3f}; peor operacion {x.min()*100:.2f}% (q01 {np.quantile(x,0.01)*100:.2f}%)")
gap = x < -(lossU / P) - 0.001
print(f"   operaciones que perdieron mas que el SL+costos (hueco): {gap.sum()} de {len(x)}; peor exceso {((x + lossU/P)[gap]).min()*100 if gap.any() else 0:.2f} pp")
def mc(wv, n_paths=20000, kscale=None):
    wv = wv.copy()
    if kscale is not None:
        kopen = np.array([np.sum((ti < ti[i]) & (te > ti[i])) for i in range(len(ti))])
        wv = wv / (1 + kscale * kopen)
    wk = te // WEEK; weeks = np.arange(START // WEEK, END // WEEK + 1)
    ws = np.array([(wv * x)[wk == k].sum() for k in weeks])
    idx = rng.integers(0, len(weeks), (n_paths, 52))
    eq = np.cumprod(1 + ws[idx], 1)
    pk = np.maximum.accumulate(np.concatenate([np.ones((n_paths, 1)), eq], 1), 1)[:, 1:]
    mdd = (1 - eq / pk).max(1)
    dsum = np.bincount(np.unique(te // DAY, return_inverse=True)[1], weights=wv * x)
    return mdd, eq[:, -1], dsum.min(), np.sum(wv * x) / np.sum(wv)
for lab, ks, wv in (("P2 sin reduccion", None, w), ("P2 con f/(1+0.4k)", 0.4, w), ("plano w=0.10", None, np.full(len(w), 0.10)),
                    ("P2 con F_RISK 3 %", None, np.minimum(0.10, 0.03 / (lossU / P)))):
    mdd, fin, wd, Ew = mc(wv, kscale=ks)
    print(f"   {lab}: MDD p50 {np.median(mdd)*100:.1f}% p95 {np.percentile(mdd,95)*100:.1f}% p99 {np.percentile(mdd,99)*100:.1f}% "
          f"P(MDD>20%) {np.mean(mdd>0.2):.4f}; peor dia {wd*100:.2f}% del capital; ret 1 ano mediana {np.median(fin)*100-100:+.1f}% p5 {np.percentile(fin,5)*100-100:+.1f}%; E por nocional {Ew*100:+.3f}%")
p = np.mean(x > 0); Ny = int(round(len(x) / ((END - START) / (365.25 * DAY))))
for L in (6, 7, 8, 9, 10):
    print(f"   P(racha >= {L} en {Ny} ops/ano, p={p:.3f}) = {p_streak(L, Ny, 1-p):.4f}")
# CUSUM: P(falsa alarma en 1 ano) si la E real es la de diseno, para la regla sum r < n*E_lcb - 2*sd*sqrt(n), n>=30
sd = x.std(ddof=1); Elcb = 0.0016
fa = 0
for _ in range(4000):
    r = rng.choice(x, Ny)
    cs = np.cumsum(r); n = np.arange(1, Ny + 1)
    fa += np.any((n >= 30) & (cs < n * Elcb - 2 * sd * np.sqrt(n)))
print(f"   CUSUM sd={sd*100:.2f}%: P(falsa alarma en 1 ano | E de diseno) = {fa/4000:.3f}")
xT2 = np.concatenate([tr.net_ret for _, tr in res["T48"]]); sdT = xT2.std(ddof=1); fa = 0
for _ in range(4000):
    r = rng.choice(xT2, 262); cs = np.cumsum(r); n = np.arange(1, 263)
    fa += np.any((n >= 30) & (cs < n * 0.0032 - 2 * sdT * np.sqrt(n)))
print(f"   (T48) CUSUM: P(falsa alarma en 1 ano) = {fa/4000:.3f}")
