"""R2A tabla resumen (lee los JSON de be2b_*) y pila v3 re-medida UNA vez con bootstrap por episodio e IC beta-binomial.
La combinacion pre-especificada (mejor seleccion + mejor salida + H 384) solo se arma si cada pieza paso su tamiz; si
ninguna pasa, la pila v3 sigue siendo pila + H 384 y aqui solo se re-mide con la estadistica de esta ronda.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2b_common as K

ENS = ["ENS13", "ENS12", "ENS12U"]
J = lambda f: json.load(open(os.path.join(K.OUT2, f), encoding="utf-8"))
KIND = {"H1": "episodio", "H6": "episodio", "H4": "selección (mixta)", "H7": "dentro", "H10": "dentro", "H2": "dentro",
        "H3": "dentro", "D2": "dentro", "H5": "dentro", "H8": "dentro", "H9": "dentro", "geo": "dentro (control)"}


def verdict(res, k):
    base = res["ENS13"][k]["base"]
    rn, rb = res["ENS13"][k]["summary"], res["ENS13"][f"pila {base}"]["summary"]
    c = res["ENS13"][k]["compare"]
    cmp_by = {e: res[e][k]["compare"] for e in ENS if res[e][k].get("compare")}
    ok, why = E.candidate(cmp_by)
    if "cond_wr_same_exit" in rn:
        frac = (rn["cond_wr_same_exit"] - rb["cond_wr_same_exit"]) / c["dWR"] if c["dWR"] > 0 else float("nan")
    elif "cond_wr" in rn and "cond_wr" in rb and c["dWR"] > 0:
        frac = (rn["cond_wr"] - rb["cond_wr"]) / c["dWR"]
    else:
        frac = float("nan")
    ok = ok and (not np.isfinite(frac) or frac <= 0.5)
    rep = sum(1 for e in ENS if res[e][k].get("compare") and np.isfinite(res[e][k]["compare"].get("dWR", np.nan))
              and res[e][k]["compare"]["dWR"] > 0 and res[e][k]["compare"]["dE"] >= 0)
    return ok, frac, rep


rows = []
for f in ("be2b_sel.json", "be2b_h2.json", "be2b_h3.json", "be2b_h4h5.json", "be2b_h8h9.json"):
    res = J(f)
    for k in res["ENS13"]:
        if k.startswith("pila") or k.startswith("diag") or k.startswith("_"):
            continue
        o = res["ENS13"][k]; r, c, bb = o["summary"], o["compare"], o.get("bb")
        if not r.get("n"):
            continue
        ok, frac, rep = verdict(res, k)
        tag = k.split()[0] if k.split()[0] in KIND else ("geo" if k.startswith("geometr") else k.split()[0])
        reps = " ; ".join(f"{res[e][k]['compare']['dWR']*100:+.1f} / {res[e][k]['compare']['dE']:+.2f}"
                          if res[e][k].get("compare") and np.isfinite(res[e][k]["compare"].get("dWR", np.nan)) else "–" for e in ("ENS12", "ENS12U"))
        bbs = f"{bb['mu']*100:.1f} [{bb['lo']*100:.1f}, {bb['hi']*100:.1f}]" if bb else "–"
        rows.append(f"| {k.rsplit(' [', 1)[0]} | {o['base']} | {KIND.get(tag, '?')} | {r['n']} | {r['wr']*100:.1f} [{r['wr_lo']*100:.1f}, {r['wr_hi']*100:.1f}] | {bbs} | "
                    f"{r['E_pct']:+.2f} | {r['E_R']:+.3f} | {r['t_day']:.2f} | {r['rand_wr']*100:.1f} / {r['rand_E']:+.2f} | "
                    + (f"{r['cond_wr_same_exit']*100:.1f} / {r['cond_E_same_exit']:+.2f}" if "cond_wr_same_exit" in r else
                       (f"{r['cond_wr']*100:.1f} / {r['cond_E']:+.2f}" if "cond_wr" in r else "–"))
                    + f" | {c['dWR']*100:+.1f} / {c['dE']:+.2f} | {c['p_dWR_le0']:.2f} / {c['p_dE_le0']:.2f} | {c['folds_imp']}/6 (={c['folds_tie']}) | "
                    f"{r['n_ep']} | {reps} | {frac*100:.0f} % |".replace("nan %", "–") + f" {'PASA' if ok else 'no'} |")

head = ("| Regla | Base | Tipo | n | WR % [Wilson] | WR beta-bin. [IC 95] | E % | E_R | t día | Azar WR/E | Azar cond. (regla) WR/E | "
        "ΔWR / ΔE vs base | P(ΔWR≤0) / P(ΔE≤0) boot. episodio | pliegues mejor (=) | episodios | réplica ENS12 ; ENS12U (ΔWR / ΔE) | "
        "azar explica % de ΔWR | tamiz |")
sep = "|" + "---|" * 18

# pila v3 re-medida
v3 = []
for e in ENS:
    D = E.load(e)
    bs = K.bases(D)
    t0, t1 = bs["X5"][1], bs["H384"][1]
    r0, r1 = E.summ(t0, "pila X5"), E.summ(t1, "pila v3 = pila + H 384")
    c = K.compare_ep(t1, t0)
    b0, b1 = K.betabin_ci(t0), K.betabin_ci(t1)
    v3.append((e, r0, b0, None))
    v3.append((e, r1, b1, c))
E.jdump(dict(v3=[(e, r, b, c) for e, r, b, c in v3]), os.path.join(K.OUT2, "be2b_final.json"))
out = ["## Tabla resumen R2A (fila principal ENS13)\n", head, sep] + rows + ["", "## Pila v3 re-medida (bootstrap por episodio, IC beta-binomial)\n", K.HEAD, K.HEAD2]
for e, r, b, c in v3:
    out.append(K.row(e, "X5" if c is None else "H384", r, c, b))
print("\n".join(out))
with open(os.path.join(K.OUT2, "be2b_final_tables.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
