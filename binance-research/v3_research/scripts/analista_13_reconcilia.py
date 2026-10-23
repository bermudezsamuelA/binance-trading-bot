"""Ronda 2 - Conciliación de C1 con el Gestor de Riesgo (en 15m no hay borde bruto en 3 447 reglas).
1) Retorno futuro BRUTO por decil del score OOS (no solapado por moneda) a 1h/4h/12h/24h: ¿el borde está en la
   selección (decil superior) y en el horizonte, y la señal promedio tiene ~0 como mide el Gestor?
2) Entradas de C1 con las geometrías ATR del Gestor (a, m en ATR14 de 15m) frente a entradas al azar (RND) con la
   misma geometría: ¿el borde sobrevive a las salidas del Gestor? (separa 'selección' de 'geometría').
3) Dependencia del régimen: C1 por régimen de BTC al entrar (precio sobre/bajo su SMA de 30 días) y por mes
   alcista/bajista de BTC."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_features as af
import C1_eval as C1
import harness as H

lines = []
P = lambda s: (print(s), lines.append(s))
START, END, SPLIT = H.ms(2023, 10, 1), H.DESIGN[1], H.ms(2024, 4, 1)
bars, data = C1.load_until(END)
syms = list(C1.SYMS)
Fs = af.add_cross({s: af.build(data[s], 20) for s in syms}, syms)
ST = C1.signal_table(data, Fs)
take, score, thr, _ = C1.scores(ST, START, END)
n_cfg = 0

# 1) deciles
P("1) Retorno BRUTO medio (%) por decil del score OOS, no solapado por moneda; t entre paréntesis. c = 0.24 %")
for part, (a, b) in (("A 2023-10..2024-03", (START, SPLIT)), ("B 2024-04..2025-06", (SPLIT, END))):
    m = (ST["t"] >= a) & (ST["t"] < b) & np.isfinite(score)
    edges = np.quantile(score[m], np.linspace(0, 1, 11))
    P(f"  {part}: N señales={m.sum()}")
    for h in (4, 16, 48, 96):
        row = []
        for dcl in range(10):
            sel = m & (score >= edges[dcl]) & (score <= edges[dcl + 1] if dcl == 9 else score < edges[dcl + 1])
            rs = []
            for si, s in enumerate(syms):
                ii = np.sort(ST["idx"][sel & (ST["si"] == si)])
                last = -10 ** 9
                c = data[s]["c"]
                for i in ii:
                    if i >= last + h and i + h < len(c):
                        rs.append(c[i + h] / c[i] - 1); last = i
            r = np.array(rs)
            row.append(f"{r.mean()*100:+.2f}({r.mean()/(r.std(ddof=1)/np.sqrt(len(r))):+.1f})")
        n_cfg += 1
        P(f"    h={h:3d}: " + " ".join(row))
    # todas las señales y deriva incondicional
    for h in (16, 96):
        rs, ru = [], []
        for si, s in enumerate(syms):
            c = data[s]["c"]; t = data[s]["t"]
            ii = np.sort(ST["idx"][m & (ST["si"] == si)])
            last = -10 ** 9
            for i in ii:
                if i >= last + h and i + h < len(c):
                    rs.append(c[i + h] / c[i] - 1); last = i
            jj = np.flatnonzero((t >= a) & (t < b))[::h]
            jj = jj[jj + h < len(c)]
            ru.extend(c[jj + h] / c[jj] - 1)
        P(f"    h={h}: todas las señales MR20 {np.mean(rs)*100:+.3f}% | incondicional (deriva) {np.mean(ru)*100:+.3f}%")

# 2) geometrías del Gestor sobre entradas de C1 y RND
P("\n2) Entradas C1 (decil sup.) vs RND con geometrías ATR14 del Gestor (TP=P+a*ATR, SL=P-m*ATR, H velas de 15m)")
geoms = [("ATR a=1 m=3 H=96 (WR alto)", 1.0, 3.0, 96), ("ATR a=1.5 m=4 H=48", 1.5, 4.0, 48),
         ("ATR a=3 m=3 H=96", 3.0, 3.0, 96), ("C1 primaria G3H96", None, None, None)]
rng = np.random.default_rng(3)
for name, a_, m_, Hh in geoms:
    res = {}
    for lab in ("C1", "RND"):
        trs = []
        for si, s in enumerate(syms):
            b = bars[s]
            atr = H.rolling_mean(H.true_range(b.h, b.l, b.c), 14)
            ent = np.zeros(len(b), bool)
            if lab == "C1":
                ent[ST["idx"][(ST["si"] == si) & take]] = True
            else:
                cand = np.arange(b.idx(START), b.idx(END) - 1)
                ent[rng.choice(cand, 3000, replace=False)] = True
            if a_ is None:
                mu = H.rolling_mean(b.c, 20); R = mu - b.c
                if lab == "RND":   # misma escala relativa típica de C1: R = 2.9 % (mediana TP de C1)
                    R = 0.029 * b.c
                    mu = b.c + R
                tr = H.simulate(b, ent, mu, b.c - 3 * R, period=(b.idx(START), b.idx(END)), max_hold=96)
            else:
                tr = H.simulate(b, ent, b.c + a_ * atr, b.c - m_ * atr, period=(b.idx(START), b.idx(END)), max_hold=Hh)
            trs.append(tr)
        res[lab] = H.metrics(H.Trades.concat(trs))
        n_cfg += 1
    c, r = res["C1"], res["RND"]
    P(f"  {name:28s} C1: N={c['n']:4d} WR={c['wr']*100:4.1f}% E={c['E_pct']:+.3f}% (t={c['t']:+.2f}) E_R={c['E_R']:+.3f} | "
      f"RND: N={r['n']:4d} WR={r['wr']*100:4.1f}% E={r['E_pct']:+.3f}% E_R={r['E_R']:+.3f} | ΔWR={100*(c['wr']-r['wr']):+.1f}pp")

# 3) régimen
P("\n3) C1 primaria por régimen de BTC al entrar")
trs = C1.simulate_all(bars, data, ST, take, START, END, "PRIMARIA_G3H96")
T = H.Trades.concat(trs)
bb = bars["BTCUSDT"]
sma30 = H.rolling_mean(bb.c, 2880)
pos = np.searchsorted(bb.t, T.entry_t)
up = bb.c[pos] > sma30[pos]
mon = T.entry_t.astype("datetime64[ms]").astype("datetime64[M]")
mret = {}
for u in np.unique(mon):
    t0 = u.astype("datetime64[ms]").astype(np.int64); t1 = (u + 1).astype("datetime64[ms]").astype(np.int64)
    i0, i1 = bb.idx(t0), min(bb.idx(t1), len(bb)) - 1
    mret[u] = bb.c[i1] / bb.c[i0] - 1
bull_m = np.array([mret[u] > 0 for u in mon])
for lab, mk in (("BTC > SMA30d", up), ("BTC < SMA30d", ~up), ("mes BTC alcista", bull_m), ("mes BTC bajista", ~bull_m)):
    m = H.metrics(T.subset(mk))
    P(f"  {lab:16s}: N={m['n']:4d} WR={m['wr']*100:4.1f}% [{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}] E={m['E_pct']:+.3f}% (t={m['t']:+.2f})")
P(f"\nConfiguraciones/diagnósticos en este script: {n_cfg}")
H.log_trials("analista", n_cfg, "R2 conciliacion: deciles x horizontes, C1/RND con geometrias ATR del Gestor", "design")
with open(os.path.join(C1.HERE, "..", "output", "analista", "13_reconcilia.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
