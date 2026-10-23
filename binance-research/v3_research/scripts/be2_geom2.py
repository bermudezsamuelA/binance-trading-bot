"""R2-E15 Geometria con barrera de tiempo larga, elegida en walk-forward (DISENO). Pre-registro (escrito antes de correr;
OJO: la familia se inspira en R2-E1, R2-E7 y R2-E12, es decir, en resultados de la prueba; por eso solo cuenta la
version con eleccion fuera de la prueba):
- Rejilla: a in {0.5, 0.6, 0.7}, m in {1.75, 2.25}, H in {288, 384, 576} (18 geometrias; X5 = (0.7, 1.75, 288)).
- Senales: las de la pila (p >= theta y A >= 1), sin cambios.
- S1: geometria elegida con las operaciones de los pliegues ANTERIORES (pliegue 0 = X5): max WR con E_prev >= E_prev(X5).
- S2: geometria elegida en la VALIDACION de cada pliegue (todas las velas de validacion con p >= theta y A_val >= 1,
  resultado por vela): max WR_val con E_val >= E_val(X5). Vale tambien para el pliegue 0.
Registro: 18 x 2.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H = E.B, E.H

GRID = [(a, m, h) for a in (0.5, 0.6, 0.7) for m in (1.75, 2.25) for h in (288, 384, 576)]
X5 = (0.7, 1.75, 288)


def val_gated(D, k):
    v = D["vals"][k]
    N = len(D["tg"])
    j = np.searchsorted(D["tg"], v["t"])
    sigv = v["p"] >= v["thr"]
    S = np.zeros((4, N), bool); S[v["ci"], j] = sigv
    per = E.roll_any(S, E.W)
    A = per.sum(0)[j] - per[v["ci"], j]
    return v["rows"][sigv & (A >= 1)], v["t"][sigv & (A >= 1)]


def run(ens):
    D = E.load(ens)
    g1 = D["A"] >= 1
    ref = E.trade_table(D, D["stack"], g1)
    tabs, netall = {}, {}
    for g in GRID:
        Dg = E.with_geom(D, *g)
        tabs[g] = E.trade_table(Dg, D["stack"], g1)
        _, lab = E.ensure_geom(*g)
        netall[g] = np.concatenate([lab[s][0] for s in H.SYMBOLS])
    res = {"pila": dict(summary=E.summ(ref, "pila X5"))}
    for sel in ("S1 pliegues anteriores", "S2 validación"):
        chosen, pieces = [], []
        for k in range(6):
            if sel.startswith("S1"):
                if k == 0:
                    gk = X5
                else:
                    s5 = tabs[X5]["fold"] < k
                    e5 = tabs[X5]["x"][s5].mean()
                    gk, bkey = X5, None
                    for g in GRID:
                        s = tabs[g]["fold"] < k
                        if not s.any() or tabs[g]["x"][s].mean() < e5 - 1e-12:
                            continue
                        key = (float(np.mean(tabs[g]["x"][s] > 0)), float(tabs[g]["x"][s].mean()))
                        if bkey is None or key > bkey:
                            gk, bkey = g, key
            else:
                rows, tv = val_gated(D, k)
                t0 = H.ms(*B.TESTS[k][0], 1)
                gk, bkey = X5, None
                if len(rows):
                    hmax = max(h for _, _, h in GRID)
                    okp = tv < t0 - (hmax + 1) * E.C.MS15  # purga con la H mas larga, igual para todas
                    x5 = netall[X5][rows][okp]; f5 = np.isfinite(x5)
                    e5 = np.nanmean(x5)
                    for g in GRID:
                        x = netall[g][rows][okp]
                        f = np.isfinite(x)
                        if f.sum() < 50 or np.nanmean(x) < e5 - 1e-12:
                            continue
                        key = (float(np.mean(x[f] > 0)), float(np.mean(x[f])))
                        if bkey is None or key > bkey:
                            gk, bkey = g, key
            chosen.append(gk)
            pieces.append(E.sub_table(tabs[gk], tabs[gk]["fold"] == k))
        comp = E.cat_tables(pieces)
        r = E.summ(comp, f"E15 {sel}")
        c = E.compare(comp, ref)
        res[f"E15 {sel}"] = dict(summary=r, compare=c, chosen=[E.gname(*g) for g in chosen])
        print(ens, sel, [E.gname(*g) for g in chosen], r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}",
              f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']} ties {c['folds_tie']}", flush=True)
    return res


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    res = {ens: run(ens) for ens in ens_list}
    E.log_once("geom2", 36, "R2-E15 geometria (a 0.5-0.7, m 1.75/2.25, H 288/384/576) elegida en WF: pliegues anteriores y validacion")
    E.jdump(res, os.path.join(E.OUT2, "be2_geom2.json"))
    L = ["# R2-E15 geometría con H largo elegida fuera de la prueba\n", E.HEAD, E.HEAD2]
    labs = list(res[ens_list[0]].keys())
    for lab in labs:
        for ens in ens_list:
            L.append(E.row(ens, res[ens][lab]["summary"], res[ens][lab].get("compare")))
    L.append("")
    for lab in labs[1:]:
        ok, why = E.candidate({ens: res[ens][lab]["compare"] for ens in ens_list})
        L.append(f"- {lab}: {'CANDIDATA' if ok else 'no'} — {why}")
        for ens in ens_list:
            L.append(f"  - {ens} elegidas: {res[ens][lab]['chosen']}")
            L.append(E.detail(ens, res[ens][lab]["summary"], res[ens][lab]["compare"]))
    with open(os.path.join(E.OUT2, "be2_geom2.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
