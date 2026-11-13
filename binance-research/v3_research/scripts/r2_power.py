"""Ronda 2 (Validador): potencia de la prueba unica en HOLDOUT para C1 (solo datos de DISENO).
Usa las operaciones OOS de C1 en DISENO (2023-10..2025-06) para estimar sigma por operacion, el efecto de
diseno por agrupamiento diario (DEFF = (t_iid / t_cluster_dia)^2), y calcula:
  * potencia de H1 (E neta > 0, t agrupado por dia, unilateral alfa = 0.05) con n = 200 / 300 / 400,
    si E real = E de diseno, 2/3 de ella o la mitad (maldicion del ganador);
  * P(poder afirmar WR >= 70 %) = P(limite inferior de Wilson >= 0.70) si el WR real es el de diseno;
  * semiancho del IC de Wilson con n = 300.
Salida: output/validador/r2_power.txt
"""
import os
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r2_audit_c1 as A  # noqa: E402  (reconstruye C1 en DISENO; no toca el holdout)
import harness as H  # noqa: E402

OUT = []


def P(s=""):
    print(s, flush=True)
    OUT.append(s)


def t_cluster(x, key):
    n, mu = len(x), x.mean()
    u = np.unique(key)
    resid = np.array([(x[key == k] - mu).sum() for k in u])
    se = np.sqrt((resid ** 2).sum()) / n * np.sqrt(len(u) / (len(u) - 1))
    return mu / se


P("\n\n#################### POTENCIA DE LA PRUEBA EN HOLDOUT ####################")
for g in ("T48", "G2H96", "G3H96"):
    T, m = A.base[g]
    x = T.net_ret
    t_iid = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    t_day = t_cluster(x, T.entry_t // 86_400_000)
    deff = (t_iid / t_day) ** 2
    sd = x.std(ddof=1)
    months = 21
    P(f"\n{g}: n diseno OOS = {len(x)} ({len(x)/months:.1f}/mes; 2025-S1: {len(T.between(H.ms(2025,1), H.DESIGN[1]))/6:.1f}/mes), "
      f"E = {x.mean()*100:+.3f} %, sigma = {sd*100:.2f} %, WR = {m['wr']*100:.1f} %, t_iid = {t_iid:.2f}, t_dia = {t_day:.2f}, DEFF = {deff:.2f}")
    for n in (200, 300, 400):
        row = []
        for frac in (1.0, 2 / 3, 0.5):
            mu = x.mean() * frac
            ncp = mu / (sd * np.sqrt(deff / n))
            pw = 1 - stats.norm.cdf(1.645 - ncp)
            row.append(f"E real {frac:.2f}xE ({mu*100:+.2f} %): potencia {pw*100:4.0f} %")
        p = m["wr"]
        # WR observado minimo para que el limite inferior de Wilson (95 % bilateral) sea >= 0.70 con n operaciones
        kmin = next(k for k in range(n + 1) if H.wilson(k, n)[1] >= 0.70)
        se_wr = np.sqrt(p * (1 - p) / n * deff)
        p_claim = 1 - stats.norm.cdf((kmin / n - p) / se_wr)
        half = (H.wilson(p * n, n)[2] - H.wilson(p * n, n)[1]) / 2
        P(f"  n={n}: " + "; ".join(row) + f" | WR observado minimo para afirmar WR>=70 %: {kmin/n*100:.1f} % "
          f"-> P(afirmarlo | WR real {p*100:.1f} %) = {p_claim*100:.0f} %; semiancho IC Wilson = {half*100:.1f} pp")
open(os.path.join(H.VALIDADOR_DIR, "r2_power.txt"), "w", encoding="utf-8").write("\n".join(OUT))
