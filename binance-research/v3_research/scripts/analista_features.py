"""Variables candidatas para filtrar señales. TODAS causales: usan solo información hasta el cierre de la vela i."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac


def rolling_var(x, W):
    m = ac.roll_mean(x, W)
    m2 = ac.roll_mean(x * x, W)
    return np.maximum(m2 - m * m, 1e-30)


def build(d, n=20):
    c, h, l, o, v, tb, t = d["c"], d["h"], d["l"], d["o"], d["v"], d["tb"], d["t"]
    N = len(c)
    F = {}
    r = ac.logret(c)
    mu, sd = ac.roll_mean_std(c, n)
    F["z"] = (c - mu) / sd                                   # profundidad en sigmas de precio (la del bot)
    F["R_pct"] = (mu - c) / c                                # distancia a la media (riesgo de MR)
    s96 = ac.roll_std_ret(r, 96)
    s16 = ac.roll_std_ret(r, 16)
    s384 = ac.roll_std_ret(r, 384)
    F["zr"] = np.log(c / mu) / s96                           # profundidad en sigmas de retorno de 15m
    F["sig96"] = s96                                         # volatilidad realizada 24h (por vela)
    F["volratio"] = s16 / s384                               # sigma corta / sigma larga
    F["bbw"] = 2 * sd / mu                                   # ancho de banda relativo (k=1)
    # régimen: VR(4), rho(1), vida media OU sobre 7 días (672 velas)
    W = 672
    v1 = rolling_var(r, W)
    r4 = ac.roll_sum(r, 4)
    r4 = np.nan_to_num(r4)
    v4 = rolling_var(r4, W)
    F["VR4"] = v4 / (4 * v1)
    r16 = np.nan_to_num(ac.roll_sum(r, 16))
    F["VR16"] = rolling_var(r16, W) / (16 * v1)
    rl = np.concatenate([[0.0], r[:-1]])
    cov = ac.roll_mean(r * rl, W) - ac.roll_mean(r, W) * ac.roll_mean(rl, W)
    F["rho1"] = cov / v1
    X = np.log(c) - np.log(c[0])
    xl = np.concatenate([[X[0]], X[:-1]])
    dy = X - xl
    cxy = ac.roll_mean(xl * dy, W) - ac.roll_mean(xl, W) * ac.roll_mean(dy, W)
    vxx = rolling_var(xl, W)
    beta = cxy / vxx
    with np.errstate(invalid="ignore", divide="ignore"):
        hl = np.where(beta < 0, -np.log(2) / np.log1p(np.minimum(beta, -1e-9)), 1e5)
    F["log_halflife"] = np.log10(np.clip(hl, 1, 1e5))
    # tendencia en temporalidad mayor (desde velas de 15m)
    lc = np.log(c)
    for name, k in (("ret_1h", 4), ("ret_4h", 16), ("ret_1d", 96), ("ret_3d", 288), ("ret_7d", 672)):
        x = np.full(N, np.nan)
        x[k:] = lc[k:] - lc[:-k]
        F[name] = x
    sma800 = ac.roll_mean(c, 800)                            # ~ SMA200 de 1h / SMA50 de 4h
    F["dist_sma800"] = np.log(c / sma800)
    sma96 = ac.roll_mean(c, 96)
    sl96 = np.full(N, np.nan)
    sl96[16:] = np.log(sma96[16:] / sma96[:-16])
    F["slope_sma96"] = sl96
    # pendiente de la SMA de 4h (50 periodos = 800 velas) en las últimas 4h
    s8 = np.full(N, np.nan)
    s8[16:] = np.log(sma800[16:] / sma800[:-16])
    F["slope_sma800"] = s8
    # RSI
    F["rsi14"] = ac.rsi_wilder(c, 14)
    hidx = np.where(t % 3600000 == 2700000)[0]               # velas que cierran en la hora exacta
    rsi_h = ac.rsi_wilder(c[hidx], 14)
    pos = np.searchsorted(hidx, np.arange(N), side="right") - 1
    rh = np.full(N, np.nan)
    ok = pos >= 0
    rh[ok] = rsi_h[pos[ok]]
    F["rsi14_1h"] = rh
    # horario
    hour = ((t // 3600000) % 24).astype(float)
    F["hour"] = hour
    F["dow"] = (((t // 86400000) + 3) % 7).astype(float)     # 0 = lunes
    # retorno de la vela normalizado por la sigma típica de su hora (estimación expansiva, causal)
    hr = hour.astype(int)
    sig_h = np.full(N, np.nan)
    acc = np.zeros(24); cnt = np.zeros(24)
    r2 = r * r
    # expansiva por hora: usa solo velas anteriores de esa hora
    for hh in range(24):
        ii = np.where(hr == hh)[0]
        cs = np.cumsum(r2[ii])
        k = np.arange(1, len(ii) + 1)
        prev = np.concatenate([[np.nan], np.sqrt(cs[:-1] / k[:-1])])
        sig_h[ii] = prev
    with np.errstate(invalid="ignore", divide="ignore"):
        sig_h = np.where(sig_h > 0, sig_h, np.nan)
    F["r0_hnorm"] = r / sig_h
    F["sig96_hnorm"] = s96 / sig_h                           # vol actual relativa a la típica de esa hora
    # volumen y desequilibrio taker
    vm96 = np.full(N, np.nan)
    vm96[1:] = ac.roll_mean(v, 96)[:-1]
    F["relvol"] = v / vm96
    F["relvol4"] = ac.roll_sum(v, 4) / (4 * vm96)
    with np.errstate(invalid="ignore", divide="ignore"):
        F["tb"] = np.where(v > 0, tb / v, 0.5)
        F["tb4"] = ac.roll_sum(tb, 4) / ac.roll_sum(v, 4)
        F["tb96"] = ac.roll_sum(tb, 96) / ac.roll_sum(v, 96)
    # posición en el rango reciente
    mx96, mn96 = ac.roll_max(h, 96), ac.roll_min(l, 96)
    F["pos96"] = (c - mn96) / (mx96 - mn96)
    mx672, mn672 = ac.roll_max(h, 672), ac.roll_min(l, 672)
    F["dd_7d"] = np.log(c / mx672)
    F["up_7d"] = np.log(c / mn672)
    F["pos672"] = (c - mn672) / (mx672 - mn672)
    # forma de la vela de la señal
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        F["lowwick"] = np.where(rng > 0, (c - l) / rng, 0.5)
    F["r0"] = r
    # velas bajistas consecutivas
    dn = (r < 0).astype(int)
    run = np.zeros(N)
    for i in range(1, N):
        run[i] = run[i - 1] + 1 if dn[i] else 0
    F["down_run"] = run
    return F


def add_cross(Fs, syms):
    """Variables de contexto de mercado: BTC y número de monedas en 'dip' simultáneo."""
    btc = Fs["BTCUSDT"]
    zstack = np.vstack([Fs[s]["z"] for s in syms])
    breadth = np.sum(zstack < -2, axis=0).astype(float)
    r4stack = np.vstack([Fs[s]["ret_4h"] for s in syms])
    for s in syms:
        Fs[s]["btc_ret_4h"] = btc["ret_4h"].copy()
        Fs[s]["btc_ret_1d"] = btc["ret_1d"].copy()
        Fs[s]["btc_z"] = btc["z"].copy()
        Fs[s]["breadth_dip"] = breadth
        others = [j for j, x in enumerate(syms) if x != s]
        with np.errstate(invalid="ignore"):
            Fs[s]["rel_ret_4h"] = Fs[s]["ret_4h"] - r4stack[others].mean(axis=0)   # caída idiosincrática
    return Fs


FEATURES = ["z", "R_pct", "zr", "sig96", "volratio", "bbw", "VR4", "VR16", "rho1", "log_halflife",
            "ret_1h", "ret_4h", "ret_1d", "ret_3d", "ret_7d", "dist_sma800", "slope_sma96", "slope_sma800",
            "rsi14", "rsi14_1h", "hour", "dow", "r0_hnorm", "sig96_hnorm", "relvol", "relvol4", "tb", "tb4", "tb96",
            "pos96", "dd_7d", "up_7d", "pos672", "lowwick", "r0", "down_run",
            "btc_ret_4h", "btc_ret_1d", "btc_z", "breadth_dip", "rel_ret_4h"]
