"""Evalua predicciones walk-forward: calibracion Platt y umbral elegidos SOLO en validacion de cada pliegue,
simulacion con harness.simulate, comparacion contra el azar (misma moneda, mes y geometria), estres de costos.

Uso: python -I nn_report.py --preds lgb_G1_f1_s0[,mlp_G1_f1_s0,...] --geom G1 [--rule wr70|maxE] [--label texto]
"""
import argparse, os, sys, json, math
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_common as C
H = C.H

CACHE = os.environ.get("NN_CACHE") or os.path.join(C.RESEARCH, "tmp", "nn_cache")
PRED = os.path.join(C.RESEARCH, "tmp", "nn_preds")
OUTD = os.path.join(C.RESEARCH, "output", "constructor")
QS = [0.5, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.98, 0.99, 0.995]
MIN_VAL = 150
MIN_DAYS = 15


def platt_fit(s, y):
    s = np.asarray(s, float); y = np.asarray(y, float)
    mu, sd = s.mean(), s.std() + 1e-12
    z = (s - mu) / sd

    def nll(w):
        q = w[0] * z + w[1]
        return np.mean(np.logaddexp(0, q) - y * q)
    w = minimize(nll, np.array([1.0, 0.0]), method="BFGS").x
    return (float(w[0] / sd), float(w[1] - w[0] * mu / sd))


def platt_apply(s, ab):
    return 1 / (1 + np.exp(-(ab[0] * np.asarray(s, float) + ab[1])))


def choose_threshold(p, net, rule="wr70", day=None):
    """Umbral sobre p calibrada que maximiza E en validacion con WR >= 0.70 (rule=wr70) o sin restriccion
    (rule=maxE). Exige >= MIN_VAL velas seleccionadas y >= MIN_DAYS dias distintos (las velas se solapan)."""
    best = None
    for q in QS:
        thr = float(np.quantile(p, q))
        sel = p >= thr
        n = int(sel.sum())
        if n < MIN_VAL or (day is not None and len(np.unique(day[sel])) < MIN_DAYS):
            continue
        wr = float(np.mean(net[sel] > 0)); e = float(np.mean(net[sel]))
        feas = (e > 0) and (wr >= 0.70 if rule == "wr70" else True)
        if feas and (best is None or e > best[2]):
            best = (thr, wr, e, n, q)
    return best


def cluster_t(x, day):
    x = np.asarray(x, float)
    if len(x) < 3:
        return float("nan")
    r = x - x.mean()
    u, inv = np.unique(day, return_inverse=True)
    sums = np.bincount(inv, weights=r)
    se = math.sqrt(np.sum(sums ** 2)) / len(x)
    return float(x.mean() / se) if se > 0 else float("nan")


def coin_bars(sym, n):
    a = np.load(C.find_file(C.RESEARCH, "klines", f"{sym}_15m.npy"))[:n]
    return H.Bars(a, sym)


