"""Potencia de (a) y (b) para la prueba v2 (8 monedas, 457 dias) a la frecuencia observada en la fase 2. Reservado."""
import math, sys, os
import numpy as np
from scipy import stats
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import wilson
days = 457; yrs = days / 365.25
rng = np.random.default_rng(0)
def pow_b(p, n, deff, sims=20000):
    se = math.sqrt(deff * p * (1 - p) / n)
    ph = np.clip(rng.normal(p, se, sims), 0, 1)
    return float(np.mean([wilson(round(x * n), n)[1] >= 0.70 for x in ph]))
def pow_a(E, sd, n, deff, z=1.645):
    t = E / (sd * math.sqrt(deff / n)); return float(stats.norm.cdf(t - z)), t
for rate, lab in ((51.1, "fase 2 (51/moneda/ano)"), (22.0, "diseno v1 (22/moneda/ano)")):
    n = int(round(8 * yrs * rate))
    print(f"\nfrecuencia {lab}: n esperado = {n}")
    for p in (0.687, 0.72, 0.75, 0.78, 0.80):
        print(f"  (b) WR verdadero {p:.3f}: potencia iid = {pow_b(p, n, 1.0):.2f}, con DEFF 3.08 = {pow_b(p, n, 3.08):.2f}")
    for E, lab2 in ((0.41, "E fase 2"), (0.93, "E diseno v1")):
        pw, t = pow_a(E, 3.79, n, 3.08)
        print(f"  (a) {lab2} {E:+.2f} %, sd 3.79 %, DEFF 3.08: t esperado {t:.2f}, potencia {pw:.2f}")
