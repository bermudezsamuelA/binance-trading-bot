"""Ronda 2 (Validador): auditoria de fuga de informacion y protocolo de aceptacion de C1 (solo DISENO).

C1 = MR20 (z<-2, R>=0.5 %) + score ridge (41 variables + hora sen/cos + moneda), objetivo ret a 96 velas
clip +-20 %, lambda = 0.1*N_train, reentrenamiento mensual expansivo con purga, compra si score >= Q90 del
entrenamiento. Geometrias T48 / G2H96 / G3H96.

Partes:
  1. Causalidad empirica: se recalculan las variables con datos truncados en i y se comparan con las de la
     serie completa (una variable con mirada al futuro cambiaria).
  2. Reimplementacion independiente del pipeline con asserts (purga, normalizacion y Q90 solo con entrenamiento)
     y comparacion con analista_09_robustez.scores.
  3. Protocolo: pliegues 3 meses (>= 4/6 con E>0), WF 12/3/3 estricto (ventana movil 12 meses, reajuste
     trimestral), costos 0.30 %, retraso de 1 vela, embargo extra, placebo de etiquetas permutadas, DSR
     con el conteo total del equipo y PBO (CSCV) sobre la familia de variantes de C1.
Salida: output/validador/r2_audit_c1.txt / .json
"""
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analista_common as ac  # noqa: E402
import analista_features as af  # noqa: E402
import analista_09_robustez as rb  # noqa: E402
import harness as H  # noqa: E402

OUT = []
RES = {}


def P(s=""):
    print(s, flush=True)
    OUT.append(s)


SYMS = ac.SYMS
FULL = rb.FULL
START_OOS = H.ms(2023, 10, 1)
END_D = H.DESIGN[1]
GEOM = {"T48": (None, 48), "G2H96": (2.0, 96), "G3H96": (3.0, 96), "T96": (None, 96), "G1H48": (1.0, 48)}

data = {s: ac.load(s) for s in SYMS}
Fs = af.add_cross({s: af.build(data[s], 20) for s in SYMS}, SYMS)
bars = {s: H.load(s) for s in SYMS}
for s in SYMS:  # los indices de diseno del Analista son prefijo de las velas del arnes
    assert np.array_equal(data[s]["t"], bars[s].t[:data[s]["N"]])

