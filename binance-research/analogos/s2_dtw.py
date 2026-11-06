"""Sugerencia 2: DTW con banda de Sakoe-Chiba sobre los candidatos euclidianos (doc/plan-analogos.md).

Pasos: (1) M candidatos con la distancia euclidiana de la sugerencia 1; (2) se re-ordenan con DTW de banda r;
(3) un vecino por episodio y los k mejores; (4) opcional: el futuro del vecino se mide en h' = round(h*s) velas, con s la
pendiente del camino en el último 30 % de la ventana. Como h' puede llegar a 2h, aquí el margen de la biblioteca es
2 * max(h) = 48 velas para todas las variantes (r = 0 incluida), así la comparación es justa y sin fuga.
La cota LB_Keogh no hace falta con M candidatos fijos: se calcula DTW de todos ellos (es exacto dentro de los M).

Uso: python s2_dtw.py [--L 48] [--rapido]
"""
import argparse
import itertools
import time
from types import SimpleNamespace

import numpy as np

import common as C
import s1_knn as S1

LAG = 48
M = 200
RS = [0.0, 0.05, 0.10, 0.20]


def dtw_batch(A, Bm, R, want_dirs=False):
    """DTW con banda |i-j| <= R. A: (b, L), Bm: (b, m, L). Devuelve la distancia (b, m) y las direcciones del camino."""
    b, m, L = Bm.shape
    inf = np.float32(1e30)
    prev = np.full((b, m, L + 1), inf, np.float32)
    prev[:, :, 0] = 0
    dirs = np.zeros((b, m, L, L), np.int8) if want_dirs else None
    for i in range(1, L + 1):
        cur = np.full((b, m, L + 1), inf, np.float32)
        ai = A[:, None, i - 1]
        for j in range(max(1, i - R), min(L, i + R) + 1):
            c = (ai - Bm[:, :, j - 1]) ** 2
            up, left, diag = prev[:, :, j], cur[:, :, j - 1], prev[:, :, j - 1]
            best = np.minimum(np.minimum(up, left), diag)
            cur[:, :, j] = c + best
            if want_dirs:
                dirs[:, :, i - 1, j - 1] = np.where(diag <= np.minimum(up, left), 2, np.where(up <= left, 0, 1))
        prev = cur
    return np.sqrt(prev[:, :, L]), dirs


def path_speed(dirs, tail=0.3):
    """Pendiente Δj/Δi del camino óptimo en el último `tail` de la ventana. dirs: (b, m, L, L)."""
    b, m, L, _ = dirs.shape
    i = np.full((b, m), L - 1); j = np.full((b, m), L - 1)
    i0 = int(L * (1 - tail))
    j_at = np.full((b, m), -1)
    bb, mm = np.meshgrid(np.arange(b), np.arange(m), indexing="ij")
    for _ in range(2 * L):
        hit = (i <= i0) & (j_at < 0)
        j_at[hit] = j[hit]
        done = (i == 0) & (j == 0)
        if done.all():
            break
        d = dirs[bb, mm, i, j]
        d = np.where(i == 0, 1, np.where(j == 0, 0, d))
        i = np.where(done, i, i - (d != 1))
        j = np.where(done, j, j - (d != 0))
    j_at[j_at < 0] = 0
    return (L - 1 - j_at) / max(L - 1 - i0, 1)


def rerank(data, L, multi=False, r=0.1, k=30, scaled=False, block=128):
    W = C.shape_windows(data["close"], L, "forma")
    nb = S1.neighbors(data, W, multi, lag=LAG, cand=M, return_cand=True)
    lib = SimpleNamespace(coin=nb["lib_coin"], t=nb["lib_t"])
    R = int(np.ceil(r * L))
    nq = len(nb["qt"])
    I = np.full((nq, k), -1, np.int64); Dd = np.full((nq, k), np.inf, np.float32); S = np.ones((nq, k))
    for s in range(0, nq, block):
        rows = np.arange(s, min(s + block, nq))
        cand = nb["I"][rows]
        ok = cand >= 0
        cc = np.maximum(cand, 0)
        A = W[nb["qc"][rows], nb["qt"][rows]]
        Bm = W[lib.coin[cc], lib.t[cc]]
        if R == 0:
            d = np.sqrt(((A[:, None, :] - Bm) ** 2).sum(2))
        else:
            d, _ = dtw_batch(A, Bm, R)
        d = np.where(ok, d, np.inf)
        o = np.argsort(d, 1, kind="stable")
        p, g = np.take_along_axis(cand, o, 1), np.take_along_axis(d, o, 1)
        p, g = C.episode_filter(lib, p, g, C.SEP, k)
        I[rows], Dd[rows] = p, g
        if scaled and R > 0:
            pp = np.maximum(p, 0)
            _, dirs = dtw_batch(A, W[lib.coin[pp], lib.t[pp]], R, want_dirs=True)
            S[rows] = path_speed(dirs)
    return nb, I, Dd, S


def evaluate(data, nb, I, Dd, S, hs=(12, 24), ks=(10, 30), qs=S1.QS, scaled=False, label=None):
    T, lp = data["T"], np.log(data["close"])
    rows = []
    for h in hs:
        y = C.future_returns(data["close"], h)[nb["qc"], nb["qt"]]
        ok = I >= 0
        c, t = nb["lib_coin"][np.maximum(I, 0)], nb["lib_t"][np.maximum(I, 0)]
        hh = np.clip(np.rint(h * S), h // 2, 2 * h).astype(int) if scaled else np.full(I.shape, h)
        tt = np.minimum(t + hh, lp.shape[1] - 1)
        F = np.where(ok, lp[c, tt] - lp[c, t], np.nan)
        for k in ks:
            Fk = F[:, :k]
            n = np.isfinite(Fk).sum(1)
            yhat = np.where(n > 0, np.nansum(Fk, 1) / np.maximum(n, 1), np.nan)
            frac = np.where(n > 0, (Fk > 0).sum(1) / np.maximum(n, 1), np.nan)
            for q in qs:
                r = C.evaluate(T[nb["qt"]], nb["qc"], yhat, frac, y, h, q, int(T[-1]))
                rows.append({**(label or {}), "h": h, "k": k, "q": q, **r})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--L", type=int, default=48)
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args(argv)
    data = C.load_hourly(C.BASE)
    rows = []
    for r in ([0.0, 0.1] if a.rapido else RS):
        for scaled in ((False, True) if r > 0 else (False,)):
            t0 = time.time()
            nb, I, Dd, S = rerank(data, a.L, r=r, scaled=scaled)
            rows += evaluate(data, nb, I, Dd, S, scaled=scaled, label={"L": a.L, "r": r, "h_escalado": int(scaled)})
            print(f"[S2] r={r} escalado={scaled}: {time.time() - t0:.0f} s; pendiente media {np.nanmean(S):.2f}", flush=True)
    S1.write_csv(rows, "s2_rejilla.csv")
    best = C.best_on_design(rows)
    por_r = {f"r={r}, h' {'escalado' if s else 'fijo'}": C.best_on_design([x for x in rows if x["r"] == r and x["h_escalado"] == s])
             for r in RS for s in (0, 1) if any(x["r"] == r and x["h_escalado"] == s for x in rows)}
    C.save_json({"mejor_en_diseno": best, "pasa_criterio": C.passes(best) if best else False, "por_variante": por_r}, "s2_resumen.json")
    print(f"[S2] Mejor en diseño: {S1.flat(best) if best else None}")
    print(f"[S2] ¿Pasa el criterio? {C.passes(best) if best else False}")


if __name__ == "__main__":
    main()
