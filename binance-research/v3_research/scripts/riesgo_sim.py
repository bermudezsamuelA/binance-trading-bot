"""riesgo_sim.py - simulador de salidas (triple barrera y variantes) del Gestor de Riesgo, ronda 1.

Reglas (iguales a las del equipo):
  * Solo se usan velas de DISENO: 2023-01-01 <= t < 2025-07-01 (UTC). El holdout NO se toca.
  * Entrada al CIERRE de la vela de la senal i. TP/SL se evaluan con high/low de las velas i+1..i+H.
  * Si en una misma vela se tocan TP y SL -> cuenta como SL. Si la vela abre por debajo del SL,
    se sale a la apertura (gap). El TP se paga exactamente al precio del TP (nunca mejor).
  * Barrera vertical: si no se toco nada en H velas, se sale al cierre de la vela i+H.
  * Costos: 0.10 % comision + 0.02 % spread/deslizamiento POR LADO (s = 0.0012) => c ~ 0.24 % ida y vuelta.
    r_neto = P_salida*(1-s) / (P_entrada*(1+s)) - 1.
  * Solo long; una posicion por moneda a la vez (la siguiente entrada debe ser una vela > vela de salida).
  * Los candidatos se truncan a i <= N-1-HMAX para que ninguna trayectoria use datos posteriores al diseno.
"""
import os
import datetime as dt
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

HERE = os.path.dirname(os.path.abspath(__file__))
KDIR = os.path.join(HERE, "..", "klines")
OUTDIR = os.path.join(HERE, "..", "output", "riesgo")
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]


def ms(y, m, d):
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000)


T_DESIGN0 = ms(2023, 1, 1)
T_HOLDOUT = ms(2025, 7, 1)
S_SIDE = 0.0012
C_RT = 1 - (1 - S_SIDE) / (1 + S_SIDE)  # costo ida y vuelta efectivo (~0.2398 %)
HMAX = 960  # 10 dias de velas de 15m: margen comun para truncar candidatos


def load(sym, agg=1):
    """Velas de diseno. agg=4 agrega 15m -> 1h, agg=16 -> 4h (alineadas al reloj UTC)."""
    a = np.load(os.path.join(KDIR, f"{sym}_15m.npy"))
    a = a[(a[:, 0] >= T_DESIGN0) & (a[:, 0] < T_HOLDOUT)]
    if agg > 1:
        key = (a[:, 0] // (agg * 900000)).astype(np.int64)
        st = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
        en = np.r_[st[1:] - 1, len(a) - 1]
        a = np.column_stack([a[st, 0], a[st, 1], np.maximum.reduceat(a[:, 2], st),
                             np.minimum.reduceat(a[:, 3], st), a[en, 4],
                             np.add.reduceat(a[:, 5], st), np.add.reduceat(a[:, 6], st)])
    return dict(t=a[:, 0], o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], v=a[:, 5])


def roll_mean_std(x, n):
    mu = np.full(len(x), np.nan)
    sd = np.full(len(x), np.nan)
    w = swv(x, n)
    mu[n - 1:] = w.mean(1)
    sd[n - 1:] = w.std(1, ddof=1)
    return mu, sd


def atr(d, n=14):
    h, l, c = d["h"], d["l"], d["c"]
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(c), np.nan)
    out[n - 1:] = swv(tr, n).mean(1)
    return out


def net_ret(px_exit, px_entry):
    return px_exit * (1 - S_SIDE) / (px_entry * (1 + S_SIDE)) - 1


def first_true(M):
    """Columna (0-based) del primer True de cada fila; M.shape[1] si no hay ninguno."""
    f = M.argmax(1)
    f[~M[np.arange(len(M)), f]] = M.shape[1]
    return f


class Fwd:
    """Matrices de las velas futuras i+1..i+H de cada candidato."""

    def __init__(self, d, idx, H, mu=None):
        J = idx[:, None] + np.arange(1, H + 1)[None, :]
        self.O, self.H, self.L, self.C = d["o"][J], d["h"][J], d["l"][J], d["c"][J]
        self.MU = mu[J] if mu is not None else None
        self.n = len(idx)


