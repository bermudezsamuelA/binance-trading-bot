"""Comun del laboratorio "bleeding edge" ronda 2 (2026-10-16). SOLO DISENO (tests 2024-01..2025-06).

Construye sobre be_common (probabilidades calibradas del walk-forward, umbral por pliegue, X5 y la alineacion
moneda-operacion corregida de simulate_entries). Anade:
- carga de los 3 ensambles (ENS13, ENS12, ENS12U = ENS12 con pesos de unicidad);
- compuerta A_model (W = 48) y variantes sobre la rejilla temporal comun de las 4 monedas;
- geometrias de salida nuevas (a, m, H) calculadas con nn_common.label_all sobre datos de diseno;
- tabla por operacion con azar (misma moneda, mes y geometria) y azar condicionado a la regla;
- comparacion INCREMENTAL frente a la pila (v2 + A >= 1, W = 48): Delta WR / Delta E, bootstrap por dias,
  pliegues que mejoran, monedas y episodios.
"""
import os, sys, json, math
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import be_common as B  # noqa: E402
H, C, R, V = B.H, B.C, B.R, B.V

OUT2 = os.path.join(B.RESEARCH, "output", "bleeding_edge_r2")
os.makedirs(OUT2, exist_ok=True)
GCACHE = os.path.join(B.RESEARCH, "tmp", "be2_geom")
os.makedirs(GCACHE, exist_ok=True)
PD = os.path.join(B.OUT, "preds")
_L = lambda kind, ss, u: [f"{kind}{'uniq' if u else 'v4'}_G3_f1_s{s}" for s in ss]
ENSEMBLES = {"ENS13": (B.ENS13, None),
             "ENS12": (_L("lgb", range(6), 0) + _L("mlp", range(6), 0), [PD]),
             "ENS12U": (_L("lgb", range(6), 1) + _L("mlp", range(6), 1), [PD])}
W = 48
NB = 5000
RNG_SEED = 20261016


# ------------------------------------------------------------------ carga
def load(name):
    tags, pdirs = ENSEMBLES[name]
    D = B.load_ens(tags, pred_dirs=pdirs)
    D["name"] = name
    tg = D["cache"]["BTCUSDT"]["t"].astype(np.int64)
    D["tg"] = tg
    D["jrow"] = np.searchsorted(tg, D["t"])
    assert np.all(tg[D["jrow"]] == D["t"])
    D["sig"] = D["p"] >= D["thr"]
    D["A"] = gate_count(D, D["sig"])
    D["stack"] = D["sig"] & (D["A"] >= 1)
    return D


def to_grid(D, vals, fill=np.nan, dtype=float):
    G = np.full((4, len(D["tg"])), fill, dtype=dtype)
    G[D["ci"], D["jrow"]] = vals
    return G


def from_grid(D, G):
    return G[D["ci"], D["jrow"]]


def roll_any(G, w):
    return np.array([H.rolling_max(g.astype(float), w) > 0 for g in G])


def gate_count(D, sig, w=W, coins=None, before_only=False):
    """Numero de OTRAS monedas con senal en las ultimas w velas (incluida la actual; before_only excluye la actual)."""
    S = to_grid(D, sig, False, bool)
    per = roll_any(S, w)
    if before_only:
        per = np.concatenate([np.zeros((4, 1), bool), per[:, :-1]], 1)
    if coins is not None:
        msk = np.zeros(4, bool); msk[list(coins)] = True
        per = per & msk[:, None]
    tot = per.sum(0)
    return tot[D["jrow"]] - per[D["ci"], D["jrow"]]


# ------------------------------------------------------------------ geometrias
def gname(a, m, h):
    return f"g{a:.2f}_{m:.2f}_{h}"


def ensure_geom(a, m, h):
    """Registra la geometria en nn_common.GEOMS y devuelve {sym: (net, why, jx)} sobre las velas del cache (diseno)."""
    g = gname(a, m, h)
    C.GEOMS[g] = (a, m, h)
    out = {}
    for s in H.SYMBOLS:
        f = os.path.join(GCACHE, f"{s}_{g}.npz")
        if not os.path.exists(f):
            arr = C.load_spot(C.RESEARCH, s)
            arr = arr[arr[:, 0] < H.DESIGN[1]]
            S = C.spot_core(arr)
            net, why, jx = C.label_all(S, g, len(S["c"]))
            np.savez(f, net=net, why=why, jx=jx)
        z = np.load(f)
        out[s] = (z["net"], z["why"], z["jx"])
    return g, out


