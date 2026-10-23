"""Ronda 1 - Paso 7: ¿existe un subconjunto de señales MR cuyo retorno futuro BRUTO supere c = 0.24 %?
Ridge walk-forward (mensual, expansivo, con purga de h velas) que predice ret_h = c[i+h]/c[i]-1 de cada señal
MR(20,2,R>=0.5%) con las 41 variables + hora (sen/cos) + moneda. Se mide, fuera de muestra:
  - correlación de rangos (Spearman) entre predicción y realizado,
  - retorno bruto medio del decil / quintil superior (umbral = cuantil de las predicciones de ENTRENAMIENTO),
    no solapado por moneda, en DISEÑO-A (2023-10..2024-03) y DISEÑO-B (2024-04..2025-06).
Además se reevalúa el meta-labeling logístico (paso 5) con E en % y su t."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import datetime as dt
from scipy import stats
import analista_common as ac
import analista_features as af


def ridge(X, y, lam):
    Xb = np.hstack([np.ones((len(X), 1)), X])
    L = lam * np.eye(Xb.shape[1]); L[0, 0] = 0
    return np.linalg.solve(Xb.T @ Xb + L, Xb.T @ y)


def main():
    lines = []
    P = lambda s: (print(s), lines.append(s))
    data = {s: ac.load(s) for s in ac.SYMS}
    Fs = {s: af.build(data[s], 20) for s in ac.SYMS}
    Fs = af.add_cross(Fs, ac.SYMS)
    feats = [f for f in af.FEATURES if f not in ("hour", "dow")]
    n_cfg = 0
    for h in (16, 48, 96):
        Xs, ys, Ts, syms, idxs = [], [], [], [], []
        for si, s in enumerate(ac.SYMS):
            d = data[s]; F = Fs[s]; c = d["c"]
            with np.errstate(invalid="ignore"):
                idx = np.where((F["z"] < -2) & (F["R_pct"] >= 0.005))[0]
            idx = idx[(idx >= 900) & (idx + h < len(c))]
            X = np.column_stack([F[f][idx] for f in feats] +
                                [np.sin(2 * np.pi * F["hour"][idx] / 24), np.cos(2 * np.pi * F["hour"][idx] / 24)] +
                                [np.full(len(idx), 1.0 if j == si else 0.0) for j in range(4)])
            Xs.append(X); ys.append(c[idx + h] / c[idx] - 1); Ts.append(d["t"][idx]); syms.append(np.full(len(idx), si)); idxs.append(idx)
        X = np.vstack(Xs); y = np.concatenate(ys); T = np.concatenate(Ts); S = np.concatenate(syms); I = np.concatenate(idxs)
        pred = np.full(len(y), np.nan)
        thr = {q: np.full(len(y), np.nan) for q in (0.8, 0.9)}
        months = sorted(set(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m") for t in T))
        for mth in [m for m in months if m >= "2023-10"]:
            y0, m0 = int(mth[:4]), int(mth[5:])
            start = dt.datetime(y0, m0, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
            end = dt.datetime(y0 + (m0 == 12), 1 if m0 == 12 else m0 + 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
            tr = T + h * 900000 < start           # purga: el retorno de entrenamiento ya se conocía
            te = (T >= start) & (T < end)
            if not te.any():
                continue
            mu = np.nanmean(X[tr], 0); sd = np.nanstd(X[tr], 0); sd[sd == 0] = 1
            Z = lambda A: np.nan_to_num(np.clip((A - mu) / sd, -5, 5))
            yt = np.clip(y[tr], -0.2, 0.2)
            w = ridge(Z(X[tr]), yt, lam=float(tr.sum()) * 0.1)
            ptr = np.hstack([np.ones((tr.sum(), 1)), Z(X[tr])]) @ w
            pred[te] = np.hstack([np.ones((te.sum(), 1)), Z(X[te])]) @ w
            for q in thr:
                thr[q][te] = np.quantile(ptr, q)
        ok = ~np.isnan(pred)
        A = T < ac.SPLIT_AB_MS
        P(f"\n=== h = {h} velas ({h/4:.0f} h) ===")
        for part, pm in (("A", ok & A), ("B", ok & ~A)):
            rho, pv = stats.spearmanr(pred[pm], y[pm])
            P(f"  {part}: Spearman(pred, ret_h) = {rho:+.3f} (p={pv:.3g}, N señales={pm.sum()})")
            for q in (None, 0.8, 0.9):
                sel_all = pm if q is None else pm & (pred >= thr[q])
                rs = []
                for si in range(4):
                    ii = np.where(sel_all & (S == si))[0]
                    ii = ii[np.argsort(I[ii])]
                    last = -10 ** 9; keep = []
                    for j in ii:
                        if I[j] >= last + h:
                            keep.append(j); last = I[j]
                    rs.append(y[keep])
                r = np.concatenate(rs)
                n_cfg += 1
                t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
                tn = (r.mean() - ac.COST) / (r.std(ddof=1) / np.sqrt(len(r)))
                lab = "todas" if q is None else f"top {int((1-q)*100)}%"
                P(f"     {lab:8s}: N={len(r):4d} ret bruto medio={r.mean()*100:+.3f}% (t={t:+.1f}) "
                  f"neto={(r.mean()-ac.COST)*100:+.3f}% (t={tn:+.1f}) P(neto>0)={(r > ac.COST).mean()*100:.1f}%")
    P(f"\nConfiguraciones en este script: {n_cfg} (3 horizontes x 3 cortes x 2 partes; ridge sin ajuste de lambda)")
    with open(os.path.join(ac.OUTDIR, "07_ridge.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
