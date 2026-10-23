"""R2-E4 Re-entrada en el mismo episodio tras cerrar por TP (DISENO). Pre-registro (escrito antes de correr):

Pila: p >= theta y A(W=48) >= 1, salida X5, una posicion por moneda. La pila ya re-entra si aparece una senal NUEVA
(p >= theta) despues de la salida. La regla nueva anade: tras una salida por TP en la vela e, entrar en la primera vela
b > e (del mismo pliegue) en la que la senal propia siga "activa" (alguna vela con p >= theta en las ultimas L velas)
y la compuerta siga abierta (A >= 1). L in {48, 16}. Se itera la simulacion hasta que el conjunto de entradas no cambia.
Se registran 2 configuraciones.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H = E.B, E.H


def reentry_mask(D, Lw, max_iter=8):
    N = len(D["tg"])
    S = E.to_grid(D, D["sig"], False, bool)
    lat = E.roll_any(S, Lw)
    Ag = E.to_grid(D, D["A"], 0, int)
    ok_g = lat & (Ag >= 1)
    fold_g = E.to_grid(D, D["fold"], -1, int)
    row_g = E.to_grid(D, np.arange(len(D["rows"])), -1, int)
    mask = D["stack"].copy()
    added = set()
    for it in range(max_iter):
        T, syms = B.simulate_entries(D, mask)
        new = 0
        for k in range(len(T)):
            if T.reason[k] != 0:
                continue
            i = H.SYMBOLS.index(syms[k])
            e = int(T.exit_idx[k]); f = fold_g[i, int(T.sig_idx[k])]
            b = e + 1
            while b < N and fold_g[i, b] == f and b <= e + Lw:
                if ok_g[i, b]:
                    r = row_g[i, b]
                    if r >= 0 and not mask[r]:
                        mask[r] = True; added.add(int(r)); new += 1
                    break
                b += 1
        if new == 0:
            break
    return mask, added


def run(ens):
    D = E.load(ens)
    ref = E.trade_table(D, D["stack"], D["A"] >= 1)
    res = {"pila": dict(summary=E.summ(ref, "pila v2 + A≥1"))}
    for Lw in (48, 16):
        mask, added = reentry_mask(D, Lw)
        t = E.trade_table(D, mask, D["A"] >= 1)
        lab = f"Re-entrada tras TP, señal activa L={Lw}"
        r = E.summ(t, lab); c = E.compare(t, ref)
        # operaciones de re-entrada (vela de senal sin p >= theta)
        rowg = E.to_grid(D, np.arange(len(D["rows"])), -1, int)
        rr = rowg[t["sidx"], t["sig_idx"]]
        isre = ~D["sig"][rr]
        sub = E.summ(E.sub_table(t, isre), f"solo re-entradas L={Lw}") if isre.any() else dict(n=0, label="solo re-entradas")
        res[lab] = dict(summary=r, compare=c, reentries=sub, n_added_rows=len(added))
        print(ens, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} "
              f"P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", "| re-entradas", sub.get("n"),
              f"{sub.get('wr', float('nan'))*100:.1f}", f"{sub.get('E_pct', float('nan')):+.2f}", flush=True)
    return res


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    res = {ens: run(ens) for ens in ens_list}
    E.log_once("reentry", 2, "R2-E4 re-entrada tras TP con senal activa (L=48, 16) y compuerta abierta")
    E.jdump(res, os.path.join(E.OUT2, "be2_reentry.json"))
    L = ["# R2-E4 re-entrada tras TP en el mismo episodio\n", E.HEAD, E.HEAD2]
    labs = list(res[ens_list[0]].keys())
    for lab in labs:
        for ens in ens_list:
            L.append(E.row(ens, res[ens][lab]["summary"], res[ens][lab].get("compare")))
            if "reentries" in res[ens][lab]:
                L.append(E.row(ens, res[ens][lab]["reentries"]))
    L.append("")
    for lab in labs[1:]:
        ok, why = E.candidate({ens: res[ens][lab]["compare"] for ens in ens_list})
        L.append(f"- {lab}: {'CANDIDATA' if ok else 'no'} — {why}")
        for ens in ens_list:
            L.append(E.detail(ens, res[ens][lab]["summary"], res[ens][lab]["compare"]))
    with open(os.path.join(E.OUT2, "be2_reentry.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
