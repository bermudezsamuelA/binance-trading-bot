"""Ronda 3 - Efecto de la regla P2-final sobre las operaciones de C1 en DISEÑO (2023-10..2025-06)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_features as af
import C1_eval as C1
import harness as H
START, END = H.ms(2023, 10, 1), H.DESIGN[1]
bars, data = C1.load_until(END)
Fs = af.add_cross({s: af.build(data[s], 20) for s in C1.SYMS}, list(C1.SYMS))
ST = C1.signal_table(data, Fs)
take, _, _, _ = C1.scores(ST, START, END)
s = 0.0012
for g, F_RISK in (("PRIMARIA_G3H96", 0.03), ("SECUNDARIA_T48", 0.015)):
    T = H.Trades.concat(C1.simulate_all(bars, data, ST, take, START, END, g))
    P_, SL = T.entry_px, T.sl
    lossP = np.where(np.isfinite(SL), (P_ - SL + s * (P_ + SL)) / P_, 0.15)
    w = np.minimum(0.10, F_RISK / lossP)
    Q = np.maximum(lossP + 0.02, 0.15) if g.startswith("PRIM") else np.full(len(P_), 0.15)
    # recorrido cronológico con topes (las 4 monedas): nocional <= 0.40 y sum w*Q <= 0.06
    order = np.argsort(T.entry_t, kind="stable")
    open_ = []; taken = np.zeros(len(T), bool); wt = np.zeros(len(T))
    for k in order:
        open_ = [(e, ww, qq) for (e, ww, qq) in open_ if e > T.entry_t[k]]
        notional = sum(x[1] for x in open_); heat = sum(x[1] * x[2] for x in open_)
        wk = min(w[k], 0.40 - notional, (0.06 - heat) / Q[k])
        if wk > 1e-6:
            taken[k] = True; wt[k] = wk
            open_.append((T.exit_t[k], wk, Q[k]))
    r = T.net_ret
    blocked = ~taken; red = taken & (wt < w - 1e-9)
    print(f"{g}: N={len(T)} | lossU/P p50={np.median(lossP)*100:.1f}% p90={np.percentile(lossP,90)*100:.1f}% máx={lossP.max()*100:.1f}% | "
          f"w<0.10 por F_RISK: {np.mean(w < 0.10)*100:.1f}% | Q_TAIL>0.15: {np.mean(Q > 0.15)*100:.1f}% | "
          f"bloqueadas por topes: {blocked.sum()} (E={r[blocked].mean()*100 if blocked.any() else float('nan'):+.2f}%), "
          f"reducidas: {red.sum()} | E por nocional con topes={np.sum(wt*r)/np.sum(wt)*100:+.3f}% vs sin topes={r.mean()*100:+.3f}% | "
          f"retorno total sobre capital={np.sum(wt*r)*100:+.1f}% en 21 meses")
