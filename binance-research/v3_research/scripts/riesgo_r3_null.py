"""riesgo_r3_null.py - Monte Carlo de DISENO de G3H96 (P2-final, tope 6 %) con la E por operacion desplazada a la
cota usada por el CUSUM y a 0: donde cae el resultado real del holdout (15 meses: -7.42 %, MDD 9.0 %)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "riesgo_r3_p2final.py"), encoding="utf-8").read().split("print(f\"G3H96 N=")[0])
wv, _, _ = sizing(0.03, True, 0.06)
wk = te // WEEK; weeks = np.arange(START // WEEK, END // WEEK + 1)
for lab, shift in (("E de diseno", 0.0), ("E = 0", -x.mean()), ("E = -0.50 %", -x.mean() - 0.005)):
    xx = x + shift
    ws = np.array([(wv * xx)[wk == k].sum() for k in weeks])
    idx = rng.integers(0, len(weeks), (20000, 65))  # 15 meses
    eq = np.cumprod(1 + ws[idx], 1)
    pk = np.maximum.accumulate(np.concatenate([np.ones((20000, 1)), eq], 1), 1)[:, 1:]
    mdd = (1 - eq / pk).max(1)
    print(f"{lab}: 15 meses retorno p5/p50/p95 {np.percentile(eq[:,-1],5)*100-100:+.1f}/{np.median(eq[:,-1])*100-100:+.1f}/{np.percentile(eq[:,-1],95)*100-100:+.1f}%; "
          f"P(ret <= -7.42 %) {np.mean(eq[:,-1] <= 0.9258):.3f}; MDD p50/p95 {np.median(mdd)*100:.1f}/{np.percentile(mdd,95)*100:.1f}%")
