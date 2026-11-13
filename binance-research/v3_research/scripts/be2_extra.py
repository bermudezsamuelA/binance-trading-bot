"""R2-E10/E11 (DISENO). Ideas anadidas por el laboratorio (pre-registro escrito antes de correr):

E10 Co-firma de un ensamble entrenado distinto: la senal de la pila solo se toma si el OTRO ensamble (con pesos de unicidad,
    menos sobreajustado a los panicos grandes) tambien la ve en la misma vela, con la MISMA selectividad: umbral del otro
    ensamble = cuantil de sus probabilidades de validacion al mismo nivel q que ocupa theta del ensamble principal en su
    propia validacion. Pila ENS13 y ENS12: co-firma de ENS12U; pila ENS12U: co-firma de ENS13.
E11 Regimen de BTC: cierre de BTC > SMA de 30 dias (2880 velas), causal, ademas de la pila.
Registro: 2.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H, C, R, V = E.B, E.H, E.C, E.R, E.V


def same_selectivity_thr(Dm, Do):
    """Umbral por fila del ensamble Do con la misma selectividad que theta de Dm (en validacion)."""
    thr = np.full(len(Do["rows"]), np.inf)
    for k in range(6):
        vm, vo = Dm["vals"][k], Do["vals"][k]
        if not np.isfinite(vm["thr"]):
            continue
        q = float(np.mean(vm["p"] < vm["thr"]))
        thr[Do["fold"] == k] = float(np.quantile(vo["p"], q))
    return thr


def run(ens, other, Dcache):
    D = Dcache[ens]; Do = Dcache[other]
    assert np.array_equal(D["rows"], Do["rows"])
    ref = E.trade_table(D, D["stack"], D["A"] >= 1)
    res = {"pila": dict(summary=E.summ(ref, "pila v2 + A≥1"))}
    thr_o = same_selectivity_thr(D, Do)
    agree = Do["p"] >= thr_o
    lab = f"E10 co-firma de {other} (misma selectividad)"
    t = E.trade_table(D, D["stack"] & agree, D["A"] >= 1)
    r = E.summ(t, lab); c = E.compare(t, ref)
    res[lab] = dict(summary=r, compare=c)
    bt, up = V.btc_regime(0)
    j = np.minimum(np.searchsorted(bt, D["t"]), len(bt) - 1)
    reg = (bt[j] == D["t"]) & up[j]
    lab2 = "E11 BTC > SMA 30 d"
    t2 = E.trade_table(D, D["stack"] & reg, (D["A"] >= 1) & reg)
    r2 = E.summ(t2, lab2); c2 = E.compare(t2, ref)
    res[lab2] = dict(summary=r2, compare=c2)
    for lb, rr, cc in ((lab, r, c), (lab2, r2, c2)):
        print(ens, lb, rr["n"], f"{rr['wr']*100:.1f}", f"{rr['E_pct']:+.2f}", f"dWR {cc['dWR']*100:+.1f} dE {cc['dE']:+.2f} "
              f"P {cc['p_dWR_le0']:.2f}/{cc['p_dE_le0']:.2f} folds {cc['folds_imp']}", flush=True)
    return res


if __name__ == "__main__":
    Dc = {e: E.load(e) for e in ("ENS13", "ENS12", "ENS12U")}
    res = {"ENS13": run("ENS13", "ENS12U", Dc), "ENS12": run("ENS12", "ENS12U", Dc), "ENS12U": run("ENS12U", "ENS13", Dc)}
    E.log_once("extra", 2, "R2-E10 co-firma de otro ensamble (misma selectividad); R2-E11 BTC > SMA30d")
    E.jdump(res, os.path.join(E.OUT2, "be2_extra.json"))
    ens_list = list(res)
    L = ["# R2-E10/E11 co-firma de otro ensamble y régimen de BTC\n", E.HEAD, E.HEAD2]
    labs = [k for k in res["ENS13"]]
    keymap = lambda ens, lab: lab if lab in res[ens] else [k for k in res[ens] if k.startswith(lab[:4])][0]
    for lab in labs:
        for ens in ens_list:
            k = keymap(ens, lab)
            L.append(E.row(ens, res[ens][k]["summary"], res[ens][k].get("compare")))
    L.append("")
    for lab in labs[1:]:
        ok, why = E.candidate({ens: res[ens][keymap(ens, lab)]["compare"] for ens in ens_list})
        L.append(f"- {lab}: {'CANDIDATA' if ok else 'no'} — {why}")
        for ens in ens_list:
            k = keymap(ens, lab)
            L.append(E.detail(ens, res[ens][k]["summary"], res[ens][k]["compare"]))
    with open(os.path.join(E.OUT2, "be2_extra.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
