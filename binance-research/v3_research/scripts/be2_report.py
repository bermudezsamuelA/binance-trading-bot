"""Tabla consolidada de la ronda 1 del laboratorio (lee los JSON de output/bleeding_edge_r2; no simula nada)."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E

O = E.OUT2
J = lambda f: json.load(open(os.path.join(O, f), encoding="utf-8"))
ENS = ["ENS13", "ENS12", "ENS12U"]


def line(exp, lab, per_ens):
    r13, c13 = per_ens["ENS13"]
    if not r13.get("n"):
        return f"| {exp} | {lab} | 0 | | | | | | | | | | | | |"
    cond = f"{r13['cond_wr']*100:.1f} / {r13['cond_E']:+.2f}" if "cond_wr" in r13 else "–"
    rep = []
    for e in ("ENS12", "ENS12U"):
        r, c = per_ens.get(e, (None, None))
        rep.append(f"{c['dWR']*100:+.1f} / {c['dE']:+.2f}" if c and c.get("dWR") is not None and np.isfinite(c["dWR"]) else "–")
    ok, why = E.candidate({e: c for e, (r, c) in per_ens.items() if c})
    return (f"| {exp} | {lab} | {r13['n']} | {r13['wr']*100:.1f} [{r13['wr_lo']*100:.1f}, {r13['wr_hi']*100:.1f}] | "
            f"{r13['E_pct']:+.2f} | {r13['E_R']:+.3f} | {r13['t_day']:.2f} | {r13['rand_wr']*100:.1f} / {r13['rand_E']:+.2f} | {cond} | "
            f"{c13['dWR']*100:+.1f} / {c13['dE']:+.2f} | {c13['p_dWR_le0']:.2f} / {c13['p_dE_le0']:.2f} | "
            f"{c13['folds_imp']}/6 (={c13['folds_tie']}) | {r13['n_ep']} | {rep[0]} | {rep[1]} | {'sí' if ok else 'no'} |")


rows = []
g = J("be2_gatevar_ENS13_ENS12_ENS12U.json")
for lab in g["ENS13"]:
    if lab in ("pila", "desc", "val_q"):
        continue
    rows.append(line("E2/E3", lab, {e: (g[e][lab]["summary"], g[e][lab]["compare"]) for e in ENS}))
g13, g12 = J("be2_geom_ENS13.json"), J("be2_geom_ENS12_ENS12U.json")
for sel in ("wr_guard", "maxE"):
    pe = {"ENS13": (g13["ENS13"]["wf"][sel]["summary"], g13["ENS13"]["wf"][sel]["compare"])}
    for e in ("ENS12", "ENS12U"):
        pe[e] = (g12[e]["wf"][sel]["summary"], g12[e]["wf"][sel]["compare"])
    rows.append(line("E1", f"geometría WF ({sel})", pe))
for f, exp in (("be2_reentry.json", "E4"), ("be2_stage2.json", "E5/E6"), ("be2_joint.json", "E7–E9"),
               ("be2_extra.json", "E10/E11"), ("be2_tpdecay.json", "E12"), ("be2_extra2.json", "E13/E14"),
               ("be2_geom2.json", "E15")):
    d = J(f)
    for lab in d["ENS13"]:
        if lab in ("pila", "control", "desc_reb") or lab.startswith("H"):
            continue
        pe = {}
        for e in ENS:
            k = lab if lab in d[e] else [x for x in d[e] if x.startswith(lab[:4])][0]
            pe[e] = (d[e][k]["summary"], d[e][k]["compare"])
        rows.append(line(exp, lab, pe))
head = ("| Exp. | Regla | n | WR % [Wilson] | E % | E_R | t día | Azar WR / E | Azar cond. WR / E | ΔWR / ΔE vs pila | "
        "P(ΔWR≤0) / P(ΔE≤0) | pliegues mejor (=empates) | episodios | ENS12 ΔWR / ΔE | ENS12U ΔWR / ΔE | candidata |")
sep = "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
print(head); print(sep)
for r in rows:
    print(r)
