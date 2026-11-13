"""Tamanos minimos de muestra del protocolo anti-sobreajuste. Salida: output/validador/sample_size.md
1) n para que el limite inferior de Wilson supere 70 % dado un WR observado (72, 75, 80 %).
2) n para que E > 0 sea significativa con el modelo de dos resultados (gana b*R - c, pierde R + c):
   mu = p b R - (1-p) R - c ;  sigma = (b+1) R sqrt(p(1-p)) ;  n = ((z_{1-a/N} + z_{pot}) sigma / mu)^2
"""
import os
import sys

from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

C = H.COST_RT * 100  # 0.24 (%)
L = ["# Tamanos minimos de muestra", ""]
L += ["## 1. Limite inferior de Wilson > 70 %", "",
      "| WR observado | n (IC bilateral 95 %, z=1.96) | n (unilateral 95 %, z=1.645) | n con Bonferroni N=100 (z=3.29) |", "|---|---|---|---|"]
for p in (0.72, 0.75, 0.80):
    n1 = H.min_n_wilson(p, 0.70, 1.959964)
    n2 = H.min_n_wilson(p, 0.70, 1.644854)
    n3 = H.min_n_wilson(p, 0.70, stats.norm.ppf(1 - 0.05 / 100))
    L.append(f"| {p*100:.0f} % | {n1} | {n2} | {n3} |")
    print("Wilson", p, n1, n2, n3)
L += ["", "## 2. E neta > 0 significativa (unilateral alfa=5 %, potencia 80 %)", "",
      f"Costo c = {C:.2f} % ida y vuelta. R = distancia al SL en % del precio; b = TP/SL.", "",
      "| WR p | b | R % | p* | E neta % | E en R | sigma % | n (N=1) | n (Bonferroni N=100) | n (N=1000) |", "|---|---|---|---|---|---|---|---|---|---|"]
rows = []
for p in (0.72, 0.75, 0.80):
    for b in (0.33, 0.5, 0.75, 1.0):
        for R in (0.5, 1.0, 2.0):
            mu, sd = H.two_outcome_moments(p, b, R, C)
            ps = H.breakeven_p(b, R, C)
            ns = [H.min_n_mean(mu, sd, 0.05, 0.8, N) for N in (1, 100, 1000)]
            f = lambda x: "inf" if x == float("inf") else f"{x:.0f}"  # noqa: E731
            L.append(f"| {p*100:.0f} % | {b} | {R} | {ps*100:.1f} % | {mu:+.3f} | {mu/R:+.3f} | {sd:.3f} | {f(ns[0])} | {f(ns[1])} | {f(ns[2])} |")
            rows.append((p, b, R, ps, mu, sd, ns))
            print(f"p={p} b={b} R={R}: p*={ps:.3f} mu={mu:+.3f}% sd={sd:.3f}% n={[f(x) for x in ns]}")
L += ["", "Lectura: con WR 70-80 % el b tiene que ser < 1 para que sea alcanzable, y entonces el R tiene que ser",
      "grande frente a c (>= 1-2 %) para que E neta sea positiva; las combinaciones con E <= 0 aparecen con n = inf."]
open(os.path.join(H.VALIDADOR_DIR, "sample_size.md"), "w", encoding="utf-8").write("\n".join(L))
