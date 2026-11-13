"""Comun del Constructor: carga de datos (spot + futuros), variables causales, etiquetas de triple barrera.

Convenciones de tiempo: la vela i de 15 m abre en t_i y cierra en t_i + 15 min. Todas las variables de la
vela i usan solo informacion disponible al CIERRE de i:
  * metrics (5 min, create_time = inicio de la ventana): solo filas con create_time <= t_i + 5 min.
  * funding: solo liquidaciones con calc_time <= t_i + 15 min.
  * premiumIndex / klines de futuros de 15 m: la vela con el mismo open_time (cierra a la vez que la spot).
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(RESEARCH, "scripts"))
import harness as H  # noqa: E402

MS15 = 900_000
SIGMA_WIN = 672          # 7 dias de velas de 15 m para la volatilidad de referencia
COST = 0.0024            # ida y vuelta (0.12 % por lado)


# ------------------------------------------------------------------ utilidades NaN-tolerantes
def ffill(x, max_gap=None):
    x = np.asarray(x, float).copy()
    idx = np.where(np.isfinite(x), np.arange(len(x)), -1)
    np.maximum.accumulate(idx, out=idx)
    out = np.where(idx >= 0, x[np.maximum(idx, 0)], np.nan)
    if max_gap is not None:
        gap = np.arange(len(x)) - idx
        out[gap > max_gap] = np.nan
    return out


def rmean(x, n):
    return H.rolling_mean(np.asarray(x, float), n)


def rstd(x, n):
    return H.rolling_std(np.asarray(x, float), n)


def lag(x, k):
    return H.shift(np.asarray(x, float), k)


def safe_log(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(np.where(np.asarray(x, float) > 0, x, np.nan))


def _nan_rsum(x, n):
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    cs = np.concatenate(([0.0], np.cumsum(np.where(ok, x, 0.0))))
    cn = np.concatenate(([0], np.cumsum(ok)))
    s = np.full(len(x), np.nan); k = np.full(len(x), 0.0)
    s[n - 1:] = cs[n:] - cs[:-n]; k[n - 1:] = cn[n:] - cn[:-n]
    return s, k


def zs(x, n):
    """z-score rodante tolerante a NaN (exige >= n/2 valores validos en la ventana)."""
    x = np.asarray(x, float)
    s1, k = _nan_rsum(x, n)
    s2, _ = _nan_rsum(x * x, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        m = s1 / k
        var = np.maximum(s2 / k - m * m, 0) * k / np.maximum(k - 1, 1)
        z = (x - m) / np.sqrt(var)
    z[k < n / 2] = np.nan
    return z


# ------------------------------------------------------------------ carga
def find_file(data_dir, sub, name):
    for p in (os.path.join(data_dir, sub, name), os.path.join(data_dir, name)):
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"{name} no encontrado en {data_dir} ni en {data_dir}/{sub}")


def load_spot(data_dir, sym):
    return np.load(find_file(data_dir, "klines", f"{sym}_15m.npy"))


def load_fut(data_dir, sym):
    out = {}
    for k in ("metrics", "funding", "premium15m", "fut15m"):
        out[k] = np.load(find_file(data_dir, "futures", f"{sym}_{k}.npy"))
    return out


def align_exact(t, src_t):
    """indice en src con el mismo open_time que t (o -1)."""
    j = np.searchsorted(src_t, t)
    j = np.minimum(j, len(src_t) - 1)
    ok = src_t[j] == t
    return np.where(ok, j, -1)


def align_asof(t_avail, src_t, max_age_ms):
    """ultimo indice de src con src_t <= t_avail y antiguedad <= max_age_ms (o -1)."""
    j = np.searchsorted(src_t, t_avail, side="right") - 1
    ok = (j >= 0) & (t_avail - src_t[np.maximum(j, 0)] <= max_age_ms)
    return np.where(ok, j, -1)


def take(src, j):
    return np.where(j >= 0, src[np.maximum(j, 0)], np.nan)


# ------------------------------------------------------------------ variables
def spot_core(a):
    t, o, h, l, c, v, tbv = (a[:, k] for k in range(7))
    lr = H.log_returns(c)
    s15 = H.rolling_std(np.nan_to_num(lr), SIGMA_WIN)       # sigma por vela (7 dias)
    return dict(t=t, o=o, h=h, l=l, c=c, v=v, tbv=tbv, lr=lr, s15=s15)


def spot_features(S, B):
    """S: dict de la moneda; B: dict de BTC (alineado al mismo indice). Devuelve dict nombre->array."""
    c, h, l, o, v, tbv, lr, s15 = S["c"], S["h"], S["l"], S["o"], S["v"], S["tbv"], S["lr"], S["s15"]
    F = {}
    lc = np.log(c)
    for k in (1, 4, 16, 48, 96, 288, 672):
        F[f"ret_{k}"] = (lc - lag(lc, k)) / (s15 * np.sqrt(k))
    F["vol_ratio_16_96"] = safe_log(rstd(np.nan_to_num(lr), 16) / rstd(np.nan_to_num(lr), 96))
    F["vol_ratio_96_672"] = safe_log(rstd(np.nan_to_num(lr), 96) / s15)
    F["vol_level"] = safe_log(s15 * np.sqrt(96) / COST)           # R/c aproximado de la geometria
    atr = H.atr(h, l, c, 14)
    F["atr_rel"] = atr / c / s15
    for n in (20, 96, 672):
        F[f"z_{n}"] = (c - rmean(c, n)) / (c * s15 * np.sqrt(n / 2.0))
    for n in (96, 672):
        mx, mn = H.rolling_max(h, n), H.rolling_min(l, n)
        F[f"rngpos_{n}"] = (c - mn) / np.maximum(mx - mn, 1e-12)
        F[f"dd_{n}"] = np.log(c / mx) / (s15 * np.sqrt(n))
    d = np.diff(c, prepend=np.nan)
    up = H.ema(np.nan_to_num(np.maximum(d, 0)), alpha=1 / 14)
    dn = H.ema(np.nan_to_num(np.maximum(-d, 0)), alpha=1 / 14)
    F["rsi14"] = up / np.maximum(up + dn, 1e-12) - 0.5
    lv = safe_log(v + 1e-9)
    F["vol_rel_1"] = lv - rmean(lv, 672)
    F["vol_rel_16"] = rmean(lv, 16) - rmean(lv, 672)
    F["vol_rel_96"] = rmean(lv, 96) - rmean(lv, 672)
    imb = np.where(v > 0, tbv / np.maximum(v, 1e-12) - 0.5, 0.0)
    for n in (1, 4, 16, 96):
        F[f"taker_imb_{n}"] = rmean(imb, n) if n > 1 else imb
    rng = np.maximum(h - l, 1e-12)
    F["bar_body"] = (c - o) / rng
    F["bar_upwick"] = (h - np.maximum(o, c)) / rng
    F["bar_range"] = (h - l) / c / s15
    hr = ((S["t"] // 3_600_000) % 24).astype(float)
    wd = (((S["t"] // 86_400_000) + 3) % 7).astype(float)    # 0 = lunes
    F["hour_sin"], F["hour_cos"] = np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)
    F["wd_sin"], F["wd_cos"] = np.sin(2 * np.pi * wd / 7), np.cos(2 * np.pi * wd / 7)
    # contexto BTC
    bl = np.log(B["c"])
    for k in (4, 16, 96, 672):
        F[f"btc_ret_{k}"] = (bl - lag(bl, k)) / (B["s15"] * np.sqrt(k))
    F["btc_z_672"] = (B["c"] - rmean(B["c"], 672)) / (B["c"] * B["s15"] * np.sqrt(336))
    F["btc_vol_ratio"] = safe_log(rstd(np.nan_to_num(B["lr"]), 96) / B["s15"])
    F["rel_btc_96"] = (lc - lag(lc, 96)) - (bl - lag(bl, 96))
    F["rel_btc_672"] = (lc - lag(lc, 672)) - (bl - lag(bl, 672))
    corr_n = 672
    x, y = np.nan_to_num(lr), np.nan_to_num(B["lr"])
    mx_, my_ = rmean(x, corr_n), rmean(y, corr_n)
    cov = rmean(x * y, corr_n) - mx_ * my_
    F["beta_btc"] = cov / np.maximum(rmean(y * y, corr_n) - my_ ** 2, 1e-18)
    return F


def futures_features(S, FU):
    t, c, v = S["t"], S["c"], S["v"]
    F = {}
    M = FU["metrics"]
    M = M[np.argsort(M[:, 0], kind="stable")]
    # Regla del Verificador (regla_metrics.md): un registro con create_time T se conoce en T + 5 min; aqui se exige
    # T <= t_i + 5 min (margen recomendado para vivo). Relleno hacia adelante por columna desde el ultimo valor
    # VALIDO con antiguedad <= 30 min; si no hay, NaN + indicador de faltante. Nunca hacia atras.
    t_av = t + 300_000

    def col(k, x=None):
        x = M[:, k] if x is None else x
        ok = np.isfinite(x)
        j = align_asof(t_av, M[ok, 0], 1_800_000)
        return take(x[ok], j)
    oi, oiv = col(1), col(2)
    top_acc, top_pos, glob_acc = col(3), col(4), col(5)
    # taker ratio: media (log) de los registros T en {t_av-10, t_av-5, t_av} (exige los 3 contiguos)
    tk = safe_log(M[:, 6])
    mt = M[:, 0]
    tk3 = np.full(len(tk), np.nan)
    if len(tk) >= 3:
        contig = (mt[2:] - mt[:-2]) == 600_000
        tk3[2:] = np.where(contig, (tk[2:] + tk[1:-1] + tk[:-2]) / 3, np.nan)
    taker = col(0, tk3)
    F["metrics_missing"] = (~np.isfinite(oi)).astype(float)
    loi = safe_log(oi)
    for k in (1, 4, 16, 96):
        F[f"oi_chg_{k}"] = (loi - lag(loi, k))
    F["oi_z_672"] = zs(loi, 672)
    F["oi_to_vol"] = safe_log(oiv / np.maximum(rmean(v * c, 96) * 96, 1e-9))
    for nm, x in (("top_acc", top_acc), ("top_pos", top_pos), ("glob_acc", glob_acc)):
        lx = safe_log(x)
        F[f"{nm}_lvl"] = lx
        F[f"{nm}_chg_16"] = lx - lag(lx, 16)
        F[f"{nm}_chg_96"] = lx - lag(lx, 96)
        F[f"{nm}_z_672"] = zs(lx, 672)
    F["fut_taker_1"] = taker
    F["fut_taker_4"] = rmean(np.nan_to_num(taker), 4)
    F["fut_taker_16"] = rmean(np.nan_to_num(taker), 16)
    # funding
    FR = FU["funding"]
    jf = align_asof(t + MS15, FR[:, 0], 9 * 3_600_000)
    fr = ffill(take(FR[:, 1], jf), 40)
    F["funding"] = fr * 1e4
    F["funding_z_2016"] = zs(fr, 2016)
    # prima (premium index) y base futuros/spot
    P = FU["premium15m"]
    jp = align_exact(t, P[:, 0])
    prem = ffill(take(P[:, 4], jp), 2) * 1e4
    F["premium"] = prem
    F["premium_16"] = rmean(np.nan_to_num(prem), 16)
    F["premium_z_672"] = zs(prem, 672)
    K = FU["fut15m"]
    jk = align_exact(t, K[:, 0])
    fc = ffill(take(K[:, 4], jk), 2)
    fv = take(K[:, 5], jk)
    ftb = take(K[:, 6], jk)
    basis = (fc / c - 1) * 1e4
    F["basis"] = basis
    F["basis_z_672"] = zs(basis, 672)
    fimb = np.where(fv > 0, ftb / np.maximum(fv, 1e-12) - 0.5, np.nan)
    F["fut_imb_1"] = fimb
    F["fut_imb_16"] = rmean(np.nan_to_num(fimb), 16)
    F["fut_spot_vol"] = safe_log(rmean(np.nan_to_num(fv), 16) / np.maximum(rmean(v, 16), 1e-12))
    return F


def seq_channels(S, B, FU=None):
    """Canales por vela para la red de secuencias (normalizados de forma causal)."""
    s15 = S["s15"]
    ch = [np.nan_to_num(S["lr"]) / s15,
          (S["h"] - S["l"]) / S["c"] / s15,
          (S["c"] - S["o"]) / np.maximum(S["h"] - S["l"], 1e-12),
          safe_log(S["v"] + 1e-9) - rmean(safe_log(S["v"] + 1e-9), 672),
          np.where(S["v"] > 0, S["tbv"] / np.maximum(S["v"], 1e-12) - 0.5, 0.0) * 4,
          np.nan_to_num(B["lr"]) / B["s15"]]
    names = ["lr", "range", "body", "vol", "imb", "btc_lr"]
    if FU is not None:
        FF = futures_features(S, FU)
        ch += [FF["oi_chg_1"] / np.maximum(rstd(np.nan_to_num(FF["oi_chg_1"]), 672), 1e-9),
               FF["fut_taker_1"] * 3, FF["premium_z_672"], FF["fut_imb_1"] * 4]
        names += ["d_oi", "fut_taker", "premium_z", "fut_imb"]
    X = np.stack(ch, 1).astype(np.float32)
    X = np.clip(np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0), -8, 8)
    return X, names


# ------------------------------------------------------------------ etiquetas
GEOMS = {
    # nombre: (a, m, H)  TP = c*(1 + a*sd), SL = c*(1 - m*sd), sd = sigma15(672)*sqrt(96) (vol diaria)
    "G1": (0.5, 1.0, 96),
    "G2": (0.4, 1.2, 96),
    "G3": (0.75, 1.5, 192),
    "G4": (0.4, 1.2, 192),
    "G5": (0.6, 1.5, 192),
}


def barriers(S, geom):
    a, m, Hh = GEOMS[geom]
    sd = S["s15"] * np.sqrt(96)
    return S["c"] * (1 + a * sd), S["c"] * (1 - m * sd), Hh


def label_all(S, geom, i_end, fee=H.FEE, slip=H.SLIP):
    """Resultado de entrar al cierre de CADA vela i < i_end con la geometria (misma logica que harness.simulate,
    salida nunca usa velas >= i_end). Devuelve net (N,), reason (N,), exit_idx (N,). NaN donde no hay sigma."""
    o, h, l, c = S["o"], S["h"], S["l"], S["c"]
    tp, sl, Hh = barriers(S, geom)
    N = len(c)
    done = np.zeros(N, bool)
    px = np.full(N, np.nan)
    why = np.full(N, -1)
    jx = np.full(N, -1)
    idx = np.arange(N)
    for k in range(1, Hh + 1):
        j = idx + k
        valid = (j < i_end) & ~done
        jj = np.minimum(j, N - 1)
        hs = valid & (l[jj] <= sl)
        ht = valid & ~hs & (h[jj] >= tp)
        px[hs] = np.minimum(sl[hs], o[jj][hs]); why[hs] = 1; jx[hs] = jj[hs]
        px[ht] = tp[ht]; why[ht] = 0; jx[ht] = jj[ht]
        done |= hs | ht
        # barrera de tiempo
        if k == Hh:
            tm = valid & ~hs & ~ht
            px[tm] = c[jj][tm]; why[tm] = 2; jx[tm] = jj[tm]; done |= tm
    # las que llegan al final del periodo sin cerrar: END al cierre de i_end-1
    rest = ~done & (idx < i_end - 1)
    px[rest] = c[i_end - 1]; why[rest] = 3; jx[rest] = i_end - 1
    net = H.net_return(c, px, fee, slip)
    bad = ~np.isfinite(tp) | ~np.isfinite(sl) | (idx >= i_end - 1) | (sl >= c)
    net = np.where(bad, np.nan, net)
    return net, why, jx


# ------------------------------------------------------------------ ensamblado por moneda
def build_symbol(data_dir, sym, use_fut=True, t_end_ms=None):
    a = load_spot(data_dir, sym)
    b = load_spot(data_dir, "BTCUSDT")
    if t_end_ms is not None:
        a = a[a[:, 0] < t_end_ms]
    # alinear BTC al indice de la moneda (mismo open_time)
    jb = align_exact(a[:, 0], b[:, 0])
    bb = np.where(jb[:, None] >= 0, b[np.maximum(jb, 0)], np.nan)
    bb[:, 0] = a[:, 0]
    for k in range(1, 7):
        bb[:, k] = ffill(bb[:, k])
    S, B = spot_core(a), spot_core(bb)
    F = spot_features(S, B)
    FU = load_fut(data_dir, sym) if use_fut else None
    if use_fut:
        F.update(futures_features(S, FU))
    return S, B, F, FU
