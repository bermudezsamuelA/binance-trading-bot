"""R2-E13/E14 (DISENO). Ideas anadidas por el laboratorio (pre-registro escrito antes de correr):

E13 Panico aislado en el tiempo: la volatilidad se agrupa; los panicos en racha (poco tiempo desde el episodio de mercado
    anterior) suelen ser cambios de regimen que rebotan menos. Regla: la pila solo si el episodio de mercado actual empezo
    >= 3 dias (288 velas) despues del final (ultima senal) del episodio anterior. Episodio como en R2-E2 (hueco > 48 velas).
E14 Umbral elegido en VALIDACION ya con la compuerta: en cada pliegue se aplica la regla v2 (max E con WR_val >= w) solo a
    las velas de validacion con A >= 1 (compuerta calculada en validacion). w in {0.75, 0.80}. Si la validacion con
    compuerta no cumple los minimos (150 velas, 15 dias), se usa theta v2 del pliegue.
Registro: 3.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H, C, R, V = E.B, E.H, E.C, E.R, E.V


def episode_gap_ok(D, min_gap=288):
    S = E.to_grid(D, D["sig"], False, bool)
    anyb = np.where(S.any(0))[0]
    N = len(D["tg"])
    okg = np.zeros(N, bool)
    starts = [0] + [k for k in range(1, len(anyb)) if anyb[k] - anyb[k - 1] > E.W] + [len(anyb)]
    prev_end = -10 ** 9
    for e in range(len(starts) - 1):
        bars = anyb[starts[e]:starts[e + 1]]
        gap = bars[0] - prev_end
        if gap >= min_gap:
            okg[bars[0]:min(N, bars[-1] + E.W + 1)] = True
        prev_end = bars[-1]
    return okg[D["jrow"]]


def gated_val_thr(D, wr_min):
    N = len(D["tg"])
    thr = D["thr"].copy()
    used = []
    for k in range(6):
        v = D["vals"][k]
        if not np.isfinite(v["thr"]):
            used.append(None); continue
        j = np.searchsorted(D["tg"], v["t"])
        S = np.zeros((4, N), bool); S[v["ci"], j] = v["p"] >= v["thr"]
        per = E.roll_any(S, E.W)
        A = per.sum(0)[j] - per[v["ci"], j]
        g = A >= 1
        ch = V.choose(v["p"][g], v["netX"][g], (v["t"][g] // B.DAY), wr_min) if g.sum() > 0 else None
        if ch is None:
            used.append(("fallback", float(v["thr"]), int(g.sum())))
            continue
        thr[D["fold"] == k] = ch[0]
        used.append(("gated", float(ch[0]), float(v["thr"]), int(g.sum())))
    return thr, used


def run(ens):
    D = E.load(ens)
    ref = E.trade_table(D, D["stack"], D["A"] >= 1)
    res = {"pila": dict(summary=E.summ(ref, "pila v2 + A≥1"))}
    ok = episode_gap_ok(D)
    lab = "E13 episodio ≥ 3 días después del anterior"
    t = E.trade_table(D, D["stack"] & ok, (D["A"] >= 1) & ok)
    res[lab] = dict(summary=E.summ(t, lab), compare=E.compare(t, ref))
    for w in (0.75, 0.80):
        thr, used = gated_val_thr(D, w)
        sig2 = D["p"] >= thr
        A2 = E.gate_count(D, sig2)
        m = sig2 & (A2 >= 1)
        lab2 = f"E14 θ elegido en validación con compuerta (WR_val ≥ {w:.2f})"
        t2 = E.trade_table(D, m, A2 >= 1)
        res[lab2] = dict(summary=E.summ(t2, lab2), compare=E.compare(t2, ref), thr_used=used)
    for lb, o in res.items():
        if lb == "pila":
            continue
        r, c = o["summary"], o["compare"]
        if r.get("n"):
            print(ens, lb, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} "
                  f"P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", o.get("thr_used", ""), flush=True)
    return res


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    res = {ens: run(ens) for ens in ens_list}
    E.log_once("extra2", 3, "R2-E13 episodio aislado >= 3 dias; R2-E14 theta elegido en validacion con compuerta (0.75, 0.80)")
    E.jdump(res, os.path.join(E.OUT2, "be2_extra2.json"))
    L = ["# R2-E13/E14 episodio aislado en el tiempo y θ elegido con la compuerta en validación\n", E.HEAD, E.HEAD2]
    labs = list(res[ens_list[0]].keys())
    for lab in labs:
        for ens in ens_list:
            L.append(E.row(ens, res[ens][lab]["summary"], res[ens][lab].get("compare")))
    L.append("")
    for lab in labs[1:]:
        ok, why = E.candidate({ens: res[ens][lab]["compare"] for ens in ens_list})
        L.append(f"- {lab}: {'CANDIDATA' if ok else 'no'} — {why}")
        for ens in ens_list:
            L.append(E.detail(ens, res[ens][lab]["summary"], res[ens][lab]["compare"]))
            if "thr_used" in res[ens][lab]:
                L.append(f"  - θ por pliegue: {res[ens][lab]['thr_used']}")
    with open(os.path.join(E.OUT2, "be2_extra2.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
