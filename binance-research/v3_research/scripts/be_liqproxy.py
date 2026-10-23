"""E03-proxy - LIQUIDACIONES aproximadas con los metrics de futuros de 5 min (ya en el modelo como variables).

Pregunta: dentro de las senales del ensamble (p >= umbral del pliegue), ¿hay un gradiente monotono del WR / E segun
  * oi_chg_4  (caida de OI en 1 h: cierre forzado o voluntario de posiciones, "OI flush"),
  * oi_chg_16 (4 h), fut_taker_4 (ratio taker comprador/vendedor de futuros en 1 h, log),
  * premium_z_672 (prima del perpetuo en z), funding_z_2016, oi_to_vol, top_pos_chg_16, glob_acc_chg_16?
Los cortes de tercil se fijan con las senales de VALIDACION de cada pliegue (causal); el resultado por vela es X5.
Despues, 3 compuertas pre-especificadas (tercil "mas forzado"): OI flush, taker vendedor, prima negativa.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H

D = B.load_ens()
FEATS = ["oi_chg_4", "oi_chg_16", "fut_taker_4", "premium_z_672", "funding_z_2016", "oi_to_vol", "top_pos_chg_16",
         "glob_acc_chg_16", "ret_4", "bar_range", "vol_rel_1"]
names = list(D["cache"]["BTCUSDT"]["names"])
X = {}
for f in FEATS:
    k = names.index(f)
    col = np.full(len(D["rows"]), np.nan)
    for ci_, s in enumerate(H.SYMBOLS):
        m = D["ci"] == ci_
        col[m] = D["cache"][s]["X"][D["ii"][m], k]
    X[f] = col
# filas de validacion para cortes: misma estructura (vals[k]['rows'] son filas globales del pool)
P0 = np.load(os.path.join(B.R.PRED, f"{B.ENS13[0]}.npz"))
ci_all, ii_all = P0["ci"], P0["ii"]


def feat_at(f, rows):
    k = names.index(f)
    out = np.full(len(rows), np.nan)
    for ci_, s in enumerate(H.SYMBOLS):
        m = ci_all[rows] == ci_
        out[m] = D["cache"][s]["X"][ii_all[rows][m], k]
    return out


sig = D["p"] >= D["thr"]
okx = np.isfinite(D["netX"])
# cortes por pliegue con las senales de validacion
terc = {f: np.full(len(D["rows"]), -1) for f in FEATS}
for k in range(6):
    V = D["vals"][k]
    sv = V["p"] >= V["thr"]
    fm = D["fold"] == k
    for f in FEATS:
        x = feat_at(f, V["rows"][sv])
        x = x[np.isfinite(x)]
        if len(x) < 30:
            continue
        q1, q2 = np.quantile(x, [1 / 3, 2 / 3])
        v = X[f][fm]
        terc[f][fm] = np.where(~np.isfinite(v), -1, np.where(v <= q1, 0, np.where(v <= q2, 1, 2)))
lines = ["# E03-proxy: liquidaciones aproximadas con metrics de 5 min (diseno, ENS13, X5)\n",
         "Cortes de tercil fijados con las senales de validacion de cada pliegue. Resultado por vela (solapado).\n",
         "| Variable | T1 (bajo) velas / WR % / E % | T2 | T3 (alto) | azar en T1 / T3 (WR %, E %) |", "|---|---|---|---|---|"]
for f in FEATS:
    cells = []
    for tt in (0, 1, 2):
        s = sig & okx & (terc[f] == tt)
        cells.append(f"{s.sum()} / {np.mean(D['netX'][s] > 0)*100:.1f} / {np.mean(D['netX'][s])*100:+.2f}" if s.sum() else "0")
    r1 = okx & (terc[f] == 0); r3 = okx & (terc[f] == 2)
    lines.append(f"| {f} | " + " | ".join(cells) +
                 f" | {np.mean(D['netX'][r1]>0)*100:.1f}, {np.mean(D['netX'][r1])*100:+.2f} / {np.mean(D['netX'][r3]>0)*100:.1f}, {np.mean(D['netX'][r3])*100:+.2f} |")
lines += ["\n## Compuertas pre-especificadas (simulacion con una posicion por moneda)\n"] + list(B.MD_HEAD_C)
res = {}
gates = [("v2 sin compuerta", None),
         ("OI flush: oi_chg_4 en T1 (caida mas fuerte de OI)", terc["oi_chg_4"] == 0),
         ("Taker vendedor: fut_taker_4 en T1", terc["fut_taker_4"] == 0),
         ("Prima negativa: premium_z_672 en T1", terc["premium_z_672"] == 0),
         ("Sin OI flush: oi_chg_4 en T2-T3", terc["oi_chg_4"] >= 1),
         ("EXPLORATORIO post-hoc: oi_to_vol en T1 (OI bajo frente al volumen)", terc["oi_to_vol"] == 0)]
for lab, g in gates:
    m = sig if g is None else sig & g
    T, s = B.simulate_entries(D, m)
    r = B.summarize_trades(T, s, D, label=lab, cond_base=None if g is None else B.cond_base(D, g))
    lines.append(B.md_row(r)); print(B.fmt(r)); res[lab] = r
B.log_once("liqproxy", len(FEATS) + 4, "E03-proxy liquidaciones: 11 gradientes por tercil + 4 compuertas (diseno)")
B.log_once("liqproxy_extra", 1, "E03-proxy exploratorio post-hoc: compuerta oi_to_vol T1 (diseno)")
with open(os.path.join(B.OUT, "be_liqproxy.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_liqproxy.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
print("\n".join(lines))
