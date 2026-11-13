"""Sugerencia 5: biblioteca de todas las monedas y acuerdo con la temporalidad de 4 h (doc/plan-analogos.md).

Consultas: las 4 monedas base (BTC, ETH, SOL, DOGE). Biblioteca: (a) la misma moneda, (b) las 4 base, (c) las 4 base más
las otras 19 monedas de v3_research/tmp/new20 (desde 2023-01). Ventanas de forma z (L = 48 h), h = 24 h.
Filtro de 4 h: la misma búsqueda con velas de 4 h (L = 24 velas = 4 días, h = 6 velas) y se exige ŷ_4h >= 0 en la última
vela de 4 h ya cerrada. El tiempo de la biblioteca se mide en horas desde 1970, así el margen de 24 h vale para todas.

Uso: python s5_multi.py
"""
import os
import time

import numpy as np

import common as C
import s1_knn as S1

L, H, STRIDE = 48, 24, 4
NEW20 = os.path.join(C.RESEARCH, "tmp", "new20")


def block(symbols, dirs=None, step=1, L=L, h=H, start=None):
    d = C.load_hourly(symbols, dirs=dirs, step=step, start=start)
    W = C.shape_windows(d["close"], L)
    Y = C.future_returns(d["close"], h)
    hours = d["T"] // C.HOUR
    return d, W, Y, hours


def build(parts):
    """parts: lista de (W, Y, hours, coin_ids). Devuelve la biblioteca y el retorno futuro de cada fila."""
    X, cc, tt, yy = [], [], [], []
    for W, Y, hours, ids in parts:
        for c in range(W.shape[0]):
            ok = np.isfinite(W[c]).all(1)
            X.append(W[c][ok]); cc.append(np.full(ok.sum(), ids[c])); tt.append(hours[ok]); yy.append(Y[c][ok])
    X, cc, tt, yy = map(np.concatenate, (X, cc, tt, yy))
    lib = C.Library(X, cc, tt)
    o = np.lexsort((cc, tt))
    return lib, yy[o]


def run_queries(lib, ly, W, Y, hours, d, coins_filter=None, k=100, step_bars=1):
    T = d["T"]
    qc, qt = C.queries(T, W.shape[0], C.TRAIN_END, T[-1] - H * step_bars * C.HOUR, STRIDE // step_bars or 1)
    I, D = C.knn(lib, W[qc, qt], hours[qt], k, lag=C.MARGIN)
    return qc, qt, I, D


def main():
    t0 = time.time()
    base, Wb, Yb, hb = block(C.BASE)
    others = [f[:-8] for f in sorted(os.listdir(os.path.join(NEW20, "klines"))) if f[:-8] not in C.BASE]
    oth, Wo, Yo, ho = block(others, dirs=[NEW20])
    print(f"[S5] {len(others)} monedas extra desde {C.iso(oth['T'][0])}", flush=True)
    end = int(base["T"][-1])
    rows, info = [], {}
    libs = {"1 moneda": None, "4 monedas": build([(Wb, Yb, hb, np.arange(4))]),
            "23 monedas": build([(Wb, Yb, hb, np.arange(4)), (Wo, Yo, ho, 4 + np.arange(len(others)))])}
    preds = {}
    for name, lb in libs.items():
        t1 = time.time()
        if lb is None:                                       # biblioteca de la misma moneda: una por moneda
            qc_all, qt_all, I_all, D_all, ly_all = [], [], [], [], []
            for c in range(4):
                lib, ly = build([(Wb[c:c + 1], Yb[c:c + 1], hb, np.array([c]))])
                qc, qt, I, D = run_queries(lib, ly, Wb[c:c + 1], Yb[c:c + 1], hb, base)
                yhat, frac = {}, {}
                qc_all.append(np.full(len(qt), c)); qt_all.append(qt)
                for k in (30, 100):
                    yhat[k], frac[k] = C.predict(ly, I, D, k, False)
                ly_all.append((yhat, frac))
            qc = np.concatenate(qc_all); qt = np.concatenate(qt_all)
            P = {k: (np.concatenate([x[0][k] for x in ly_all]), np.concatenate([x[1][k] for x in ly_all])) for k in (30, 100)}
            same = 1.0
        else:
            lib, ly = lb
            qc, qt, I, D = run_queries(lib, ly, Wb, Yb, hb, base)
            P = {k: C.predict(ly, I, D, k, False) for k in (30, 100)}
            ok = I[:, :30] >= 0
            same = float((lib.coin[np.maximum(I[:, :30], 0)] == qc[:, None])[ok].mean())
        preds[name] = (qc, qt, P)
        info[name] = {"vecinos_de_la_misma_moneda": round(same, 3), "segundos": round(time.time() - t1)}
        y = Yb[qc, qt]
        for k in (30, 100):
            for q in S1.QS:
                r = C.evaluate(base["T"][qt], qc, *P[k], y, H, q, end)
                rows.append({"biblioteca": name, "filtro_4h": 0, "k": k, "q": q, **r})
        print(f"[S5] {name}: {info[name]}", flush=True)
    # filtro de 4 h (biblioteca de las 4 monedas base, velas de 4 h)
    d4, W4, Y4, h4 = block(C.BASE, step=4, L=24, h=6)
    lib4, ly4 = build([(W4, Y4, h4, np.arange(4))])
    qc4, qt4 = np.repeat(np.arange(4), W4.shape[1]), np.tile(np.arange(W4.shape[1]), 4)
    ok4 = np.isfinite(W4[qc4, qt4]).all(1) & (d4["T"][qt4] >= C.TRAIN_END - 30 * 24 * C.HOUR)
    I4, D4 = C.knn(lib4, W4[qc4[ok4], qt4[ok4]], h4[qt4[ok4]] + 4, 30, lag=C.MARGIN + 4)   # +4: la vela cierra 4 h después
    yh4 = np.full((4, W4.shape[1]), np.nan)
    yh4[qc4[ok4], qt4[ok4]] = C.predict(ly4, I4, D4, 30, False)[0]
    for name, (qc, qt, P) in preds.items():
        close_ms = base["T"][qt] + C.HOUR
        j = np.searchsorted(d4["T"] + 4 * C.HOUR, close_ms, "right") - 1     # última vela de 4 h ya cerrada
        f4 = np.where(j >= 0, yh4[qc, np.maximum(j, 0)], np.nan)
        y = Yb[qc, qt]
        for k in (30, 100):
            yhat, frac = P[k]
            frac = np.where(np.nan_to_num(f4, nan=-1) >= 0, frac, 0.0)
            for q in S1.QS:
                r = C.evaluate(base["T"][qt], qc, yhat, frac, y, H, q, end)
                rows.append({"biblioteca": name, "filtro_4h": 1, "k": k, "q": q, **r})
    S1.write_csv(rows, "s5_rejilla.csv")
    best = C.best_on_design(rows)
    por = {f"{b}, filtro 4h {'sí' if f else 'no'}": C.best_on_design([r for r in rows if r["biblioteca"] == b and r["filtro_4h"] == f])
           for b in libs for f in (0, 1)}
    C.save_json({"mejor_en_diseno": best, "pasa_criterio": C.passes(best) if best else False, "por_variante": por,
                 "bibliotecas": info, "monedas_extra": others}, "s5_resumen.json")
    print(f"[S5] Mejor en diseño: {S1.flat(best) if best else None}")
    print(f"[S5] ¿Pasa el criterio? {C.passes(best) if best else False}  ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
