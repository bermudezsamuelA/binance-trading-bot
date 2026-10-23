"""Unidades independientes y estres de ejecucion en panicos (DISENO, ENS13, X5).
(1) Episodios: dias con operaciones agrupados si distan <= 2 dias; WR y E por episodio para v2 y v2 + A_model >= 1.
(2) Estres de deslizamiento en las salidas por SL (la profundidad cae en las capitulaciones): +0.5 % y +1.0 % extra
    en cada salida por SL (y por hueco), sin cambiar las demas.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H

D = B.load_ens()
tg = D["cache"]["BTCUSDT"]["t"].astype(np.int64)
jrow = np.searchsorted(tg, D["t"])
sig = D["p"] >= D["thr"]
per = []
for ci_ in range(4):
    m = D["ci"] == ci_
    v = np.zeros(len(tg), bool); v[jrow[m][sig[m]]] = True
    per.append(H.rolling_max(v.astype(float), 48) > 0)
per = np.array(per)
A48 = per.sum(0)[jrow] - per[D["ci"], jrow]
lines = ["# Episodios independientes y estres de SL (diseno)\n",
         "| Conjunto | n op | días | episodios (días a ≤ 2 días se unen) | WR por episodio (P&L del episodio > 0) | E media por episodio (suma de % ) | op. en los 5 episodios mayores | E sin los 5 episodios mayores % | E con SL +0.5 % / +1.0 % extra |",
         "|---|---|---|---|---|---|---|---|---|"]
res = {}
for lab, mask in (("v2", sig), ("v2 + A_model≥1", sig & (A48 >= 1)), ("v2 y A_model=0", sig & (A48 == 0))):
    T, s = B.simulate_entries(D, mask)
    x = T.net_ret
    day = T.entry_t // B.DAY
    ud = np.unique(day)
    ep = np.zeros(len(ud), int)
    for k in range(1, len(ud)):
        ep[k] = ep[k - 1] + (1 if ud[k] - ud[k - 1] > 2 else 0)
    epi = ep[np.searchsorted(ud, day)]
    ne = epi.max() + 1
    pnl = np.bincount(epi, weights=x)
    cnt = np.bincount(epi)
    top5 = np.argsort(-cnt)[:5]
    rest = ~np.isin(epi, top5)
    sl = T.reason == 1
    e05 = (x - np.where(sl, 0.005, 0)).mean() * 100
    e10 = (x - np.where(sl, 0.010, 0)).mean() * 100
    lines.append(f"| {lab} | {len(x)} | {len(ud)} | {ne} | {np.mean(pnl>0)*100:.0f} % ({int(np.sum(pnl>0))}/{ne}) | {pnl.mean()*100:+.2f} | "
                 f"{int(cnt[top5].sum())} | {x[rest].mean()*100:+.2f} (n={int(rest.sum())}, WR {np.mean(x[rest]>0)*100:.0f} %) | {e05:+.2f} / {e10:+.2f} (SL {sl.mean()*100:.0f} %) |")
    res[lab] = dict(n=len(x), days=len(ud), episodes=int(ne), ep_wr=float(np.mean(pnl > 0)), top5=int(cnt[top5].sum()),
                    E_rest=float(x[rest].mean() * 100), E_sl05=e05, E_sl10=e10, sl_rate=float(sl.mean()))
    print(lines[-1])
B.log_once("events", 0, "episodios y estres SL (sin configuraciones nuevas)")
with open(os.path.join(B.OUT, "be_events.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_events.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
