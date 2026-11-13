"""Tamanos de muestra para los criterios pre-registrados (a) y (b). Solo teoria; no usa datos reservados."""
import math, sys, os
import numpy as np
from scipy import stats
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import wilson
def n_wilson_obs(p, p0=0.70):
    for n in range(10, 200000):
        if wilson(round(p * n), n)[1] >= p0 and wilson(math.floor(p * n), n)[1] >= p0:
            return n
def n_wilson_power(p, p0=0.70, power=0.8):
    lo_n, hi_n = 10, 200000
    def pw(n):
        k = np.arange(n + 1); ok = np.array([wilson(int(x), n)[1] >= p0 for x in k[int(p0 * n):]])
        kmin = int(p0 * n) + int(np.argmax(ok)) if ok.any() else n + 1
        return stats.binom.sf(kmin - 1, n, p)
    for n in list(range(20, 3000, 5)) + list(range(3000, 60000, 100)):
        if pw(n) >= power:
            return n
print("(b) Wilson: n minimo")
print("WR | n con WR observado = WR | n con potencia 80 % si WR verdadero = WR")
for p in (0.72, 0.73, 0.75, 0.78, 0.80):
    print(f"{p:.2f} | {n_wilson_obs(p)} | {n_wilson_power(p)}")
z1, z2, DEFF = 1.645, 0.8416, 1.5
print("\n(a) E>0 con t_dia>1.645: modelo de dos resultados con ventaja dp sobre el azar de la misma geometria")
print("p | dp | b | R% | c% | mu% | sigma% | n(50%)xDEFF | n(80%)xDEFF")
for p in (0.75, 0.80):
    for dp in (0.05, 0.10, 0.15):
        b = 1 / (p - dp) - 1
        for R in (0.01, 0.02, 0.04, 0.065):
            for c in (0.0024, 0.0030):
                mu = R * (p * (1 + b) - 1) - c
                sg = R * (1 + b) * math.sqrt(p * (1 - p))
                if mu <= 0:
                    print(f"{p} | {dp} | {b:.2f} | {R*100:.1f} | {c*100:.2f} | {mu*100:+.3f} | {sg*100:.2f} | E<=0 | E<=0"); continue
                n50 = (z1 * sg / mu) ** 2 * DEFF; n80 = ((z1 + z2) * sg / mu) ** 2 * DEFF
                print(f"{p} | {dp} | {b:.2f} | {R*100:.1f} | {c*100:.2f} | {mu*100:+.3f} | {sg*100:.2f} | {n50:.0f} | {n80:.0f}")
days = (np.datetime64("2026-10-01") - np.datetime64("2025-07-01")).astype(int)
print("\nperiodo primario:", days, "dias,", days * 96, "velas 15m por moneda, 6 monedas ->", 6 * days * 96, "velas")
for rate in (30, 60, 120, 250):
    print(f"  a {rate} ops/moneda/ano -> {rate * 6 * days / 365.25:.0f} operaciones")
