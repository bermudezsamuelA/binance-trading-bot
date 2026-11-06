"""riesgo_r2_extra.py - C1/T48: excursion adversa maxima (MAE) para fijar un stop de catastrofe que no altere la
estrategia, MDD p99 al tamano propuesto, y efecto de reducir el tamano segun posiciones abiertas (regla de riesgo,
no cambia senal ni salidas). Solo DISENO."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import riesgo_r2_c1 as C  # reutiliza scores y run() (re-ejecuta el analisis de C1)
import harness as Hh

T, coin = C.run("T48")
x = T.net_ret.astype(float)
mae = np.empty(len(T))
for k in range(len(T)):
    s = Hh.load(C.ac.SYMS[coin[k]])
    lo = s.l[T.entry_idx[k] + 1:T.exit_idx[k] + 1].min()
    mae[k] = lo / T.entry_px[k] - 1
print(f"MAE T48: mediana {np.median(mae)*100:.2f}%  p95 {np.percentile(mae,5)*100:.2f}%  p99 {np.percentile(mae,1)*100:.2f}%  peor {mae.min()*100:.2f}%")
for w in (0.05, 0.10):
    mdd, fin, ruin, wsum = C.mc_portfolio(T, w, n_paths=20000)
    print(f"w={w}: MDD p50 {np.median(mdd)*100:.1f}% p95 {np.percentile(mdd,95)*100:.1f}% p99 {np.percentile(mdd,99)*100:.1f}%; retorno 1 ano p1 {np.percentile(fin,1)*100-100:+.1f}%")
# posiciones abiertas (otras monedas) al momento de cada entrada
o = np.argsort(T.entry_t)
kopen = np.array([np.sum((T.entry_t < T.entry_t[i]) & (T.exit_t > T.entry_t[i])) for i in range(len(T))])
print("distribucion de k_abiertas al entrar:", np.bincount(kopen, minlength=4)[:5], "E por k:", [round(x[kopen == k].mean() * 100, 3) if (kopen == k).any() else None for k in range(4)])
for rho in (0.0, 0.5):
    w = 0.10 / (1 + kopen * rho)
    day = (T.exit_t // 86400000).astype(np.int64)
    ud, inv = np.unique(day, return_inverse=True)
    dsum = np.bincount(inv, weights=w * x)
    wk = (T.exit_t // C.WEEK).astype(np.int64)
    weeks = np.arange(C.START // C.WEEK, C.END // C.WEEK + 1)
    ws = np.array([(w * x)[wk == k].sum() for k in weeks])
    idx = C.rng.integers(0, len(weeks), (20000, 52))
    eq = np.cumprod(1 + ws[idx], 1)
    pk = np.maximum.accumulate(np.concatenate([np.ones((20000, 1)), eq], 1), 1)[:, 1:]
    mdd = (1 - eq / pk).max(1)
    print(f"rho={rho}: nocional medio {w.mean():.3f}, retorno/ano mediano {np.median(eq[:,-1])*100-100:+.1f}%, peor dia {dsum.min()*100:.2f}% del capital, "
          f"MDD p50 {np.median(mdd)*100:.1f}% p95 {np.percentile(mdd,95)*100:.1f}%, E ponderada por nocional {np.sum(w*x)/np.sum(w)*100:+.3f}%")