def with_geom(D, a, m, h):
    """Copia superficial de D con netX y cache de la geometria (a, m, h)."""
    g, lab = ensure_geom(a, m, h)
    cache = {}
    for s in H.SYMBOLS:
        z = dict(D["cache"][s])
        assert len(lab[s][0]) == len(z["c"]), (s, len(lab[s][0]), len(z["c"]))
        z[f"net_{g}"] = lab[s][0]; z[f"why_{g}"] = lab[s][1]
        cache[s] = z
    Dg = dict(D)
    Dg["cache"] = cache
    Dg["exit_geom"] = g
    netall = np.concatenate([lab[s][0] for s in H.SYMBOLS])
    whyall = np.concatenate([lab[s][1] for s in H.SYMBOLS])
    Dg["netX"] = netall[D["rows"]]
    Dg["whyX"] = whyall[D["rows"]]
    Dg["geom"] = (a, m, h)
    return Dg


# ------------------------------------------------------------------ tabla por operacion
def trade_table(D, mask, gate=None, fee=H.FEE, slip=H.SLIP):
    """Simula la mascara y devuelve un dict de arrays por operacion (ordenadas por entrada)."""
    T, syms = B.simulate_entries(D, mask, fee=fee, slip=slip)
    if T is None or len(T) == 0:
        return None
    _, base = B.rand_base(D)
    cb = B.cond_base(D, gate) if gate is not None else None
    sidx = np.array([H.SYMBOLS.index(s) for s in syms])
    mon = B.month_of(T.entry_t)
    key = sidx * 1_000_000 + mon
    fold = np.full(len(T), -1)
    for k, (te0, te1) in enumerate(B.TESTS):
        fold[(T.entry_t >= H.ms(*te0, 1)) & (T.entry_t < H.ms(*te1, 1))] = k
    tab = dict(x=T.net_ret.astype(float), et=T.entry_t.astype(np.int64), sidx=sidx, fold=fold,
               reason=T.reason.astype(int), r_mult=T.r_mult.astype(float), risk=T.risk_pct.astype(float),
               bw=np.array([base[int(k)][0] for k in key]), be=np.array([base[int(k)][1] for k in key]),
               sig_idx=T.sig_idx.astype(int), exit_idx=T.exit_idx.astype(int))
    if cb is not None:
        tab["cw"] = np.array([cb.get(int(k), (np.nan, np.nan))[0] for k in key])
        tab["ce"] = np.array([cb.get(int(k), (np.nan, np.nan))[1] for k in key])
    tab["T"] = T
    return tab


def cat_tables(tabs):
    tabs = [t for t in tabs if t is not None]
    keys = [k for k in tabs[0] if k != "T" and all(k in t for t in tabs)]
    out = {k: np.concatenate([t[k] for t in tabs]) for k in keys}
    o = np.argsort(out["et"], kind="stable")
    return {k: v[o] for k, v in out.items()}


def sub_table(tab, m):
    return {k: (v[m] if k != "T" else None) for k, v in tab.items() if k != "T"}


def episodes(et):
    day = et // B.DAY
    ud = np.unique(day)
    ep = np.zeros(len(ud), int)
    for k in range(1, len(ud)):
        ep[k] = ep[k - 1] + (1 if ud[k] - ud[k - 1] > 2 else 0)
    return ep[np.searchsorted(ud, day)]


