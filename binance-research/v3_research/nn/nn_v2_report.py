"""v2: evalua en el walk-forward de DISENO un ensamble entrenado con etiquetas G3 y operado con otra geometria de
salida, con umbral elegido SOLO en validacion bajo WR_val >= wr_min. No modifica nada de la v1 (solo importa).

Uso: python -I nn_v2_report.py --preds tagA,tagB --exit X3 --wrmin 0.75 [--regime none|btc30] [--label txt]
"""
import argparse, os, sys, json, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_common as C
import nn_report as R
H = C.H

# geometrias de salida v2 (a, m, H) con b entre 0.4 y 0.7
GEOMS_V2 = {"X1": (0.6, 1.5, 192), "X2": (0.8, 2.0, 288), "X3": (0.75, 1.5, 288), "X4": (1.0, 2.0, 288),
            "X5": (0.7, 1.75, 288)}
C.GEOMS.update(GEOMS_V2)
CACHE = R.CACHE
LAB = os.path.join(C.RESEARCH, "tmp", "nn_cache_v2")
os.makedirs(LAB, exist_ok=True)
OUTD = os.path.join(C.RESEARCH, "output", "constructor")


# Geometrias con las que se generaron las etiquetas que ya estan en LAB con el nombre corto {sym}_{geom}.npy.
LEGACY_LAB = {"X1": (0.6, 1.5, 192), "X2": (0.8, 2.0, 288), "X3": (0.75, 1.5, 288), "X4": (1.0, 2.0, 288),
              "X5": (0.7, 1.75, 288)}


def label_path(s, exit_geom):
    """Archivo de etiquetas de LAB. La clave incluye la geometria completa (TP, SL y barrera de tiempo H): una corrida
    con H 384 ya no reutiliza las etiquetas de H 288. Las geometrias de LEGACY_LAB conservan su archivo de siempre."""
    a, m, Hh = C.GEOMS[exit_geom]
    if LEGACY_LAB.get(exit_geom) == (a, m, Hh):
        return os.path.join(LAB, f"{s}_{exit_geom}.npy")
    return os.path.join(LAB, f"{s}_{exit_geom}_a{a:g}_m{m:g}_H{Hh}.npy")


def load_cache(exit_geom):
    cache = {}
    for s in H.SYMBOLS:
        z = dict(np.load(os.path.join(CACHE, f"{s}.npz")))
        if f"net_{exit_geom}" not in z:
            p = label_path(s, exit_geom)
            if not os.path.exists(p):
                a = C.load_spot(C.RESEARCH, s)
                a = a[a[:, 0] < H.DESIGN[1]]
                S = C.spot_core(a)
                net, _, _ = C.label_all(S, exit_geom, len(S["c"]))
                np.save(p, net)
            z[f"net_{exit_geom}"] = np.load(p)
        cache[s] = z
    return cache


def btc_regime(n_needed):
    """1 si BTC cierra por encima de su SMA de 30 dias (2880 velas), causal."""
    a = C.load_spot(C.RESEARCH, "BTCUSDT")
    a = a[a[:, 0] < H.DESIGN[1]]
    sma = H.rolling_mean(a[:, 4], 2880)
    return a[:, 0].astype(np.int64), (a[:, 4] > sma)


OBJ = {"v": "E"}


def choose(p, net, day, wr_min):
    """Cuantil de p en validacion: maximiza E (OBJ=E) o el numero de velas (OBJ=n) sujeto a WR >= wr_min, E > 0."""
    best = None
    for q in R.QS + [0.997]:
        thr = float(np.quantile(p, q))
        sel = p >= thr
        n = int(sel.sum())
        if n < R.MIN_VAL or len(np.unique(day[sel])) < R.MIN_DAYS:
            continue
        wr = float(np.mean(net[sel] > 0)); e = float(np.mean(net[sel]))
        key = e if OBJ["v"] == "E" else n
        if e > 0 and wr >= wr_min and (best is None or key > best[5]):
            best = (thr, wr, e, n, q, key)
    return best


