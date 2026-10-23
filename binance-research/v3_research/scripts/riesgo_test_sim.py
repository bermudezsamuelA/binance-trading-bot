"""Pruebas minimas del simulador (casos a mano + martingala sin deriva)."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
import numpy as np
import riesgo_sim as S
# Caso a mano: entrada 100 en i=0, ATR=1. Vela1: H=100.5 L=99.6; Vela2: H=101.2 L=98.9 (toca TP=101 y SL=99 -> SL)
d = dict(o=np.array([100, 100, 100.4, 97.0, 100.]), h=np.array([100, 100.5, 101.2, 97.5, 100.]),
         l=np.array([100, 99.6, 98.9, 96.0, 100.]), c=np.array([100, 100.2, 99.5, 97.2, 100.]))
F = S.Fwd(d, np.array([0]), 3)
px, col, k = S.sim_barrier(F, np.array([100.]), np.array([101.]), np.array([99.]), 3)
print("empate TP/SL -> SL:", px, col, k)            # esperado 99, col 1, -1
px, col, k = S.sim_barrier(F, np.array([100.]), np.array([102.]), np.array([98.]), 3)
print("gap bajo SL -> apertura:", px, col, k)       # vela3 abre 97 < 98 -> 97, col 2
px, col, k = S.sim_barrier(F, np.array([100.]), np.array([110.]), np.array([90.]), 3)
print("tiempo -> cierre vela H:", px, col, k)       # 97.2, col 2, 0
# Martingala: paseo aleatorio en log sin deriva, velas con 20 subpasos
rng = np.random.default_rng(1)
n, sub = 60000, 20
x = np.cumsum(rng.normal(0, 0.001, n * sub)).reshape(n, sub)
P = 100 * np.exp(x)
d = dict(o=np.r_[100, P[:-1, -1]], h=P.max(1), l=P.min(1), c=P[:, -1])
d["h"] = np.maximum(d["h"], d["o"]); d["l"] = np.minimum(d["l"], d["o"])
d["t"] = np.arange(n) * 900000.0
A = S.atr(d)
idx = np.arange(20, n - 200, 7)
F = S.Fwd(d, idx, 96)
for a, m in [(0.5, 2.0), (1, 1), (2, 1)]:
    px, col, k = S.sim_barrier(F, d["c"][idx], d["c"][idx] + a * A[idx], d["c"][idx] - m * A[idx], 96)
    g = (px / d["c"][idx] - 1) / (m * A[idx] / d["c"][idx])
    print(f"a={a} m={m}: p(TP)={np.mean(k==1):.3f} (cont. m/(a+m)={m/(a+m):.3f}), E_bruta en R={g.mean():+.4f}")
