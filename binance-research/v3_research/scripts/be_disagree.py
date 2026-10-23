"""E09 - Desacuerdo del ensamble y calibracion de la cola; E01d - bootstrap por dias de la diferencia de la compuerta
A_model. DISENO, ENS13, X5.
(1) Para cada vela de test: media y desviacion de las 13 probabilidades Platt. Cortes de tercil de la desviacion
    fijados con las senales de VALIDACION de cada pliegue. ¿Las senales con poco desacuerdo ganan mas?
(2) Isotonica (en validacion, sobre la etiqueta X5) frente a Platt (etiqueta G3): brecha de calibracion en la cola.
(3) Bootstrap por bloques de dias de la diferencia E(A_model>=1) - E(A_model=0) en las operaciones v2.
"""
import os, sys, json
import numpy as np
from sklearn.isotonic import IsotonicRegression
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H
R = B.R
C = B.C

D = B.load_ens()
P = [np.load(os.path.join(R.PRED, f"{tg}.npz")) for tg in B.ENS13]
netG3 = P[0]["net"]; yG3 = (netG3 > 0).astype(float)
cache = D["cache"]
netX_all = np.concatenate([cache[s]["net_X5"] for s in H.SYMBOLS])
t_all = P[0]["t"]
sd_t = np.zeros(len(D["p"])); iso_t = np.zeros(len(D["p"]))
off = 0
lines = ["# E09 desacuerdo del ensamble y calibracion de la cola; E01d bootstrap de la compuerta A_model (diseno)\n"]
terc = np.full(len(D["p"]), -1)
calib_rows = []
for k in range(6):
    vr, tr_ = P[0][f"f{k}_val_rows"], P[0][f"f{k}_tst_rows"]
    pv = []; pt = []
    for p in P:
        ab = R.platt_fit(p[f"f{k}_val_s"], yG3[vr])
        pv.append(R.platt_apply(p[f"f{k}_val_s"], ab)); pt.append(R.platt_apply(p[f"f{k}_tst_s"], ab))
    pv, pt = np.array(pv), np.array(pt)
    mv, sv = pv.mean(0), pv.std(0)
    mt, st = pt.mean(0), pt.std(0)
    n = len(tr_)
    assert np.allclose(mt, D["p"][off:off + n])
    sd_t[off:off + n] = st
    thr = D["thr"][off]
    okv = np.isfinite(netX_all[vr]) & (t_all[vr] < t_all[tr_].min() - 289 * C.MS15)
    sel_v = okv & (mv >= thr)
    if sel_v.sum() >= 30:
        q1, q2 = np.quantile(sv[sel_v], [1 / 3, 2 / 3])
        terc[off:off + n] = np.where(st <= q1, 0, np.where(st <= q2, 1, 2))
    # isotonica sobre la etiqueta X5 en validacion
    ir = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(mv[okv], (netX_all[vr][okv] > 0).astype(float))
    iso_t[off:off + n] = ir.predict(mt)
    off += n
sig = D["p"] >= D["thr"]
okx = np.isfinite(D["netX"])
lines += ["## (1) Desacuerdo entre los 13 modelos (desviacion de las probabilidades), senales v2, resultado por vela\n",
          "| Tercil de desacuerdo | velas | dias | WR vela % | E vela % |", "|---|---|---|---|---|"]
for tt, nm in ((0, "T1 (poco desacuerdo)"), (1, "T2"), (2, "T3 (mucho desacuerdo)")):
    s = sig & okx & (terc == tt)
    lines.append(f"| {nm} | {s.sum()} | {len(np.unique(D['day'][s]))} | {np.mean(D['netX'][s]>0)*100:.1f} | {np.mean(D['netX'][s])*100:+.2f} |")
corr = np.corrcoef(sd_t[sig], D["p"][sig])[0, 1]
lines.append(f"\nCorrelacion desacuerdo vs p_hat en las senales: {corr:+.2f} (si es alta, filtrar por desacuerdo corta las mejores senales).\n")
lines += list(B.MD_HEAD)
res = {}
for lab, m in (("v2", sig), ("v2 y desacuerdo en T1-T2 (abstenerse en T3)", sig & (terc <= 1)),
               ("v2 y desacuerdo en T1", sig & (terc == 0))):
    T, s = B.simulate_entries(D, m)
    r = B.summarize_trades(T, s, D, label=lab)
    lines.append(B.md_row(r)); print(B.fmt(r)); res[lab] = r
