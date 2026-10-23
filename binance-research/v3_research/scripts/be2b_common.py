"""Comun de la ronda 2 parte A del laboratorio (hipotesis de metodos del Investigador B). SOLO DISENO.

Anade a be2_common:
- bootstrap por EPISODIO (dias con operaciones de ambos conjuntos, unidos si distan <= 2 dias) para Delta WR / Delta E;
- IC del WR con efectos aleatorios por episodio (beta-binomial, verosimilitud perfilada);
- tamiz extra: fraccion de la mejora de WR que explica el azar condicionado a la regla nueva (debe ser <= 1/2);
- simulacion con barreras arbitrarias por vela (TP/SL en arrays) y etiquetas por vela con esas barreras (azar);
- rebote de las 4 anclas (>= 1 sigma de 4 h sobre el minimo de 16 velas) y brecha g = -dd_96 (en s_d).
"""
import os, sys, math
import numpy as np
from scipy.stats import betabinom
from scipy.optimize import minimize_scalar
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H, C, R, V = E.B, E.H, E.C, E.R, E.V
OUT2 = E.OUT2
NB = 5000

_S = {}


def spot(sym):
    """Velas de diseno (las mismas del cache) con spot_core: o, h, l, c, s15."""
    if sym not in _S:
        a = C.load_spot(C.RESEARCH, sym)
        a = a[a[:, 0] < H.DESIGN[1]]
        _S[sym] = C.spot_core(a)
    return _S[sym]


def gap_g(sym):
    S = spot(sym)
    mx = H.rolling_max(S["h"], 96)
    return -np.log(S["c"] / mx) / (S["s15"] * np.sqrt(96))


def anchors_rebound(D):
    """Grid (4, N): 1 si la ancla esta >= 1 sigma de 4 h por encima de su minimo de 16 velas (causal)."""
    out = []
    for s in H.SYMBOLS:
        S = spot(s)
        up = (S["c"] - H.rolling_min(S["l"], 16)) / (S["c"] * S["s15"] * 4) >= 1
        assert len(up) == len(D["tg"])
        out.append(np.where(np.isfinite(S["s15"]), up, False))
    return np.array(out, float)


def others_frac(D, G):
    """Fraccion de las OTRAS 3 anclas con G = 1, por fila de D."""
    return (G.sum(0)[D["jrow"]] - G[D["ci"], D["jrow"]]) / 3.0


def label_arr(S, tp, sl, Hh, i_end, fee=H.FEE, slip=H.SLIP):
    """Como nn_common.label_all pero con barreras dadas por vela."""
    o, h, l, c = S["o"], S["h"], S["l"], S["c"]
    N = len(c)
    done = np.zeros(N, bool); px = np.full(N, np.nan); why = np.full(N, -1)
    idx = np.arange(N)
    for k in range(1, Hh + 1):
        j = idx + k
        valid = (j < i_end) & ~done
        jj = np.minimum(j, N - 1)
        hs = valid & (l[jj] <= sl)
        ht = valid & ~hs & (h[jj] >= tp)
        px[hs] = np.minimum(sl[hs], o[jj][hs]); why[hs] = 1
        px[ht] = tp[ht]; why[ht] = 0
        done |= hs | ht
        if k == Hh:
            tm = valid & ~hs & ~ht
            px[tm] = c[jj][tm]; why[tm] = 2; done |= tm
    rest = ~done & (idx < i_end - 1)
    px[rest] = c[i_end - 1]; why[rest] = 3
    net = H.net_return(c, px, fee, slip)
    bad = ~np.isfinite(tp) | ~np.isfinite(sl) | (idx >= i_end - 1) | (sl >= c) | (tp <= c)
    return np.where(bad, np.nan, net), why


def with_barriers(D, tp_by_sym, sl_by_sym, Hh, tag):
    """Copia de D con netX = etiqueta por vela de las barreras dadas (para el azar con la misma salida)."""
    nets, whys = [], []
    for s in H.SYMBOLS:
        f = os.path.join(E.GCACHE, f"{s}_{tag}.npz")
        if os.path.exists(f):
            z = np.load(f); n, w = z["net"], z["why"]
        else:
            S = spot(s)
            n, w = label_arr(S, tp_by_sym[s], sl_by_sym[s], Hh, len(S["c"]))
            np.savez(f, net=n, why=w)
        nets.append(n); whys.append(w)
    Dx = dict(D)
    Dx["netX"] = np.concatenate(nets)[D["rows"]]
    Dx["whyX"] = np.concatenate(whys)[D["rows"]]
    Dx["barriers"] = (tp_by_sym, sl_by_sym, Hh)
    Dx["exit_geom"] = tag
    return Dx


