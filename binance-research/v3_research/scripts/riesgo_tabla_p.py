"""riesgo_tabla_p.py - (a) R/c necesario para E>0 con WR objetivo; (b) probabilidades de primer paso medidas vs
martingala y p* con costos; (c) E por tramo de c/R; (d) efecto del redondeo round(x,2) en DOGE."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import riesgo_sim as S

print("(a) R/c minimo para E>0:  E/R = p(1+b) - 1 - c/R  =>  R/c > 1/(p(1+b)-1)")
print("      b:   " + "  ".join(f"{b:>6.2f}" for b in [0.25, 1/3, 0.43, 0.5, 0.75, 1.0]))
for p in [0.70, 0.75, 0.80]:
    cells = []
    for b in [0.25, 1/3, 0.43, 0.5, 0.75, 1.0]:
        e = p * (1 + b) - 1
        cells.append(f"{1/e:6.1f}" if e > 0 else "   inf")
    print(f"  p={p:.2f}: " + "  ".join(cells))
print("  con c=0.24 %: R/c=8 -> R=1.92 %; R/c=20 -> R=4.8 %. Mediana ATR14 15m: BTC 0.27 %, ETH 0.35 %, SOL 0.60 %, DOGE 0.53 %")

print("\n(b) Primer paso (H=96 velas), geometrias con p_martingala=m/(a+m) en [0.70,0.80]")
for tf in ["15m", "1h"]:
    rows = list(csv.DictReader(open(os.path.join(S.OUTDIR, f"frontera_{tf}.csv"), encoding="utf-8")))
    for r in rows:
        if r["fam"] != "ATR" or not r["params"].endswith("H=96"):
            continue
        a, m = [float(x.split("=")[1]) for x in r["params"].split(";")[:2]]
        p0 = m / (a + m)
        if not (0.70 <= p0 <= 0.80) or r["entry"] not in ("RND", "MR(n=48,k=2.0)", "BO(n=96,k=2.5)", "MR(n=96,k=2.5)"):
            continue
        N, ptp, cR = float(r["N"]), float(r["tp_rate"]), float(r["cR_med"])
        b = a / m
        pst = (1 + cR) / (1 + b)
        z = (ptp - pst) / np.sqrt(ptp * (1 - ptp) / N)
        print(f"  {tf} {r['entry']:<15} a={a:<4} m={m:<3} b={b:.2f} p0={p0:.3f} P(TP 1o)={ptp:.3f} "
              f"(sl {float(r['sl_rate']):.3f}) c/R={cR:.2f} p*={pst:.3f} margen={ptp-pst:+.3f} z={z:+.1f} WRneto={float(r['WR']):.3f} E_R={float(r['E_R']):+.3f} N={N:.0f}")

print("\n(c) E por quintil de c/R (15m, ATR a=1,m=3,H=48)")
DS = S.datasets(1)
for entry in [("RND", 0, 0), ("MR", 48, 2.0), ("BO", 96, 2.5)]:
    tr = S.pooled_trades(DS, entry, [dict(fam="ATR", a=1.0, m=3.0, H=48)], 4000)[0]
    cR = S.C_RT / tr["R"]
    X = tr["net"] / tr["R"]
    q = np.quantile(cR, [0, .2, .4, .6, .8, 1])
    out = []
    for i in range(5):
        mk = (cR >= q[i]) & (cR <= q[i + 1])
        out.append(f"c/R {q[i]:.2f}-{q[i+1]:.2f}: E_R {X[mk].mean():+.3f} bruto {(X[mk]+cR[mk]).mean():+.3f}")
    print(f"  {entry}: " + " | ".join(out))

print("\n(d) DOGE: TrendFollowing n=24 k=0.8 (config en vivo) con round(TP,2)/round(SL,2) en 15m de diseno")
d = S.load("DOGEUSDT")
mu, sd = S.roll_mean_std(d["c"], 24)
P = d["c"]
sig = np.flatnonzero(P > mu + 0.8 * sd)
R = P[sig] - mu[sig]
tp, sl = P[sig] + 2 * R, mu[sig]
tpr, slr = np.round(tp, 2), np.round(sl, 2)
inst = (tpr <= P[sig]) | (slr >= P[sig])
Rr = (P[sig] - slr) / P[sig]
print(f"  senales {len(sig)}; R real mediano {np.median(R/P[sig])*100:.2f} %; con redondeo: TP<=entrada o SL>=entrada en {inst.mean()*100:.1f} %"
      f"; R redondeado mediano {np.median(Rr[~inst])*100:.2f} % ; b redondeado mediano {np.median(((tpr-P[sig])/(P[sig]-slr))[~inst]):.2f} (deberia ser 2)")
