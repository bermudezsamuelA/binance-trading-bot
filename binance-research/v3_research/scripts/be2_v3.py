"""R2 pila v3 (DISENO) y comprobaciones de E7. Se mide UNA vez, sin re-optimizar.

Pieza que pasa con reserva: E7 (barrera de tiempo mas larga con a = 0.7, m = 1.75). Regla para la prueba prospectiva:
H = 384 (lo que elige el selector WF "WR con guarda de E" con los 6 pliegues de ENS13: H = 384 y 576 empatan en WR y
384 tiene mas E). Se reporta tambien la version honesta en walk-forward (H elegido con los pliegues anteriores).
Comprobaciones (no son configuraciones nuevas de la pila): efecto de H = 384 en v2 sin compuerta y en senales aisladas
(si el efecto es estructural, aparece en todas), costos 0.19 % (BNB), episodios y meses.
Frontera WR-E (POST HOC, solo informativa, no candidata): X5, H384, D2 (TP2 +0.6 % desde 36 h), H384 + D2, (0.6, 1.75, 384).
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2_tpdecay as TD
B, H = E.B, E.H


def months(tab):
    mon = B.month_of(tab["et"])
    u, inv = np.unique(mon, return_inverse=True)
    pnl = np.bincount(inv, weights=tab["x"])
    return int(np.sum(pnl > 0)), len(u)


def run(ens):
    D = E.load(ens)
    g1 = D["A"] >= 1
    ref = E.trade_table(D, D["stack"], g1)
    D384 = E.with_geom(D, 0.7, 1.75, 384)
    out = {}
    rows = []
    for lab, Dx, mask, gate, fee in (("pila (X5) 0.24 %", D, D["stack"], g1, H.FEE),
                                     ("pila v3 = pila + H 384 · 0.24 %", D384, D["stack"], g1, H.FEE),
                                     ("pila v3 = pila + H 384 · 0.19 % (BNB)", D384, D["stack"], g1, 0.00075),
                                     ("v2 sin compuerta X5", D, D["sig"], None, H.FEE),
                                     ("v2 sin compuerta H 384", D384, D["sig"], None, H.FEE),
                                     ("señal aislada A=0 X5", D, D["sig"] & (D["A"] == 0), D["A"] == 0, H.FEE),
                                     ("señal aislada A=0 H 384", D384, D["sig"] & (D["A"] == 0), D["A"] == 0, H.FEE)):
        t = E.trade_table(Dx, mask, gate, fee=fee)
        r = E.summ(t, lab)
        r["months_pos"] = months(t)
        c = E.compare(t, ref) if "pila v3" in lab else None
        out[lab] = dict(summary=r, compare=c)
        rows.append((lab, r, c))
        print(ens, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", "meses", r["months_pos"], flush=True)
    # frontera post hoc
    ctl = TD.sim(D, D["stack"])
    fr = {}
    for lab, kw in (("X5", {}), ("H 384", dict(Hh=384)),
                    ("D2 (TP2 +0.6 % desde 36 h)", dict(decay_at=144, tp2_fn=lambda e, sd: e * 1.006)),
                    ("H 384 + D2", dict(Hh=384, decay_at=144, tp2_fn=lambda e, sd: e * 1.006)),
                    ("(0.6, 1.75, 384)", dict(a=0.6, Hh=384))):
        t = TD.sim(D, D["stack"], **kw)
        r = E.summ(t, lab); c = E.compare(t, ctl)
        fr[lab] = dict(summary=r, compare=c)
    out["frontier"] = fr
    return out


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    res = {ens: run(ens) for ens in ens_list}
    E.log_once("v3", 3, "R2 pila v3 (pila + H384) medida una vez; frontera post hoc H384+D2 y (0.6,1.75,384) solo informativa")
    E.jdump(res, os.path.join(E.OUT2, "be2_v3.json"))
    L = ["# R2 pila v3 en diseño (medida una vez) y frontera WR–E post hoc\n", E.HEAD, E.HEAD2]
    labs = [k for k in res[ens_list[0]] if k != "frontier"]
    for lab in labs:
        for ens in ens_list:
            o = res[ens][lab]
            L.append(E.row(ens, o["summary"], o.get("compare")))
    L.append("\nMeses positivos / meses con operaciones:\n")
    for lab in labs:
        L.append(f"- {lab}: " + ", ".join(f"{e} {res[e][lab]['summary']['months_pos']}" for e in ens_list))
    L.append("\nDetalle:\n")
    for lab in labs:
        for ens in ens_list:
            L.append(E.detail(ens, res[ens][lab]["summary"], res[ens][lab].get("compare")))
    L.append("\n## Frontera WR–E (POST HOC: combinaciones elegidas después de ver resultados; no son candidatas)\n")
    L.append(E.HEAD); L.append(E.HEAD2)
    for lab in res[ens_list[0]]["frontier"]:
        for ens in ens_list:
            o = res[ens]["frontier"][lab]
            L.append(E.row(ens, o["summary"], o["compare"] if lab != "X5" else None))
    with open(os.path.join(E.OUT2, "be2_v3.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