def run(tags, exit_geom, wr_min, regime="none", label=None, verbose=True, n_configs=1):
    P = [np.load(os.path.join(R.PRED, f"{tg}.npz")) for tg in tags]
    cache = load_cache(exit_geom)
    ci, ii, t, netG3 = P[0]["ci"], P[0]["ii"], P[0]["t"], P[0]["net"]
    yG3 = (netG3 > 0).astype(float)
    netX = np.concatenate([cache[s][f"net_{exit_geom}"] for s in H.SYMBOLS])
    reg_ok = np.ones(len(t), bool)
    if regime == "btc30":
        bt, up = btc_regime(len(t))
        j = np.searchsorted(bt, t); j = np.minimum(j, len(bt) - 1)
        reg_ok = (bt[j] == t) & up[j]
    nf = sum(1 for k in P[0].files if k.endswith("_val_rows"))
    entries = {s: np.zeros(len(cache[s]["c"]), bool) for s in H.SYMBOLS}
    periods = {s: [] for s in H.SYMBOLS}
    folds = []
    for k in range(nf):
        vr, tr_ = P[0][f"f{k}_val_rows"], P[0][f"f{k}_tst_rows"]
        pv = np.zeros(len(vr)); pt = np.zeros(len(tr_))
        for p in P:
            ab = R.platt_fit(p[f"f{k}_val_s"], yG3[vr])
            pv += R.platt_apply(p[f"f{k}_val_s"], ab) / len(P)
            pt += R.platt_apply(p[f"f{k}_tst_s"], ab) / len(P)
        # purga de la geometria de salida: la etiqueta de validacion no puede usar velas del test
        hx = C.GEOMS[exit_geom][2]
        okv = reg_ok[vr] & np.isfinite(netX[vr]) & (t[vr] < t[tr_].min() - (hx + 1) * C.MS15)
        ch = choose(pv[okv], netX[vr][okv], (t[vr] // 86_400_000)[okv], wr_min)
        for ci_, s in enumerate(H.SYMBOLS):
            rows = tr_[ci[tr_] == ci_]
            if len(rows):
                periods[s].append((int(ii[rows].min()), int(ii[rows].max()) + 1))
        if ch is not None:
            sel = tr_[(pt >= ch[0]) & reg_ok[tr_]]
            for ci_, s in enumerate(H.SYMBOLS):
                entries[s][ii[sel[ci[sel] == ci_]]] = True
        folds.append(None if ch is None else (round(ch[0], 3), ch[4], round(ch[1], 3), round(ch[2] * 100, 2)))
    base = R.random_baseline(cache, exit_geom)
    lab = label or f"{'+'.join(tags)} exit={exit_geom} wr>={wr_min} reg={regime}"
    trs = R.simulate_rows(cache, exit_geom, entries, periods)
    res = R.summarize(trs, base, n_configs, lab)
    trs_s = R.simulate_rows(cache, exit_geom, entries, periods, fee=0.0013, slip=0.0002)
    res_s = R.summarize(trs_s, base, n_configs, lab + " [c=0.30%]")
    out = {"main": res[0] if isinstance(res, tuple) else res, "stress": res_s[0] if isinstance(res_s, tuple) else res_s,
           "folds": folds}
    if isinstance(res, tuple):
        T = res[1]
        out["_T"], out["_syms"] = T, res[2]
        fe = []
        for te0, te1 in [((2024, 1), (2024, 4)), ((2024, 4), (2024, 7)), ((2024, 7), (2024, 10)),
                         ((2024, 10), (2025, 1)), ((2025, 1), (2025, 4)), ((2025, 4), (2025, 7))]:
            s_ = (T.entry_t >= H.ms(*te0, 1)) & (T.entry_t < H.ms(*te1, 1))
            fe.append((int(s_.sum()), round(float(np.mean(T.net_ret[s_] > 0)), 3) if s_.any() else None,
                       round(float(np.mean(T.net_ret[s_]) * 100), 2) if s_.any() else None))
        out["fold_trades"] = fe
        x = T.net_ret
        out["main"]["t_week"] = R.cluster_t(x, T.entry_t // (7 * 86_400_000))
        out["main"]["per_coin_year"] = len(x) / 6.0
    if verbose:
        print(R.fmt(out["main"]))
        if out["main"].get("n"):
            print("   ", R.fmt(out["stress"]).split(":")[1][:60], "| t_sem %.2f | op/moneda/anio %.1f" % (out["main"]["t_week"], out["main"]["per_coin_year"]))
            print("    umbrales val:", folds, "| test por pliegue:", out.get("fold_trades"))
            print("    por moneda:", {str(k): (v[0], round(v[1], 3), round(v[2], 2)) for k, v in out["main"]["by_sym"].items()})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", required=True)
    ap.add_argument("--exit", required=True)
    ap.add_argument("--wrmin", type=float, default=0.75)
    ap.add_argument("--regime", default="none")
    ap.add_argument("--label", default=None)
    ap.add_argument("--obj", default="E")
    a = ap.parse_args()
    OBJ["v"] = a.obj
    o = run(a.preds.split(","), a.exit, a.wrmin, a.regime, a.label)
    with open(os.path.join(OUTD, "wf_results_v2.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"preds": a.preds, "exit": a.exit, "wrmin": a.wrmin, "regime": a.regime, "obj": a.obj,
                            **{k: v for k, v in o.items() if not k.startswith("_")}}, default=str) + "\n")
