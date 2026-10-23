"""Ronda 3: potencia de Holm (FWER 0.05) frente a secuencias fijas para E>0 de G3H96 y T48 (solo DISENO).
rho entre los dos t agrupados por dia se estima con los residuos diarios del OOS de diseno."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
import C1_eval as C
s, e = H.ms(2023, 10, 1), H.DESIGN[1]
bars, data = C.load_until(e, None, s)
Fs = C.af.add_cross({x: C.af.build(data[x], 20) for x in C.SYMS}, list(C.SYMS))
ST = C.signal_table(data, Fs)
take, _, _, _ = C.scores(ST, s, e)
T = {g: H.Trades.concat(C.simulate_all(bars, data, ST, take, s, e, k)) for g, k in (("G3", "PRIMARIA_G3H96"), ("T48", "SECUNDARIA_T48"))}
res, info = {}, {}
for g, t in T.items():
    x = t.net_ret; d = t.entry_t // 86400000
    u, inv = np.unique(d, return_inverse=True)
    r = np.bincount(inv, weights=x - x.mean())
    res[g] = dict(zip(u, r)); info[g] = (len(x), x.mean(), x.std(ddof=1), np.sqrt((r ** 2).sum()) / len(x))
days = sorted(set(res["G3"]) | set(res["T48"]))
a = np.array([res["G3"].get(k, 0.0) for k in days]); b = np.array([res["T48"].get(k, 0.0) for k in days])
rho = (a * b).sum() / np.sqrt((a ** 2).sum() * (b ** 2).sum())
print(f"rho entre estimadores (agrupado por dia) = {rho:.2f}")
rng = np.random.default_rng(0)
n_h = 300
for frac in (1.0, 2 / 3, 0.5):
    ncp = {}
    for g, (n, mu, sd, se) in info.items():
        deff = (se / (sd / np.sqrt(n))) ** 2
        ncp[g] = mu * frac / (sd * np.sqrt(deff / n_h))
    Z = rng.multivariate_normal([ncp["G3"], ncp["T48"]], [[1, rho], [rho, 1]], 200000)
    zg, zt = Z[:, 0], Z[:, 1]
    hi, lo = np.maximum(zg, zt), np.minimum(zg, zt)
    any_ = hi > 1.960
    both = any_ & (lo > 1.645)
    g_holm = (zg > 1.960) | (any_ & (zg > 1.645))
    t_holm = (zt > 1.960) | (any_ & (zt > 1.645))
    print(f"E real = {frac:.2f}xE diseno (n={n_h}; ncp G3 {ncp['G3']:.2f}, T48 {ncp['T48']:.2f}): "
          f"HOLM: aprueba G3 {g_holm.mean()*100:.0f} %, T48 {t_holm.mean()*100:.0f} %, alguna {any_.mean()*100:.0f} % | "
          f"SECUENCIA G3->T48: G3 {(zg>1.645).mean()*100:.0f} %, T48 {((zg>1.645)&(zt>1.645)).mean()*100:.0f} % | "
          f"SECUENCIA T48->G3: T48 {(zt>1.645).mean()*100:.0f} %, G3 {((zt>1.645)&(zg>1.645)).mean()*100:.0f} %")
