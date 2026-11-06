"""E31/E32 - ESTRUCTURALES de WR alto: grid spot y DCA/martingala. DISENO (2023-01..2025-06), velas de 15 m.

Objetivo: cuantificar de donde sale el "90-99 % de WR" de los bots comerciales y que pasa con la esperanza y la cola
cuando el inventario se valora a mercado.
GRID: rejilla estatica centrada en el precio al inicio de cada mes, 20 niveles por debajo separados delta; compra un
      lote al cruzar L_k hacia abajo y lo vende en L_k (1 + delta) (nunca en la misma vela de compra). Al cierre del
      mes se liquida el inventario restante a mercado (la perdida "escondida" se realiza). Comision maker 0.10 %/lado.
DCA : ciclo que compra 1 unidad al cierre, ordenes de seguridad en -2, -5, -9.5, -16, -25 % con multiplicador 2
      (1+2+4+8+16+32 = 63 unidades), TP +1.5 % sobre el precio medio; sin stop (variante: stop -35 % desde la 1a
      compra). Taker 0.10 % + 0.02 %.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H


def grid_month(o, h, l, c, t, delta, levels=20, fee=0.001):
    mon = B.month_of(t)
    cyc = []          # retornos netos por ciclo cerrado (sobre el nocional del lote)
    liq = []          # retornos netos de los lotes liquidados a fin de mes
    for m in np.unique(mon):
        idx = np.flatnonzero(mon == m)
        p0 = c[idx[0]]
        L = p0 * (1 - delta) ** np.arange(1, levels + 1)
        held = np.zeros(levels, bool)
        bought_at = np.full(levels, -1)
        for j in idx[1:]:
            # ventas primero (lotes comprados en velas anteriores)
            sell = held & (h[j] >= L * (1 + delta)) & (bought_at < j)
            for k in np.flatnonzero(sell):
                g = (1 + delta)
                cyc.append((g - 1) - fee * (1 + g))
                held[k] = False
            buy = (~held) & (l[j] < L)
            held |= buy
            bought_at[buy] = j
        for k in np.flatnonzero(held):
            g = c[idx[-1]] / L[k]
            liq.append((g - 1) - fee * (1 + g))
    return np.array(cyc), np.array(liq)


def dca(o, h, l, c, stop=None, cost=0.0012):
    so = np.array([0.0, -0.02, -0.05, -0.095, -0.16, -0.25])
    mult = 2.0 ** np.arange(6)
    cycles = []        # (ret neto sobre capital invertido, capital maximo invertido en unidades de lote base, motivo)
    worst_mtm = 0.0
    i, n = 0, len(c)
    while i < n - 1:
        p0 = c[i]
        lv = p0 * (1 + so)
        filled = np.zeros(6, bool); filled[0] = True
        units = mult[0]; cost_basis = p0 * mult[0]
        j = i + 1
        closed = False
        while j < n:
            # nuevas ordenes de seguridad (limite) tocadas en la vela
            for k in range(1, 6):
                if not filled[k] and l[j] <= lv[k]:
                    filled[k] = True; units += mult[k]; cost_basis += lv[k] * mult[k]
            avg = cost_basis / units
            mtm = l[j] / avg - 1
            worst_mtm = min(worst_mtm, mtm * cost_basis / (p0 * 63))   # perdida sobre el capital maximo (63 lotes)
            if stop is not None and l[j] <= p0 * (1 + stop):
                px = min(p0 * (1 + stop), o[j])
                g = px / avg
                cycles.append(((g - 1) - cost * (1 + g), cost_basis / p0, "stop", j - i))
                closed = True; break
            tp = avg * 1.015
            if h[j] >= tp:
                g = 1.015
                cycles.append(((g - 1) - cost * (1 + g), cost_basis / p0, "tp", j - i))
                closed = True; break
            j += 1
        if not closed:
            g = c[n - 1] / (cost_basis / units)
            cycles.append(((g - 1) - cost * (1 + g), cost_basis / p0, "abierto", n - 1 - i))
            break
        i = j + 1
    return cycles, worst_mtm


lines = ["# E31/E32 estructurales de WR alto (diseno 2023-01..2025-06, 15 m)\n",
         "## Grid spot (rejilla mensual, 20 niveles, inventario liquidado a fin de mes)\n",
         "| Moneda | delta | ciclos cerrados | WR ciclos % | E por ciclo % | lotes liquidados a fin de mes | E de esos lotes % | E total por lote % (ciclos + liquidados) | comprar y mantener del periodo % |",
         "|---|---|---|---|---|---|---|---|---|"]
res = {}
for sym in ("BTCUSDT", "SOLUSDT", "ETHUSDT", "DOGEUSDT"):
    bars = H.load(sym)
    i0, i1 = H.bounds(bars, "design")
    o, h, l, c, t = (x[i0:i1] for x in (bars.o, bars.h, bars.l, bars.c, bars.t))
    bh = (c[-1] / c[0] - 1) * 100
    for delta in (0.005, 0.01):
        cyc, liq = grid_month(o, h, l, c, t, delta)
        allx = np.concatenate([cyc, liq])
        lines.append(f"| {sym} | {delta*100:.1f} % | {len(cyc)} | {np.mean(cyc>0)*100:.1f} | {cyc.mean()*100:+.2f} | {len(liq)} | "
                     f"{liq.mean()*100:+.2f} | {allx.mean()*100:+.3f} | {bh:+.0f} |")
        res[f"grid {sym} {delta}"] = dict(cycles=len(cyc), wr=float(np.mean(cyc > 0)), E_cycle=float(cyc.mean() * 100),
                                          n_liq=len(liq), E_liq=float(liq.mean() * 100), E_all=float(allx.mean() * 100))
        print(lines[-1])
lines += ["\n## DCA / martingala (5 ordenes de seguridad, x2, TP +1.5 % sobre el precio medio)\n",
          "| Moneda | variante | ciclos | WR ciclos % | E por ciclo (sobre capital invertido) % | peor ciclo % | capital medio / maximo usado (lotes base, de 63) | peor perdida latente sobre el capital máximo % | ciclos abiertos al final |",
          "|---|---|---|---|---|---|---|---|---|"]
for sym in ("BTCUSDT", "SOLUSDT", "ETHUSDT", "DOGEUSDT"):
    bars = H.load(sym)
    i0, i1 = H.bounds(bars, "design")
    o, h, l, c = (x[i0:i1] for x in (bars.o, bars.h, bars.l, bars.c))
    for stop in (None, -0.35):
        cy, wm = dca(o, h, l, c, stop)
        r = np.array([x[0] for x in cy]); cap = np.array([x[1] for x in cy])
        op = sum(1 for x in cy if x[2] == "abierto")
        lines.append(f"| {sym} | {'sin stop' if stop is None else 'stop −35 %'} | {len(cy)} | {np.mean(r>0)*100:.1f} | "
                     f"{np.average(r, weights=cap)*100:+.3f} | {r.min()*100:+.1f} | {cap.mean():.1f} / {cap.max():.0f} | {wm*100:.1f} | {op} |")
        res[f"dca {sym} {stop}"] = dict(n=len(cy), wr=float(np.mean(r > 0)), E_w=float(np.average(r, weights=cap) * 100),
                                        worst=float(r.min() * 100), worst_mtm=float(wm * 100))
        print(lines[-1])
B.log_once("structural", 16, "E31/E32 grid delta{0.5,1}% x4 monedas, DCA con/sin stop x4 monedas (diseno, pedagogico)")
with open(os.path.join(B.OUT, "be_structural.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_structural.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