def fold_periods(D):
    per = {}
    for k in range(6):
        for ci_ in range(4):
            m = (D["fold"] == k) & (D["ci"] == ci_)
            if m.any():
                per[(ci_, k)] = (int(D["ii"][m].min()), int(D["ii"][m].max()) + 1)
    return per


def trade_table_arr(Dx, mask, gate=None, fee=H.FEE, slip=H.SLIP):
    """Como be2_common.trade_table pero con las barreras por vela de Dx['barriers'] (harness.simulate)."""
    tp_by, sl_by, Hh = Dx["barriers"]
    per = fold_periods(Dx)
    trs = []
    for ci_, s in enumerate(H.SYMBOLS):
        n = len(Dx["cache"][s]["c"])
        bars = R.coin_bars(s, n)
        ent = np.zeros(n, bool)
        m = mask & (Dx["ci"] == ci_)
        ent[Dx["ii"][m]] = True
        for k in range(6):
            if (ci_, k) not in per:
                continue
            tr = H.simulate(bars, ent, tp_by[s], sl_by[s], period=per[(ci_, k)], max_hold=Hh, fee=fee, slip=slip)
            if len(tr):
                trs.append((s, tr))
    if not trs:
        return None
    T = H.Trades.concat([x for _, x in trs])
    syms_cat = np.concatenate([[s] * len(x) for s, x in trs])
    et_cat = np.concatenate([x.entry_t for _, x in trs])
    syms = syms_cat[np.argsort(et_cat, kind="stable")]
    return _table(Dx, T, syms, gate)


def _table(Dx, T, syms, gate):
    _, base = B.rand_base(Dx)
    cb = B.cond_base(Dx, gate) if gate is not None else None
    sidx = np.array([H.SYMBOLS.index(s) for s in syms])
    key = sidx * 1_000_000 + B.month_of(T.entry_t)
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
    return tab


def table_from_list(Dx, rows_list, gate=None):
    """rows_list: (ci, b, e, net, reason, fold, risk, t_entry) -> tabla (para simuladores propios)."""
    T = np.array([x[:7] for x in rows_list], float)
    et = np.array([x[7] for x in rows_list], np.int64)
    o = np.argsort(et, kind="stable"); T, et = T[o], et[o]
    _, base = B.rand_base(Dx)
    cb = B.cond_base(Dx, gate) if gate is not None else None
    sidx = T[:, 0].astype(int)
    key = sidx * 1_000_000 + B.month_of(et)
    tab = dict(x=T[:, 3], et=et, sidx=sidx, fold=T[:, 5].astype(int), reason=T[:, 4].astype(int),
               r_mult=T[:, 3] / T[:, 6], risk=T[:, 6], sig_idx=T[:, 1].astype(int), exit_idx=T[:, 2].astype(int),
               bw=np.array([base[int(kk)][0] for kk in key]), be=np.array([base[int(kk)][1] for kk in key]))
    if cb is not None:
        tab["cw"] = np.array([cb.get(int(kk), (np.nan, np.nan))[0] for kk in key])
        tab["ce"] = np.array([cb.get(int(kk), (np.nan, np.nan))[1] for kk in key])
    return tab


