"""R2-E1 Geometria de salida condicionada a la compuerta (DISENO). Pre-registro (escrito antes de correr):

- Senales: las de la pila (p >= theta del pliegue y A_model(W=48) >= 1), sin cambios.
- Rejilla fija de 30 geometrias: a in {0.4, 0.5, 0.6, 0.7, 0.9}, m in {1.25, 1.75, 2.25}, H in {192, 288}
  (TP = c(1 + a s_d), SL = c(1 - m s_d), s_d = sigma15(672) sqrt(96)). X5 = (0.7, 1.75, 288).
- Eleccion en walk-forward: en el pliegue k se usa la geometria elegida con las operaciones de los pliegues 0..k-1
  (pliegue 0: X5). Selector principal "WR con guarda de E": max WR con E_prev >= E_prev(X5) (empate: mayor E).
  Selector secundario "max E".
- Comparacion: contra la pila (X5) y contra el azar condicionado a la compuerta con la MISMA geometria.
- Deriva implicita nu (s_d por dia): se invierte P(TP antes que SL) = (1 - e^{2 nu m}) / (e^{-2 nu a} - e^{2 nu m})
  con la fraccion TP / (TP + SL) de las operaciones (excluye salidas por tiempo).
Replica en ENS13, ENS12 y ENS12U. Se registran 30 geometrias x 2 selectores.
"""
import os, sys, json
import numpy as np
from scipy.optimize import brentq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H = E.B, E.H

AS = (0.4, 0.5, 0.6, 0.7, 0.9)
MS = (1.25, 1.75, 2.25)
HS = (192, 288)
GRID = [(a, m, h) for a in AS for m in MS for h in HS]
X5 = (0.7, 1.75, 288)


def nu_implied(p, a, m):
    f = lambda v: ((1 - np.exp(2 * v * m)) / (np.exp(-2 * v * a) - np.exp(2 * v * m)) if abs(v) > 1e-9 else m / (a + m)) - p
    try:
        return float(brentq(f, -3, 3))
    except Exception:
        return float("nan")


def tp_frac(why):
    tp, sl = np.sum(why == 0), np.sum(why == 1)
    return tp / (tp + sl) if tp + sl else float("nan")


def stats_prev(tab, k):
    s = tab["fold"] < k
    if not s.any():
        return float("nan"), float("nan"), 0
    return float(np.mean(tab["x"][s] > 0)), float(tab["x"][s].mean()), int(s.sum())


def run(ens):
    D = E.load(ens)
    gate = D["A"] >= 1
    tabs, rows_g = {}, []
    for g in GRID:
        Dg = E.with_geom(D, *g)
        t = E.trade_table(Dg, D["stack"], gate)
        tabs[g] = t
        r = E.summ(t, E.gname(*g))
        # deriva implicita: modelo (operaciones), azar condicionado (velas con compuerta) y azar (todas las velas)
        ok = np.isfinite(Dg["netX"])
        nu_m = nu_implied(tp_frac(t["reason"]), g[0], g[1])
        nu_c = nu_implied(tp_frac(Dg["whyX"][ok & gate]), g[0], g[1])
        nu_r = nu_implied(tp_frac(Dg["whyX"][ok]), g[0], g[1])
        r.update(nu_model=nu_m, nu_cond=nu_c, nu_rand=nu_r, time_rate=float(np.mean(t["reason"] == 2)))
        rows_g.append((g, r))
        print(ens, E.gname(*g), r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"cond {r['cond_wr']*100:.1f}/{r['cond_E']:+.2f}",
              f"nu {nu_m:.3f}/{nu_c:.3f}/{nu_r:.3f}", flush=True)
    ref = tabs[X5]
    out = {}
    for sel in ("wr_guard", "maxE"):
        chosen, pieces = [], []
        for k in range(6):
            if k == 0:
                gk = X5
            else:
                wr5, e5, _ = stats_prev(tabs[X5], k)
                best, bkey = X5, None
                for g in GRID:
                    wr, e, n = stats_prev(tabs[g], k)
                    if n == 0:
                        continue
                    if sel == "wr_guard":
                        if e < e5 - 1e-12:
                            continue
                        key = (wr, e)
                    else:
                        key = (e, wr)
                    if bkey is None or key > bkey:
                        best, bkey = g, key
                gk = best
            chosen.append(gk)
            pieces.append(E.sub_table(tabs[gk], tabs[gk]["fold"] == k))
        comp = E.cat_tables(pieces)
        r = E.summ(comp, f"WF {sel}")
        c = E.compare(comp, ref)
        out[sel] = dict(summary=r, compare=c, chosen=[E.gname(*g) for g in chosen])
        print(ens, sel, [E.gname(*g) for g in chosen], r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}",
              f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", flush=True)
    return D, rows_g, out, ref


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    res = {}
    for ens in ens_list:
        D, rows_g, out, ref = run(ens)
        res[ens] = dict(grid={E.gname(*g): r for g, r in rows_g}, wf=out, ref=E.summ(ref, "pila X5"))
    E.log_once("geom", len(GRID) * 2, "R2-E1 geometria condicionada a la compuerta: 30 geometrias (a,m,H) x 2 selectores WF")
    tag = "_".join(ens_list)
    E.jdump(res, os.path.join(E.OUT2, f"be2_geom_{tag}.json"))
    L = [f"# R2-E1 geometria condicionada a la compuerta ({', '.join(ens_list)})\n"]
    for ens in ens_list:
        rr = res[ens]
        L.append(f"\n## {ens}\n")
        L.append("Rejilla completa (DESCRIPTIVA: mirar esta tabla para elegir sería usar la prueba).\n")
        L.append("| Geometría | n | WR % | E % | E_R | t día | Azar cond. WR / E | ΔWR / ΔE vs azar cond. | TP % / tiempo % | ν modelo / azar cond. / azar |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for gname, r in rr["grid"].items():
            L.append(f"| {gname} | {r['n']} | {r['wr']*100:.1f} | {r['E_pct']:+.2f} | {r['E_R']:+.3f} | {r['t_day']:.2f} | "
                     f"{r['cond_wr']*100:.1f} / {r['cond_E']:+.2f} | {r['dWR_cond']*100:+.1f} / {r['dE_cond']:+.2f} | "
                     f"{r['tp_rate']*100:.0f} / {r['time_rate']*100:.0f} | {r['nu_model']:.3f} / {r['nu_cond']:.3f} / {r['nu_rand']:.3f} |")
        L.append("\nElección en walk-forward:\n")
        L.append(E.HEAD); L.append(E.HEAD2)
        L.append(E.row(ens, rr["ref"]))
        for sel, o in rr["wf"].items():
            L.append(E.row(ens, o["summary"], o["compare"]))
        for sel, o in rr["wf"].items():
            L.append(f"- {sel}: geometrías elegidas por pliegue {o['chosen']}")
            L.append(E.detail(ens, o["summary"], o["compare"]))
    with open(os.path.join(E.OUT2, f"be2_geom_{tag}.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
