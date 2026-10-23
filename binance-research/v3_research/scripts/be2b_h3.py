"""R2A H3 TP reducido por ESTADO (DISENO; regla DENTRO del episodio). Pre-registro (copiado de investigador_B.md):

Salida X5 (base H = 288) o X5 con H = 384 (base E7). Desde la vela j >= entrada + 8 (2 h), al cierre de j se dispara si
(i) las otras 3 anclas estan rebotadas (L_j = 1, la misma definicion de H1) y (ii) c_j < entrada (1 + 0.35 s_d).
Desde la vela j + 1, TP2 = entrada * 1.006 (si la apertura ya supera TP2, se vende a la apertura). SL y H sin cambio.
Comparacion: D2 (mismo TP2, disparador por tiempo a las 36 h = 144 velas) con el mismo simulador; X5 / H 384.
Se reporta la fraccion de operaciones en que se dispara. Azar condicionado con la misma salida: 1 de cada 8 velas con A >= 1.
Registro (antes de correr): H3 x 2 bases + D2 con H 384 = 3.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2b_common as K
B, H, C, R = E.B, E.H, E.C, E.R

E.log_once("r2a_h3", 3, "R2A H3 TP2 +0.6% disparado por estado (3 anclas rebotadas y posicion < mitad del TP, desde 2 h); x2 bases; D2 con H384")


def make_exit(D, mode, Hh, Lg):
    bars = {s: R.coin_bars(s, len(D["cache"][s]["c"])) for s in H.SYMBOLS}
    sdv = {s: D["cache"][s]["s15"] * np.sqrt(96) for s in H.SYMBOLS}

    def ex(i, b, i1):
        s = H.SYMBOLS[i]; Bs = bars[s]
        entry = float(Bs.c[b]); sd = float(sdv[s][b])
        if not np.isfinite(sd):
            return None
        tp, sl = entry * (1 + 0.7 * sd), entry * (1 - 1.75 * sd)
        last = min(b + Hh, i1 - 1)
        if last < b + 1:
            return None
        k = np.arange(b + 1, last + 1)
        hs = Bs.l[k] <= sl; ht = Bs.h[k] >= tp
        hit = hs | ht
        kb = int(np.argmax(hit)) if hit.any() else None
        if mode == "state":
            trig = (k >= b + 8) & (Lg[i, k] >= 1) & (Bs.c[k] < entry * (1 + 0.35 * sd))
        elif mode == "time":
            trig = k >= b + 144
        else:
            trig = np.zeros(len(k), bool)
        kt = int(np.argmax(trig)) if trig.any() else None
        if kb is not None and (kt is None or kb <= kt):
            j = int(k[kb])
            if hs[kb]:
                return j, min(sl, float(Bs.o[j])), H.SL, entry, sl, False
            return j, tp, H.TP, entry, sl, False
        if kt is not None:
            jt = int(k[kt]); tp2 = entry * 1.006
            j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, jt + 1, i1, entry, tp2, sl, None, b + Hh - jt)
            if j < jt + 1:  # fin del pliegue justo en la vela del disparo
                return jt, float(Bs.c[jt]), H.END, entry, sl, True
            if why == H.TP and j == jt + 1 and Bs.o[j] > tp2:
                px = float(Bs.o[j])
            return int(j), float(px), int(why), entry, sl, True
        if b + Hh <= i1 - 1:
            return b + Hh, float(Bs.c[b + Hh]), H.TIME, entry, sl, False
        return i1 - 1, float(Bs.c[i1 - 1]), H.END, entry, sl, False
    return ex


def sim(D, mask, ex):
    per = K.fold_periods(D)
    idx = np.where(mask)[0]
    idx = idx[np.lexsort((-D["p"][idx], D["jrow"][idx]))]
    busy = np.full(4, -1); out = []; fired = 0
    for r in idx:
        i = int(D["ci"][r]); b = int(D["ii"][r]); k = int(D["fold"][r])
        if busy[i] >= b:
            continue
        res = ex(i, b, per[(i, k)][1])
        if res is None:
            continue
        j, px, why, entry, sl, fr = res
        out.append((i, b, j, float(H.net_return(entry, px)), why, k, (entry - sl) / entry, int(D["t"][r])))
        fired += int(fr); busy[i] = j
    return out, fired


def rand_exit(D, ex, step=8):
    per = K.fold_periods(D)
    sel = np.where((D["A"] >= 1) & np.isfinite(D["netX"]))[0][::step]
    xs = []
    for r in sel:
        res = ex(int(D["ci"][r]), int(D["ii"][r]), per[(int(D["ci"][r]), int(D["fold"][r]))][1])
        if res is None:
            continue
        xs.append(float(H.net_return(res[3], res[1])))
    x = np.array(xs)
    return float(np.mean(x > 0)), float(x.mean() * 100), len(x)


def run(ens):
    D = E.load(ens)
    g1 = D["A"] >= 1
    Lg = K.anchors_rebound(D)
    Lo = (Lg.sum(0)[None, :] - Lg) / 3.0  # fraccion de las otras 3, por moneda y vela
    res = {}
    for bname, Hh in (("X5", 288), ("H384", 384)):
        ref = None
        for mode, lab in (("none", f"pila {bname} (simulador propio)"), ("state", "H3 TP2 por estado"), ("time", "D2 TP2 por tiempo (36 h)")):
            ex = make_exit(D, mode, Hh, Lo)
            rows, fired = sim(D, D["stack"], ex)
            t = K.table_from_list(D, rows, g1)
            r = E.summ(t, lab)
            rr = rand_exit(D, ex)
            r["cond_wr_same_exit"], r["cond_E_same_exit"], r["cond_n"] = rr
            if mode == "none":
                ref = t; c = None
                res[f"pila {bname}"] = dict(summary=r, bb=K.betabin_ci(t), base=bname, fired=0)
            else:
                c = K.compare_ep(t, ref)
                res[f"{lab} [{bname}]"] = dict(summary=r, compare=c, bb=K.betabin_ci(t), base=bname, kind="dentro",
                                             fired=fired / max(1, r["n"]))
            print(ens, bname, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", "azar misma salida", rr,
                  "" if c is None else f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']} disparo {fired}/{r['n']}",
                  flush=True)
    return res


if __name__ == "__main__":
    ens_list = ["ENS13", "ENS12", "ENS12U"]
    res = {e: run(e) for e in ens_list}
    E.jdump(res, os.path.join(K.OUT2, "be2b_h3.json"))
    L = ["# R2A H3 TP2 disparado por estado frente a D2 (por tiempo)\n",
         "Azar condicionado con la MISMA salida: 1 de cada 8 velas con A ≥ 1 (WR %, E %, n), en la columna de notas.\n", K.HEAD, K.HEAD2]
    keys = list(res["ENS13"].keys())
    for k in keys:
        for e in ens_list:
            o = res[e][k]
            L.append(K.row(e, o["base"], o["summary"], o.get("compare"), o.get("bb")))
    L.append("\n## Tamiz (la fracción explicada por el azar usa el azar con la misma salida)\n")
    for k in keys:
        if k.startswith("pila"):
            continue
        base = res["ENS13"][k]["base"]
        cmp_by = {e: res[e][k]["compare"] for e in ens_list}
        ok, why = E.candidate(cmp_by)
        rn, rb = res["ENS13"][k]["summary"], res["ENS13"][f"pila {base}"]["summary"]
        frac = (rn["cond_wr_same_exit"] - rb["cond_wr_same_exit"]) / res["ENS13"][k]["compare"]["dWR"] if res["ENS13"][k]["compare"]["dWR"] > 0 else float("nan")
        ok = ok and (not np.isfinite(frac) or frac <= 0.5)
        L.append(f"- {k}: {'PASA' if ok else 'no'} — {why}; azar con la misma salida {rn['cond_wr_same_exit']*100:.1f} % / {rn['cond_E_same_exit']:+.2f} % "
                 f"frente a {rb['cond_wr_same_exit']*100:.1f} % / {rb['cond_E_same_exit']:+.2f} % (explica {frac*100:.0f} % de ΔWR); "
                 f"se dispara en " + ", ".join(f"{e} {res[e][k]['fired']*100:.0f} %" for e in ens_list))
        for e in ens_list:
            L.append("  " + E.detail(e, res[e][k]["summary"], res[e][k]["compare"]))
    with open(os.path.join(K.OUT2, "be2b_h3.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
