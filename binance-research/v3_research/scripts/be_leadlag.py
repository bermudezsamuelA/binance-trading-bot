"""E25 - Posicion de la moneda dentro del panico del universo (rezago relativo), prueba de informacion barata.
rel_k = z de la caida de la moneda en k velas menos la media transversal de las 18 monedas (z en sigma propia).
¿Las senales v2 de monedas que caen MAS que el mercado (rel muy negativo: idiosincratico) ganan menos, y las que
caen MENOS o ya se rezagan del rebote ganan mas? Cortes de tercil fijados con las senales de validacion. DISENO."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H
C = B.C

D = B.load_ens()
tg = D["cache"]["BTCUSDT"]["t"].astype(np.int64)
P0 = np.load(os.path.join(B.R.PRED, f"{B.ENS13[0]}.npz"))
names = list(H.SYMBOLS) + B.OTHER18
Z = {4: [], 16: []}
for s in names:
    p = os.path.join(B.RESEARCH, "klines", f"{s}_15m.npy")
    if not os.path.exists(p):
        p = os.path.join(B.RESEARCH, "verificador", "data", f"{s}_15m.npy")
    a = np.load(p); a = a[a[:, 0] < H.DESIGN[1]]
    c = a[:, 4]; lr = H.log_returns(c); s15 = H.rolling_std(np.nan_to_num(lr), 672); lc = np.log(c)
    j = np.minimum(np.searchsorted(a[:, 0], tg), len(a) - 1); ok = a[j, 0] == tg
    for k in Z:
        z = (lc - H.shift(lc, k)) / (s15 * np.sqrt(k))
        Z[k].append(np.where(ok, z[j], np.nan))
rel_t = {k: None for k in Z}
for k in Z:
    M = np.array(Z[k])
    cs = np.nanmean(M, 0)
    rel_t[k] = (M[:4] - cs[None, :])       # 4 monedas de diseno


def rel_rows(k, ci, ii):
    tt = P0["t"] if False else None
    return rel_t[k][ci, ii]


sig = D["p"] >= D["thr"]
okx = np.isfinite(D["netX"])
lines = ["# E25 rezago relativo dentro del panico del universo (diseno, ENS13, X5)\n",
         "| Variable | T1 (cae más que el mercado) velas / WR % / E % | T2 | T3 (cae menos que el mercado) |", "|---|---|---|---|"]
res = {}
for k in (4, 16):
    v = rel_t[k][D["ci"], D["ii"]]
    terc = np.full(len(v), -1)
    for f in range(6):
        V = D["vals"][f]
        sv = V["p"] >= V["thr"]
        rv = rel_t[k][P0["ci"][V["rows"][sv]], P0["ii"][V["rows"][sv]]]
        rv = rv[np.isfinite(rv)]
        q1, q2 = np.quantile(rv, [1 / 3, 2 / 3])
        fm = D["fold"] == f
        terc[fm] = np.where(~np.isfinite(v[fm]), -1, np.where(v[fm] <= q1, 0, np.where(v[fm] <= q2, 1, 2)))
    cells = []
    for tt in (0, 1, 2):
        s = sig & okx & (terc == tt)
        cells.append(f"{s.sum()} / {np.mean(D['netX'][s]>0)*100:.1f} / {np.mean(D['netX'][s])*100:+.2f}")
    lines.append(f"| rel_{k} | " + " | ".join(cells) + " |")
    res[f"rel_{k}"] = cells
print("\n".join(lines))
B.log_once("leadlag", 2, "E25 rezago relativo rel_4, rel_16: gradiente por tercil (diseno, descriptivo)")
with open(os.path.join(B.OUT, "be_leadlag.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