def random_baseline(cache, geom, ok_rows=None):
    """WR y E del azar por (moneda, mes): media sobre todas las velas validas de ese mes."""
    out = {}
    for sym, z in cache.items():
        net = z[f"net_{geom}"]
        # mes (AAAAMM) de cada vela con su propio open_time (ms). Antes se tomaba por bloques de 96 velas y, con
        # huecos en los datos (2023-03-24 faltan 5 velas), 135 velas por moneda caian en el mes equivocado.
        mon = z["t"].astype(np.int64)[:len(net)].astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)
        mm = (mon // 12 + 1970) * 100 + mon % 12 + 1
        okm = np.isfinite(net) & (np.arange(len(net)) >= 800)
        for m in np.unique(mm[okm]):
            s = okm & (mm == m)
            out[(sym, int(m))] = (float(np.mean(net[s] > 0)), float(np.mean(net[s])))
    return out


def simulate_rows(cache, geom, entries_by_sym, periods, fee=H.FEE, slip=H.SLIP):
    trs = []
    a, m, Hh = C.GEOMS[geom]
    for sym, ent in entries_by_sym.items():
        z = cache[sym]
        n = len(z["c"])
        bars = coin_bars(sym, n)
        sd = z["s15"] * np.sqrt(96)
        tp, sl = z["c"] * (1 + a * sd), z["c"] * (1 - m * sd)
        for (i0, i1) in periods[sym]:
            tr = H.simulate(bars, ent, tp, sl, period=(i0, i1), max_hold=Hh, fee=fee, slip=slip)
            tr.meta["sym"] = sym
            if len(tr):
                trs.append((sym, tr))
    return trs


def summarize(trs, base, n_configs, label):
    import datetime as dt
    if not trs:
        return {"label": label, "n": 0}
    # Trades.concat ya ordena por entry_t (argsort estable sobre los entry_t concatenados). La moneda de cada
    # operacion se reordena con esa MISMA permutacion (igual que be_common.simulate_entries).
    T = H.Trades.concat([t for _, t in trs])
    syms_cat = np.concatenate([[s] * len(t) for s, t in trs])
    et_cat = np.concatenate([t.entry_t for _, t in trs])
    syms = syms_cat[np.argsort(et_cat, kind="stable")]
    T.meta["t0"] = int(H.ms(2024, 1, 1)); T.meta["t1"] = int(H.ms(2025, 7, 1))
    m = H.metrics(T, n_configs=n_configs)
    months = [int(dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).strftime("%Y%m")) for x in T.entry_t]
    bw = np.array([base[(s, mo)][0] for s, mo in zip(syms, months)])
    be = np.array([base[(s, mo)][1] for s, mo in zip(syms, months)])
    day = T.entry_t // 86_400_000
    x = T.net_ret
    out = {"label": label, "n": m["n"], "wr": m["wr"], "wr_lo": m["wr_lo"], "wr_hi": m["wr_hi"], "b_eff": m["b_eff"],
           "E_pct": m["E_pct"], "E_R": m["E_R"], "pf": m["pf"], "mdd_pct": m["mdd_pct"], "mdd_R": m["mdd_R"],
           "t_day": cluster_t(x, day), "rand_wr": float(bw.mean()), "rand_E_pct": float(be.mean() * 100),
           "dWR": m["wr"] - float(bw.mean()), "dE_pct": (float(x.mean()) - float(be.mean())) * 100,
           "t_dE_day": cluster_t(x - be, day), "risk_med_pct": m["risk_med_pct"], "tp_rate": m["tp_rate"],
           "time_rate": m["time_rate"], "p_bonf": m["p_bonf"],
           "by_sym": {s: (int((syms == s).sum()), float(np.mean(x[syms == s] > 0)) if (syms == s).any() else None,
                          float(np.mean(x[syms == s]) * 100) if (syms == s).any() else None) for s in np.unique(syms)}}
    return out, T, syms


def fmt(r):
    if r.get("n", 0) == 0:
        return f"{r['label']}: sin operaciones"
    return (f"{r['label']}: n={r['n']} WR={r['wr']*100:.1f}% [{r['wr_lo']*100:.1f},{r['wr_hi']*100:.1f}] "
            f"b={r['b_eff']:.2f} E={r['E_pct']:+.3f}% ({r['E_R']:+.3f}R) PF={r['pf']:.2f} MDD={r['mdd_pct']:.1f}% "
            f"t_dia={r['t_day']:.2f} | azar WR={r['rand_wr']*100:.1f}% E={r['rand_E_pct']:+.3f}% | "
            f"dWR={r['dWR']*100:+.1f}pt dE={r['dE_pct']:+.3f}% (t_dia {r['t_dE_day']:.2f}) R_med={r['risk_med_pct']:.2f}%")


