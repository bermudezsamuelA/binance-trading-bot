"""Sugerencia 3: vecinos en el espacio de estados del mercado (forma + contexto) (doc/plan-analogos.md).

Cada hora y moneda se describe con 10 variables calculadas con datos hasta el cierre de la vela. La distancia es
d^2 = sum_f w_f (x_tf - x_sf)^2 / sigma_f,<t^2: sigma se calcula con las filas de la biblioteca anteriores al mes de la
consulta (se actualiza una vez por mes). Pesos aprendidos y PCA se ajustan solo con el periodo de entrenamiento.

Uso: python s3_estado.py [--rapido]
"""
import argparse
import time

import numpy as np
from scipy.stats import rankdata

import common as C
import s1_knn as S1

FEATS = ["r24", "curv", "r6", "vol_rel", "volumen_rel", "taker", "pos_7d", "tendencia_btc", "funding", "d_oi"]
SHAPE = [0, 1, 2]


def roll_sum(x, w):
    c = np.concatenate([np.zeros(x.shape[:-1] + (1,)), np.nancumsum(x, -1)], -1)
    out = np.full(x.shape, np.nan)
    out[..., w - 1:] = c[..., w:] - c[..., :-w]
    return out


def features(data) -> np.ndarray:
    lp = np.log(data["close"])
    nc, n = lp.shape
    r = np.full_like(lp, np.nan); r[:, 1:] = np.diff(lp, axis=1)
    r0 = np.nan_to_num(r)
    s30 = np.sqrt(np.maximum(roll_sum(r0 ** 2, 720) / 720 - (roll_sum(r0, 720) / 720) ** 2, 1e-12))
    s24 = np.sqrt(np.maximum(roll_sum(r0 ** 2, 24) / 24 - (roll_sum(r0, 24) / 24) ** 2, 1e-12))
    lag = lambda a, k: np.concatenate([np.full((nc, k), np.nan), a[:, :-k]], 1)
    V, K = data["volume"], data["taker"]
    v24, v720, k24 = roll_sum(V, 24), roll_sum(V, 720), roll_sum(K, 24)
    mn = np.full_like(lp, np.nan); mx = np.full_like(lp, np.nan)
    sw = np.lib.stride_tricks.sliding_window_view(lp, 168, axis=1)
    mn[:, 167:], mx[:, 167:] = sw.min(-1), sw.max(-1)
    btc = lp[data["symbols"].index("BTCUSDT")]
    sma = roll_sum(np.exp(btc)[None], 720)[0] / 720
    trend = np.broadcast_to(btc - np.log(sma), lp.shape)
    oi = np.log(data["oi"])
    X = np.stack([
        (lp - lag(lp, 24)) / (s30 * np.sqrt(24)),
        (lp - 2 * lag(lp, 12) + lag(lp, 24)) / (s30 * np.sqrt(12)),
        (lp - lag(lp, 6)) / (s30 * np.sqrt(6)),
        s24 / s30,
        (v24 / 24) / (v720 / 720),
        (2 * k24 - v24) / v24,
        (lp - mn) / np.maximum(mx - mn, 1e-12),
        trend,
        data["funding"],
        oi - lag(oi, 24),
    ], -1)
    X[:, :720] = np.nan
    return X.astype(np.float64)


def learned_weights(X, y, T):
    tr = np.flatnonzero(T < C.TRAIN_END - 24 * C.HOUR)
    w = []
    for f in range(X.shape[-1]):
        a, b = X[:, tr, f].ravel(), y[:, tr].ravel()
        ok = np.isfinite(a) & np.isfinite(b)
        w.append(abs(np.corrcoef(rankdata(a[ok]), rankdata(b[ok]))[0, 1]))
    w = np.array(w)
    return w / w.mean(), np.array(w)


