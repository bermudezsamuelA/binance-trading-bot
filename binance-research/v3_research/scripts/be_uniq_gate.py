"""Pila candidata v3 en DISENO: ENS12 ponderado por unicidad + compuerta de co-senal A_model(W=48) >= 1, frente a
ENS12 sin ponderar con y sin compuerta, y ENS13 v2. Salida X5, regla v2, c = 0.24 % y 0.19 % (BNB)."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H
PD = os.path.join(B.OUT, "preds")
L = lambda kind, ss, u: [f"{kind}{'uniq' if u else 'v4'}_G3_f1_s{s}" for s in ss]


def gate(D, W=48):
    tg = D["cache"]["BTCUSDT"]["t"].astype(np.int64)
    jrow = np.searchsorted(tg, D["t"])
    sig = D["p"] >= D["thr"]
    per = []
    for ci_ in range(4):
        m = D["ci"] == ci_
        v = np.zeros(len(tg), bool); v[jrow[m][sig[m]]] = True
        per.append(H.rolling_max(v.astype(float), W) > 0)
    per = np.array(per)
    return per.sum(0)[jrow] - per[D["ci"], jrow]


lines = ["# Pila candidata v3 (diseno): unicidad + co-senal\n"] + list(B.MD_HEAD_C)
out = {}
for lab, tags in (("ENS13 v2", B.ENS13), ("ENS12 sin ponderar", L("lgb", range(6), 0) + L("mlp", range(6), 0)),
                  ("ENS12 ponderado (unicidad)", L("lgb", range(6), 1) + L("mlp", range(6), 1))):
    D = B.load_ens(tags, pred_dirs=[PD])
    sig = D["p"] >= D["thr"]
    A = gate(D)
    for glab, m, g in (("", sig, None), (" + co-señal A≥1", sig & (A >= 1), A >= 1), (" y señal aislada A=0", sig & (A == 0), A == 0)):
        for cl, fee in (("0.24 %", 0.001), ("0.19 % BNB", 0.00075)):
            if cl != "0.24 %" and glab != " + co-señal A≥1":
                continue
            T, s = B.simulate_entries(D, m, fee=fee)
            r = B.summarize_trades(T, s, D, label=f"{lab}{glab} [{cl}]", cond_base=None if g is None else B.cond_base(D, g))
            lines.append(B.md_row(r)); print(B.fmt(r), flush=True); out[r["label"]] = r
B.log_once("uniq_gate", 2, "Pila v3: ENS12 ponderado + co-senal; c 0.24/0.19 (diseno)")
with open(os.path.join(B.OUT, "be_uniq_gate.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_uniq_gate.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, default=float, indent=1)
