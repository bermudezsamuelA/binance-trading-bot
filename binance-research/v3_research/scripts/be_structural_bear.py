"""E31/E32 (DESCRIPTIVO, holdout gastado 2025-07..2026-09, mercado bajista): grid y DCA con solo precios spot.
No decide nada del modelo; solo muestra la cola de las estructuras de WR alto fuera del mercado alcista de diseno."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
import be_structural as S
H = B.H
lines = ["# E31/E32 DESCRIPTIVO en el periodo bajista 2025-07..2026-09 (holdout gastado; solo precios, no decide nada)\n",
         "| Moneda | estructura | ciclos | WR ciclos % | E % (ciclo o lote) | peor ciclo/lote % | peor perdida latente % | comprar y mantener % |",
         "|---|---|---|---|---|---|---|---|"]
res = {}
for sym in ("BTCUSDT", "SOLUSDT", "ETHUSDT", "DOGEUSDT"):
    bars = H.load(sym)
    i0, i1 = H.bounds(bars, "holdout", reason="be_structural_bear: descriptivo de grid/DCA (solo precios spot) en mercado bajista; no decide nada del modelo")
    o, h, l, c, t = (x[i0:i1] for x in (bars.o, bars.h, bars.l, bars.c, bars.t))
    bh = (c[-1] / c[0] - 1) * 100
    cyc, liq = S.grid_month(o, h, l, c, t, 0.01)
    allx = np.concatenate([cyc, liq])
    lines.append(f"| {sym} | grid 1 % | {len(cyc)} (+{len(liq)} liquidados) | {np.mean(cyc>0)*100:.1f} | {allx.mean()*100:+.3f} por lote | {liq.min()*100:+.1f} | – | {bh:+.0f} |")
    for stop in (None, -0.35):
        cy, wm = S.dca(o, h, l, c, stop)
        r = np.array([x[0] for x in cy]); cap = np.array([x[1] for x in cy])
        lines.append(f"| {sym} | DCA {'sin stop' if stop is None else 'stop −35 %'} | {len(cy)} | {np.mean(r>0)*100:.1f} | "
                     f"{np.average(r, weights=cap)*100:+.3f} por ciclo | {r.min()*100:+.1f} | {wm*100:.1f} | {bh:+.0f} |")
    print("\n".join(lines[-3:]))
with open(os.path.join(B.OUT, "be_structural_bear.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
