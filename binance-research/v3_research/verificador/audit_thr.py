"""Comprueba que el umbral congelado sale del cuantil 0.98 de p en la VALIDACION 2025-04-01..2025-07-01-193 velas
(4 monedas de diseno) y no de otro periodo. Usa los modelos congelados."""
import os, sys, json
import numpy as np
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, "nn"))
import nn_common as C, nn_wf as W, nn_report as RP
import lightgbm as lgb, torch
H = C.H
spec = json.load(open(os.path.join(R, "output", "constructor", "spec_nn.json"), encoding="utf-8"))
names = spec["variables"]; M = os.path.join(R, "nn", "models")
mem = []
for m in spec["miembros"]:
    if m["kind"] == "lgb":
        mem.append(("lgb", lgb.Booster(model_file=os.path.join(M, m["file"])), None, m["platt"]))
    else:
        sc = np.load(os.path.join(M, m["scaler"])); net = W.torch_model("mlp", len(names), 0)
        net.load_state_dict(torch.load(os.path.join(M, m["file"]))); net.eval()
        mem.append(("mlp", net, (sc["mu"], sc["sd"]), m["platt"]))
V0, T0 = W.ms(2025, 4), W.ms(2025, 7); purge = 193 * C.MS15
P, NET, D = [], [], []
for sym in H.SYMBOLS:
    S, B, F, FU = C.build_symbol(R, sym, True, t_end_ms=H.DESIGN[1])
    X = np.stack([F[k] for k in names], 1).astype(np.float32); X[~np.isfinite(X)] = np.nan
    net, _, _ = C.label_all(S, "G3", len(X))
    t = S["t"]; idx = np.arange(len(X))
    val = (idx >= W.WARM) & np.isfinite(net) & (t >= V0) & (t < T0 - purge)
    p = np.zeros(val.sum())
    for kind, mod, sc, ab in mem:
        s = mod.predict(X[val], raw_score=True) if kind == "lgb" else mod(torch.from_numpy(W.standardize(X[val], sc[0], sc[1]))).detach().numpy()
        p += RP.platt_apply(s, ab) / len(mem)
    P.append(p); NET.append(net[val]); D.append(t[val] // 86_400_000)
p = np.concatenate(P); net = np.concatenate(NET); d = np.concatenate(D)
print("n_val", len(p), "(spec", spec["entrenamiento"]["n_validacion"], ")  q0.98 =", float(np.quantile(p, 0.98)), "(spec", spec["regla"]["umbral"], ")")
print("choose_threshold:", RP.choose_threshold(p, net, "wr70", day=d))