def summ(tab, label=""):
    if tab is None or len(tab["x"]) == 0:
        return dict(label=label, n=0)
    x = tab["x"]; n = len(x); k = int((x > 0).sum())
    p, lo, hi = B.wilson(k, n)
    day = tab["et"] // B.DAY
    epi = episodes(tab["et"])
    pnl = np.bincount(epi, weights=x)
    r = dict(label=label, n=n, wr=p, wr_lo=lo, wr_hi=hi, E_pct=float(x.mean() * 100),
             E_R=float(np.nanmean(tab["r_mult"])), t_day=B.cluster_t(x, day),
             rand_wr=float(tab["bw"].mean()), rand_E=float(tab["be"].mean() * 100),
             n_ep=int(epi.max() + 1), ep_wr=float(np.mean(pnl > 0)), ndays=int(len(np.unique(day))),
             avg_win=float(x[x > 0].mean() * 100) if k else float("nan"),
             avg_loss=float(-x[x <= 0].mean() * 100) if k < n else float("nan"),
             tp_rate=float(np.mean(tab["reason"] == 0)), sl_rate=float(np.mean(tab["reason"] == 1)))
    if "cw" in tab:
        ok = np.isfinite(tab["ce"])
        r.update(cond_wr=float(np.nanmean(tab["cw"])), cond_E=float(np.nanmean(tab["ce"]) * 100),
                 dWR_cond=p - float(np.nanmean(tab["cw"])),
                 dE_cond=float((x[ok] - tab["ce"][ok]).mean() * 100),
                 t_dE_cond=B.cluster_t(x[ok] - tab["ce"][ok], day[ok]))
    r["by_fold"] = []
    for f in range(6):
        s = tab["fold"] == f
        r["by_fold"].append((int(s.sum()), float(np.mean(x[s] > 0)) if s.any() else float("nan"),
                             float(np.mean(x[s]) * 100) if s.any() else float("nan")))
    r["by_coin"] = {}
    for ci_ in range(4):
        s = tab["sidx"] == ci_
        r["by_coin"][H.SYMBOLS[ci_][:-4]] = (int(s.sum()), float(np.mean(x[s] > 0)) if s.any() else float("nan"),
                                             float(np.mean(x[s]) * 100) if s.any() else float("nan"))
    return r


def _day_agg(tab, U):
    day = tab["et"] // B.DAY
    j = np.searchsorted(U, day)
    n = np.bincount(j, minlength=len(U)).astype(float)
    w = np.bincount(j, weights=(tab["x"] > 0).astype(float), minlength=len(U))
    s = np.bincount(j, weights=tab["x"], minlength=len(U))
    return n, w, s


