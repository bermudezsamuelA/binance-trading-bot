"""Comun de los experimentos "bleeding edge" (juez y laboratorio, 2026-10-15).

Solo DISENO (2023-01..2025-06). Reconstruye, sin reentrenar, las probabilidades calibradas (Platt en validacion)
del ensamble v2 (ENS13: 6 LGB + 6 MLP + 1 CNN, etiqueta G3) en el walk-forward de 6 pliegues (tests 2024Q1..2025Q2),
el umbral de cada pliegue elegido SOLO en validacion (regla v2: max E con WR_val >= 0.75) y los resultados por vela
con la salida X5 (0.7, 1.75, 288). Nada toca el holdout.
"""
import os, sys, datetime as dt, math
import numpy as np
try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(RESEARCH, "nn"))
import harness as H  # noqa: E402
import nn_common as C  # noqa: E402
import nn_report as R  # noqa: E402
import nn_v2_report as V  # noqa: E402

OUT = os.path.join(RESEARCH, "output", "bleeding_edge")
os.makedirs(OUT, exist_ok=True)
ENS13 = [f"lgbv4_G3_f1_s{k}" for k in range(6)] + [f"mlpv4_G3_f1_s{k}" for k in range(6)] + ["cnnv4_G3_f1_s0"]
ENS6 = [f"lgbv4_G3_f1_s{k}" for k in range(3)] + [f"mlpv4_G3_f1_s{k}" for k in range(3)]
TESTS = [((2024, 1), (2024, 4)), ((2024, 4), (2024, 7)), ((2024, 7), (2024, 10)), ((2024, 10), (2025, 1)),
         ((2025, 1), (2025, 4)), ((2025, 4), (2025, 7))]
OTHER18 = ["ADAUSDT", "ATOMUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOTUSDT", "ETCUSDT", "FILUSDT", "LINKUSDT",
           "LTCUSDT", "NEARUSDT", "TRXUSDT", "UNIUSDT", "XRPUSDT"]
DAY = 86_400_000


def month_of(tms):
    return np.array([int(dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).strftime("%Y%m")) for x in tms])


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def cluster_t(x, g):
    return R.cluster_t(np.asarray(x, float), np.asarray(g))


