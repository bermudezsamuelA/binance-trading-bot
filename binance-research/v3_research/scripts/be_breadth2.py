"""E01b - Amplitud por MODELO (A_model): estabilidad por pliegue y moneda, complemento, A>=2, umbral relajado con
A>=1, y % de meses ganadores. DISENO solamente."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H

D = B.load_ens()
tg = D["cache"]["BTCUSDT"]["t"].astype(np.int64)
jrow = np.searchsorted(tg, D["t"])


def A_model(sig, W):
    per = []
    for ci_ in range(4):
        m = D["ci"] == ci_
        v = np.zeros(len(tg), bool)
        v[jrow[m][sig[m]]] = True
        per.append(H.rolling_max(v.astype(float), W) > 0)
    per = np.array(per)
    return per.sum(0)[jrow] - per[D["ci"], jrow]


def by_fold(T):
    out = []
    for te0, te1 in B.TESTS:
        s = (T.entry_t >= H.ms(*te0, 1)) & (T.entry_t < H.ms(*te1, 1))
        out.append((int(s.sum()), round(float(np.mean(T.net_ret[s] > 0)) * 100, 1) if s.any() else None,
                    round(float(np.mean(T.net_ret[s])) * 100, 2) if s.any() else None))
    return out


def months_pos(T):
    mon = B.month_of(T.entry_t)
    allm = sorted(set(B.month_of(D["t"])))
    pnl = {m: 0.0 for m in allm}
    for m, x in zip(mon, T.net_ret):
        pnl[m] += x
    act = [m for m in allm if (mon == m).any()]
    k = sum(1 for m in act if pnl[m] > 0)
    return k, len(act), len(allm)


sig = D["p"] >= D["thr"]
lines = ["# E01b amplitud por modelo (diseno, ENS13, X5)\n"]
lines += list(B.MD_HEAD_C)
res = {}
cfgs = []
base_T, base_s = B.simulate_entries(D, sig)
cfgs.append(("v2 sin compuerta", sig, None))
A48 = A_model(sig, 48)
A16 = A_model(sig, 16)
cfgs.append(("A_model W=48 = 0 (complemento: senal aislada)", sig & (A48 == 0), A48 == 0))
cfgs.append(("A_model W=48 ≥ 1", sig & (A48 >= 1), A48 >= 1))
cfgs.append(("A_model W=48 ≥ 2", sig & (A48 >= 2), A48 >= 2))
cfgs.append(("A_model W=16 = 0 (complemento)", sig & (A16 == 0), A16 == 0))
for dlt in (0.02, 0.04):
    low = D["p"] >= D["thr"] - dlt
    cfgs.append((f"p ≥ thr−{dlt} y A_model W=48 ≥ 1", low & (A48 >= 1), A48 >= 1))
# A con senales de umbral bajo (cuantas monedas estan "casi" capitulando): q mas ancha
siglow = D["p"] >= D["thr"] - 0.04
A48L = A_model(siglow, 48)
cfgs.append(("v2 y A_low(thr−0.04) W=48 ≥ 2", sig & (A48L >= 2), A48L >= 2))
n_new = 0
for lab, m, g in cfgs:
    T, s = B.simulate_entries(D, m)
    r = B.summarize_trades(T, s, D, label=lab, cond_base=None if g is None else B.cond_base(D, g))
    if T is not None and len(T):
        r["by_fold"] = by_fold(T)
        r["by_coin"] = {c: (int((s == c).sum()), round(float(np.mean(T.net_ret[s == c] > 0)) * 100, 1),
                            round(float(np.mean(T.net_ret[s == c])) * 100, 2)) for c in np.unique(s)}
        r["months_pos"] = months_pos(T)
    lines.append(B.md_row(r))
    print(B.fmt(r)); print("   pliegues", r.get("by_fold"), "| monedas", r.get("by_coin"), "| meses +", r.get("months_pos"))
    res[lab] = r
    n_new += 1
lines.append("\nPor pliegue (n, WR %, E %), por moneda y meses positivos/meses con operaciones/meses totales:\n")
for lab, r in res.items():
    lines.append(f"- {lab}: pliegues {r.get('by_fold')}; monedas {r.get('by_coin')}; meses + {r.get('months_pos')}")
B.log_once("breadth2", n_new - 1, "E01b A_model: complementos, A>=2, umbral relajado d{0.02,0.04} con A>=1, A_low>=2")
with open(os.path.join(B.OUT, "be_breadth2.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_breadth2.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, default=float, indent=1)
