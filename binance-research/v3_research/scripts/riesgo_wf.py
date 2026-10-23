"""riesgo_wf.py - walk-forward anual simple dentro de DISENO sobre la frontera: elegir en el ano t, medir en t+1."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.stats import spearmanr
import riesgo_sim as S
for tf in ["15m", "1h"]:
    rows = [r for r in csv.DictReader(open(os.path.join(S.OUTDIR, f"frontera_{tf}.csv"), encoding="utf-8"))
            if r["entry"] != "RND" and float(r["N"]) >= 200]
    E = np.array([[float(r[f"E_R_{y}"]) for y in (2023, 2024, 2025)] for r in rows])
    ok = np.all(np.isfinite(E), 1)
    E = E[ok]; rows = [r for r, o in zip(rows, ok) if o]
    print(f"[{tf}] configs={len(rows)}  E_R>0 por ano: 2023 {np.mean(E[:,0]>0)*100:.1f}%  2024 {np.mean(E[:,1]>0)*100:.1f}%  2025H1 {np.mean(E[:,2]>0)*100:.1f}%  los 3 anos: {np.mean(np.all(E>0,1))*100:.1f}% ({np.all(E>0,1).sum()})")
    for a, b in [(0, 1), (1, 2)]:
        rho = spearmanr(E[:, a], E[:, b]).correlation
        top = np.argsort(-E[:, a])[:10]
        print(f"   elegir en {2023+a} -> probar en {2023+b}: Spearman {rho:+.2f}; top-10 en {2023+a}: E_R medio {E[top,a].mean():+.3f} -> {E[top,b].mean():+.3f} "
              f"(mediana de todas en {2023+b}: {np.median(E[:,b]):+.3f}); mejor: {rows[top[0]]['entry']} {rows[top[0]]['fam']} {rows[top[0]]['params']} {E[top[0],a]:+.3f}->{E[top[0],b]:+.3f}")
    allpos = np.flatnonzero(np.all(E > 0, 1))
    for i in allpos:
        r = rows[i]
        print(f"   positiva los 3 anos: {r['entry']} {r['fam']} {r['params']} WR={float(r['WR'])*100:.1f} E_R={float(r['E_R']):+.3f} t_mes={float(r['t_month']):+.2f} anos={np.round(E[i],3)}")
