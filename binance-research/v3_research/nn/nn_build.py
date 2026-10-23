"""Construye y cachea variables, canales de secuencia y etiquetas (solo DISENO: t < 2025-07-01)."""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_common as C
H = C.H

DATA = C.RESEARCH
# variante de robustez: "lag1h" retrasa 1 hora TODOS los datos de futuros (prueba de que la ventaja no viene de
# minutos de solapamiento con la operacion)
VAR = sys.argv[1] if len(sys.argv) > 1 else ""
OUT = os.path.join(C.RESEARCH, "tmp", "nn_cache" + ("_" + VAR if VAR else ""))
os.makedirs(OUT, exist_ok=True)
T_END = H.DESIGN[1]

for sym in H.SYMBOLS:
    t0 = time.time()
    S, B, F, FU = C.build_symbol(DATA, sym, use_fut=True, t_end_ms=T_END)
    if VAR == "lag1h":
        F.update(C.futures_features(dict(S, t=S["t"] - 3_600_000), FU))
    names = sorted(F)
    X = np.stack([F[k] for k in names], 1).astype(np.float32)
    X[~np.isfinite(X)] = np.nan
    Q, qn = C.seq_channels(S, B, FU)
    N = len(S["c"])
    lab = {}
    for g in C.GEOMS:
        net, why, jx = C.label_all(S, g, N)
        lab[f"net_{g}"] = net; lab[f"why_{g}"] = why; lab[f"jx_{g}"] = jx
    np.savez(os.path.join(OUT, f"{sym}.npz"), t=S["t"], X=X, names=np.array(names), Q=Q, qnames=np.array(qn),
             s15=S["s15"], c=S["c"], **lab)
    # verificacion contra harness.simulate en una muestra
    bars = H.Bars(np.load(C.find_file(DATA, "klines", f"{sym}_15m.npy"))[:N], sym)
    rng = np.random.default_rng(0)
    smp = np.sort(rng.choice(np.arange(800, N - 300), 300, replace=False))
    maxdiff = 0.0
    for g in C.GEOMS:
        tp, sl, Hh = C.barriers(S, g)
        for i in smp[:100]:
            e = np.zeros(N, bool); e[i] = True
            tr = H.simulate(bars, e, tp, sl, period=(0, N), max_hold=Hh)
            if len(tr):
                maxdiff = max(maxdiff, abs(tr.net_ret[0] - lab[f"net_{g}"][i]))
    nanfrac = np.isnan(X[2000:]).mean(0)
    worst = [(names[k], round(float(nanfrac[k]), 3)) for k in np.argsort(-nanfrac)[:4]]
    print(sym, "N", N, "vars", X.shape[1], "canales", Q.shape[1], "max|dif etiqueta-harness|", f"{maxdiff:.2e}",
          "NaN max", worst, f"{time.time()-t0:.0f}s", flush=True)
print("nombres:", list(names))
