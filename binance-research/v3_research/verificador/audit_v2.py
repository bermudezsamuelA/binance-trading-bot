"""Auditoria v2 (solo DISENO, 4 monedas originales):
 1) perturbacion del futuro sobre las 74 variables Y los 10 canales de secuencia (CNN), varios cortes;
 2) umbral: p del ensamble de 13 en la validacion [2025-04-01, 2025-07-01 - 289 velas) con etiquetas X5 -> cuantil 0.98 y choose();
 3) extension de etiquetas: la ultima vela de validacion + 288 velas < 2025-07-01 y el ajuste + 192 < 2025-04-01."""
import os, sys, json
import numpy as np
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, "nn"))
import nn_common as C, nn_wf as W, nn_report as RP, nn_v2_report as V
import lightgbm as lgb, torch
H = C.H
spec = json.load(open(os.path.join(R, "output", "constructor", "spec_nn_v2.json"), encoding="utf-8"))
names = spec["variables"]; END = H.DESIGN[1]
orig_spot, orig_fut = C.load_spot, C.load_fut
def build(sym, cut_t=None, m_off=300_000, seed=1):
    rng = np.random.default_rng(seed)
    def ls(d, s):
        a = orig_spot(d, s).copy()
        if cut_t is not None:
            m = a[:, 0] > cut_t
            a[m, 1:5] *= np.exp(rng.normal(0, 0.05, m.sum()))[:, None]
            a[m, 5] *= rng.uniform(0.2, 5, m.sum()); a[m, 6] = a[m, 5] * rng.uniform(0, 1, m.sum())
        return a
    def lf(d, s):
        FU = {k: v.copy() for k, v in orig_fut(d, s).items()}
        if cut_t is not None:
            M = FU["metrics"]; m = M[:, 0] > cut_t + m_off; M[m, 1:] *= rng.uniform(0.5, 2, (m.sum(), 6))
            F_ = FU["funding"]; m = F_[:, 0] > cut_t + 900_000; F_[m, 1] = rng.normal(0, 0.001, m.sum())
            for k in ("premium15m", "fut15m"):
                A = FU[k]; m = A[:, 0] > cut_t; A[m, 1:] *= rng.uniform(0.5, 2, (m.sum(), A.shape[1] - 1))
        return FU
    C.load_spot, C.load_fut = ls, lf
    try:
        S, B, F, FU = C.build_symbol(R, sym, use_fut=True, t_end_ms=END)
        Q = C.seq_channels(S, B, FU)[0]
    finally:
        C.load_spot, C.load_fut = orig_spot, orig_fut
    return S, B, F, FU, np.stack([F[k] for k in names], 1), Q
worst = 0.0
for sym in ("DOGEUSDT", "BTCUSDT"):
    S, B, F, FU, X0, Q0 = build(sym)
    t = S["t"]; rng = np.random.default_rng(7)
    cuts = list(rng.choice(np.arange(5000, len(t) - 2000), 5, replace=False)) + [int(np.searchsorted(t, H.ms(2024, 3, 4)) + 3)]
    for ci in cuts:
        *_, X1, Q1 = build(sym, int(t[ci]))
        for nm, A0, A1 in (("X", X0, X1), ("Q", Q0, Q1)):
            a, b = A0[:ci + 1], A1[:ci + 1]
            both = np.isfinite(a) & np.isfinite(b)
            d = float(np.where(both, np.abs(a - b), 0).max()); nm_ = int((np.isfinite(a) != np.isfinite(b)).sum())
            aft = float((np.abs(A0[ci + 1:ci + 50] - A1[ci + 1:ci + 50]) > 1e-9).mean())
            worst = max(worst, d, nm_)
            print(f"[perturbacion] {sym} {H.iso(int(t[ci]))} {nm}: max|dif| antes = {d:.1e}, NaN distintos = {nm_}, frac cambiada despues = {aft:.2f}", flush=True)
print("RESUMEN perturbacion v2: peor diferencia antes del corte =", worst)
# 2-3) umbral y extension de etiquetas
M = os.path.join(R, "nn", "models_v2"); mem = []
for m in spec["miembros"]:
    if m["kind"] == "lgb":
        mem.append(("lgb", lgb.Booster(model_file=os.path.join(M, m["file"])), None, m["platt"]))
    else:
        sc = np.load(os.path.join(M, m["scaler"])); net = W.torch_model(m["kind"], len(names), 10)
        net.load_state_dict(torch.load(os.path.join(M, m["file"]))); net.eval(); mem.append((m["kind"], net, (sc["mu"], sc["sd"]), m["platt"]))
V0, T0 = W.ms(2025, 4), W.ms(2025, 7); pX = (288 + 1) * C.MS15
P, NX, D, TV = [], [], [], []
for sym in H.SYMBOLS:
    S, B, F, FU = C.build_symbol(R, sym, True, t_end_ms=END)
    X = np.stack([F[k] for k in names], 1).astype(np.float32); X[~np.isfinite(X)] = np.nan
    Q = C.seq_channels(S, B, FU)[0]
    netG3, _, _ = C.label_all(S, "G3", len(X)); netX, _, jx = C.label_all(S, "X5", len(X))
    t = S["t"]; idx = np.arange(len(X))
    val = np.flatnonzero((idx >= W.WARM) & np.isfinite(netG3) & (t >= V0) & (t < T0 - pX) & np.isfinite(netX))
    p = np.zeros(len(val))
    for kind, mod, sc, ab in mem:
        if kind == "lgb":
            s = mod.predict(X[val], raw_score=True)
        else:
            Z = torch.from_numpy(W.standardize(X[val], sc[0], sc[1]))
            xs = None
            if kind == "cnn":
                w = val[:, None] + np.arange(-W.SEQ_L + 1, 1)[None, :]
                xs = torch.from_numpy(Q[w].transpose(0, 2, 1).copy())
            with torch.no_grad():
                s = mod(Z, xs).numpy()
        p += RP.platt_apply(s, ab) / len(mem)
    P.append(p); NX.append(netX[val]); D.append(t[val] // 86_400_000); TV.append((t[val].max(), t[jx[val]].max()))
p = np.concatenate(P); nx = np.concatenate(NX); d = np.concatenate(D)
print("n_val", len(p), "(spec", spec["entrenamiento"]["n_validacion"], ") q0.98 =", float(np.quantile(p, 0.98)), "(spec", spec["regla"]["umbral"], ")")
V.OBJ["v"] = "E"; print("choose:", V.choose(p, nx, d, 0.75))
print("ultima vela de validacion y ultima salida X5 usada:", [(H.iso(int(a)), H.iso(int(b))) for a, b in TV], "< 2025-07-01")