def run(pred_tags, geom, rule="wr70", n_configs=1, label=None, verbose=True):
    P = [np.load(os.path.join(PRED, f"{tg}.npz")) for tg in pred_tags]
    cache = {s: np.load(os.path.join(CACHE, f"{s}.npz")) for s in H.SYMBOLS}
    ci, ii, t, net = P[0]["ci"], P[0]["ii"], P[0]["t"], P[0]["net"]
    y = (net > 0).astype(float)
    nf = sum(1 for k in P[0].files if k.endswith("_val_rows"))
    entries = {s: np.zeros(len(cache[s]["c"]), bool) for s in H.SYMBOLS}
    periods = {s: [] for s in H.SYMBOLS}
    folds = []
    for k in range(nf):
        vr, tr_ = P[0][f"f{k}_val_rows"], P[0][f"f{k}_tst_rows"]
        pv = np.zeros(len(vr)); pt = np.zeros(len(tr_))
        for p in P:
            ab = platt_fit(p[f"f{k}_val_s"], y[vr])
            pv += platt_apply(p[f"f{k}_val_s"], ab) / len(P)
            pt += platt_apply(p[f"f{k}_tst_s"], ab) / len(P)
        ch = choose_threshold(pv, net[vr], rule, day=t[vr] // 86_400_000)
        for ci_, s in enumerate(H.SYMBOLS):
            rows = tr_[ci[tr_] == ci_]
            if len(rows):
                periods[s].append((int(ii[rows].min()), int(ii[rows].max()) + 1))
        if ch is not None:
            sel = tr_[pt >= ch[0]]
            for ci_, s in enumerate(H.SYMBOLS):
                entries[s][ii[sel[ci[sel] == ci_]]] = True
        folds.append({"fold": k, "thr": None if ch is None else ch[0], "q": None if ch is None else ch[4],
                      "val_wr": None if ch is None else ch[1], "val_E": None if ch is None else ch[2],
                      "n_sel_test_bars": 0 if ch is None else int((pt >= ch[0]).sum())})
    base = random_baseline(cache, geom)
    lab = label or f"{'+'.join(pred_tags)} {geom} {rule}"
    trs = simulate_rows(cache, geom, entries, periods)
    res = summarize(trs, base, n_configs, lab)
    trs_s = simulate_rows(cache, geom, entries, periods, fee=0.0013, slip=0.0002)
    res_s = summarize(trs_s, base, n_configs, lab + " [c=0.30%]")
    out = {"main": res[0] if isinstance(res, tuple) else res, "stress": res_s[0] if isinstance(res_s, tuple) else res_s,
           "folds": folds}
    if isinstance(res, tuple):
        T, syms = res[1], res[2]
        out["_T"], out["_syms"] = T, syms
        fold_E = []
        for k, (te0, te1) in enumerate([((2024, 1), (2024, 4)), ((2024, 4), (2024, 7)), ((2024, 7), (2024, 10)),
                                         ((2024, 10), (2025, 1)), ((2025, 1), (2025, 4)), ((2025, 4), (2025, 7))]):
            s_ = (T.entry_t >= H.ms(*te0, 1)) & (T.entry_t < H.ms(*te1, 1))
            fold_E.append((int(s_.sum()), float(np.mean(T.net_ret[s_] > 0)) if s_.any() else None,
                           float(np.mean(T.net_ret[s_]) * 100) if s_.any() else None))
        out["fold_trades"] = fold_E
    if verbose:
        print(fmt(out["main"])); print(fmt(out["stress"]))
        print("  pliegues (thr, q, WRval, Eval):", [(f["fold"], None if f["thr"] is None else round(f["thr"], 3), f["q"],
              None if f["val_wr"] is None else round(f["val_wr"], 3), None if f["val_E"] is None else round(f["val_E"] * 100, 3))
              for f in folds])
        if "fold_trades" in out:
            print("  test por pliegue (n, WR, E%):", [(a, None if b is None else round(b, 3), None if c is None else round(c, 3)) for a, b, c in out["fold_trades"]])
        if out["main"].get("n"):
            print("  por moneda (n, WR, E%):", {k: (v[0], None if v[1] is None else round(v[1], 3), None if v[2] is None else round(v[2], 3)) for k, v in out["main"]["by_sym"].items()})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", required=True)
    ap.add_argument("--geom", required=True)
    ap.add_argument("--rule", default="wr70")
    ap.add_argument("--label", default=None)
    a = ap.parse_args()
    o = run(a.preds.split(","), a.geom, a.rule, label=a.label)
    os.makedirs(OUTD, exist_ok=True)
    with open(os.path.join(OUTD, "wf_results.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"preds": a.preds, "geom": a.geom, "rule": a.rule, **{k: v for k, v in o.items() if not k.startswith("_")}},
                           default=float) + "\n")
