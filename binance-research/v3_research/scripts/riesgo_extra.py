"""riesgo_extra.py - umbrales de racha (P<1 %/ano), N necesario para detectar E, Kelly de un sistema WR 75 %."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from riesgo_sizing import p_streak
for name, p, Ny in [("1h CHAN m=3 (WR 42 %)", 0.420, 194), ("1h ATR a=1.5 m=4 (WR 74.7 %)", 0.747, 350), ("15m BOT_MR n=20 k=2 (WR 48.6 %)", 0.486, 2292)]:
    L = next(L for L in range(2, 80) if p_streak(L, Ny, 1 - p) < 0.01)
    print(f"{name}: racha de perdidas con P<1 % en un ano ({Ny} ops) = {L}")
print("Sistema hipotetico WR=75 %, pagos netos +b / -1:")
for E in [0.02, 0.05, 0.10]:
    p = 0.75; b = (E + (1 - p)) / p
    sd = np.sqrt(p * b * b + (1 - p) - E * E)
    fK = p - (1 - p) / b
    print(f"  E={E:+.2f}R -> b_neto={b:.3f}, Kelly f*={fK:.3f}, sigma_X={sd:.3f}, N para t=2: {(2*sd/E)**2:.0f}, N para t=4.18 (Bonferroni 3447): {(4.18*sd/E)**2:.0f}")
rho = 0.4
for k in range(4):
    print(f"  posiciones abiertas k={k}: f_nueva = f_base/(1+k*rho) = {1/(1+k*rho):.3f} f_base; calor total = {sum(1/(1+j*rho) for j in range(k+1)):.2f} f_base")
print("N_eff 4 monedas: rho=0.4 ->", round(4 / (1 + 3 * 0.4), 2), "; rho=0.7 ->", round(4 / (1 + 3 * 0.7), 2))
