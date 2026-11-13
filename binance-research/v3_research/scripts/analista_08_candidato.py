"""Ronda 1 - Paso 8: candidato 'MR + score ridge' simulado con harness.py (arnés del Validador).
Score: ridge walk-forward mensual expansivo (purga h velas) que predice ret_h (h = 48 y 96) de cada señal
MR(20,2,R>=0.5%) con 41 variables estandarizadas + hora + moneda (lambda = 0.1*N_train, sin ajuste).
Regla: operar la señal si score >= cuantil q de los scores del ENTRENAMIENTO (q = 0.8 / 0.9).
Geometrías FIJAS para comparar (el Gestor de Riesgo optimizará las salidas):
  T48 / T96: solo salida por tiempo (48 / 96 velas)       G1H48: TP=SMA20, SL=c-R, H=48 (b=1)
  G2H96: TP=SMA20, SL=c-2R, H=96 (b=0.5)                  G3H96: TP=SMA20, SL=c-3R, H=96 (b=0.33)
Periodo evaluable: 2023-10 .. 2025-06 (los meses previos solo entrenan). Nada del holdout."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import datetime as dt
import analista_common as ac
import analista_features as af
import harness as Hh

FEATS = [f for f in af.FEATURES if f not in ("hour", "dow")]
NAMES = FEATS + ["hour_sin", "hour_cos", "BTC", "ETH", "SOL", "DOGE"]


def ridge(X, y, lam):
    Xb = np.hstack([np.ones((len(X), 1)), X])
    L = lam * np.eye(Xb.shape[1]); L[0, 0] = 0
    return np.linalg.solve(Xb.T @ Xb + L, Xb.T @ y)


def build_scores(data, Fs, h):
    rows = []
    for si, s in enumerate(ac.SYMS):
        d = data[s]; F = Fs[s]; c = d["c"]
        with np.errstate(invalid="ignore"):
            idx = np.where((F["z"] < -2) & (F["R_pct"] >= 0.005))[0]
        idx = idx[idx >= 900]
        X = np.column_stack([F[f][idx] for f in FEATS] +
                            [np.sin(2 * np.pi * F["hour"][idx] / 24), np.cos(2 * np.pi * F["hour"][idx] / 24)] +
                            [np.full(len(idx), 1.0 if j == si else 0.0) for j in range(4)])
        y = np.full(len(idx), np.nan)
        okf = idx + h < len(c)
        y[okf] = c[idx[okf] + h] / c[idx[okf]] - 1
        rows.append((si, idx, X, y, d["t"][idx]))
    X = np.vstack([r[2] for r in rows]); y = np.concatenate([r[3] for r in rows]); T = np.concatenate([r[4] for r in rows])
    S = np.concatenate([np.full(len(r[1]), r[0]) for r in rows]); I = np.concatenate([r[1] for r in rows])
    score = np.full(len(y), np.nan)
    thr = {q: np.full(len(y), np.nan) for q in (0.8, 0.9)}
    coefs = []
    months = sorted(set(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m") for t in T))
    for mth in [m for m in months if m >= "2023-10"]:
        y0, m0 = int(mth[:4]), int(mth[5:])
        start = dt.datetime(y0, m0, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
        end = dt.datetime(y0 + (m0 == 12), 1 if m0 == 12 else m0 + 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
        tr = (T + h * 900000 < start) & ~np.isnan(y)
        te = (T >= start) & (T < end)
        mu = np.nanmean(X[tr], 0); sd = np.nanstd(X[tr], 0); sd[sd == 0] = 1
        Z = lambda A: np.nan_to_num(np.clip((A - mu) / sd, -5, 5))
        w = ridge(Z(X[tr]), np.clip(y[tr], -0.2, 0.2), lam=float(tr.sum()) * 0.1)
        coefs.append(w[1:])
        ptr = np.hstack([np.ones((tr.sum(), 1)), Z(X[tr])]) @ w
        score[te] = np.hstack([np.ones((te.sum(), 1)), Z(X[te])]) @ w
        for q in thr:
            thr[q][te] = np.quantile(ptr, q)
    return dict(S=S, I=I, T=T, score=score, thr=thr, coef=np.mean(coefs, 0), coef_sd=np.std(coefs, 0),
                coef_pos=np.mean(np.array(coefs) > 0, 0))


def main():
    lines = []
    P = lambda s: (print(s), lines.append(s))
    data = {s: ac.load(s) for s in ac.SYMS}
    Fs = {s: af.build(data[s], 20) for s in ac.SYMS}
    Fs = af.add_cross(Fs, ac.SYMS)
    bars = {s: Hh.load(s) for s in ac.SYMS}
    START = Hh.ms(2023, 10, 1)
    n_cfg = 0
    allres = {}
    for h in (48, 96):
        sc = build_scores(data, Fs, h)
        o = np.argsort(-np.abs(sc["coef"]))[:14]
        P(f"\n######## Score ridge h={h} ({h//4} h) ########")
        P("Coeficientes estandarizados medios (en % de retorno por 1 sd; signo estable = fracción de meses > 0):")
        P("  " + "; ".join(f"{NAMES[j]} {sc['coef'][j]*100:+.3f} ({sc['coef_pos'][j]*100:.0f}%)" for j in o))
        for q in (0.9, 0.8):
            for gname, (m_sl, H, tpon) in {"T48": (None, 48, False), "T96": (None, 96, False),
                                          "G1H48": (1.0, 48, True), "G2H96": (2.0, 96, True), "G3H96": (3.0, 96, True)}.items():
                trs = {"A": [], "B": []}
                for si, s in enumerate(ac.SYMS):
                    b = bars[s]
                    i0, i1 = Hh.bounds(b, "design")
                    msk = sc["S"] == si
                    ii = sc["I"][msk]; scv = sc["score"][msk]; th = sc["thr"][q][msk]
                    ent = np.zeros(len(b), bool)
                    with np.errstate(invalid="ignore"):
                        take = ii[(scv >= th)]
                    ent[take] = True
                    mu = Hh.rolling_mean(b.c, 20)
                    R = mu - b.c
                    tp = mu if tpon else None
                    sl = (b.c - m_sl * R) if m_sl else None
                    risk = None if m_sl else R      # sin SL: r_mult relativo a la distancia a la media
                    for part, (a0, a1) in (("A", (START, ac.SPLIT_AB_MS)), ("B", (ac.SPLIT_AB_MS, ac.DESIGN_END_MS))):
                        p0, p1 = b.idx(a0), b.idx(a1)
                        tr = Hh.simulate(b, ent, tp, sl, period=(p0, p1), max_hold=H, risk=risk)
                        trs[part].append(tr)
                n_cfg += 1
                for part in ("A", "B"):
                    T_ = Hh.Trades.concat(trs[part])
                    m = Hh.metrics(T_, n_configs=1)
                    mon = 6 if part == "A" else 15
                    per = " ".join(f"{s[:3]}:{len(t)}/{(t.net_ret > 0).mean()*100 if len(t) else float('nan'):.0f}%"
                                   for s, t in zip(ac.SYMS, trs[part]))
                    P(f"  q{int(q*100)} {gname:6s} {part}: N={m['n']:4d} ({m['n']/mon:4.1f}/mes) WR={m['wr']*100:4.1f}% "
                      f"[{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}] b={m['b_eff']:.2f} E={m['E_pct']:+.3f}% (t={m['t']:+.2f}) "
                      f"E_R={m['E_R']:+.3f} PF={m['pf']:.2f} MDD_R={m['mdd_R']:.1f} rachaP={m['max_loss_streak']} "
                      f"Rmed={m['risk_med_pct']:.2f}% hold={m['hold_med_bars']:.0f} | {per}")
                    allres[f"h{h}_q{q}_{gname}_{part}"] = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                                                          for k, v in m.items()}
                # meses positivos (A+B) para la geometría
                T_ = Hh.Trades.concat(trs["A"] + trs["B"])
                mon = T_.entry_t.astype("datetime64[ms]").astype("datetime64[M]")
                um = np.unique(mon)
                pm = [T_.net_ret[mon == u].sum() for u in um]
                P(f"           meses con suma neta > 0: {sum(1 for x in pm if x > 0)}/{len(um)}")
    P(f"\nConfiguraciones evaluadas en este script: {n_cfg} (2 horizontes x 2 cuantiles x 5 geometrías fijas)")
    with open(os.path.join(ac.OUTDIR, "08_candidato.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    with open(os.path.join(ac.OUTDIR, "08_candidato.json"), "w", encoding="utf-8") as fh:
        json.dump(allres, fh, indent=1, default=str)
    Hh.log_trials("analista", n_cfg, "R1 candidato MR20 + score ridge (h48/h96, q80/q90) x 5 geometrias fijas", "design")


if __name__ == "__main__":
    main()
