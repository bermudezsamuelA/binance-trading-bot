"""Utilidades del Analista (ronda 1): carga SOLO el periodo de DISEÑO, indicadores causales,
simulación honesta (high/low, empate = SL, costos) y métricas.

Reglas de simulación
- Entrada al CIERRE de la vela de la señal (c[i]).
- TP/SL evaluados con high/low desde la vela i+1. Si en la misma vela se tocan TP y SL -> SL.
- Si la vela abre por debajo del SL (hueco), se sale a la apertura (peor precio). El TP se llena al TP.
- Barrera de tiempo opcional H (velas): salida al cierre de la vela i+H.
- Si los datos de DISEÑO se acaban, se cierra al último cierre disponible (resultado 'fin').
- Solo long, una posición por moneda: una señal solo se toma si su índice es > índice de salida previo.
- Costos: c = 0.24 % ida y vuelta (0.10 % comisión + 0.02 % deslizamiento por lado): r_neto = r_bruto - 0.0024.
"""
import os
import sys
import numpy as np
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from numpy.lib.stride_tricks import sliding_window_view as swv

HERE = os.path.dirname(os.path.abspath(__file__))
KLINES = os.path.abspath(os.path.join(HERE, "..", "klines"))
OUTDIR = os.path.abspath(os.path.join(HERE, "..", "output", "analista"))
os.makedirs(OUTDIR, exist_ok=True)

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
DESIGN_START_MS = 1672531200000      # 2023-01-01 00:00 UTC
DESIGN_END_MS = 1751328000000        # 2025-07-01 00:00 UTC (exclusivo) -> holdout empieza aquí
SPLIT_AB_MS = 1711929600000          # 2024-04-01 00:00 UTC: DISEÑO-A [2023-01, 2024-03], DISEÑO-B [2024-04, 2025-06]
COST = 0.0024


def load(sym):
    """Carga velas de 15m y recorta ESTRICTAMENTE al periodo de diseño (nunca devuelve holdout)."""
    a = np.load(os.path.join(KLINES, f"{sym}_15m.npy"))
    a = a[(a[:, 0] >= DESIGN_START_MS) & (a[:, 0] < DESIGN_END_MS)]
    assert a[-1, 0] < DESIGN_END_MS
    d = dict(t=a[:, 0].astype(np.int64), o=a[:, 1].copy(), h=a[:, 2].copy(), l=a[:, 3].copy(),
             c=a[:, 4].copy(), v=a[:, 5].copy(), tb=a[:, 6].copy())
    d["sym"] = sym
    d["N"] = len(a)
    return d


# ----------------------------------------------------------------- indicadores
def roll_mean_std(x, n):
    m = np.full(len(x), np.nan)
    s = np.full(len(x), np.nan)
    w = swv(x, n)
    m[n - 1:] = w.mean(1)
    s[n - 1:] = w.std(1, ddof=1)
    return m, s


def roll_sum(x, n):
    """Suma móvil de x[i-n+1..i] (NaN las primeras n-1)."""
    cs = np.concatenate([[0.0], np.cumsum(x)])
    out = np.full(len(x), np.nan)
    out[n - 1:] = cs[n:] - cs[:-n]
    return out


def roll_mean(x, n):
    return roll_sum(x, n) / n


def roll_max(x, n):
    out = np.full(len(x), np.nan)
    out[n - 1:] = swv(x, n).max(1)
    return out


def roll_min(x, n):
    out = np.full(len(x), np.nan)
    out[n - 1:] = swv(x, n).min(1)
    return out


def logret(c):
    r = np.zeros(len(c))
    r[1:] = np.diff(np.log(c))
    return r


def roll_std_ret(r, n):
    m = roll_mean(r, n)
    m2 = roll_mean(r * r, n)
    return np.sqrt(np.maximum(m2 - m * m, 0) * n / (n - 1))


