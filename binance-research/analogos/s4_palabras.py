"""Sugerencia 4: patrones como palabras (SAX simple) con conteo en línea (doc/plan-analogos.md).

Cada vela se traduce a un símbolo según su retorno estandarizado r_t / sigma_30d, con cortes en cuantiles del periodo de
entrenamiento. Una palabra son los últimos n símbolos. Para la consulta t solo se cuentan las apariciones con s <= t - 24
(su resultado ya se conoce), juntando las 4 monedas. Se compra si la palabra apareció al menos min_n veces, la cota
inferior de Wilson de P(sube) supera la tasa base y el retorno medio supera el costo. Con corrección de Bonferroni,
z se ajusta al número de palabras posibles.

Uso: python s4_palabras.py
"""
import itertools
import math
import time

import numpy as np
from scipy.stats import norm

import common as C
import s1_knn as S1


def symbols(data, levels: int):
    lp = np.log(data["close"])
    r = np.full_like(lp, np.nan); r[:, 1:] = np.diff(lp, axis=1)
    r0 = np.nan_to_num(r)
    c = np.concatenate([np.zeros((lp.shape[0], 1)), np.cumsum(r0 ** 2, 1)], 1)
    s30 = np.full_like(lp, np.nan); s30[:, 720:] = np.sqrt((c[:, 720 + 1:] - c[:, 1:-720]) / 720)
    z = r / s30
    tr = data["T"] < C.TRAIN_END
    cuts = np.nanquantile(z[:, tr], np.linspace(0, 1, levels + 1)[1:-1])
    s = np.digitize(z, cuts)
    s[~np.isfinite(z)] = -1
    return s, cuts


def words(s, n, levels):
    nc, T = s.shape
    w = np.full((nc, T), -1, np.int64)
    for t in range(n - 1, T):
        blk = s[:, t - n + 1:t + 1]
        ok = (blk >= 0).all(1)
        w[ok, t] = (blk[ok] * (levels ** np.arange(n))).sum(1)
    return w


def wilson_low(up, n, z):
    if n == 0:
        return 0.0
    p = up / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def run(data, n, levels, h, min_n, bonf, stride=S1.STRIDE):
    s, _ = symbols(data, levels)
    W = words(s, n, levels)
    Y = C.future_returns(data["close"], h)
    T = data["T"]
    nc, N = W.shape
    qc, qt = C.queries(T, nc, C.TRAIN_END, T[-1] - 24 * C.HOUR, stride)
    order = np.argsort(qt, kind="stable")
    z = norm.ppf(1 - 0.05 / (levels ** n)) if bonf else norm.ppf(0.95)
    cnt, up, sy = {}, {}, {}
    tot = [0, 0]
    added = 720 + n
    yhat = np.full(len(qt), np.nan); frac = np.zeros(len(qt))
    for i in order:
        t = qt[i]
        while added <= t - 24:                                   # entran las horas cuyo futuro ya terminó
            for c in range(nc):
                w, y = W[c, added], Y[c, added]
                if w >= 0 and np.isfinite(y):
                    cnt[w] = cnt.get(w, 0) + 1; up[w] = up.get(w, 0) + (y > 0); sy[w] = sy.get(w, 0.0) + y
                    tot[0] += 1; tot[1] += y > 0
            added += 1
        w = W[qc[i], t]
        k = cnt.get(w, 0)
        if w < 0 or k < min_n:
            continue
        yhat[i] = sy[w] / k
        frac[i] = 1.0 if wilson_low(up[w], k, z) > tot[1] / max(tot[0], 1) else 0.0
    y = Y[qc, qt]
    return C.evaluate(T[qt], qc, yhat, frac, y, h, 0.5, int(T[-1]))


def main():
    data = C.load_hourly(C.BASE)
    rows = []
    for n, levels, h, min_n, bonf in itertools.product([3, 4, 5, 6], [3, 4], [12, 24], [30, 100], [0, 1]):
        t0 = time.time()
        r = run(data, n, levels, h, min_n, bonf)
        rows.append({"n": n, "niveles": levels, "h": h, "min_apariciones": min_n, "bonferroni": bonf, **r})
    S1.write_csv(rows, "s4_rejilla.csv")
    best = C.best_on_design(rows, min_n=50)
    sin_corr = C.best_on_design([r for r in rows if not r["bonferroni"]], min_n=50)
    con_corr = C.best_on_design([r for r in rows if r["bonferroni"]], min_n=50)
    C.save_json({"mejor_en_diseno": best, "pasa_criterio": C.passes(best) if best else False,
                 "mejor_sin_correccion": sin_corr, "mejor_con_bonferroni": con_corr}, "s4_resumen.json")
    print(f"[S4] Mejor en diseño: {S1.flat(best) if best else None}")
    print(f"[S4] ¿Pasa el criterio? {C.passes(best) if best else False}")


if __name__ == "__main__":
    main()
