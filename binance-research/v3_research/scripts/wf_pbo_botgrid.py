"""Cuanto sobreajusta el procedimiento actual del bot? (solo DISENO, variante honesta B).

Para cada moneda: rejilla del bot (n=8..96 paso 4 x k=0.8..3.2 paso 0.2: np.arange da 13 valores = 299) x {MR, TF, SQ} = 897 configs
(VWAP = MR). Con la matriz meses x configuraciones (suma mensual de retornos netos) se calcula:
  * PBO por CSCV (S=10 bloques de 3 meses, 252 combinaciones),
  * walk-forward 12/3/3 y 1/1/1 (este ultimo = lo que hace el bot: optimizar con el ultimo mes y operar el siguiente),
    con la regla de seleccion del bot (mejor config por estrategia con >5 operaciones, luego la estrategia de mayor PnL),
  * Deflated Sharpe del mejor IS de todo DISENO con N = 897.
Salida: output/validador/wf_pbo_botgrid.md / .json
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import bot_replica as BR  # noqa: E402

WINDOWS = [int(w) for w in np.arange(8, 100, 4)]
MULTS = [round(float(m), 2) for m in np.arange(0.8, 3.2, 0.2)]
CODES = ("MR", "TF", "SQ")
CFGS = [(c, w, m) for c in CODES for w in WINDOWS for m in MULTS]


def select(Msum, Mcnt, rows):
    """Regla del bot sobre los meses `rows`: mejor (n,k) por estrategia con >5 op., luego mayor PnL."""
    pnl = Msum[rows].sum(0)
    cnt = Mcnt[rows].sum(0)
    best_j, best_p = None, -np.inf
    for code in CODES:
        idx = [j for j, cf in enumerate(CFGS) if cf[0] == code and cnt[j] > 5]
        if not idx:
            continue
        j = idx[int(np.argmax(pnl[idx]))]
        if pnl[j] > best_p:
            best_j, best_p = j, pnl[j]
    return best_j


def wf(trs, months, Msum, Mcnt, tr_m, te_m, step):
    oos = []
    picks = []
    s = 0
    while s + tr_m + te_m <= len(months):
        rows_tr = list(range(s, s + tr_m))
        rows_te = months[s + tr_m:s + tr_m + te_m]
        j = select(Msum, Mcnt, rows_tr)
        if j is not None:
            t = trs[j]
            mm = t.entry_t.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)
            mm = (1970 + mm // 12) * 100 + (mm % 12) + 1
            oos.append(t.subset(np.isin(mm, rows_te)))
            picks.append(CFGS[j])
        s += step
    return H.Trades.concat(oos), picks


out, md = {}, ["# Sobreajuste del procedimiento del bot (DISENO, variante honesta B)", "",
               f"Rejilla: {len(CFGS)} configuraciones por moneda (299 x MR/TF/SQ). Costos 0.24 %.", ""]
H.log_trials("validador", len(CFGS) * len(H.SYMBOLS), "rejilla original del bot (MR/TF/SQ x 23 n x 13 k) x 4 monedas, variante B")
for sym in H.SYMBOLS:
    t0 = time.time()
    bars = H.load(sym)
    i0, i1 = H.bounds(bars, "design")
    months = np.unique(bars.month[i0:i1])
    cache = {}
    trs = []
    for code, w, m in CFGS:
        sig, tp, sl = BR.signals(bars, code, w, m, cache=cache)
        trs.append(H.simulate(bars, sig, tp, sl, period=(i0, i1)))
    Msum = H.monthly_matrix(trs, months, "net_ret")
    ones = []
    for t in trs:
        t2 = t.subset(np.ones(len(t), bool))
        t2.net_ret = np.ones(len(t))
        ones.append(t2)
    Mcnt = H.monthly_matrix(ones, months, "net_ret")
    tot = Msum.sum(0)
    ntr = Mcnt.sum(0)
    E_cfg = tot / np.maximum(ntr, 1)
    res = {"n_configs": len(CFGS), "frac_configs_E_pos": float(np.mean(tot > 0)),
           "E_cfg_pct_quantiles": [float(q * 100) for q in np.quantile(E_cfg[ntr > 30], [0.05, 0.5, 0.95])]}
    # PBO
    pb = H.pbo_cscv(Msum, S=10)
    res["pbo_S10"] = pb
    # mejor IS de todo DISENO y su DSR
    jb = int(np.argmax(np.where(ntr > 30, tot, -np.inf)))
    srs = np.array([H.sharpe(t.net_ret) if len(t) > 30 else np.nan for t in trs])
    dsr = H.deflated_sharpe(trs[jb].net_ret, n_trials=len(CFGS), sr_trials=srs[np.isfinite(srs)])
    mb = H.metrics(trs[jb], n_configs=len(CFGS))
    res["best_IS"] = {"cfg": CFGS[jb], "metrics": mb, "dsr": dsr}
    # walk-forward
    for name, (a, b_, c_) in {"WF 12/3/3": (12, 3, 3), "WF 1/1/1 (como el bot)": (1, 1, 1)}.items():
        tro, picks = wf(trs, months, Msum, Mcnt, a, b_, c_)
        mo = H.metrics(tro, n_configs=1, boot=2000)
        res[name] = {"metrics": mo, "picks": picks}
    out[sym] = res
    md += [f"## {sym}", "",
           f"- Configuraciones con E neta > 0 en DISENO: {res['frac_configs_E_pos']*100:.1f} % de {len(CFGS)}; "
           f"E por operacion (percentiles 5/50/95, configs con >30 op.): " + ", ".join(f"{q:+.3f} %" for q in res["E_cfg_pct_quantiles"]),
           f"- PBO (CSCV, S=10, {pb['n_combinations']} combinaciones): **{pb['pbo']:.2f}**; P(el elegido IS pierde OOS) = {pb['p_oos_loss']:.2f}; "
           f"pendiente OOS~IS = {pb['slope_oos_on_is']:.2f}",
           f"- Mejor IS de todo DISENO {CFGS[jb]}: n={mb['n']}, WR {mb['wr']*100:.1f} %, E {mb['E_pct']:+.3f} %, p={mb['p_value']:.3g}, "
           f"p_Bonf(N={len(CFGS)})={mb['p_bonf']:.3g}; SR/op={dsr['sr']:.3f}, SR0={dsr['sr0']:.3f}, PSR(0)={dsr['psr0']:.3f}, **DSR={dsr['dsr']:.3f}**", "",
           H.md_header("Walk-forward (OOS concatenado)")]
    for name in ("WF 12/3/3", "WF 1/1/1 (como el bot)"):
        md.append(H.md_row(name, res[name]["metrics"]))
    md.append("")
    print(sym, f"{time.time()-t0:.0f}s", "PBO", round(pb["pbo"], 2), "fracEpos", round(res["frac_configs_E_pos"], 3),
          "bestIS", CFGS[jb], round(mb["E_pct"], 3), "DSR", round(dsr["dsr"], 3))
    for name in ("WF 12/3/3", "WF 1/1/1 (como el bot)"):
        print("   ", H.fmt(res[name]["metrics"], name))
open(os.path.join(H.VALIDADOR_DIR, "wf_pbo_botgrid.md"), "w", encoding="utf-8").write("\n".join(md))
json.dump(out, open(os.path.join(H.VALIDADOR_DIR, "wf_pbo_botgrid.json"), "w"), indent=1, default=float)
