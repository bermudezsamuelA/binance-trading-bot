"""R2-E5/E6 Segunda etapa parsimoniosa (DISENO). Pre-registro (escrito antes de correr):

Filas: velas de la pila (p >= theta y A(W=48) >= 1). Etiqueta: resultado X5 por vela > 0.
Variables (causales, en la vela t de la moneda i):
  LR5: A (n.o de otras monedas con senal en 48 velas), p - theta, max_{j != i} max_{48 velas} p_j - theta,
       retorno log de BTC en 16 velas (4 h), hora UTC (seno y coseno).
  LR6: LR5 + fraccion de las 18 monedas (4 + 14 spot del verificador, solo precio) cuyo cierre esta >= 1 sigma de 4 h
       (4 * sigma15(672) * c) por encima de su minimo de 16 velas ("ya rebotaron desde el minimo de 4 h").
Entrenamiento walk-forward: en el pliegue k (k >= 1) se entrena SOLO con las filas de la pila de los pliegues 0..k-1,
purgando las filas cuya etiqueta (288 velas) entra en el pliegue k. Regresion logistica L2 (C = 1), variables
estandarizadas con la media y desviacion del entrenamiento. Pliegue 0: sin filtro (= pila).
Umbral: se conserva la fila si p2 >= cuantil q de p2 en las filas de entrenamiento; q in {0.25, 0.50}.
4 configuraciones (LR5, LR6) x (q25, q50). Replica en ENS13, ENS12 y ENS12U.
"""
import os, sys
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H, C = E.B, E.H, E.C

VER = os.path.join(B.RESEARCH, "verificador", "data")


def rebound_frac(tg):
    """Fraccion de las 18 monedas con c >= min(l, 16) * ... (>= 1 sigma de 4 h sobre el minimo de 16 velas)."""
    syms = list(H.SYMBOLS) + B.OTHER18
    flags = []
    for s in syms:
        if s in H.SYMBOLS:
            a = C.load_spot(C.RESEARCH, s)
        else:
            a = np.load(os.path.join(VER, f"{s}_15m.npy"))
        a = a[a[:, 0] < H.DESIGN[1]]
        t, l, c = a[:, 0].astype(np.int64), a[:, 3], a[:, 4]
        lr = np.diff(np.log(c), prepend=np.nan)
        s15 = H.rolling_std(lr, 672)
        mn = H.rolling_min(l, 16)
        f = np.where(np.isfinite(s15) & np.isfinite(mn), ((c - mn) / (c * s15 * 4) >= 1).astype(float), np.nan)
        j = np.searchsorted(t, tg)
        ok = (j < len(t)) & (t[np.minimum(j, len(t) - 1)] == tg)
        g = np.full(len(tg), np.nan)
        g[ok] = f[j[ok]]
        flags.append(g)
    F = np.array(flags)
    return np.nanmean(F, 0), np.sum(np.isfinite(F), 0)


