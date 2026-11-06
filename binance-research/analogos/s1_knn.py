"""Sugerencia 1: vecinos más cercanos sobre la forma del precio (doc/plan-analogos.md).

Uso (desde binance-research/analogos):  python s1_knn.py [--rapido]
Salida: output/s1_rejilla.csv y output/s1_resumen.json
"""
import argparse
import csv
import itertools
import os
import time

import numpy as np

import common as C

KS, HS, QS = [10, 30, 100], [4, 12, 24], [0.5, 0.55, 0.6, 0.65, 0.7]
STRIDE = 2            # una consulta cada 2 h por moneda


def neighbors(data, W, multi: bool, kmax=100, stride=STRIDE, lag=C.MARGIN, cand=None, return_cand=False):
    """Vecinos de todas las consultas (diseño + validación). W: ventanas (monedas, t, d)."""
    T = data["T"]
    nc, n, _ = W.shape
    end = T[-1] - max(HS) * C.HOUR
    qc, qt = C.queries(T, nc, C.TRAIN_END, end, stride)
    valid = np.isfinite(W).all(2)
    width = cand if return_cand else kmax
    I = np.full((len(qt), width), -1, np.int64)
    Dd = np.full((len(qt), width), np.inf, np.float32)
    groups = [list(range(nc))] if multi else [[c] for c in range(nc)]
    libs = []
    for g in groups:
        rows = [(c, t) for c in g for t in np.flatnonzero(valid[c])]
        lc = np.array([r[0] for r in rows]); lt = np.array([r[1] for r in rows])
        lib = C.Library(W[lc, lt], lc, lt)
        sel = np.flatnonzero(np.isin(qc, g))
        i, d = C.knn(lib, W[qc[sel], qt[sel]], qt[sel], kmax, lag=lag, cand=cand, return_cand=return_cand)
        I[sel] = np.where(i >= 0, i + sum(len(x.t) for x in libs), -1)
        Dd[sel] = d
        libs.append(lib)
    lib_coin = np.concatenate([x.coin for x in libs]); lib_t = np.concatenate([x.t for x in libs])
    return {"qc": qc, "qt": qt, "I": I, "D": Dd, "lib_coin": lib_coin, "lib_t": lib_t, "libs": libs}


def grid(data, nb, label: dict, ks=KS, hs=HS, qs=QS, weights=(0, 1)):
    T = data["T"]
    end = int(T[-1])
    rows = []
    for h in hs:
        Y = C.future_returns(data["close"], h)
        ly = Y[nb["lib_coin"], nb["lib_t"]]
        y = Y[nb["qc"], nb["qt"]]
        for k, w in itertools.product(ks, weights):
            yhat, frac = C.predict(ly, nb["I"], nb["D"], k, bool(w))
            for q in qs:
                r = C.evaluate(T[nb["qt"]], nb["qc"], yhat, frac, y, h, q, end)
                rows.append({**label, "h": h, "k": k, "peso": w, "q": q, **r})
    return rows


def flat(r):
    out = {k: v for k, v in r.items() if k not in ("dis", "val")}
    for p in ("dis", "val"):
        out.update({f"{p}_{k}": v for k, v in r[p].items()})
    return out


def write_csv(rows, name):
    os.makedirs(C.OUT_DIR, exist_ok=True)
    fl = [flat(r) for r in rows]
    with open(os.path.join(C.OUT_DIR, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fl[0]), lineterminator="\n")
        w.writeheader(); w.writerows(fl)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true", help="rejilla pequeña (para probar)")
    a = ap.parse_args(argv)
    data = C.load_hourly(C.BASE)
    print(f"[S1] {len(data['T'])} velas de 1 h, {C.iso(data['T'][0])} a {C.iso(data['T'][-1])}", flush=True)
    configs = [("precio", 48, 0), ("retornos", 48, 0)] + [("forma", L, m) for L in (24, 48, 96) for m in (0, 1)]
    if a.rapido:
        configs = [("forma", 48, 0)]
    rows = []
    for norm, L, multi in configs:
        t0 = time.time()
        W = C.shape_windows(data["close"], L, norm)
        nb = neighbors(data, W, bool(multi))
        rows += grid(data, nb, {"norma": norm, "L": L, "biblioteca": "4 monedas" if multi else "1 moneda"})
        print(f"[S1] {norm} L={L} {'4 monedas' if multi else '1 moneda'}: {time.time() - t0:.0f} s", flush=True)
    write_csv(rows, "s1_rejilla.csv")
    base = {h: C.always_buy(data["T"], data["close"], h, int(data["T"][-1])) for h in HS}
    best = C.best_on_design(rows)
    path = {}
    for name, f in (("precio crudo", lambda r: r["norma"] == "precio"), ("retornos", lambda r: r["norma"] == "retornos"),
                    ("forma z, 1 moneda", lambda r: r["norma"] == "forma" and r["biblioteca"] == "1 moneda"),
                    ("forma z, 4 monedas", lambda r: r["norma"] == "forma" and r["biblioteca"] == "4 monedas")):
        b = C.best_on_design([r for r in rows if f(r)])
        if b:
            path[name] = b
    C.save_json({"mejor_en_diseno": best, "pasa_criterio": C.passes(best) if best else False, "por_paso": path,
                 "comprar_siempre": base, "n_configuraciones": len(rows)}, "s1_resumen.json")
    print(f"[S1] Mejor en diseño: {flat(best) if best else None}")
    print(f"[S1] ¿Pasa el criterio en validación? {C.passes(best) if best else False}")


if __name__ == "__main__":
    main()