def search(data, X, use, std=True, w=None, pca_m=0, lag=C.MARGIN, k=100, stride=S1.STRIDE):
    """Vecinos por bloques mensuales: sigma con datos anteriores al mes. Devuelve dict como S1.neighbors."""
    T = data["T"]
    nc, n, _ = X.shape
    Xu = X[:, :, use]
    w = np.ones(len(use)) if w is None else w[use]
    valid = np.isfinite(Xu).all(-1)
    lc, lt = np.nonzero(valid)
    o = np.lexsort((lc, lt)); lc, lt = lc[o], lt[o]
    rows = Xu[lc, lt]
    end = T[-1] - 24 * C.HOUR
    qc, qt = C.queries(T, nc, C.TRAIN_END, end, stride)
    keep = valid[qc, qt]; qc, qt = qc[keep], qt[keep]
    proj = None
    if pca_m:
        tr = T[lt] < C.TRAIN_END
        sg = rows[tr].std(0) if std else np.ones(len(use))
        Z = (rows[tr] - rows[tr].mean(0)) / sg * np.sqrt(w)
        vals, vecs = np.linalg.eigh(np.cov(Z.T))
        proj = (vecs[:, np.argsort(vals)[::-1][:pca_m]], sg)
    I = np.full((len(qt), k), -1, np.int64); Dd = np.full((len(qt), k), np.inf, np.float32)
    mon = C.months(T[qt])
    for u in np.unique(mon):
        sel = np.flatnonzero(mon == u)
        t_start = T[qt[sel]].min()
        past = T[lt] < t_start
        if proj is not None:
            V, sg = proj
            Z = rows / sg * np.sqrt(w) @ V
            Q = Xu[qc[sel], qt[sel]] / sg * np.sqrt(w) @ V
        else:
            sg = rows[past].std(0) if std else np.ones(len(use))
            Z = rows / sg * np.sqrt(w)
            Q = Xu[qc[sel], qt[sel]] / sg * np.sqrt(w)
        lib = C.Library(Z, lc, lt)
        i, d = C.knn(lib, Q, qt[sel], k, lag=lag)
        I[sel], Dd[sel] = i, d
    return {"qc": qc, "qt": qt, "I": I, "D": Dd, "lib_coin": lib.coin, "lib_t": lib.t}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args(argv)
    data = C.load_hourly(C.BASE, futures=True)
    X = features(data)
    y24 = C.future_returns(data["close"], 24)
    w_learn, ic_train = learned_weights(X, y24, data["T"])
    print("[S3] IC de entrenamiento por variable:", dict(zip(FEATS, np.round(ic_train, 3))), flush=True)
    ALL = list(range(len(FEATS)))
    steps = [("0 · solo forma", dict(use=SHAPE)),
             ("1 · + contexto sin estandarizar", dict(use=ALL, std=False)),
             ("2 · + estandarizar", dict(use=ALL)),
             ("3 · + pesos aprendidos", dict(use=ALL, w=w_learn)),
             ("4 · + PCA (m = 4)", dict(use=ALL, w=w_learn, pca_m=4)),
             ("solo contexto", dict(use=ALL[3:])),
             ("control con fuga: sin margen", dict(use=ALL, w=w_learn, lag=1))]
    if a.rapido:
        steps = steps[2:4]
    rows, resumen = [], {}
    for name, kw in steps:
        t0 = time.time()
        nb = search(data, X, **kw)
        r = S1.grid(data, nb, {"paso": name}, ks=[30, 100], hs=[12, 24], weights=(0,))
        rows += r
        b = C.best_on_design(r)
        resumen[name] = b
        print(f"[S3] {name}: {time.time() - t0:.0f} s; mejor en diseño -> val E {b['val']['e'] if b else None} "
              f"IC {b['val']['ic'] if b else None}", flush=True)
    S1.write_csv(rows, "s3_rejilla.csv")
    honest = [x for x in rows if not x["paso"].startswith("control")]
    best = C.best_on_design(honest)
    C.save_json({"variables": FEATS, "ic_entrenamiento": dict(zip(FEATS, np.round(ic_train, 4))),
                 "pesos_aprendidos": dict(zip(FEATS, np.round(w_learn, 3))), "por_paso": resumen,
                 "mejor_en_diseno": best, "pasa_criterio": C.passes(best) if best else False}, "s3_resumen.json")
    print(f"[S3] Mejor en diseño: {S1.flat(best) if best else None}")
    print(f"[S3] ¿Pasa el criterio? {C.passes(best) if best else False}")


if __name__ == "__main__":
    main()
