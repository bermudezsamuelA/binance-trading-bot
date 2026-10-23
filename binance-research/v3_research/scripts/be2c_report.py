"""R2B tablas del informe (lee be2c_dvol.json; no simula)."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2b_common as K

res = json.load(open(os.path.join(K.OUT2, "be2c_dvol.json"), encoding="utf-8"))
ENS = ["ENS13", "ENS12", "ENS12U", "ENS6"]
CONT = {"ENS13": "contaminado", "ENS12": "no contaminado", "ENS12U": "no contaminado", "ENS6": "no contaminado (v1)"}
rules = [k.rsplit(" [", 1)[0] for k in res["ENS13"] if k.endswith("[X5]")]
L = []


def holm(ps):
    ps = np.array(ps, float); m = len(ps); o = np.argsort(ps); adj = np.empty(m); run = 0
    for r, i in enumerate(o):
        run = max(run, min(1, (m - r) * ps[i])); adj[i] = run
    return adj


L.append("### D1 (z30 del DVOL de BTC ≥ −1): todas las muestras\n")
L.append("| Ensamble | Base | n | WR % [Wilson] | WR beta-bin. [IC] | E % | E_R | t día | Azar WR/E | Azar cond. WR/E | ΔWR / ΔE | P_ep(ΔWR≤0) / P_ep(ΔE≤0) | pliegues que cambian: mejoran | vetadas: n · WR · E | azar que quita el mismo n: WR medio (percentil de D1) | aisladas A=0: ΔWR / ΔE | azar explica % de ΔWR | tamiz |")
L.append("|" + "---|" * 18)
for e in ENS:
    for b in ("X5", "H384"):
        o = res[e][f"D1 z30(BTC) ≥ −1 [{b}]"]; r = o["summary"]; c = o["compare"]; bb = o["bb"]; fi = o["fold_info"]; rr = o["rand_removal"]
        sc = o["screen_info"]; ic = o["iso_cmp"]
        L.append(f"| {e} ({CONT[e]}) | {b} | {r['n']} | {r['wr']*100:.1f} [{r['wr_lo']*100:.1f}, {r['wr_hi']*100:.1f}] | "
                 f"{bb['mu']*100:.1f} [{bb['lo']*100:.1f}, {bb['hi']*100:.1f}] | {r['E_pct']:+.2f} | {r['E_R']:+.3f} | {r['t_day']:.2f} | "
                 f"{r['rand_wr']*100:.1f} / {r['rand_E']:+.2f} | {r['cond_wr']*100:.1f} / {r['cond_E']:+.2f} | {c['dWR']*100:+.1f} / {c['dE']:+.2f} | "
                 f"{c['p_dWR_le0']:.2f} / {c['p_dE_le0']:.2f} | {sc['folds_changed']}: {sc['folds_improved']} | "
                 f"{fi['n_vet']} · {fi['wr_vet']*100:.0f} % · {fi['E_vet']:+.2f} | {rr['wr_mean']*100:.1f} % (p{rr['pct_wr']*100:.0f}) | "
                 f"{ic['dWR']*100:+.1f} / {ic['dE']:+.2f} | {sc['frac_cond']*100:.0f} % | {'pasa' if o['screen'] else 'no'} |")
    L.append(f"| {e} | pila X5 / v3 | {res[e]['pila X5']['summary']['n']} / {res[e]['pila H384']['summary']['n']} | "
             f"{res[e]['pila X5']['summary']['wr']*100:.1f} / {res[e]['pila H384']['summary']['wr']*100:.1f} | | "
             f"{res[e]['pila X5']['summary']['E_pct']:+.2f} / {res[e]['pila H384']['summary']['E_pct']:+.2f} | | | | "
             f"{res[e]['pila X5']['summary']['cond_wr']*100:.1f} / {res[e]['pila H384']['summary']['cond_wr']*100:.1f} (WR) | — | — | — | — | — | aisladas base: "
             f"{res[e]['aisladas X5']['summary']['n']} · {res[e]['aisladas X5']['summary']['wr']*100:.1f} % · {res[e]['aisladas X5']['summary']['E_pct']:+.2f} | — | — |")

L.append("\n### Control de volatilidad y de p̂ (D1, base X5; operaciones de la pila: conservadas frente a vetadas)\n")
L.append("| Ensamble | s_d baja: conserv. n · WR · E / vetadas | s_d media | s_d alta | p̂ − θ medio: conservadas / vetadas | días de las vetadas |")
L.append("|---|---|---|---|---|---|")
for e in ENS:
    fi = res[e]["D1 z30(BTC) ≥ −1 [X5]"]["fold_info"]
    cells = []
    for nm, na, wa, ea, nb, wb, eb in fi["vol"]:
        fa = f"{na} · {wa*100:.0f} % · {ea:+.2f}" if na else "0"
        fb = f"{nb} · {wb*100:.0f} % · {eb:+.2f}" if nb else "0"
        cells.append(f"{fa} / {fb}")
    L.append(f"| {e} | {cells[0]} | {cells[1]} | {cells[2]} | {fi['p_keep']:+.3f} / {fi['p_vet']:+.3f} | {', '.join(fi['days'])} |")

L.append("\n### Consistencia por pliegue (D1, base X5): WR de las conservadas − WR de las vetadas, en los pliegues con vetadas\n")
for e in ENS:
    fi = res[e]["D1 z30(BTC) ≥ −1 [X5]"]["fold_info"]
    pos = sum(1 for f, n, d in fi["folds"] if d > 0)
    L.append(f"- {e}: " + "; ".join(f"pliegue {f} (vetadas {n}): {d*100:+.0f} pt" for f, n, d in fi["folds"]) + f" → mismo signo (+) en {pos}/{len(fi['folds'])}")

L.append("\n### Todas las reglas de la parte B (ΔWR pt / ΔE %, P_ep(ΔWR≤0), Holm sobre las 6 reglas por ensamble y base)\n")
L.append("| Regla | " + " | ".join(f"{e} {b}" for e in ENS for b in ("X5", "H384")) + " |")
L.append("|---|" + "---|" * 8)
adj = {}
for e in ENS:
    for b in ("X5", "H384"):
        ks = [f"{r} [{b}]" for r in rules if f"{r} [{b}]" in res[e]]
        ps = [res[e][k]["compare"]["p_dWR_le0"] for k in ks]
        for k, a in zip(ks, holm(ps)):
            adj[(e, k)] = a
for r in rules:
    cells = []
    for e in ENS:
        for b in ("X5", "H384"):
            k = f"{r} [{b}]"
            if k not in res[e]:
                cells.append("–"); continue
            c = res[e][k]["compare"]
            cells.append(f"{c['dWR']*100:+.1f} / {c['dE']:+.2f} · p {c['p_dWR_le0']:.2f} → Holm {adj[(e, k)]:.2f}{' · tamiz' if res[e][k]['screen'] else ''}")
    L.append(f"| {r} | " + " | ".join(cells) + " |")
L.append(f"\nInformación: {res['_info']}")
out = "\n".join(L) + "\n"
open(os.path.join(K.OUT2, "be2c_tables.md"), "w", encoding="utf-8").write(out)
print(out)
