"""Ronda 1 - Paso 1: calidad de las señales actuales con simulación honesta en DISEÑO (2023-01 a 2025-06).
- MeanReversion, TrendFollowing (RollingVolatility) y VolatilitySqueeze con los parámetros de ml_results.json
  y con una rejilla razonable.
- Línea base de entrada aleatoria (misma geometría) para medir el exceso de acierto Δp = p - p0.
- Reproducción del artefacto del backtest original (DOGE, redondeo a 2 decimales) en meses de DISEÑO.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac

BOT = {  # ml_results.json
    "BTCUSDT": dict(MR=(8, 1.4), TF=(76, 1.4), SQ=(84, 1.0)),
    "ETHUSDT": dict(MR=(20, 2.0), TF=(96, 1.4), SQ=(8, 1.4)),
    "SOLUSDT": dict(MR=(88, 0.8), TF=(56, 0.8), SQ=(16, 2.6)),
    "DOGEUSDT": dict(MR=(8, 1.6), TF=(24, 0.8), SQ=(48, 1.2)),
}


def sig_mr(d, n, k, minR=0.005):
    c = d["c"]
    mu, sd = ac.roll_mean_std(c, n)
    with np.errstate(invalid="ignore"):
        cond = c < mu - k * sd
        R = mu - c
        cond &= R >= minR * c
    i = np.where(cond)[0]
    return i, mu[i], c[i] - R[i]          # idx, TP, SL


def sig_tf(d, n, k):
    c = d["c"]
    mu, sd = ac.roll_mean_std(c, n)
    with np.errstate(invalid="ignore"):
        cond = c > mu + k * sd
    i = np.where(cond)[0]
    R = c[i] - mu[i]
    return i, c[i] + 2 * R, mu[i]


def sig_sq(d, n, k, theta=0.05, mult=2.5, minR=0.005):
    c = d["c"]
    mu, sd = ac.roll_mean_std(c, n)
    bw = 2 * k * sd / mu
    up = mu + k * sd
    armed = False
    idx = []
    for i in range(n - 1, len(c)):
        if bw[i] < theta and not armed:
            armed = True
        elif armed and c[i] > up[i]:
            armed = False
            R = c[i] - mu[i]
            if R >= minR * c[i]:
                idx.append(i)
    idx = np.array(idx, dtype=np.int64)
    R = c[idx] - mu[idx]
    return idx, c[idx] + mult * R, mu[idx]


def evaluate(d, gen, *args, H=None):
    i, tp, sl = gen(d, *args)
    if len(i) == 0:
        return None, None
    tr = ac.run_trades(d, i, tp, sl, H)
    m = ac.metrics(tr["r_net"], tr["R"], months=ac.months_span(d))
    m["n_sig"] = len(i)
    m["tp_rate"] = float((tr["out"] == 1).mean())
    # b geométrico medio (TP-entrada)/(entrada-SL)
    e = d["c"][tr["i"]]
    m["b_geom"] = float(np.median((tr["tp"] - e) / (e - tr["sl"])))
    m["cR_med"] = float(np.median(ac.COST / tr["R"]))
    return m, tr


def random_baseline(d, R, b, step=3, H=None):
    """p0: acierto TP-antes-que-SL entrando en velas arbitrarias (cada `step`) con TP = c(1+bR), SL = c(1-R)."""
    c = d["c"]
    i = np.arange(200, len(c) - 1, step)
    ex_i, ex_p, out = ac.first_touch(d, i, c[i] * (1 + b * R), c[i] * (1 - R), H)
    ok = out != 2
    r = ex_p[ok] / c[i[ok]] - 1 - ac.COST
    return float((out[ok] == 1).mean()), float((r > 0).mean()), float((r / R).mean())


def orig_backtest_month(c_month, n, k, rounding=True, payout=2.0):
    """Réplica fiel de QuantCalculator.evaluate_strategy para RollingVolatility (solo cierres, ventana congelada
    con posición abierta, round(tp,2)/round(sl,2), paga 2R, sin costos)."""
    hist = []
    pos = None
    W = L = 0
    for p in c_month:
        if pos:
            if p >= pos[0]:
                W += 1; pos = None
            elif p <= pos[1]:
                L += 1; pos = None
            continue
        hist.append(p)
        if len(hist) > n:
            hist.pop(0)
        if len(hist) < n:
            continue
        a = np.array(hist)
        mu = a.mean(); sd = a.std(ddof=1)
        if p > mu + k * sd:
            R = p - mu
            tp = p + 2 * R
            sl = mu
            if rounding:
                tp, sl = round(tp, 2), round(sl, 2)
            pos = (tp, sl)
    return W, L


def main():
    out_lines = []
    P = lambda s: (print(s), out_lines.append(s))
    n_cfg = 0
    results = {}

    P("=== 1) Estrategias con parámetros de ml_results.json, DISEÑO 2023-01..2025-06, simulación honesta ===")
    P("(entrada al cierre, TP/SL con high/low, empate=SL, costos 0.24% i/v, sin barrera de tiempo, 1 posición)")
    data = {s: ac.load(s) for s in ac.SYMS}
    for s in ac.SYMS:
        d = data[s]
        for name, gen in (("MR", sig_mr), ("TF", sig_tf), ("SQ", sig_sq)):
            n, k = BOT[s][name]
            m, tr = evaluate(d, gen, n, k)
            n_cfg += 1
            results[f"bot_{s}_{name}"] = m
            if m is None:
                P(f"{s} {name}({n},{k}): sin señales"); continue
            P(f"{s} {name:2s}({n:2d},{k}) {ac.fmt(m)} TP%={m['tp_rate']*100:.0f} b_geom={m['b_geom']:.2f} "
              f"c/R={m['cR_med']:.2f} ops/mes={m['per_month']:.1f}")

    P("\n=== 2) Rejilla razonable (mismas reglas). Columnas: N, WR, IC95, b_eff, E%, E_R(t), PF, MDD_R ===")
    grids = {
        "MR": [(n, k) for n in (8, 12, 20, 32, 48, 96) for k in (1.0, 1.5, 2.0, 2.5, 3.0)],
        "TF": [(n, k) for n in (24, 48, 96) for k in (0.8, 1.4, 2.0)],
        "SQ": [(n, k) for n in (16, 48, 84) for k in (1.0, 1.4, 2.0)],
    }
    gens = {"MR": sig_mr, "TF": sig_tf, "SQ": sig_sq}
    grid_rows = []
    for name, grid in grids.items():
        P(f"\n--- {name} ---")
        for s in ac.SYMS:
            d = data[s]
            for (n, k) in grid:
                m, tr = evaluate(d, gens[name], n, k)
                n_cfg += 1
                if m is None:
                    continue
                grid_rows.append(dict(strat=name, sym=s, n=n, k=k, **{kk: vv for kk, vv in m.items()}))
                P(f"{s:8s} {name}({n:2d},{k:.1f}) {ac.fmt(m)} ops/mes={m['per_month']:.1f}")
    # resumen: cuántas configuraciones tienen E_R > 0 con t > 2
    for name in grids:
        rows = [r for r in grid_rows if r["strat"] == name]
        pos = [r for r in rows if r["E_R"] > 0]
        sig = [r for r in rows if r["E_R"] > 0 and r["t_E_R"] > 2]
        bestwr = max(rows, key=lambda r: r["WR"])
        P(f"[{name}] configs={len(rows)}  E_R>0: {len(pos)}  E_R>0 y t>2: {len(sig)}  "
          f"WR máx={bestwr['WR']*100:.1f}% ({bestwr['sym']},{bestwr['n']},{bestwr['k']}, E_R={bestwr['E_R']:+.3f})")

    P("\n=== 3) Línea base de entrada aleatoria p0 (cada 3 velas), TP=c(1+bR), SL=c(1-R), sin barrera de tiempo ===")
    P("     columnas: P(TP primero), WR neto, E_R neto")
    for s in ac.SYMS:
        d = data[s]
        for R in (0.005, 0.01, 0.02, 0.03):
            row = []
            for b in (0.33, 0.5, 1.0, 2.0):
                p0, wr, eR = random_baseline(d, R, b)
                row.append(f"b={b}: p0={p0*100:5.1f}% WRn={wr*100:5.1f}% E_R={eR:+.3f}")
            P(f"{s:8s} R={R*100:.1f}% | " + " | ".join(row))
    P("Referencia martingala sin deriva: p0 = 1/(1+b): b=0.33->75.2%, 0.5->66.7%, 1->50%, 2->33.3%")

    P("\n=== 4) Artefacto del backtest original (DOGE TrendFollowing 24/0.8) en meses de DISEÑO ===")
    d = data["DOGEUSDT"]
    import datetime as dt
    months = {}
    for i, t in enumerate(d["t"]):
        key = dt.datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m")
        months.setdefault(key, []).append(i)
    tot = {True: [0, 0], False: [0, 0]}
    for key in sorted(months):
        ii = np.array(months[key])
        cm = d["c"][ii]
        for rnd in (True, False):
            W, L = orig_backtest_month(cm, 24, 0.8, rounding=rnd)
            tot[rnd][0] += W; tot[rnd][1] += L
        if key in ("2023-06", "2024-03", "2024-09", "2025-06"):
            W1, L1 = orig_backtest_month(cm, 24, 0.8, True)
            W0, L0 = orig_backtest_month(cm, 24, 0.8, False)
            P(f"{key}: precio medio {cm.mean():.4f} | con redondeo: {W1}G/{L1}P WR={W1/max(1,W1+L1)*100:.1f}% | "
              f"sin redondeo: {W0}G/{L0}P WR={W0/max(1,W0+L0)*100:.1f}%")
    for rnd in (True, False):
        W, L = tot[rnd]
        P(f"Total 30 meses DISEÑO, {'CON' if rnd else 'SIN'} round(tp,2)/round(sl,2): {W}G/{L}P WR={W/(W+L)*100:.1f}%")
    P(f"\nConfiguraciones evaluadas en este script: {n_cfg} (+ 32 líneas base aleatorias, no son selección)")
    with open(os.path.join(ac.OUTDIR, "01_base.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))
    with open(os.path.join(ac.OUTDIR, "01_base_grid.json"), "w", encoding="utf-8") as f:
        json.dump(dict(bot=results, grid=grid_rows, n_cfg=n_cfg), f, indent=1, default=float)


if __name__ == "__main__":
    main()