# (2) calibracion de la cola
lines += ["\n## (2) Calibracion en la cola (todas las velas de test, resultado X5 por vela)\n",
          "| Cuantil de p_hat | velas | p_hat Platt medio (etiqueta G3) | isotonica X5 media | WR X5 realizado % |", "|---|---|---|---|---|"]
qs = np.quantile(D["p"][okx], [0.9, 0.95, 0.98, 0.99, 0.995, 1.0])
for a, b in zip(qs[:-1], qs[1:]):
    s = okx & (D["p"] >= a) & (D["p"] < b if b < qs[-1] else D["p"] <= b)
    lines.append(f"| [{a:.3f}, {b:.3f}] | {s.sum()} | {D['p'][s].mean():.3f} | {iso_t[s].mean():.3f} | {np.mean(D['netX'][s]>0)*100:.1f} |")
for thr_iso in (0.80, 0.85):
    T, s = B.simulate_entries(D, iso_t >= thr_iso)
    r = B.summarize_trades(T, s, D, label=f"isotonica X5 >= {thr_iso} (sin umbral v2)")
    lines.append("\n" + "\n".join(B.MD_HEAD) + "\n" + B.md_row(r)); print(B.fmt(r)); res[r["label"]] = r
# (3) bootstrap por dias de la diferencia de la compuerta A_model W=48
tg = cache["BTCUSDT"]["t"].astype(np.int64)
jrow = np.searchsorted(tg, D["t"])
per = []
for ci_ in range(4):
    m = D["ci"] == ci_
    v = np.zeros(len(tg), bool); v[jrow[m][sig[m]]] = True
    per.append(H.rolling_max(v.astype(float), 48) > 0)
per = np.array(per)
A48 = per.sum(0)[jrow] - per[D["ci"], jrow]
T, s = B.simulate_entries(D, sig)
rowmap = {(H.SYMBOLS.index(ss), int(i)): k for k, (ss, i) in enumerate(zip(s, T.sig_idx))}
gA = np.zeros(len(T), bool)
for r_ in np.flatnonzero(sig):
    key = (int(D["ci"][r_]), int(D["ii"][r_]))
    if key in rowmap:
        gA[rowmap[key]] = A48[r_] >= 1
x = T.net_ret; day = T.entry_t // B.DAY
ud = np.unique(day)
rng = np.random.default_rng(7)
diffs, dwr = [], []
for _ in range(5000):
    pick = rng.choice(ud, len(ud), replace=True)
    idx = np.concatenate([np.flatnonzero(day == d) for d in pick])
    a, b_ = idx[gA[idx]], idx[~gA[idx]]
    if len(a) and len(b_):
        diffs.append(x[a].mean() - x[b_].mean()); dwr.append(np.mean(x[a] > 0) - np.mean(x[b_] > 0))
diffs, dwr = np.array(diffs) * 100, np.array(dwr) * 100
lines.append(f"\n## (3) Bootstrap por dias (5000) de la compuerta A_model W=48 sobre las 188 operaciones v2\n\n"
             f"- E(A>=1) - E(A=0) = {(x[gA].mean()-x[~gA].mean())*100:+.2f} % ; IC 95 % [{np.percentile(diffs,2.5):+.2f}, {np.percentile(diffs,97.5):+.2f}] ; P(dif <= 0) = {np.mean(diffs<=0):.3f}\n"
             f"- WR(A>=1) - WR(A=0) = {(np.mean(x[gA]>0)-np.mean(x[~gA]>0))*100:+.1f} pt ; IC 95 % [{np.percentile(dwr,2.5):+.1f}, {np.percentile(dwr,97.5):+.1f}] ; P(dif <= 0) = {np.mean(dwr<=0):.3f}\n"
             f"- n(A>=1) = {gA.sum()} en {len(np.unique(day[gA]))} dias; n(A=0) = {(~gA).sum()} en {len(np.unique(day[~gA]))} dias")
print(lines[-1])
B.log_once("disagree", 4, "E09 desacuerdo T1-T2 y T1, isotonica X5 >= {0.80,0.85} (diseno); bootstrap A_model sin config nueva")
with open(os.path.join(B.OUT, "be_disagree.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_disagree.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