def _resolve(F, H, j_sl, sl, j_other, px_other_fn):
    """Resuelve SL (prioritario en empate) frente a otra salida; si nada, cierre de la vela H."""
    r = np.arange(F.n)
    sl_first = (j_sl <= j_other) & (j_sl < H)
    ot_first = (j_other < j_sl) & (j_other < H)
    tim = ~(sl_first | ot_first)
    px = np.empty(F.n)
    col = np.empty(F.n, np.int64)
    kind = np.zeros(F.n, np.int8)
    px[sl_first] = np.minimum(sl[sl_first], F.O[r[sl_first], j_sl[sl_first]])
    col[sl_first] = j_sl[sl_first]
    kind[sl_first] = -1
    px[ot_first] = px_other_fn(r[ot_first], j_other[ot_first])
    col[ot_first] = j_other[ot_first]
    kind[ot_first] = 1
    px[tim] = F.C[r[tim], H - 1]
    col[tim] = H - 1
    return px, col, kind


def sim_barrier(F, P, tp, sl, H):
    js = first_true(F.L[:, :H] <= sl[:, None])
    jt = first_true(F.H[:, :H] >= tp[:, None])
    return _resolve(F, H, js, sl, jt, lambda rr, jj: tp[rr])


def sim_dynmean(F, P, sl, H):
    """Sale al cierre de la primera vela cuyo cierre >= SMA_n de esa vela (salida en la media)."""
    js = first_true(F.L[:, :H] <= sl[:, None])
    jm = first_true(F.C[:, :H] >= F.MU[:, :H])
    return _resolve(F, H, js, sl, jm, lambda rr, jj: F.C[rr, jj])


def sim_chandelier(F, P, A, m, H):
    """Stop = max(P, highs de i+1..j-1) - m*ATR_entrada; se evalua con el low de la vela j."""
    runmax = np.maximum.accumulate(np.concatenate([P[:, None], F.H[:, :H - 1]], axis=1), axis=1)
    stop = runmax - m * A[:, None]
    r = np.arange(F.n)
    js = first_true(F.L[:, :H] <= stop)
    hit = js < H
    jj = np.minimum(js, H - 1)
    px = np.where(hit, np.minimum(stop[r, jj], F.O[r, jj]), F.C[:, H - 1])
    col = np.where(hit, js, H - 1)
    kind = np.where(hit, np.where(px > P, 1, -1), 0).astype(np.int8)
    return px, col, kind


def sim_partial(F, P, A, a1, a2, m, H):
    """50 % en TP1 = P + a1*ATR; el resto con stop en break-even neto y TP2 = P + a2*ATR."""
    tp1, sl = P + a1 * A, P - m * A
    px1, col1, k1 = sim_barrier(F, P, tp1, sl, H)
    net = net_ret(px1, P)
    col = col1.copy()
    g = np.flatnonzero(k1 == 1)
    if len(g):
        be = P[g] * (1 + S_SIDE) / (1 - S_SIDE)
        tp2 = P[g] + a2 * A[g]
        after = np.arange(H)[None, :] > col1[g][:, None]
        jb = first_true((F.L[g, :H] <= be[:, None]) & after)
        jt = first_true((F.H[g, :H] >= tp2[:, None]) & after)
        b_first = (jb <= jt) & (jb < H)
        t_first = (jt < jb) & (jt < H)
        tim = ~(b_first | t_first)
        px2 = np.empty(len(g))
        c2 = np.empty(len(g), np.int64)
        px2[b_first] = np.minimum(be[b_first], F.O[g[b_first], jb[b_first]])
        c2[b_first] = jb[b_first]
        px2[t_first] = tp2[t_first]
        c2[t_first] = jt[t_first]
        px2[tim] = F.C[g[tim], H - 1]
        c2[tim] = H - 1
        net[g] = 0.5 * net_ret(px1[g], P[g]) + 0.5 * net_ret(px2, P[g])
        col[g] = c2
    return net, col, k1


