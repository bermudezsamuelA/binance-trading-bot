"""Ronda 1 - Paso 9: robustez del candidato 'MR20 + score ridge h=96, decil superior' (DISEÑO 2023-10..2025-06).
Variantes: lambda in {0.01, 0.1, 1}*N_train; modelo completo (47 columnas) vs compacto (12 variables con signo
estable en los 21 reajustes mensuales); entrada al cierre vs a la apertura siguiente (next_open, niveles
re-anclados). Geometrías fijas: T48, G2H96, G3H96. Desglose por moneda con E y t."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import datetime as dt
import analista_common as ac
import analista_features as af
import harness as Hh

FULL = [f for f in af.FEATURES if f not in ("hour", "dow")]
COMPACT = ["pos672", "ret_1d", "dd_7d", "ret_4h", "sig96_hnorm", "slope_sma800", "rel_ret_4h", "R_pct", "bbw",
           "btc_ret_1d", "rsi14_1h", "rsi14"]


def scores(data, Fs, h, feats, lam_mult, q=0.9, extras=True):
    S_, I_, T_, X_, Y_ = [], [], [], [], []
    for si, s in enumerate(ac.SYMS):
        F = Fs[s]; c = data[s]["c"]
        with np.errstate(invalid="ignore"):
            idx = np.where((F["z"] < -2) & (F["R_pct"] >= 0.005))[0]
        idx = idx[idx >= 900]
        cols = [F[f][idx] for f in feats]
        if extras:
            cols += [np.sin(2 * np.pi * F["hour"][idx] / 24), np.cos(2 * np.pi * F["hour"][idx] / 24)]
            cols += [np.full(len(idx), 1.0 if j == si else 0.0) for j in range(4)]
        y = np.full(len(idx), np.nan)
        ok = idx + h < len(c)
        y[ok] = c[idx[ok] + h] / c[idx[ok]] - 1
        S_.append(np.full(len(idx), si)); I_.append(idx); T_.append(data[s]["t"][idx]); X_.append(np.column_stack(cols)); Y_.append(y)
    S = np.concatenate(S_); I = np.concatenate(I_); T = np.concatenate(T_); X = np.vstack(X_); y = np.concatenate(Y_)
    take = np.zeros(len(y), bool)
    months = sorted(set(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m") for t in T))
    for mth in [m for m in months if m >= "2023-10"]:
        y0, m0 = int(mth[:4]), int(mth[5:])
        start = dt.datetime(y0, m0, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
        end = dt.datetime(y0 + (m0 == 12), 1 if m0 == 12 else m0 + 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
        tr = (T + h * 900000 < start) & ~np.isnan(y)
        te = (T >= start) & (T < end)
        mu = np.nanmean(X[tr], 0); sd = np.nanstd(X[tr], 0); sd[sd == 0] = 1
        Z = lambda A: np.hstack([np.ones((len(A), 1)), np.nan_to_num(np.clip((A - mu) / sd, -5, 5))])
        Xt = Z(X[tr])
        L = lam_mult * tr.sum() * np.eye(Xt.shape[1]); L[0, 0] = 0
        w = np.linalg.solve(Xt.T @ Xt + L, Xt.T @ np.clip(y[tr], -0.2, 0.2))
        th = np.quantile(Xt @ w, q)
        take[te] = (Z(X[te]) @ w) >= th
    return S, I, take


def run(bars, S, I, take, gname, entry_mode="close"):
    m_sl, H, tpon = {"T48": (None, 48, False), "G2H96": (2.0, 96, True), "G3H96": (3.0, 96, True)}[gname]
    START = Hh.ms(2023, 10, 1)
    out = {"A": [], "B": []}
    for si, s in enumerate(ac.SYMS):
        b = bars[s]
        ent = np.zeros(len(b), bool)
        ent[I[(S == si) & take]] = True
        mu = Hh.rolling_mean(b.c, 20); R = mu - b.c
        tp = mu if tpon else None
        sl = (b.c - m_sl * R) if m_sl else None
        for part, (a0, a1) in (("A", (START, ac.SPLIT_AB_MS)), ("B", (ac.SPLIT_AB_MS, ac.DESIGN_END_MS))):
            out[part].append(Hh.simulate(b, ent, tp, sl, period=(b.idx(a0), b.idx(a1)), max_hold=H,
                                         risk=(None if m_sl else R), entry_mode=entry_mode, levels="relative"))
    return out


def line(m):
    return (f"N={m['n']:4d} WR={m['wr']*100:4.1f}% [{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}] b={m['b_eff']:.2f} "
            f"E={m['E_pct']:+.3f}% (t={m['t']:+.2f}) PF={m['pf']:.2f}")


def main():
    lines = []
    P = lambda s: (print(s), lines.append(s))
    data = {s: ac.load(s) for s in ac.SYMS}
    Fs = af.add_cross({s: af.build(data[s], 20) for s in ac.SYMS}, ac.SYMS)
    bars = {s: Hh.load(s) for s in ac.SYMS}
    n_cfg = 0
    variants = [("completo", FULL, 0.1, True, "close"), ("completo", FULL, 0.01, True, "close"),
                ("completo", FULL, 1.0, True, "close"), ("compacto", COMPACT, 0.1, False, "close"),
                ("compacto", COMPACT, 1.0, False, "close"), ("completo", FULL, 0.1, True, "next_open")]
    for name, feats, lam, ex, em in variants:
        S, I, take = scores(data, Fs, 96, feats, lam, extras=ex)
        P(f"\n--- {name} lambda={lam}*N entrada={em} ---")
        for g in ("T48", "G2H96", "G3H96"):
            out = run(bars, S, I, take, g, em)
            n_cfg += 1
            mA = Hh.metrics(Hh.Trades.concat(out["A"])); mB = Hh.metrics(Hh.Trades.concat(out["B"]))
            P(f"  {g:6s} A: {line(mA)} | B: {line(mB)}")
            if name == "completo" and lam == 0.1 and em == "close":
                for si, s in enumerate(ac.SYMS):
                    tA = Hh.metrics(out["A"][si]); tB = Hh.metrics(out["B"][si])
                    P(f"         {s:8s} A: {line(tA)} | B: {line(tB)}")
    P(f"\nConfiguraciones evaluadas en este script: {n_cfg}")
    with open(os.path.join(ac.OUTDIR, "09_robustez.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    Hh.log_trials("analista", n_cfg, "R1 robustez candidato ridge (lambda, compacto, next_open) x 3 geometrias", "design")


if __name__ == "__main__":
    main()
