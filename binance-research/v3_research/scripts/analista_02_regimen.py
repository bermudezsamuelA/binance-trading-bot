"""Ronda 1 - Paso 2a: ¿hay reversión o persistencia en los retornos? rho(k) y VR(q) (Lo-MacKinlay, robusto a
heterocedasticidad) por moneda, en DISEÑO completo y por semestre. También estacionalidad horaria (t_h, sigma_h)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac
import datetime as dt

def vr_stats(r, q):
    r = r - r.mean()
    T = len(r)
    var1 = (r @ r) / T
    rq = np.convolve(r, np.ones(q), "valid")
    m = q * (T - q + 1) * (1 - q / T)
    varq = (rq @ rq) / m
    vr = varq / var1
    # z robusto (Lo-MacKinlay heteroscedasticity-consistent)
    theta = 0.0
    den = (r @ r) ** 2
    for j in range(1, q):
        dj = (r[j:] ** 2 @ r[:-j] ** 2) * T / den
        theta += (2 * (q - j) / q) ** 2 * dj
    z = (vr - 1) / np.sqrt(theta / T)
    return vr, z

def rho(r, k):
    r = r - r.mean()
    return (r[k:] @ r[:-k]) / (r @ r)

lines = []
P = lambda s: (print(s), lines.append(s))
P("Retornos log de 15m, DISEÑO 2023-01..2025-06. rho(k) y VR(q) con z robusto (|z|>2 significativo)")
for s in ac.SYMS:
    d = ac.load(s)
    r = ac.logret(d["c"])[1:]
    T = len(r)
    se = 1 / np.sqrt(T)
    P(f"\n{s}: T={T}  1/sqrt(T)={se:.4f}")
    P("  rho(1..4) = " + ", ".join(f"{rho(r,k):+.4f}" for k in (1, 2, 3, 4)))
    for q in (2, 4, 8, 16, 48, 96):
        vr, z = vr_stats(r, q)
        P(f"  VR({q:2d}) = {vr:.3f}  z* = {z:+.2f}")
    # por semestre
    t = d["t"][1:]
    yrs = [(2023, 1), (2023, 7), (2024, 1), (2024, 7), (2025, 1)]
    row = []
    for (y, m) in yrs:
        a = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
        b = dt.datetime(y + (m == 7), 1 if m == 7 else 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
        mk = (t >= a) & (t < b)
        rr = r[mk]
        vr4, z4 = vr_stats(rr, 4)
        vr16, z16 = vr_stats(rr, 16)
        row.append(f"{y}-{'S1' if m==1 else 'S2'}: rho1={rho(rr,1):+.3f} VR4={vr4:.3f}({z4:+.1f}) VR16={vr16:.3f}({z16:+.1f})")
    P("  " + "\n  ".join(row))
    # estacionalidad horaria
    hr = ((d["t"][1:] // 3600000) % 24).astype(int)
    tvals = []
    sig = []
    for hh in range(24):
        x = r[hr == hh]
        tvals.append(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        sig.append(x.std(ddof=1))
    tvals = np.array(tvals); sig = np.array(sig)
    P("  t_h por hora UTC: " + " ".join(f"{h}:{tv:+.1f}" for h, tv in enumerate(tvals)))
    P(f"  |t_h|>3 en horas: {[h for h in range(24) if abs(tvals[h])>3]}   sigma_h máx/mín = {sig.max()/sig.min():.2f} "
      f"(máx a las {sig.argmax()}h, mín a las {sig.argmin()}h)")
with open(os.path.join(ac.OUTDIR, "02_regimen.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