def simulate(F, ctx, cfg):
    """Devuelve (r_neto, columna_salida, R_fraccion, tipo) para cada candidato del bloque."""
    P, A, MU = ctx["P"], ctx["A"], ctx["MU"]
    fam, H = cfg["fam"], cfg["H"]
    if fam == "ATR":
        tp, sl = P + cfg["a"] * A, P - cfg["m"] * A
        px, col, kind = sim_barrier(F, P, tp, sl, H)
        return net_ret(px, P), col, cfg["m"] * A / P, kind
    if fam == "PATH":  # TP = fraccion f del camino hacia la media de entrada
        tp, sl = P + cfg["f"] * (MU - P), P - cfg["m"] * A
        px, col, kind = sim_barrier(F, P, tp, sl, H)
        return net_ret(px, P), col, cfg["m"] * A / P, kind
    if fam == "MEAN":
        sl = P - cfg["m"] * A
        px, col, kind = sim_dynmean(F, P, sl, H)
        return net_ret(px, P), col, cfg["m"] * A / P, kind
    if fam == "CHAN":
        px, col, kind = sim_chandelier(F, P, A, cfg["m"], H)
        return net_ret(px, P), col, cfg["m"] * A / P, kind
    if fam == "PART":
        net, col, kind = sim_partial(F, P, A, cfg["a1"], cfg["a2"], cfg["m"], H)
        return net, col, cfg["m"] * A / P, kind
    if fam == "BOT_MR":  # geometria actual de MeanReversion: TP = mu, SL simetrico (b = 1)
        R = MU - P
        px, col, kind = sim_barrier(F, P, MU, P - R, H)
        return net_ret(px, P), col, R / P, kind
    if fam == "BOT_BO":  # geometria actual de TrendFollowing: SL = mu, TP = P + 2R (b = 2)
        R = P - MU
        px, col, kind = sim_barrier(F, P, P + 2 * R, MU, H)
        return net_ret(px, P), col, R / P, kind
    raise ValueError(fam)


def candidates(d, entry, ind):
    """Indices de velas con senal. entry = ('MR'|'BO'|'RND', n, k)."""
    typ, n, k = entry
    N = len(d["c"])
    ok = np.isfinite(ind["atr"])
    if typ == "RND":
        sig = ok.copy()
    else:
        mu, sd = ind[("ms", n)]
        z = (d["c"] - mu) / sd
        ok &= np.isfinite(z)
        sig = ok & ((z < -k) if typ == "MR" else (z > k))
    sig[N - 1 - HMAX:] = False
    return np.flatnonzero(sig)


def run_outcomes(d, ind, entry, cfgs, chunk):
    """Calcula el desenlace de TODOS los candidatos para cada configuracion (antes de encadenar)."""
    cand = candidates(d, entry, ind)
    n_mu = entry[1] if entry[0] != "RND" else 20
    mu_full = ind[("ms", n_mu)][0]
    nc, N = len(cfgs), len(cand)
    NET = np.zeros((nc, N), np.float32)
    XB = np.zeros((nc, N), np.int64)
    RR = np.zeros((nc, N), np.float32)
    KD = np.zeros((nc, N), np.int8)
    Hn = max(c["H"] for c in cfgs)
    for s in range(0, N, chunk):
        idx = cand[s:s + chunk]
        F = Fwd(d, idx, Hn, mu_full)
        ctx = dict(P=d["c"][idx], A=ind["atr"][idx], MU=mu_full[idx])
        for ci, cfg in enumerate(cfgs):
            net, col, R, kind = simulate(F, ctx, cfg)
            NET[ci, s:s + chunk] = net
            XB[ci, s:s + chunk] = idx + col + 1
            RR[ci, s:s + chunk] = R
            KD[ci, s:s + chunk] = kind
        del F
    return cand, NET, XB, RR, KD


def chain(cand, xb, valid=None):
    """Una posicion por moneda: tras salir en la vela e, la siguiente entrada es el primer candidato > e."""
    nxt = np.searchsorted(cand, xb, side="right")
    sel = []
    k = 0
    N = len(cand)
    if valid is None:
        while k < N:
            sel.append(k)
            k = nxt[k]
    else:
        while k < N:
            if valid[k]:
                sel.append(k)
                k = nxt[k]
            else:
                k += 1
    return np.array(sel, np.int64)


def indicators(d, ns=(20, 48, 96)):
    ind = {"atr": atr(d, 14)}
    for n in set(ns) | {20}:
        ind[("ms", n)] = roll_mean_std(d["c"], n)
    return ind