# ------------------------------------------------------------------------------------------------
# 1. Causalidad empirica por truncamiento
# ------------------------------------------------------------------------------------------------
P("=== 1. Causalidad empirica (variables recalculadas con datos truncados en i) ===")
rng = np.random.default_rng(7)
N = data["BTCUSDT"]["N"]
cuts = np.sort(np.concatenate([rng.integers(3000, N - 1, 10), [N // 2, N - 2]]))
maxdiff = {f: 0.0 for f in af.FEATURES}
for i in cuts:
    trunc = {s: {k: (v[:i + 1] if isinstance(v, np.ndarray) else v) for k, v in data[s].items()} for s in SYMS}
    for s in SYMS:
        trunc[s]["N"] = i + 1
    Ft = af.add_cross({s: af.build(trunc[s], 20) for s in SYMS}, SYMS)
    for s in SYMS:
        for f in af.FEATURES:
            a = Fs[s][f][i - 3:i + 1]
            b = Ft[s][f][i - 3:i + 1]
            both_nan = np.isnan(a) & np.isnan(b)
            d = np.where(both_nan, 0.0, np.abs(a - b))
            d = np.nan_to_num(d, nan=np.inf)
            sc = np.nanstd(Fs[s][f]) or 1.0
            maxdiff[f] = max(maxdiff[f], float(np.max(d) / sc))
bad = {f: v for f, v in maxdiff.items() if v > 1e-9}
P(f"  {len(cuts)} cortes x 4 monedas x 4 velas x {len(af.FEATURES)} variables. Diferencia maxima relativa: "
  f"{max(maxdiff.values()):.2e}. Variables con diferencia > 1e-9: {bad if bad else 'ninguna'}")
RES["causalidad_maxdiff"] = maxdiff


# ------------------------------------------------------------------------------------------------
# 2. Reimplementacion independiente del pipeline
# ------------------------------------------------------------------------------------------------
def signal_table(h, feats=FULL, extras=True):
    S_, I_, T_, X_, Y_, YT_ = [], [], [], [], [], []
    for si, s in enumerate(SYMS):
        F, c, t = Fs[s], data[s]["c"], data[s]["t"]
        with np.errstate(invalid="ignore"):
            idx = np.flatnonzero((F["z"] < -2) & (F["R_pct"] >= 0.005))
        idx = idx[idx >= 900]
        cols = [F[f][idx] for f in feats]
        if extras:
            cols += [np.sin(2 * np.pi * F["hour"][idx] / 24), np.cos(2 * np.pi * F["hour"][idx] / 24)]
            cols += [np.full(len(idx), 1.0 if j == si else 0.0) for j in range(4)]
        y = np.full(len(idx), np.nan)
        yt = np.full(len(idx), np.iinfo(np.int64).max)  # instante en que se conoce la etiqueta (cierre de i+h)
        ok = idx + h < len(c)
        y[ok] = c[idx[ok] + h] / c[idx[ok]] - 1
        yt[ok] = t[idx[ok] + h] + 900_000
        S_.append(np.full(len(idx), si)); I_.append(idx); T_.append(t[idx]); X_.append(np.column_stack(cols))
        Y_.append(y); YT_.append(yt)
    return dict(S=np.concatenate(S_), I=np.concatenate(I_), T=np.concatenate(T_), X=np.vstack(X_),
                y=np.concatenate(Y_), yt=np.concatenate(YT_))


def month_starts(a, b):
    out, y, m = [], a.year, a.month
    while (y, m) < (b.year, b.month):
        out.append(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def c1_take(tab, lam=0.1, q=0.9, refit_months=1, train_months=None, embargo_ms=0, permute=None,
            first=dt.datetime(2023, 10, 1, tzinfo=dt.timezone.utc), last=dt.datetime(2025, 7, 1, tzinfo=dt.timezone.utc)):
    """Reentrena cada `refit_months` meses; entrenamiento = senales cuya etiqueta se conocio antes del inicio
    (menos embargo_ms) y, si train_months, solo las de los ultimos train_months meses. Devuelve take (bool)."""
    X, y, T, yt = tab["X"], tab["y"], tab["T"], tab["yt"]
    take = np.zeros(len(y), bool)
    score = np.full(len(y), np.nan)
    ms_list = month_starts(first, last)
    prng = np.random.default_rng(permute) if permute is not None else None
    for k in range(0, len(ms_list), refit_months):
        st = int(ms_list[k].timestamp() * 1000)
        en_dt = ms_list[k + refit_months] if k + refit_months < len(ms_list) else last
        en = int(en_dt.timestamp() * 1000)
        tr = (yt <= st - embargo_ms) & ~np.isnan(y)
        if train_months:
            m0 = ms_list[k]
            yy, mm = m0.year, m0.month - train_months
            while mm <= 0:
                yy, mm = yy - 1, mm + 12
            tr &= T >= int(dt.datetime(yy, mm, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        te = (T >= st) & (T < en)
        assert np.all(yt[tr] <= st), "fuga: etiqueta de entrenamiento no conocida al inicio del test"
        assert not np.any(tr & te)
        mu = np.nanmean(X[tr], 0)
        sd = np.nanstd(X[tr], 0)
        sd[sd == 0] = 1
        Z = lambda A: np.hstack([np.ones((len(A), 1)), np.nan_to_num(np.clip((A - mu) / sd, -5, 5))])  # noqa: E731
        Xt = Z(X[tr])
        yv = np.clip(y[tr], -0.2, 0.2)
        if prng is not None:
            yv = prng.permutation(yv)
        L = lam * tr.sum() * np.eye(Xt.shape[1])
        L[0, 0] = 0
        w = np.linalg.solve(Xt.T @ Xt + L, Xt.T @ yv)
        th = np.quantile(Xt @ w, q)
        score[te] = Z(X[te]) @ w
        take[te] = score[te] >= th
    return take, score


def sim_c1(tab, take, gname, period=(START_OOS, END_D), fee=H.FEE, slip=H.SLIP, delay=0):
    m_sl, Hh = GEOM[gname]
    out = []
    for si, s in enumerate(SYMS):
        b = bars[s]
        mu = H.rolling_mean(b.c, 20)
        R = mu - b.c
        ii = tab["I"][(tab["S"] == si) & take]
        ent = np.zeros(len(b), bool)
        if delay == 0:
            ent[ii] = True
            tp = mu if m_sl else None
            sl = (b.c - m_sl * R) if m_sl else None
            risk = None if m_sl else R
        else:  # entrar `delay` velas despues, con niveles relativos de la vela de senal
            jj = ii + delay
            ent[jj] = True
            rel = np.full(len(b), np.nan)
            rel[jj] = R[ii] / b.c[ii]
            tpr = np.full(len(b), np.nan)
            tpr[jj] = mu[ii] / b.c[ii]
            tp = b.c * tpr if m_sl else None
            sl = b.c * (1 - m_sl * rel) if m_sl else None
            risk = b.c * rel if not m_sl else None
        p0, p1 = b.idx(period[0]), b.idx(period[1])
        out.append(H.simulate(b, ent, tp, sl, period=(p0, p1), max_hold=Hh, risk=risk, fee=fee, slip=slip))
    return H.Trades.concat(out)


def folds_E(T):
    res = []
    for k in range(6):
        y, m = 2024 + k // 4, 1 + 3 * (k % 4)
        a = H.ms(y, m)
        b = H.ms(y + (m + 3 > 12), (m + 3 - 1) % 12 + 1)
        sub = T.between(a, b)
        res.append((f"{y}-{m:02d}", len(sub), float(sub.net_ret.mean() * 100) if len(sub) else float("nan")))
    return res


def line(m):
    return (f"n={m['n']:4d} WR={m['wr']*100:5.1f}% [{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}] b={m['b_eff']:.2f} "
            f"E={m['E_pct']:+.3f}% t={m['t']:+.2f} PF={m['pf']:.2f} MDD_R={m['mdd_R']:.1f}")


def month_t(T):
    mon = T.entry_t.astype("datetime64[ms]").astype("datetime64[M]")
    u = np.unique(mon)
    s = np.array([T.net_ret[mon == x].sum() for x in u])
    return float(s.mean() / s.std(ddof=1) * np.sqrt(len(s))), s


P("\n=== 2. Reimplementacion independiente (asserts de purga y normalizacion) ===")
tab96 = signal_table(96)
take, score = c1_take(tab96)
S9, I9, take9 = rb.scores(data, Fs, 96, FULL, 0.1)
key_mine = set(zip(tab96["S"][take], tab96["I"][take]))
key_an = set(zip(S9[take9], I9[take9]))
P(f"  senales MR20 elegibles: {len(tab96['y'])}; seleccionadas (mia/Analista): {len(key_mine)}/{len(key_an)}; "
  f"coincidencia exacta: {key_mine == key_an}")
oos = (tab96["T"] >= START_OOS)
P(f"  fraccion seleccionada en el OOS: {take[oos].mean()*100:.1f} % (Q90 de entrenamiento => 10 % esperado)")

base = {}
for g in ("T48", "G2H96", "G3H96"):
    T = sim_c1(tab96, take, g)
    m = H.metrics(T)
    tm, _ = month_t(T)
    fe = folds_E(T)
    base[g] = (T, m)
    npos = sum(1 for f in fe if f[2] > 0)
    P(f"  {g:6s} OOS 2023-10..2025-06: {line(m)} t_mes={tm:+.2f} | pliegues 3m (2024-01..2025-06) E>0: {npos}/6 "
      + " ".join(f"{f[0]}:{f[2]:+.2f}%({f[1]})" for f in fe))
    RES[f"base_{g}"] = {"metrics": m, "t_mes": tm, "folds": fe}

# ------------------------------------------------------------------------------------------------
# 3. Protocolo y pruebas de robustez
# ------------------------------------------------------------------------------------------------
P("\n=== 3a. Walk-forward 12/3/3 estricto (ventana movil de 12 meses, reajuste trimestral, test 2024-01..2025-06) ===")
for label, kw in (("12/3/3 movil", dict(refit_months=3, train_months=12)),
                  ("expansivo, reajuste trimestral", dict(refit_months=3)),
                  ("mensual expansivo + embargo extra 1 semana", dict(embargo_ms=7 * 86_400_000))):
    tk, _ = c1_take(tab96, first=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc), **kw)
    for g in ("T48", "G2H96", "G3H96"):
        T = sim_c1(tab96, tk, g, period=(H.ms(2024, 1), END_D))
        m = H.metrics(T)
        fe = folds_E(T)
        npos = sum(1 for f in fe if f[2] > 0)
        tm, _ = month_t(T)
        P(f"  [{label}] {g:6s}: {line(m)} t_mes={tm:+.2f} pliegues E>0 {npos}/6: " + " ".join(f"{f[2]:+.2f}" for f in fe))
        RES[f"wf_{label}_{g}"] = {"metrics": m, "folds": fe, "t_mes": tm}

P("\n=== 3b. Costos 0.30 % y retraso de 1 vela (15 min) ===")
for g in ("T48", "G2H96", "G3H96"):
    m30 = H.metrics(sim_c1(tab96, take, g, fee=0.0013, slip=0.0002))
    md1 = H.metrics(sim_c1(tab96, take, g, delay=1))
    P(f"  {g:6s} costo 0.30 %: {line(m30)} | retraso 1 vela: {line(md1)}")
    RES[f"cost30_{g}"] = m30
    RES[f"delay1_{g}"] = md1

P("\n=== 3c. Placebo: etiquetas permutadas dentro de cada entrenamiento (20 corridas) ===")
plac = {g: [] for g in ("T48", "G3H96")}
for k in range(20):
    tk, _ = c1_take(tab96, permute=1000 + k)
    for g in plac:
        plac[g].append(H.metrics(sim_c1(tab96, tk, g))["E_pct"])
for g, v in plac.items():
    v = np.array(v)
    real = base[g][1]["E_pct"]
    P(f"  {g:6s}: E placebo media {v.mean():+.3f}% (p5 {np.percentile(v,5):+.3f}, p95 {np.percentile(v,95):+.3f}); "
      f"E real {real:+.3f}%; P(placebo >= real) = {np.mean(v >= real):.2f}")
    RES[f"placebo_{g}"] = {"E": v.tolist(), "real": real}

P("\n=== 3d. Deflated Sharpe con distintos conteos de pruebas ===")
counts = {"familia ridge del Analista (56)": 56, "Analista (1 328)": 1328, "Analista + Gestor (8 516)": 8516,
          "equipo completo (12 104 + ronda 2)": 12104 + 60}
for g in ("T48", "G2H96", "G3H96"):
    T, m = base[g]
    _, msum = month_t(T)
    for lab, n in counts.items():
        d_tr = H.deflated_sharpe(T.net_ret, n_trials=n)
        d_mo = H.deflated_sharpe(msum, n_trials=n)
        P(f"  {g:6s} N={n:6d} ({lab}): por operacion SR={d_tr['sr']:.3f} SR0={d_tr['sr0']:.3f} DSR={d_tr['dsr']:.3f} | "
          f"por mes SR={d_mo['sr']:.3f} SR0={d_mo['sr0']:.3f} DSR={d_mo['dsr']:.3f}")
        RES[f"dsr_{g}_{n}"] = {"trade": d_tr, "month": d_mo}
    pb = {lab: H.bonferroni(float(1 - __import__('scipy').stats.t.cdf(m["t"], m["n"] - 1)), n) for lab, n in counts.items()}
    P(f"  {g:6s} Bonferroni (t iid {m['t']:+.2f}): " + "; ".join(f"{k}: {v:.3g}" for k, v in pb.items()))

P("\n=== 3e. PBO (CSCV) sobre la familia de variantes de C1 (meses 2023-10..2025-06) ===")
fam = []
tabs = {96: tab96, 48: signal_table(48)}
for h in (48, 96):
    for q in (0.8, 0.9):
        tk, _ = c1_take(tabs[h], q=q)
        for g in ("T48", "T96", "G1H48", "G2H96", "G3H96"):
            fam.append((f"h{h} q{q} lam0.1 full {g}", sim_c1(tabs[h], tk, g)))
for lam in (0.01, 1.0):
    tk, _ = c1_take(tab96, lam=lam)
    for g in ("T48", "G2H96", "G3H96"):
        fam.append((f"h96 q0.9 lam{lam} full {g}", sim_c1(tab96, tk, g)))
tabc = signal_table(96, rb.COMPACT, extras=False)
for lam in (0.1, 1.0):
    tk, _ = c1_take(tabc, lam=lam)
    for g in ("T48", "G2H96", "G3H96"):
        fam.append((f"h96 q0.9 lam{lam} compacto {g}", sim_c1(tabc, tk, g)))
months = np.array([y * 100 + m for y in (2023, 2024, 2025) for m in range(1, 13) if 202310 <= y * 100 + m <= 202506])
M = H.monthly_matrix([t for _, t in fam], months, "net_ret")
for S in (6, 10):
    pb = H.pbo_cscv(M, S=S)
    P(f"  {len(fam)} variantes, S={S} ({pb['n_combinations']} combinaciones): PBO={pb['pbo']:.2f}; "
      f"P(el elegido pierde OOS)={pb['p_oos_loss']:.2f}; OOS medio del elegido={pb['oos_best_mean']*100:+.2f}%/mes; "
      f"pendiente OOS~IS={pb['slope_oos_on_is']:+.2f}")
    RES[f"pbo_S{S}"] = pb
tot = M.sum(0)
P(f"  variantes con suma neta > 0 en 21 meses: {np.sum(tot > 0)}/{len(fam)}; mediana E por op. de la familia: "
  f"{np.median([t.net_ret.mean()*100 for _, t in fam]):+.3f}%")
H.log_trials("validador", 3 + 9 + 6 + 40 + len(fam), "R2 auditoria C1: WF 12/3/3 (9), costos/retraso (6), placebo (40), familia PBO", "design")

open(os.path.join(H.VALIDADOR_DIR, "r2_audit_c1.txt"), "w", encoding="utf-8").write("\n".join(OUT))
json.dump(RES, open(os.path.join(H.VALIDADOR_DIR, "r2_audit_c1.json"), "w"), indent=1, default=float)
