"""Contraste: mi simulador (riesgo_sim) frente al arnes compartido (harness.py) en una configuracion."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import harness as H
import riesgo_sim as S
for sym in ["BTCUSDT", "DOGEUSDT"]:
    bars = H.load(sym)
    i0, i1 = H.bounds(bars, "design")
    mu, sd = H.rolling_mean(bars.c, 20), H.rolling_std(bars.c, 20)
    A = H.atr(bars.h, bars.l, bars.c, 14, method="sma")
    sig = (bars.c < mu - 2 * sd) & np.isfinite(A)
    sig[i1 - 1 - S.HMAX:] = False
    tr = H.simulate(bars, sig, bars.c + 1.0 * A, bars.c - 2.0 * A, period=(i0, i1), max_hold=48)
    d = S.load(sym); ind = S.indicators(d, (20,))
    cand, NET, XB, RR, KD = S.run_outcomes(d, ind, ("MR", 20, 2.0), [dict(fam="ATR", a=1.0, m=2.0, H=48)], 6000)
    k = S.chain(cand, XB[0])
    print(sym, "harness N=%d WR=%.4f E=%.5f%%" % (len(tr), (tr.net_ret > 0).mean(), tr.net_ret.mean() * 100),
          "| riesgo_sim N=%d WR=%.4f E=%.5f%%" % (len(k), (NET[0, k] > 0).mean(), NET[0, k].mean() * 100))