def features(D, reb):
    N = len(D["tg"])
    Pg = E.to_grid(D, D["p"], np.nan)
    Rm = np.array([H.rolling_max(np.nan_to_num(g, nan=-1.0), E.W) for g in Pg])
    mo = np.full(len(D["rows"]), -np.inf)
    for j in range(4):
        v = Rm[j, D["jrow"]]
        mo = np.where(D["ci"] != j, np.maximum(mo, v), mo)
    btc_c = D["cache"]["BTCUSDT"]["c"]
    lb = np.log(btc_c)
    r16 = lb - np.concatenate([np.full(16, np.nan), lb[:-16]])
    hr = ((D["t"] // 3_600_000) % 24).astype(float)
    X5 = np.column_stack([D["A"].astype(float), D["p"] - D["thr"], mo - D["thr"], r16[D["jrow"]],
                          np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)])
    X6 = np.column_stack([X5, reb[D["jrow"]]])
    return X5, X6


def stage2_mask(D, X, q):
    keep = D["stack"].copy()
    y = (D["netX"] > 0).astype(int)
    coefs = []
    for k in range(1, 6):
        t0 = H.ms(*B.TESTS[k][0], 1)
        tr = D["stack"] & (D["fold"] < k) & np.isfinite(D["netX"]) & (D["t"] < t0 - (288 + 1) * C.MS15) \
            & np.all(np.isfinite(X), 1)
        te = D["stack"] & (D["fold"] == k)
        if tr.sum() < 30 or len(np.unique(y[tr])) < 2 or te.sum() == 0:
            coefs.append(None)
            continue
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-12
        m = LogisticRegression(C=1.0, max_iter=2000).fit((X[tr] - mu) / sd, y[tr])
        ptr = m.predict_proba((X[tr] - mu) / sd)[:, 1]
        thr = np.quantile(ptr, q)
        Xt = np.nan_to_num((X[te] - mu) / sd)
        pte = m.predict_proba(Xt)[:, 1]
        kk = np.zeros(len(keep), bool); kk[np.where(te)[0][pte >= thr]] = True
        keep = np.where(te, kk, keep)
        coefs.append(dict(n_train=int(tr.sum()), base=float(y[tr].mean()), coef=m.coef_[0].round(3).tolist(),
                          keep_frac=float(np.mean(pte >= thr))))
    return keep, coefs


def run(ens, reb):
    D = E.load(ens)
    ref = E.trade_table(D, D["stack"], D["A"] >= 1)
    res = {"pila": dict(summary=E.summ(ref, "pila v2 + A≥1"))}
    X5, X6 = features(D, reb)
    # descriptivo: rebote de mercado en las operaciones de la pila
    rowg = E.to_grid(D, np.arange(len(D["rows"])), -1, int)
    rr = rowg[ref["sidx"], ref["sig_idx"]]
    rb = X6[rr, -1]
    desc = {}
    for lo, hi in ((0, 0.1), (0.1, 0.25), (0.25, 0.5), (0.5, 1.01)):
        s = (rb >= lo) & (rb < hi)
        if s.any():
            desc[f"reb {lo}-{hi}"] = (int(s.sum()), float(np.mean(ref['x'][s] > 0)), float(ref["x"][s].mean() * 100))
    res["desc_reb"] = desc
    for nm, X in (("LR5", X5), ("LR6 (+rebote 18 monedas)", X6)):
        for q in (0.25, 0.50):
            mask, coefs = stage2_mask(D, X, q)
            t = E.trade_table(D, mask, D["A"] >= 1)
            lab = f"{nm} q{int(q*100)}"
            r = E.summ(t, lab); c = E.compare(t, ref)
            res[lab] = dict(summary=r, compare=c, coefs=coefs)
            print(ens, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} "
                  f"P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", flush=True)
    return res


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    D0 = B.load_ens()
    tg = D0["cache"]["BTCUSDT"]["t"].astype(np.int64)
    reb, nav = rebound_frac(tg)
    print("rebote: monedas disponibles min/med", int(nav.min()), float(np.median(nav)), "media", float(np.nanmean(reb)))
    res = {ens: run(ens, reb) for ens in ens_list}
    E.log_once("stage2", 4, "R2-E5/E6 segunda etapa logistica WF: LR5, LR6 (+rebote 18 monedas spot) x q{0.25,0.5}")
    E.jdump(res, os.path.join(E.OUT2, "be2_stage2.json"))
    L = ["# R2-E5/E6 segunda etapa logística en walk-forward\n", E.HEAD, E.HEAD2]
    labs = [k for k in res[ens_list[0]] if k != "desc_reb"]
    for lab in labs:
        for ens in ens_list:
            L.append(E.row(ens, res[ens][lab]["summary"], res[ens][lab].get("compare")))
    L.append("")
    for lab in labs[1:]:
        ok, why = E.candidate({ens: res[ens][lab]["compare"] for ens in ens_list})
        L.append(f"- {lab}: {'CANDIDATA' if ok else 'no'} — {why}")
        for ens in ens_list:
            L.append(E.detail(ens, res[ens][lab]["summary"], res[ens][lab]["compare"]))
            L.append(f"  - coeficientes por pliegue (A, p−θ, max otras−θ, BTC 4h, sen h, cos h[, rebote]): {res[ens][lab]['coefs']}")
    L.append("\nDescriptivo: operaciones de la pila por fracción de monedas rebotadas (n, WR, E %):\n")
    for ens in ens_list:
        L.append(f"- {ens}: " + "; ".join(f"{k}: {n}·{w*100:.0f}%·{e:+.2f}" for k, (n, w, e) in res[ens]["desc_reb"].items()))
    with open(os.path.join(E.OUT2, "be2_stage2.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
