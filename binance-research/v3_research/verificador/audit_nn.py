"""Auditoria de fugas del candidato NN (solo datos de DISENO de las 4 monedas originales).
 1) alineacion empirica de premium15m y fut15m con spot (correlaciones a desfases -1, 0, +1 velas)
 2) prueba de perturbacion del futuro: se alteran TODOS los datos no conocidos al cierre de la vela de corte
    (spot y BTC con open_time > t_cut; metrics con T > t_cut + umbral; funding con calc_time > t_cut + 15m;
    premium y fut15m con open_time > t_cut) y se comparan las 74 variables en todas las velas <= corte."""
import os, sys, json
import numpy as np
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, "nn"))
import nn_common as C
H = C.H
spec = json.load(open(os.path.join(R, "output", "constructor", "spec_nn.json"), encoding="utf-8"))
names = spec["variables"]
DATA = R
END = H.DESIGN[1]
# 1) alineacion
for sym in ("BTCUSDT", "SOLUSDT"):
    a = C.load_spot(DATA, sym); a = a[a[:, 0] < END]
    FU = C.load_fut(DATA, sym)
    for key, col in (("fut15m", 4), ("premium15m", 4)):
        K = FU[key]
        j = C.align_exact(a[:, 0], K[:, 0]); ok = j >= 0
        if key == "fut15m":
            x = np.diff(np.log(K[j[ok], col])); y = np.diff(np.log(a[ok, 4]))
        else:
            x = K[j[ok], col]; y = np.full(ok.sum(), np.nan)
            jk = C.align_exact(a[:, 0], FU["fut15m"][:, 0]); ok2 = jk[ok] >= 0
            y[ok2] = FU["fut15m"][jk[ok][ok2], 4] / a[ok, 4][ok2] - 1     # base futuros/spot al cierre
        out = []
        for k in (-1, 0, 1):
            xs, ys = (x[k:], y[:len(y) - k]) if k > 0 else ((x[:len(x) + k], y[-k:]) if k < 0 else (x, y))
            m = np.isfinite(xs) & np.isfinite(ys)
            out.append(round(float(np.corrcoef(xs[m], ys[m])[0, 1]), 4))
        print(f"[alineacion] {sym} {key}: corr con spot a desfase -1/0/+1 velas = {out}")
# 2) perturbacion
orig_spot, orig_fut = C.load_spot, C.load_fut
def build(sym, cut_t=None, m_off=600_000, seed=1):
    rng = np.random.default_rng(seed)
    def ls(d, s):
        a = orig_spot(d, s).copy()
        if cut_t is not None:
            m = a[:, 0] > cut_t
            f = np.exp(rng.normal(0, 0.05, m.sum()))
            a[m, 1:5] *= f[:, None]
            a[m, 5] *= rng.uniform(0.2, 5, m.sum()); a[m, 6] = a[m, 5] * rng.uniform(0, 1, m.sum())
        return a
    def lf(d, s):
        FU = {k: v.copy() for k, v in orig_fut(d, s).items()}
        if cut_t is not None:
            M = FU["metrics"]; m = M[:, 0] > cut_t + m_off
            M[m, 1:] *= rng.uniform(0.5, 2, (m.sum(), 6))
            F_ = FU["funding"]; m = F_[:, 0] > cut_t + 900_000
            F_[m, 1] = rng.normal(0, 0.001, m.sum())
            for k in ("premium15m", "fut15m"):
                A = FU[k]; m = A[:, 0] > cut_t
                A[m, 1:] *= rng.uniform(0.5, 2, (m.sum(), A.shape[1] - 1))
        return FU
    C.load_spot, C.load_fut = ls, lf
    try:
        S, B, F, FU = C.build_symbol(DATA, sym, use_fut=True, t_end_ms=END)
    finally:
        C.load_spot, C.load_fut = orig_spot, orig_fut
    return S["t"], np.stack([F[k] for k in names], 1)
worst_before, changed_after = 0.0, []
for sym in ("SOLUSDT", "ETHUSDT"):
    t, X0 = build(sym)
    rng = np.random.default_rng(42)
    cuts = list(rng.choice(np.arange(5000, len(t) - 2000), 6, replace=False))
    cuts += [int(np.searchsorted(t, H.ms(2024, 3, 3)) + 50), int(np.searchsorted(t, H.ms(2024, 3, 4)) + 7)]
    for ci in cuts:
        for m_off, lab in ((600_000, "metrics T>t+10m"), (300_000, "metrics T>t+5m")):
            _, X1 = build(sym, int(t[ci]), m_off)
            a, b = X0[:ci + 1], X1[:ci + 1]
            both = np.isfinite(a) & np.isfinite(b)
            d = np.where(both, np.abs(a - b) / (1 + np.abs(a)), 0.0)
            nanmis = int((np.isfinite(a) != np.isfinite(b)).sum())
            dmax = float(d.max()); worst_before = max(worst_before, dmax)
            bad = [names[k] for k in np.flatnonzero((d.max(0) > 1e-9) | (np.isfinite(a) != np.isfinite(b)).any(0))]
            aft = np.isfinite(X0[ci + 1:ci + 50]) & np.isfinite(X1[ci + 1:ci + 50])
            ch = float((np.abs(X0[ci + 1:ci + 50] - X1[ci + 1:ci + 50])[aft] > 1e-9).mean())
            changed_after.append(ch)
            print(f"[perturbacion] {sym} corte {H.iso(int(t[ci]))} ({lab}): max|dif| rel velas<=corte = {dmax:.2e}, "
                  f"NaN distintos = {nanmis}, variables afectadas = {bad[:6]} | frac. cambiada despues = {ch:.2f}", flush=True)
print(f"RESUMEN perturbacion: peor diferencia antes del corte = {worst_before:.2e}; cambio medio despues = {np.mean(changed_after):.2f}")
