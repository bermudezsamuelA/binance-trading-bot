"""Ronda 2 - Datos de riesgo de C1 (spec, DISEÑO OOS 2023-10..2025-06) para el Gestor de Riesgo."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_features as af
import C1_eval as C1
import harness as H
lines = []
P = lambda s: (print(s), lines.append(s))
START, END = H.ms(2023, 10, 1), H.DESIGN[1]
bars, data = C1.load_until(END)
Fs = af.add_cross({s: af.build(data[s], 20) for s in C1.SYMS}, list(C1.SYMS))
ST = C1.signal_table(data, Fs)
take, _, _, _ = C1.scores(ST, START, END)
for g in ("PRIMARIA_G3H96", "SECUNDARIA_T48"):
    trs = C1.simulate_all(bars, data, ST, take, START, END, g)
    T = H.Trades.concat(trs)
    m = H.metrics(T)
    x = T.net_ret
    # concurrencia: fracción del tiempo en posición con k monedas abiertas
    tl = bars["BTCUSDT"].t
    occ = np.zeros(len(tl), int)
    for tr in trs:
        for a, b in zip(tr.entry_idx, tr.exit_idx):
            occ[a:b + 1] += 1
    inpos = occ[(tl >= START) & (tl < END)]
    frac = [np.mean(inpos[inpos > 0] == k) for k in (1, 2, 3, 4)]
    # solapamiento: operaciones que se abren mientras otra moneda tiene una abierta
    ov = 0
    allint = [(a, b, si) for si, tr in enumerate(trs) for a, b in zip(tr.entry_idx, tr.exit_idx)]
    for a, b, si in allint:
        if any(a2 <= a <= b2 and s2 != si for a2, b2, s2 in allint):
            ov += 1
    rr = x / T.risk_pct
    bs = H.bootstrap(rr, B=4000, block=10, seed=2)
    P(f"{g}: N={m['n']} salidas TP={m['tp_rate']*100:.0f}% SL={m['sl_rate']*100:.0f}% tiempo={m['time_rate']*100:.0f}% | "
      f"ganancia media={m['avg_win_pct']:.2f}% pérdida media={m['avg_loss_pct']:.2f}% peor={x.min()*100:.2f}% mejor={x.max()*100:.2f}% "
      f"sd={x.std(ddof=1)*100:.2f}% | E_R={rr.mean():+.3f} IC95 bootstrap [{bs['lo']:+.3f},{bs['hi']:+.3f}] | "
      f"tiempo en posición con 1/2/3/4 monedas: {', '.join(f'{f*100:.0f}%' for f in frac)} | ops que abren con otra moneda abierta: {ov/len(allint)*100:.0f}% | "
      f"duración mediana {np.median(T.hold):.0f} velas | Kelly nocional E/σ² = {x.mean()/x.var(ddof=1):.2f}x")
with open(os.path.join(C1.HERE, "..", "output", "analista", "16_riesgo_c1.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