def rsi_wilder(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = np.maximum(d, 0)
    dn = np.maximum(-d, 0)
    a = 1.0 / n
    au = np.zeros(len(c))
    ad = np.zeros(len(c))
    au[n] = up[1:n + 1].mean()
    ad[n] = dn[1:n + 1].mean()
    for i in range(n + 1, len(c)):
        au[i] = au[i - 1] + a * (up[i] - au[i - 1])
        ad[i] = ad[i - 1] + a * (dn[i] - ad[i - 1])
    rs = au / np.where(ad == 0, 1e-12, ad)
    out = 100 - 100 / (1 + rs)
    out[:n] = np.nan
    return out


# ----------------------------------------------------------------- simulación
def first_touch(d, idx, tp, sl, H=None, vec_steps=600):
    """Para cada entrada idx[j] (al cierre), devuelve (exit_idx, exit_price, outcome).
    outcome: 1 = TP, -1 = SL, 0 = tiempo, 2 = fin de datos. Empate TP/SL en la misma vela = SL."""
    h, l, o, c = d["h"], d["l"], d["o"], d["c"]
    N = len(c)
    idx = np.asarray(idx, dtype=np.int64)
    tp = np.asarray(tp, dtype=float)
    sl = np.asarray(sl, dtype=float)
    n = len(idx)
    ex_i = np.full(n, -1, dtype=np.int64)
    ex_p = np.zeros(n)
    out = np.zeros(n, dtype=np.int8)
    Hmax = H if H is not None else 10 ** 9
    act = np.arange(n)
    step = 0
    while len(act) and step < min(vec_steps, Hmax):
        step += 1
        j = idx[act] + step
        endm = j >= N
        if endm.any():
            a_end = act[endm]
            ex_i[a_end] = N - 1
            ex_p[a_end] = c[N - 1]
            out[a_end] = 2
            act = act[~endm]
            j = j[~endm]
        if not len(act):
            break
        hs = l[j] <= sl[act]
        ht = h[j] >= tp[act]
        if hs.any():
            a = act[hs]
            jj = j[hs]
            ex_i[a] = jj
            ex_p[a] = np.minimum(sl[a], o[jj])
            out[a] = -1
        m = ht & ~hs
        if m.any():
            a = act[m]
            ex_i[a] = j[m]
            ex_p[a] = tp[a]
            out[a] = 1
        keep = ~(hs | ht)
        act = act[keep]
        if step == Hmax and len(act):
            jj = idx[act] + step
            ex_i[act] = jj
            ex_p[act] = c[jj]
            out[act] = 0
            act = act[:0]
    # resto: búsqueda por bloques
    for a in act:
        start = idx[a] + step + 1
        stop_lim = min(N, idx[a] + Hmax + 1)
        found = False
        while start < stop_lim:
            e = min(stop_lim, start + 8192)
            hs = l[start:e] <= sl[a]
            ht = h[start:e] >= tp[a]
            m = hs | ht
            if m.any():
                k = int(np.argmax(m))
                jj = start + k
                ex_i[a] = jj
                if hs[k]:
                    ex_p[a] = min(sl[a], o[jj])
                    out[a] = -1
                else:
                    ex_p[a] = tp[a]
                    out[a] = 1
                found = True
                break
            start = e
        if not found:
            if idx[a] + Hmax < N:
                jj = idx[a] + Hmax
                ex_i[a] = jj
                ex_p[a] = c[jj]
                out[a] = 0
            else:
                ex_i[a] = N - 1
                ex_p[a] = c[N - 1]
                out[a] = 2
    return ex_i, ex_p, out


def select_sequential(idx, ex_i):
    """Una posición a la vez: toma la señal si su índice > salida de la anterior. idx debe estar ordenado."""
    taken = []
    free = -1
    for k in range(len(idx)):
        if idx[k] > free:
            taken.append(k)
            free = ex_i[k]
    return np.array(taken, dtype=np.int64)


def wilson(w, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = w / n
    den = 1 + z * z / n
    cen = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (cen - half, cen + half)


def metrics(r_net, R, t_entry=None, months=None):
    """r_net: retorno neto por operación (fracción). R: riesgo por operación (fracción del precio, entrada - SL).
    Devuelve dict con N, WR, IC Wilson, b efectivo, E %, E R, PF, MDD (R), racha perdedora máx."""
    r_net = np.asarray(r_net, float)
    R = np.asarray(R, float)
    n = len(r_net)
    if n == 0:
        return dict(N=0)
    win = r_net > 0
    w = int(win.sum())
    lo, hi = wilson(w, n)
    gw = r_net[win].mean() if w else 0.0
    gl = -r_net[~win].mean() if n - w else np.nan
    rR = r_net / R
    eq = np.cumsum(rR)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    mdd = float(np.max(peak - eq)) if n else 0.0
    # racha perdedora
    streak = 0
    best = 0
    for x in win:
        streak = 0 if x else streak + 1
        best = max(best, streak)
    pos = r_net[r_net > 0].sum()
    neg = -r_net[r_net <= 0].sum()
    se = rR.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    se_p = r_net.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    res = dict(N=n, WR=w / n, WR_lo=lo, WR_hi=hi, b_eff=(gw / gl) if gl and gl > 0 else np.nan,
               E_pct=float(r_net.mean() * 100), t_E_pct=float(r_net.mean() / se_p) if se_p else np.nan, E_R=float(rR.mean()), t_E_R=float(rR.mean() / se) if se else np.nan,
               PF=(pos / neg) if neg > 0 else np.inf, MDD_R=mdd, maxL=best, R_med=float(np.median(R) * 100))
    if months is not None:
        res["per_month"] = n / months
    return res


def fmt(m, extra=""):
    if m.get("N", 0) == 0:
        return f"N=0 {extra}"
    return (f"N={m['N']:5d} WR={m['WR']*100:5.1f}% [{m['WR_lo']*100:4.1f},{m['WR_hi']*100:4.1f}] "
            f"b={m['b_eff']:.2f} E={m['E_pct']:+.3f}%(t={m['t_E_pct']:+.1f}) E_R={m['E_R']:+.3f} (t={m['t_E_R']:+.1f}) PF={m['PF']:.2f} "
            f"MDD={m['MDD_R']:.1f}R maxL={m['maxL']} Rmed={m['R_med']:.2f}% {extra}")


def months_span(d, mask=None):
    t = d["t"] if mask is None else d["t"][mask]
    return (t[-1] - t[0]) / (1000 * 3600 * 24 * 30.4375)


def run_trades(d, sig_idx, tp, sl, H=None, cost=COST):
    """Simula señales ordenadas (idx, tp, sl), selección secuencial, devuelve arrays de operaciones tomadas."""
    order = np.argsort(sig_idx, kind="stable")
    sig_idx, tp, sl = sig_idx[order], tp[order], sl[order]
    ex_i, ex_p, out = first_touch(d, sig_idx, tp, sl, H)
    tk = select_sequential(sig_idx, ex_i)
    entry = d["c"][sig_idx[tk]]
    r_g = ex_p[tk] / entry - 1
    R = (entry - sl[tk]) / entry
    return dict(i=sig_idx[tk], exit=ex_i[tk], out=out[tk], r_gross=r_g, r_net=r_g - cost, R=R,
                tp=tp[tk], sl=sl[tk], all_idx=sig_idx, all_ex=ex_i, all_exp=ex_p, all_out=out, all_tp=tp, all_sl=sl)