def compare(new, ref, nb=NB, seed=RNG_SEED):
    """Delta (nuevo - pila) de WR y E con bootstrap por dias (union de dias de ambos conjuntos) y pliegues."""
    if new is None or len(new["x"]) == 0:
        return dict(dWR=float("nan"), dE=float("nan"))
    U = np.unique(np.concatenate([new["et"] // B.DAY, ref["et"] // B.DAY]))
    n1, w1, s1 = _day_agg(new, U)
    n0, w0, s0 = _day_agg(ref, U)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(U), size=(nb, len(U)))
    cnt = np.zeros((nb, len(U)))
    np.add.at(cnt, (np.repeat(np.arange(nb), len(U)), idx.ravel()), 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        N1, N0 = cnt @ n1, cnt @ n0
        dwr = (cnt @ w1) / N1 - (cnt @ w0) / N0
        de = ((cnt @ s1) / N1 - (cnt @ s0) / N0) * 100
    ok = np.isfinite(dwr) & np.isfinite(de)
    dwr, de = dwr[ok], de[ok]
    WR1, WR0 = np.mean(new["x"] > 0), np.mean(ref["x"] > 0)
    E1, E0 = new["x"].mean() * 100, ref["x"].mean() * 100
    folds = []
    for f in range(6):
        a, b = new["fold"] == f, ref["fold"] == f
        if not a.any() or not b.any():
            folds.append((float("nan"), float("nan")))
            continue
        folds.append((float(np.mean(new["x"][a] > 0) - np.mean(ref["x"][b] > 0)),
                      float((new["x"][a].mean() - ref["x"][b].mean()) * 100)))
    imp = sum(1 for dw, dee in folds if np.isfinite(dw) and dw > 0 and dee >= 0)
    imp_wr = sum(1 for dw, dee in folds if np.isfinite(dw) and dw > 0)
    tie = sum(1 for dw, dee in folds if np.isfinite(dw) and dw == 0 and abs(dee) < 1e-12)
    return dict(dWR=float(WR1 - WR0), dE=float(E1 - E0), p_dWR_le0=float(np.mean(dwr <= 0)),
                p_dE_le0=float(np.mean(de <= 0)), dWR_ci=(float(np.quantile(dwr, .05)), float(np.quantile(dwr, .95))),
                dE_ci=(float(np.quantile(de, .05)), float(np.quantile(de, .95))), folds=folds, folds_imp=imp,
                folds_imp_wr=imp_wr, folds_tie=tie)


def candidate(cmp_by_ens):
    """Criterio de mejora candidata. cmp_by_ens: {ens: compare(...)}; el principal es ENS13."""
    c = cmp_by_ens.get("ENS13")
    if c is None or not np.isfinite(c["dWR"]):
        return False, "sin ENS13"
    ok_main = (c["dWR"] >= 0.01 and c["dE"] >= 0 and c["folds_imp"] >= 4 and c["p_dWR_le0"] <= 0.20
               and c["p_dE_le0"] <= 0.5)
    rep = sum(1 for k, v in cmp_by_ens.items() if np.isfinite(v.get("dWR", np.nan)) and v["dWR"] > 0 and v["dE"] >= 0)
    why = (f"ENS13 dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} pliegues {c['folds_imp']}/6 "
           f"P(dWR<=0) {c['p_dWR_le0']:.2f} P(dE<=0) {c['p_dE_le0']:.2f}; replica (dWR>0, dE>=0) en {rep}/3")
    return bool(ok_main and rep >= 2), why


# ------------------------------------------------------------------ formato
HEAD = ("| Ens. | Regla | n | WR % [Wilson] | E % | E_R | t día | Azar WR/E | Azar cond. WR/E | ΔWR / ΔE vs pila | "
        "P(ΔWR≤0) / P(ΔE≤0) | pliegues mejor (WR y E) | episodios (WR ep.) |")
HEAD2 = "|---|---|---|---|---|---|---|---|---|---|---|---|---|"


def row(ens, r, c=None):
    if not r.get("n"):
        return f"| {ens} | {r['label']} | 0 | – | – | – | – | – | – | – | – | – | – |"
    cond = f"{r['cond_wr']*100:.1f} / {r['cond_E']:+.2f}" if "cond_wr" in r else "–"
    if c is None:
        cc = ("–", "–", "–")
    else:
        cc = (f"{c['dWR']*100:+.1f} / {c['dE']:+.2f}", f"{c['p_dWR_le0']:.2f} / {c['p_dE_le0']:.2f}",
              f"{c['folds_imp']}/6 (empates {c['folds_tie']})")
    return (f"| {ens} | {r['label']} | {r['n']} | {r['wr']*100:.1f} [{r['wr_lo']*100:.1f}, {r['wr_hi']*100:.1f}] | "
            f"{r['E_pct']:+.2f} | {r['E_R']:+.3f} | {r['t_day']:.2f} | {r['rand_wr']*100:.1f} / {r['rand_E']:+.2f} | "
            f"{cond} | {cc[0]} | {cc[1]} | {cc[2]} | {r['n_ep']} ({r['ep_wr']*100:.0f} %) |")


def detail(ens, r, c=None):
    if not r.get("n"):
        return f"- {ens} · {r['label']}: sin operaciones"
    bf = ", ".join(f"{n}·{w*100:.0f}%·{e:+.2f}" if n else "0" for n, w, e in r["by_fold"])
    bc = ", ".join(f"{k} {n}·{w*100:.0f}%·{e:+.2f}" for k, (n, w, e) in r["by_coin"].items())
    s = f"- {ens} · {r['label']}: pliegues [{bf}]; monedas [{bc}]"
    if c is not None and c.get("folds"):
        s += "; Δ por pliegue (WR pt / E %) [" + ", ".join(
            f"{dw*100:+.0f}/{de:+.2f}" if np.isfinite(dw) else "–" for dw, de in c["folds"]) + "]"
    return s


def log_once(tag, n, desc):
    d = os.path.join(OUT2, ".trials")
    os.makedirs(d, exist_ok=True)
    mk = os.path.join(d, f"{tag}.done")
    if os.path.exists(mk):
        return
    H.log_trials("bleeding_edge_r2", n, desc)
    with open(mk, "w", encoding="utf-8") as f:
        f.write(f"{n} {desc}\n")


def jdump(obj, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o), indent=1)


# ------------------------------------------------------------------ validacion (umbral y compuerta en validacion)
def val_grid(D, k):
    """Senales y compuerta en la ventana de VALIDACION del pliegue k (mismas 4 monedas)."""
    v = D["vals"][k]
    tg = D["tg"]
    j = np.searchsorted(tg, v["t"])
    ok = (j < len(tg)) & (tg[np.minimum(j, len(tg) - 1)] == v["t"])
    return v, j, ok