# ------------------------------------------------------------------ estadistica por episodio
def _ep_ids(et_list):
    day = np.concatenate([et // B.DAY for et in et_list])
    ud = np.unique(day)
    ep = np.zeros(len(ud), int)
    for k in range(1, len(ud)):
        ep[k] = ep[k - 1] + (1 if ud[k] - ud[k - 1] > 2 else 0)
    return ud, ep


def compare_ep(new, ref, nb=NB, seed=E.RNG_SEED):
    """Delta (nuevo - base) con bootstrap por EPISODIO (episodios sobre la union de dias de ambos conjuntos)."""
    c = E.compare(new, ref, nb=200)  # pliegues y Delta puntual (el bootstrap por dia no se usa)
    if new is None or not np.isfinite(c.get("dWR", np.nan)):
        return c
    ud, ep = _ep_ids([new["et"], ref["et"]])
    ne = ep.max() + 1

    def agg(t):
        j = ep[np.searchsorted(ud, t["et"] // B.DAY)]
        return (np.bincount(j, minlength=ne).astype(float), np.bincount(j, weights=(t["x"] > 0).astype(float), minlength=ne),
                np.bincount(j, weights=t["x"], minlength=ne))
    n1, w1, s1 = agg(new); n0, w0, s0 = agg(ref)
    rng = np.random.default_rng(seed)
    cnt = np.zeros((nb, ne))
    idx = rng.integers(0, ne, size=(nb, ne))
    np.add.at(cnt, (np.repeat(np.arange(nb), ne), idx.ravel()), 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        dwr = (cnt @ w1) / (cnt @ n1) - (cnt @ w0) / (cnt @ n0)
        de = ((cnt @ s1) / (cnt @ n1) - (cnt @ s0) / (cnt @ n0)) * 100
    ok = np.isfinite(dwr) & np.isfinite(de)
    c.update(p_dWR_le0=float(np.mean(dwr[ok] <= 0)), p_dE_le0=float(np.mean(de[ok] <= 0)),
             dWR_ci=(float(np.quantile(dwr[ok], .05)), float(np.quantile(dwr[ok], .95))),
             dE_ci=(float(np.quantile(de[ok], .05)), float(np.quantile(de[ok], .95))), n_ep_union=int(ne), boot="episodio")
    return c


def betabin_ci(tab):
    """WR con efectos aleatorios por episodio: MLE beta-binomial de (k_e, n_e) e IC 95 % por verosimilitud perfilada."""
    epi = E.episodes(tab["et"])
    k = np.bincount(epi, weights=(tab["x"] > 0).astype(float)).astype(int)
    n = np.bincount(epi).astype(int)

    def nll(mu, rho):
        a = mu * (1 - rho) / rho; b = (1 - mu) * (1 - rho) / rho
        return -np.sum(betabinom.logpmf(k, n, a, b))

    def prof(mu):
        r = minimize_scalar(lambda lr: nll(mu, 1 / (1 + np.exp(-lr))), bounds=(-12, 3), method="bounded")
        return r.fun, 1 / (1 + np.exp(-r.x))
    grid = np.linspace(0.40, 0.995, 240)
    pv = np.array([prof(m)[0] for m in grid])
    i = int(np.argmin(pv))
    inside = grid[2 * (pv - pv[i]) <= 3.841]
    return dict(mu=float(grid[i]), lo=float(inside.min()), hi=float(inside.max()), rho=float(prof(grid[i])[1]),
                n_ep=int(len(n)))


def screen(new_r, ref_r, cmp, cmp_by_ens):
    """Tamiz: criterio del laboratorio (con bootstrap por episodio) + azar condicionado <= 1/2 de la mejora de WR."""
    ok, why = E.candidate(cmp_by_ens)
    frac = float("nan")
    if "cond_wr" in new_r and "cond_wr" in ref_r and cmp["dWR"] > 0:
        frac = (new_r["cond_wr"] - ref_r["cond_wr"]) / cmp["dWR"]
    ok2 = ok and (not np.isfinite(frac) or frac <= 0.5)
    return ok2, why + f"; azar cond. explica {frac*100:.0f} % de ΔWR" if np.isfinite(frac) else why + "; azar cond. –"


HEAD = ("| Ens. | Base | Regla | n | WR % [Wilson] | WR beta-bin. por episodio [IC] | E % | E_R | t día | Azar WR/E | "
        "Azar cond. WR/E | ΔWR / ΔE vs base | P(ΔWR≤0) / P(ΔE≤0) (boot. episodio) | pliegues mejor (=) | episodios |")
HEAD2 = "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"


def row(ens, base, r, c=None, bb=None):
    if not r.get("n"):
        return f"| {ens} | {base} | {r['label']} | 0 | | | | | | | | | | | |"
    cond = f"{r['cond_wr']*100:.1f} / {r['cond_E']:+.2f}" if "cond_wr" in r else "–"
    bbs = f"{bb['mu']*100:.1f} [{bb['lo']*100:.1f}, {bb['hi']*100:.1f}]" if bb else "–"
    if c is None or not np.isfinite(c.get("dWR", np.nan)):
        cc = ("–", "–", "–")
    else:
        cc = (f"{c['dWR']*100:+.1f} / {c['dE']:+.2f}", f"{c['p_dWR_le0']:.2f} / {c['p_dE_le0']:.2f}",
              f"{c['folds_imp']}/6 (={c['folds_tie']})")
    return (f"| {ens} | {base} | {r['label']} | {r['n']} | {r['wr']*100:.1f} [{r['wr_lo']*100:.1f}, {r['wr_hi']*100:.1f}] | {bbs} | "
            f"{r['E_pct']:+.2f} | {r['E_R']:+.3f} | {r['t_day']:.2f} | {r['rand_wr']*100:.1f} / {r['rand_E']:+.2f} | {cond} | "
            f"{cc[0]} | {cc[1]} | {cc[2]} | {r['n_ep']} ({r['ep_wr']*100:.0f} %) |")


def bases(D):
    """Las dos bases: pila X5 (H 288) y pila con H 384 (E7). Devuelve {nombre: (Dx, tabla)}."""
    g1 = D["A"] >= 1
    D384 = E.with_geom(D, 0.7, 1.75, 384)
    return {"X5": (D, E.trade_table(D, D["stack"], g1)), "H384": (D384, E.trade_table(D384, D["stack"], g1))}