# ---------------------------------------------------------------- metricas
def wilson(k, n, z=1.959964):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (c - h, c + h)


def metrics(tr):
    """tr: dict con arrays net, R, kind, t_in, t_out (ms). Devuelve dict de metricas."""
    net, R = tr["net"].astype(float), tr["R"].astype(float)
    n = len(net)
    if n < 2:
        return dict(N=n)
    X = net / R
    win = net > 0
    W = win.sum()
    aw = net[win].mean() if W else 0.0
    al = -net[~win].mean() if W < n else 0.0
    b = aw / al if al > 0 else np.inf
    pstar = al / (aw + al) if (aw + al) > 0 else np.nan
    p = W / n
    lo, hi = wilson(W, n)
    sdX = X.std(ddof=1)
    t_tr = X.mean() / sdX * np.sqrt(n) if sdX > 0 else np.nan
    order = np.argsort(tr["t_out"], kind="stable")
    cum = np.cumsum(X[order])
    peak = np.maximum.accumulate(np.r_[0.0, cum])[1:]
    mdd_R = np.max(peak - cum) if n else 0.0
    mon = (tr["t_in"] // (86400000 * 30.4375)).astype(np.int64)
    um, inv = np.unique(mon, return_inverse=True)
    msum = np.bincount(inv, weights=X)
    t_mo = msum.mean() / msum.std(ddof=1) * np.sqrt(len(msum)) if len(msum) > 2 and msum.std() > 0 else np.nan
    gp, gl = net[net > 0].sum(), -net[net < 0].sum()
    gross = net + C_RT * (1 + net)  # aproximacion del retorno bruto
    return dict(N=n, WR=p, WR_lo=lo, WR_hi=hi, avgW=aw, avgL=al, b_eff=b, pstar=pstar,
                margin=p - pstar, z_margin=(p - pstar) / np.sqrt(p * (1 - p) / n) if 0 < p < 1 else np.nan,
                E_pct=net.mean() * 100, E_R=X.mean(), t_trade=t_tr, t_month=t_mo, PF=gp / gl if gl > 0 else np.inf,
                MDD_R=mdd_R, R_med=np.median(R) * 100, cR_med=np.median(C_RT / R),
                Eg_R=(gross / R).mean(), tp_rate=(tr["kind"] == 1).mean(), sl_rate=(tr["kind"] == -1).mean(),
                n_months=len(msum))


# ---------------------------------------------------------------- orquestacion
def datasets(agg=1, ns=(20, 48, 96)):
    out = {}
    for s in SYMS:
        d = load(s, agg)
        out[s] = (d, indicators(d, ns))
    return out


def pooled_trades(DS, entry, cfgs, chunk=6000):
    """Para cada cfg devuelve el dict de operaciones encadenadas (una posicion por moneda) de las 4 monedas."""
    acc = [dict(net=[], R=[], kind=[], t_in=[], t_out=[], coin=[], hold=[]) for _ in cfgs]
    for ci_s, s in enumerate(SYMS):
        d, ind = DS[s]
        cand, NET, XB, RR, KD = run_outcomes(d, ind, entry, cfgs, chunk)
        for ci, cfg in enumerate(cfgs):
            valid = (RR[ci] >= 0.005) if cfg["fam"] == "BOT_MR" else None
            k = chain(cand, XB[ci], valid)
            a = acc[ci]
            a["net"].append(NET[ci, k]); a["R"].append(RR[ci, k]); a["kind"].append(KD[ci, k])
            a["t_in"].append(d["t"][cand[k]]); a["t_out"].append(d["t"][np.minimum(XB[ci, k], len(d["t"]) - 1)])
            a["coin"].append(np.full(len(k), ci_s, np.int8)); a["hold"].append(XB[ci, k] - cand[k])
        del NET, XB, RR, KD
    return [{kk: np.concatenate(v) for kk, v in a.items()} for a in acc]


def by_group_ER(tr, key):
    X = tr["net"] / tr["R"]
    out = {}
    for g in np.unique(key):
        m = key == g
        out[g] = (X[m].mean(), m.sum())
    return out


def year_of(t_ms):
    return np.array([dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).year for x in t_ms])
