"""Ronda 1 - Paso 5: meta-labeling walk-forward dentro de DISEÑO (regresión logística L2, solo numpy).
Señal primaria: MR(n=20, k=2, R>=0.5%) en las 4 monedas (todas las velas con señal).
Etiqueta (triple barrera): y = 1 si la operación termina con r_neto > 0, con geometría
   GH: TP = mu, SL = c - m*R, barrera de tiempo H velas (m=1 -> b=1; m=2 -> b=0.5).
Walk-forward mensual expansivo con purga: para predecir el mes M se entrena solo con señales cuya SALIDA
ocurrió antes del inicio de M. Primer mes de prueba: 2023-10 (9 meses de entrenamiento). Nada del holdout.
Regla: operar si p_hat >= umbral, umbral = cuantil q de las p_hat del ENTRENAMIENTO (q = 0.5, 0.7, 0.8, 0.9).
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import datetime as dt
import analista_common as ac
import analista_features as af

N_WIN, K_MULT, MINR = 20, 2.0, 0.005


def logit_fit(X, y, lam=1.0, iters=30):
    n, p = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(p + 1)
    Lm = lam * np.eye(p + 1)
    Lm[0, 0] = 0
    for _ in range(iters):
        z = Xb @ w
        pr = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        g = Xb.T @ (pr - y) + Lm @ w
        W = pr * (1 - pr)
        Hm = (Xb * W[:, None]).T @ Xb + Lm
        step = np.linalg.solve(Hm, g)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return w


def logit_pred(w, X):
    return 1 / (1 + np.exp(-np.clip(np.hstack([np.ones((len(X), 1)), X]) @ w, -30, 30)))


def auc(y, s):
    o = np.argsort(s)
    r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def month_key(t):
    return dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m")


def main():
    lines = []
    P = lambda s: (print(s), lines.append(s))
    data = {s: ac.load(s) for s in ac.SYMS}
    Fs = {s: af.build(data[s], N_WIN) for s in ac.SYMS}
    Fs = af.add_cross(Fs, ac.SYMS)
    feats = [f for f in af.FEATURES if f not in ("hour", "dow")]
    n_cfg = 0
    summary = {}
    for (m_sl, H) in ((1.0, 48), (2.0, 96)):
        gname = f"TP=mu SL=c-{m_sl:.0f}R H={H}"
        P(f"\n================ Geometría {gname} ================")
        rows = []
        for si, s in enumerate(ac.SYMS):
            d = data[s]; F = Fs[s]; c = d["c"]
            with np.errstate(invalid="ignore"):
                idx = np.where((F["z"] < -K_MULT) & (F["R_pct"] >= MINR))[0]
            idx = idx[idx >= 900]
            tp = c[idx] * (1 + F["R_pct"][idx])
            sl = c[idx] * (1 - m_sl * F["R_pct"][idx])
            ex_i, ex_p, out = ac.first_touch(d, idx, tp, sl, H)
            r = ex_p / c[idx] - 1 - ac.COST
            X = np.column_stack([F[f][idx] for f in feats] +
                                [np.sin(2 * np.pi * F["hour"][idx] / 24), np.cos(2 * np.pi * F["hour"][idx] / 24)] +
                                [np.full(len(idx), 1.0 if j == si else 0.0) for j in range(4)])
            rows.append(dict(s=s, idx=idx, tp=tp, sl=sl, ex_i=ex_i, ex_p=ex_p, r=r, X=X,
                             t=d["t"][idx], tex=d["t"][np.minimum(ex_i, len(c) - 1)]))
        X = np.vstack([r["X"] for r in rows]); y = (np.concatenate([r["r"] for r in rows]) > 0).astype(float)
        T = np.concatenate([r["t"] for r in rows]); TEX = np.concatenate([r["tex"] for r in rows])
        sym = np.concatenate([[k] * len(r["idx"]) for k, r in enumerate(rows)])
        months = sorted(set(month_key(t) for t in T))
        test_months = [m for m in months if m >= "2023-10"]
        phat = np.full(len(y), np.nan)
        thr = {q: np.full(len(y), np.nan) for q in (0.5, 0.7, 0.8, 0.9)}
        coefs = []
        for mth in test_months:
            y0, m0 = int(mth[:4]), int(mth[5:])
            start = dt.datetime(y0, m0, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
            end = dt.datetime(y0 + (m0 == 12), 1 if m0 == 12 else m0 + 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
            tr = TEX < start
            te = (T >= start) & (T < end)
            if te.sum() == 0:
                continue
            Xtr = X[tr]; mu = np.nanmean(Xtr, 0); sd = np.nanstd(Xtr, 0); sd[sd == 0] = 1
            Z = lambda A: np.nan_to_num(np.clip((A - mu) / sd, -5, 5))
            w = logit_fit(Z(Xtr), y[tr], lam=50.0)
            coefs.append(w)
            ptr = logit_pred(w, Z(Xtr))
            phat[te] = logit_pred(w, Z(X[te]))
            for q in thr:
                thr[q][te] = np.quantile(ptr, q)
        ok = ~np.isnan(phat)
        A_mask = T < ac.SPLIT_AB_MS
        P(f"AUC fuera de muestra (todas las señales, walk-forward): total={auc(y[ok], phat[ok]):.3f} "
          f"A(2023-10..2024-03)={auc(y[ok & A_mask], phat[ok & A_mask]):.3f} B(2024-04..2025-06)={auc(y[ok & ~A_mask], phat[ok & ~A_mask]):.3f}")
        P(f"Tasa base de y=1 (r_neto>0) en señales probadas: {y[ok].mean()*100:.1f}%")
        # coeficientes medios (estandarizados) más grandes
        wm = np.mean(coefs, 0)[1:]
        names = feats + ["hour_sin", "hour_cos", "BTC", "ETH", "SOL", "DOGE"]
        top = np.argsort(-np.abs(wm))[:10]
        P("Coeficientes medios más grandes (estandarizados): " + ", ".join(f"{names[j]}={wm[j]:+.3f}" for j in top))
        # simulación secuencial por umbral
        for q in [None, 0.5, 0.7, 0.8, 0.9]:
            for part in ("A", "B", "all"):
                rn, RR, tt = [], [], []
                per = []
                for k, rw in enumerate(rows):
                    msk = (sym == k)
                    ph = phat[msk]; th = thr[q][msk] if q else None
                    sel = ~np.isnan(ph)
                    if q:
                        sel &= ph >= th
                    pa = rw["t"] < ac.SPLIT_AB_MS
                    if part == "A":
                        sel &= pa
                    elif part == "B":
                        sel &= ~pa
                    si_ = np.where(sel)[0]
                    tk = si_[ac.select_sequential(rw["idx"][si_], rw["ex_i"][si_])]
                    e = data[rw["s"]]["c"][rw["idx"][tk]]
                    rn.append(rw["r"][tk]); RR.append((e - rw["sl"][tk]) / e); tt.append(rw["t"][tk])
                    per.append(f"{rw['s'][:3]}:{len(tk)}/{(rw['r'][tk] > 0).mean()*100 if len(tk) else float('nan'):.0f}%")
                r_ = np.concatenate(rn); R_ = np.concatenate(RR); t_ = np.concatenate(tt)
                o = np.argsort(t_)
                mm = ac.metrics(r_[o], R_[o])
                n_cfg += 1
                mons = {"A": 6, "B": 15, "all": 21}[part]
                P(f"  {'sin filtro' if q is None else f'p>=q{int(q*100)}':10s} {part:3s} {ac.fmt(mm)} ops/mes={mm['N']/mons:.0f} | {' '.join(per)}")
                summary[f"{gname}|{q}|{part}"] = mm
    P(f"\nConfiguraciones evaluadas en este script: {n_cfg} (2 geometrías x 5 umbrales; cada una en A, B y total)")
    with open(os.path.join(ac.OUTDIR, "05_meta.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
