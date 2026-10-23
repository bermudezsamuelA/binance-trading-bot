"""R2A H2 TP anclado a la brecha hasta el maximo de 24 h (DISENO; regla DENTRO del episodio). Pre-registro
(copiado de investigador_B.md, escrito antes de correr):

g_i = -dd_96 = -ln(c / max(h, 96)) / (sigma15 sqrt(96))  (en s_d).  a_i = clip(0.5 g_i, 0.35, 1.2);
TP_i = c_i (1 + a_i s_d), SL = c (1 - 1.75 s_d), H = 288 (base X5) o 384 (base E7). Senales de la pila sin cambios.
Configuraciones: (1) principal; (2) principal con theta re-elegido SOLO en validacion con la nueva etiqueta (regla v2:
max E con WR_val >= 0.75) y la compuerta recalculada con las nuevas senales; (3) sensibilidad, factor 0.6 (no decide).
Comparaciones: X5 sobre las mismas entradas; azar condicionado (A >= 1) con la MISMA salida anclada; geometria FIJA con
el a medio de la regla en las entradas de la pila (para separar "anclaje" de "TP mas chico"); diagnostico por tercil de g
(mismas entradas de la pila X5: resultado X5 frente a la etiqueta por vela con la salida anclada).
Registro (antes de correr): 4 (principal, theta re-elegido, sensibilidad, a fijo) x 2 bases = 8.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2b_common as K
B, H, C, R, V = E.B, E.H, E.C, E.R, E.V

E.log_once("r2a_h2", 8, "R2A H2 TP anclado a la brecha clip(f*g,0.35,1.2) f=0.5 (+theta re-elegido en val), f=0.6 sensib., a fijo medio; x2 bases")


def barriers(f, Hh):
    tp, sl, a_all = {}, {}, []
    for s in H.SYMBOLS:
        S = K.spot(s)
        sd = S["s15"] * np.sqrt(96)
        a = np.clip(f * K.gap_g(s), 0.35, 1.2)
        tp[s] = S["c"] * (1 + a * sd)
        sl[s] = S["c"] * (1 - 1.75 * sd)
        a_all.append(a)
    return tp, sl, np.concatenate(a_all)


def rechoose_theta(D, net_all, Hh):
    thr = D["thr"].copy(); used = []
    t_all = np.concatenate([D["cache"][s]["t"] for s in H.SYMBOLS]).astype(np.int64)
    for k in range(6):
        v = D["vals"][k]
        if not np.isfinite(v["thr"]):
            used.append(None); continue
        t0 = H.ms(*B.TESTS[k][0], 1)
        nv = net_all[v["rows"]]
        ok = np.isfinite(nv) & (v["t"] < t0 - (Hh + 1) * C.MS15)
        ch = V.choose(v["p"][ok], nv[ok], (v["t"][ok] // B.DAY), 0.75)
        if ch is None:
            used.append(("sin cambio", float(v["thr"]))); continue
        thr[D["fold"] == k] = ch[0]; used.append((float(ch[0]), float(v["thr"])))
    return thr, used


def run(ens):
    D = E.load(ens)
    g1 = D["A"] >= 1
    bases = K.bases(D)
    res = {}
    gall = np.concatenate([K.gap_g(s) for s in H.SYMBOLS])
    for bname, (Dbase, ref) in bases.items():
        Hh = 288 if bname == "X5" else 384
        res[f"pila {bname}"] = dict(summary=E.summ(ref, f"pila {bname}"), bb=K.betabin_ci(ref), base=bname)
        # medias de a en las entradas de la pila (para la geometria fija)
        _, _, a_all = barriers(0.5, Hh)
        rows_ref = np.array([np.where((D["ci"] == si) & (D["ii"] == bi))[0][0] for si, bi in zip(ref["sidx"], ref["sig_idx"])])
        a_bar = round(float(np.nanmean(a_all[D["rows"][rows_ref]])), 2)
        for f, lab in ((0.5, "H2 principal (f = 0.5)"), (0.6, "H2 sensibilidad (f = 0.6)")):
            tp, sl, _ = barriers(f, Hh)
            Dx = K.with_barriers(D, tp, sl, Hh, f"h2f{int(f*100)}_{Hh}")
            t = K.trade_table_arr(Dx, D["stack"], g1)
            r = E.summ(t, lab); c = K.compare_ep(t, ref)
            res[f"{lab} [{bname}]"] = dict(summary=r, compare=c, bb=K.betabin_ci(t), base=bname, kind="dentro")
            print(ens, bname, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"cond {r['cond_wr']*100:.1f}/{r['cond_E']:+.2f}",
                  f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", flush=True)
            if f == 0.5:
                # theta re-elegido con la nueva etiqueta (solo validacion)
                net_all = np.concatenate([np.load(os.path.join(E.GCACHE, f"{s}_h2f50_{Hh}.npz"))["net"] for s in H.SYMBOLS])
                thr2, used = rechoose_theta(D, net_all, Hh)
                sig2 = D["p"] >= thr2
                A2 = E.gate_count(D, sig2)
                t2 = K.trade_table_arr(Dx, sig2 & (A2 >= 1), A2 >= 1)
                lab2 = "H2 con θ re-elegido en validación"
                r2 = E.summ(t2, lab2); c2 = K.compare_ep(t2, ref)
                res[f"{lab2} [{bname}]"] = dict(summary=r2, compare=c2, bb=K.betabin_ci(t2), base=bname, kind="dentro", thr=used)
                print(ens, bname, lab2, r2["n"], f"{r2['wr']*100:.1f}", f"{r2['E_pct']:+.2f}", f"dWR {c2['dWR']*100:+.1f} dE {c2['dE']:+.2f}", used, flush=True)
                # diagnostico por tercil de g (mismas entradas de la pila)
                gx = gall[D["rows"][rows_ref]]
                lab_h2 = net_all[D["rows"][rows_ref]]
                qs = np.nanquantile(gx, [1 / 3, 2 / 3])
                diag = []
                for lo, hi, nm in ((-np.inf, qs[0], "g bajo"), (qs[0], qs[1], "g medio"), (qs[1], np.inf, "g alto")):
                    s_ = (gx >= lo) & (gx < hi) & np.isfinite(lab_h2)
                    diag.append((nm, int(s_.sum()), float(np.mean(ref["x"][s_] > 0)), float(ref["x"][s_].mean() * 100),
                                 float(np.mean(lab_h2[s_] > 0)), float(lab_h2[s_].mean() * 100)))
                res[f"diag {bname}"] = dict(cuts=[float(q) for q in qs], rows=diag, a_bar=a_bar)
        # geometria fija con el a medio
        Df = E.with_geom(D, a_bar, 1.75, Hh)
        tf = E.trade_table(Df, D["stack"], g1)
        labf = "geometría fija con el a medio (control de 'TP más chico')"
        rf = E.summ(tf, labf + f" a = {a_bar}"); cf = K.compare_ep(tf, ref)
        res[f"{labf} [{bname}]"] = dict(summary=rf, compare=cf, bb=K.betabin_ci(tf), base=bname, kind="dentro", a_bar=a_bar)
        print(ens, bname, labf, rf["n"], f"{rf['wr']*100:.1f}", f"{rf['E_pct']:+.2f}", f"dWR {cf['dWR']*100:+.1f} dE {cf['dE']:+.2f}", flush=True)
    return res


if __name__ == "__main__":
    ens_list = ["ENS13", "ENS12", "ENS12U"]
    res = {e: run(e) for e in ens_list}
    E.jdump(res, os.path.join(K.OUT2, "be2b_h2.json"))
    L = ["# R2A H2 TP anclado a la brecha hasta el máximo de 24 h\n", K.HEAD, K.HEAD2]
    keys = [k for k in res["ENS13"] if not k.startswith("diag")]
    for k in keys:
        for e in ens_list:
            o = res[e][k]
            L.append(K.row(e, o["base"], o["summary"], o.get("compare"), o.get("bb")))
    L.append("\n## Tamiz\n")
    for k in keys:
        if k.startswith("pila"):
            continue
        base = res["ENS13"][k]["base"]
        ok, why = K.screen(res["ENS13"][k]["summary"], res["ENS13"][f"pila {base}"]["summary"], res["ENS13"][k]["compare"],
                           {e: res[e][k]["compare"] for e in ens_list})
        L.append(f"- {k}: {'PASA' if ok else 'no'} — {why}" + (f"; θ por pliegue {res['ENS13'][k].get('thr')}" if "thr" in res["ENS13"][k] else ""))
        for e in ens_list:
            L.append("  " + E.detail(e, res[e][k]["summary"], res[e][k]["compare"]))
    L.append("\n## Diagnóstico por tercil de g (mismas entradas de la pila X5; n, WR X5, E X5, WR anclado, E anclado)\n")
    for e in ens_list:
        for b in ("X5", "H384"):
            d = res[e][f"diag {b}"]
            L.append(f"- {e} base {b} (cortes g {d['cuts'][0]:.2f} / {d['cuts'][1]:.2f}; a medio {d['a_bar']}): " + "; ".join(
                f"{nm}: {n} · {w0*100:.0f} % / {e0:+.2f} → {w1*100:.0f} % / {e1:+.2f}" for nm, n, w0, e0, w1, e1 in d["rows"]))
    with open(os.path.join(K.OUT2, "be2b_h2.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
