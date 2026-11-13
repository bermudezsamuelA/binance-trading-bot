"""E01c - Amplitud con CAPITULACIONES DE PRECIO en un universo de 18 monedas (medible en vivo y para cualquier
universo, sin el modelo). Una vela de capitulacion (patron que aprendio el ensamble): caida de 1 h <= -2.5 sigma_1h,
rango de la vela >= 3 sigma15 y volumen >= e^1 veces su media geometrica de 7 dias. A_cap(W) = numero de OTRAS
monedas (de 18) con al menos una vela de capitulacion en las ultimas W velas. DISENO.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H

D = B.load_ens()
tg = D["cache"]["BTCUSDT"]["t"].astype(np.int64)
jrow = np.searchsorted(tg, D["t"])
names = list(H.SYMBOLS) + B.OTHER18
caps = []
for s in names:
    p = os.path.join(B.RESEARCH, "klines", f"{s}_15m.npy")
    if not os.path.exists(p):
        p = os.path.join(B.RESEARCH, "verificador", "data", f"{s}_15m.npy")
    a = np.load(p)
    a = a[a[:, 0] < H.DESIGN[1]]
    o, h, l, c, v = a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    lr = H.log_returns(c)
    s15 = H.rolling_std(np.nan_to_num(lr), 672)
    lc = np.log(c)
    z4 = (lc - H.shift(lc, 4)) / (s15 * 2.0)
    rng = (h - l) / c / s15
    lv = np.log(v + 1e-9)
    vrel = lv - H.rolling_mean(lv, 672)
    cap = (np.nan_to_num(z4) <= -2.5) & (np.nan_to_num(rng) >= 3.0) & (np.nan_to_num(vrel) >= 1.0)
    j = np.minimum(np.searchsorted(a[:, 0], tg), len(a) - 1)
    caps.append(np.where(a[j, 0] == tg, cap[j], False))
caps = np.array(caps)
sig = D["p"] >= D["thr"]
lines = ["# E01c amplitud por capitulaciones de precio en 18 monedas (diseno, ENS13, X5)\n",
         f"Frecuencia de velas de capitulacion por moneda: {caps.mean(1).mean()*100:.2f} % de las velas.\n"]
res = {}
for W in (16, 48):
    anyW = np.array([H.rolling_max(x.astype(float), W) > 0 for x in caps])
    tot = anyW.sum(0)
    own = np.zeros(len(D["t"]))
    for ci_ in range(4):
        m = D["ci"] == ci_
        own[m] = anyW[ci_, jrow[m]]
    A = tot[jrow] - own
    lines.append(f"\n## W = {W} velas: distribucion de A_cap en velas de senal: " +
                 ", ".join(f"P(A≥{k})={np.mean(A[sig] >= k):.2f}" for k in (1, 2, 4, 8)) + "\n")
    lines += list(B.MD_HEAD_C)
    if W == 16:
        r0 = B.summarize_trades(*B.simulate_entries(D, sig), D, label="v2 sin compuerta")
        lines.append(B.md_row(r0))
    for k in (2, 4):
        g = A >= k
        T, s = B.simulate_entries(D, sig & g)
        r = B.summarize_trades(T, s, D, label=f"A_cap W={W} ≥ {k} de 17", cond_base=B.cond_base(D, g))
        lines.append(B.md_row(r)); print(B.fmt(r)); res[r["label"]] = r
        T, s = B.simulate_entries(D, sig & ~g)
        r = B.summarize_trades(T, s, D, label=f"  complemento A_cap W={W} < {k}", cond_base=B.cond_base(D, ~g))
        lines.append(B.md_row(r)); print(B.fmt(r)); res[r["label"]] = r
B.log_once("capbreadth", 4, "E01c A_cap (capitulaciones de precio en 18 monedas) W{16,48} x k{2,4} (diseno)")
with open(os.path.join(B.OUT, "be_capbreadth.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_capbreadth.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