def load_ens(tags=ENS13, exit_geom="X5", wr_min=0.75, pred_dirs=None):
    """Devuelve un dict con arrays por fila (todas las velas de test de los 6 pliegues, 4 monedas):
    sym_i, ii, t, p (prob. calibrada promedio), thr (umbral del pliegue), fold, netX (salida exit_geom), netG3.
    Tambien las de validacion (para los experimentos de umbral con garantia)."""
    def _p(tg):
        for d in (pred_dirs or []) + [R.PRED]:
            f = os.path.join(d, f"{tg}.npz")
            if os.path.exists(f):
                return f
        raise FileNotFoundError(tg)
    P = [np.load(_p(tg)) for tg in tags]
    cache = V.load_cache(exit_geom)
    ci, ii, t, netG3 = P[0]["ci"], P[0]["ii"], P[0]["t"], P[0]["net"]
    yG3 = (netG3 > 0).astype(float)
    netX = np.concatenate([cache[s][f"net_{exit_geom}"] for s in H.SYMBOLS])
    hx = C.GEOMS[exit_geom][2]
    rows, ps, thrs, folds, vals = [], [], [], [], []
    for k in range(6):
        vr, tr_ = P[0][f"f{k}_val_rows"], P[0][f"f{k}_tst_rows"]
        pv = np.zeros(len(vr)); pt = np.zeros(len(tr_))
        for p in P:
            ab = R.platt_fit(p[f"f{k}_val_s"], yG3[vr])
            pv += R.platt_apply(p[f"f{k}_val_s"], ab) / len(P)
            pt += R.platt_apply(p[f"f{k}_tst_s"], ab) / len(P)
        okv = np.isfinite(netX[vr]) & (t[vr] < t[tr_].min() - (hx + 1) * C.MS15)
        ch = V.choose(pv[okv], netX[vr][okv], (t[vr] // DAY)[okv], wr_min)
        thr = np.inf if ch is None else ch[0]
        rows.append(tr_); ps.append(pt); thrs.append(np.full(len(tr_), thr)); folds.append(np.full(len(tr_), k))
        vals.append(dict(rows=vr[okv], p=pv[okv], netX=netX[vr][okv], t=t[vr][okv], ci=ci[vr][okv], thr=thr))
    rows = np.concatenate(rows)
    D = dict(rows=rows, ci=ci[rows], ii=ii[rows], t=t[rows].astype(np.int64), p=np.concatenate(ps),
             thr=np.concatenate(thrs), fold=np.concatenate(folds), netX=netX[rows], netG3=netG3[rows], vals=vals,
             cache=cache, exit_geom=exit_geom)
    D["month"] = month_of(D["t"])
    D["day"] = D["t"] // DAY
    return D


def rand_base(D, mask_valid=None):
    """WR y E del azar por (moneda, mes) sobre todas las velas validas de test (misma geometria)."""
    ok = np.isfinite(D["netX"]) if mask_valid is None else (np.isfinite(D["netX"]) & mask_valid)
    key = D["ci"] * 1_000_000 + D["month"]
    out = {}
    for kk in np.unique(key[ok]):
        s = ok & (key == kk)
        out[int(kk)] = (float(np.mean(D["netX"][s] > 0)), float(np.mean(D["netX"][s])))
    return key, out


def simulate_entries(D, sel_mask, fee=H.FEE, slip=H.SLIP, exit_geom=None, entry_fee=None):
    """Simula con harness.simulate (una posicion por moneda) las velas de test marcadas en sel_mask."""
    exit_geom = exit_geom or D["exit_geom"]
    cache = D["cache"]
    entries = {s: np.zeros(len(cache[s]["c"]), bool) for s in H.SYMBOLS}
    periods = {s: [] for s in H.SYMBOLS}
    for k in range(6):
        for ci_, s in enumerate(H.SYMBOLS):
            m = (D["fold"] == k) & (D["ci"] == ci_)
            if m.any():
                periods[s].append((int(D["ii"][m].min()), int(D["ii"][m].max()) + 1))
    for ci_, s in enumerate(H.SYMBOLS):
        m = sel_mask & (D["ci"] == ci_)
        entries[s][D["ii"][m]] = True
    trs = R.simulate_rows(cache, exit_geom, entries, periods, fee=fee, slip=slip)
    if not trs:
        return None, None
    # OJO: Trades.concat ya ordena por entry_t (orden estable). La moneda de cada operacion debe reordenarse con
    # la MISMA permutacion (nn_report.summarize ya lo hace igual; antes desalineaba moneda y operacion).
    T = H.Trades.concat([x for _, x in trs])
    syms_cat = np.concatenate([[s] * len(x) for s, x in trs])
    et_cat = np.concatenate([x.entry_t for _, x in trs])
    syms = syms_cat[np.argsort(et_cat, kind="stable")]
    return T, syms


def summarize_trades(T, syms, D, base_key_fn=None, label="", n_configs=1, cond_base=None):
    """Metricas: n, WR [Wilson], E %, E_R, t por dia, azar mismo (moneda, mes, geometria) y, si se da cond_base
    (dict (sym_idx, mes) -> (wr, E) condicionado a la misma compuerta), tambien el azar condicionado."""
    if T is None or len(T) == 0:
        return dict(label=label, n=0)
    _, base = rand_base(D)
    sidx = np.array([H.SYMBOLS.index(s) for s in syms])
    mon = month_of(T.entry_t)
    key = sidx * 1_000_000 + mon
    bw = np.array([base[int(k)][0] for k in key]); be = np.array([base[int(k)][1] for k in key])
    x = T.net_ret
    day = T.entry_t // DAY
    m = H.metrics(T, n_configs=n_configs)
    out = dict(label=label, n=int(m["n"]), wr=m["wr"], wr_lo=m["wr_lo"], wr_hi=m["wr_hi"], b_eff=m["b_eff"],
               E_pct=m["E_pct"], E_R=m["E_R"], t_day=cluster_t(x, day), rand_wr=float(bw.mean()),
               rand_E=float(be.mean() * 100), dWR=m["wr"] - float(bw.mean()), dE=(x.mean() - be.mean()) * 100,
               t_dE_day=cluster_t(x - be, day), tp_rate=m["tp_rate"], ndays=int(len(np.unique(day))),
               per_coin_year=len(x) / 6.0, avg_win=float(x[x > 0].mean() * 100) if (x > 0).any() else float("nan"),
               avg_loss=float(-x[x <= 0].mean() * 100) if (x <= 0).any() else float("nan"))
    if cond_base is not None:
        cw = np.array([cond_base.get(int(k), (np.nan, np.nan))[0] for k in key])
        ce = np.array([cond_base.get(int(k), (np.nan, np.nan))[1] for k in key])
        okc = np.isfinite(ce)
        out.update(cond_rand_wr=float(np.nanmean(cw)), cond_rand_E=float(np.nanmean(ce) * 100),
                   dWR_cond=m["wr"] - float(np.nanmean(cw)), dE_cond=float((x[okc] - ce[okc]).mean() * 100),
                   t_dE_cond_day=cluster_t(x[okc] - ce[okc], day[okc]))
    return out


def cond_base(D, gate):
    """Azar condicionado: media por (moneda, mes) del resultado por vela, solo en velas donde la compuerta es cierta."""
    ok = np.isfinite(D["netX"]) & gate
    key = D["ci"] * 1_000_000 + D["month"]
    out = {}
    for kk in np.unique(key[ok]):
        s = ok & (key == kk)
        out[int(kk)] = (float(np.mean(D["netX"][s] > 0)), float(np.mean(D["netX"][s])))
    return out


def md_row(r, extra=()):
    if not r.get("n"):
        return f"| {r['label']} | 0 | – | – | – | – | – | – | – | – |"
    cols = [r["label"], str(r["n"]), f"{r['wr']*100:.1f} [{r['wr_lo']*100:.1f}, {r['wr_hi']*100:.1f}]",
            f"{r['E_pct']:+.2f}", f"{r['E_R']:+.3f}", f"{r['t_day']:.2f}",
            f"{r['rand_wr']*100:.1f} / {r['rand_E']:+.2f}", f"{r['dWR']*100:+.1f} / {r['dE']:+.2f}",
            f"{r['t_dE_day']:.2f}"]
    if "cond_rand_wr" in r:
        cols.append(f"{r['cond_rand_wr']*100:.1f} / {r['cond_rand_E']:+.2f} → Δ {r['dWR_cond']*100:+.1f} / {r['dE_cond']:+.2f} (t {r['t_dE_cond_day']:.2f})")
    cols += list(extra)
    return "| " + " | ".join(cols) + " |"


MD_HEAD = ("| Config | n | WR % [Wilson 95] | E neta % | E_R | t día | Azar WR % / E % | ΔWR pt / ΔE % | t(ΔE) día |",
           "|---|---|---|---|---|---|---|---|---|")
MD_HEAD_C = ("| Config | n | WR % [Wilson 95] | E neta % | E_R | t día | Azar WR % / E % | ΔWR pt / ΔE % | t(ΔE) día | Azar con la misma compuerta (WR/E) → Δ |",
             "|---|---|---|---|---|---|---|---|---|---|")


def fmt(r):
    if not r.get("n"):
        return f"{r['label']}: sin operaciones"
    s = (f"{r['label']}: n={r['n']} WR={r['wr']*100:.1f}% [{r['wr_lo']*100:.1f},{r['wr_hi']*100:.1f}] "
         f"E={r['E_pct']:+.3f}% ({r['E_R']:+.3f}R) t_dia={r['t_day']:.2f} | azar {r['rand_wr']*100:.1f}% "
         f"{r['rand_E']:+.3f}% | dWR={r['dWR']*100:+.1f} dE={r['dE']:+.3f} (t {r['t_dE_day']:.2f}) "
         f"ganmed={r['avg_win']:.2f} perdmed={r['avg_loss']:.2f} dias={r['ndays']}")
    if "cond_rand_wr" in r:
        s += (f" | azar cond {r['cond_rand_wr']*100:.1f}% {r['cond_rand_E']:+.3f}% dWRc={r['dWR_cond']*100:+.1f} "
              f"dEc={r['dE_cond']:+.3f} (t {r['t_dE_cond_day']:.2f})")
    return s


def log_once(tag, n, desc):
    """Registra la familia en harness.log_trials una sola vez por 'tag' (las re-ejecuciones tras corregir un error
    no duplican el registro)."""
    d = os.path.join(OUT, ".trials")
    os.makedirs(d, exist_ok=True)
    mk = os.path.join(d, f"{tag}.done")
    if os.path.exists(mk):
        return
    H.log_trials("bleeding_edge", n, desc)
    with open(mk, "w", encoding="utf-8") as f:
        f.write(f"{n} {desc}\n")
