"""R2A reglas de SELECCION del Investigador B (DISENO). Pre-registro (copiado de investigador_B.md, escrito antes de correr):

H1  (CONTAMINADA, exploratoria; regla de EPISODIO) Filtro de rezagados: L = fraccion de las OTRAS 3 anclas con
    c >= min(l, 16) + 1 sigma de 4 h (c * sigma15 * 4). Regla: pila y L < 1 (saltar si las 3 otras ya rebotaron).
    Control al reves (no decide): pila y L > 0 (saltar si L = 0). Azar condicionado: A >= 1 y la condicion de L.
H6  (regla de EPISODIO) Funding previo: f_pre = funding_z_2016 en la vela ii - 96 (24 h antes). Saltar si f_pre esta en el
    tercil inferior; corte = cuantil 1/3 de f_pre en las velas de VALIDACION con p >= theta y A_val >= 1 del pliegue.
H7  (regla DENTRO del episodio) Divergencia transversal en futuros: z transversal entre las 4 anclas (misma vela) de
    oi_chg_16 y fut_taker_4; D_i = |z_oi| + |z_taker|. Saltar si D_i > percentil 80 de D en las velas de validacion con
    p >= theta y A_val >= 1.
H10 (regla DENTRO del episodio) Co-firma del ensamble G5 (lgbv4_G5_f1_s0 + mlpv4_G5_f1_s0): Platt en validacion contra la
    etiqueta G5, theta_G5 con la regla v2 (max E con WR_val >= 0.75 sobre la salida X5, con la misma purga). Exigir
    p_G5 >= theta_G5 en la vela de entrada; si un pliegue no tiene theta_G5, la regla no actua en ese pliegue.
Bases: pila X5 (H 288) y pila con H 384 (E7). Ensambles ENS13, ENS12, ENS12U. Bootstrap por episodio.
Registro (antes de correr): H1 1 + control 1, H6 1, H7 1, H10 1 = 5 reglas x 2 bases = 10.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2b_common as K
B, H, C, R, V = E.B, E.H, E.C, E.R, E.V

E.log_once("r2a_sel", 10, "R2A seleccion: H1 rezagados L<1 (+control L>0), H6 funding previo, H7 divergencia OI/taker, H10 co-firma G5; x2 bases (X5, H384)")


def Xcol(D, name, lag=0):
    names = list(D["cache"]["BTCUSDT"]["names"])
    j = names.index(name)
    G = np.array([D["cache"][s]["X"][:, j] for s in H.SYMBOLS], float)
    if lag:
        G = np.concatenate([np.full((4, lag), np.nan), G[:, :-lag]], 1)
    return G


def val_gated_rows(D, k):
    v = D["vals"][k]
    N = len(D["tg"])
    j = np.searchsorted(D["tg"], v["t"])
    sigv = v["p"] >= v["thr"]
    S = np.zeros((4, N), bool); S[v["ci"], j] = sigv
    per = E.roll_any(S, E.W)
    A = per.sum(0)[j] - per[v["ci"], j]
    g = sigv & (A >= 1)
    return v["ci"][g], j[g]


def fold_cut(D, G, q):
    cut = np.full(len(D["rows"]), np.nan)
    for k in range(6):
        ci, j = val_gated_rows(D, k)
        vals = G[ci, j]
        vals = vals[np.isfinite(vals)]
        if len(vals):
            cut[D["fold"] == k] = np.quantile(vals, q)
    return cut


def g5_cosign(D):
    tags = ["lgbv4_G5_f1_s0", "mlpv4_G5_f1_s0"]
    P = [np.load(os.path.join(R.PRED, f"{t}.npz")) for t in tags]
    if "net" in P[0].files:
        yG5 = (P[0]["net"] > 0).astype(float)
    else:
        yG5 = (np.concatenate([D["cache"][s]["net_G5"] for s in H.SYMBOLS]) > 0).astype(float)
    netX = np.concatenate([D["cache"][s]["net_X5"] for s in H.SYMBOLS])
    t_all = np.concatenate([D["cache"][s]["t"] for s in H.SYMBOLS]).astype(np.int64)
    out = np.zeros(len(D["rows"]), bool); act = np.zeros(len(D["rows"]), bool); thr_used = []
    for k in range(6):
        vr, tr_ = P[0][f"f{k}_val_rows"], P[0][f"f{k}_tst_rows"]
        pv = np.zeros(len(vr)); pt = np.zeros(len(tr_))
        for p in P:
            ab = R.platt_fit(p[f"f{k}_val_s"], yG5[vr])
            pv += R.platt_apply(p[f"f{k}_val_s"], ab) / len(P)
            pt += R.platt_apply(p[f"f{k}_tst_s"], ab) / len(P)
        okv = np.isfinite(netX[vr]) & (t_all[vr] < t_all[tr_].min() - (288 + 1) * C.MS15)
        ch = V.choose(pv[okv], netX[vr][okv], (t_all[vr] // B.DAY)[okv], 0.75)
        m = D["fold"] == k
        pos = {int(r): i for i, r in enumerate(tr_)}
        idx = np.array([pos.get(int(r), -1) for r in D["rows"][m]])
        ptk = np.where(idx >= 0, pt[np.maximum(idx, 0)], -np.inf)
        if ch is None:
            out[m] = True; thr_used.append(None)
        else:
            out[m] = ptk >= ch[0]; act[m] = True; thr_used.append(float(ch[0]))
    return out, thr_used


def run(ens):
    D = E.load(ens)
    g1 = D["A"] >= 1
    bases = K.bases(D)
    reb = K.anchors_rebound(D)
    L = K.others_frac(D, reb)
    fz = Xcol(D, "funding_z_2016", lag=96)
    f_pre = E.from_grid(D, fz)
    cut6 = fold_cut(D, fz, 1 / 3)
    oi = Xcol(D, "oi_chg_16"); tk = Xcol(D, "fut_taker_4")
    zf = lambda G: (G - G.mean(0)) / (G.std(0) + 1e-12)
    Dg = np.abs(zf(oi)) + np.abs(zf(tk))
    dv = E.from_grid(D, Dg)
    cut7 = fold_cut(D, Dg, 0.80)
    g5, thr5 = g5_cosign(D)
    rules = {
        "H1 rezagados: L < 1 (exploratoria, contaminada)": (L < 1, g1 & (L < 1), "episodio"),
        "H1 control al revés: L > 0": (L > 0, g1 & (L > 0), "episodio"),
        "H6 funding 24 h antes ≥ tercil inferior de val.": (f_pre >= cut6, g1 & (f_pre >= cut6), "episodio"),
        "H7 divergencia OI/taker ≤ p80 de val.": (dv <= cut7, g1 & (dv <= cut7), "dentro"),
        "H10 co-firma G5": (g5, g1, "dentro"),
    }
    res = {"_info": dict(thr_G5=thr5, frac_L1_stack=float(np.mean(L[D["stack"]] >= 1)))}
    for bname, (Dx, ref) in bases.items():
        rref = E.summ(ref, f"pila {bname}")
        res[f"pila {bname}"] = dict(summary=rref, bb=K.betabin_ci(ref), base=bname)
        for lab, (cond, gate, kind) in rules.items():
            t = E.trade_table(Dx, D["stack"] & cond, gate)
            r = E.summ(t, lab)
            c = K.compare_ep(t, ref)
            comp = E.trade_table(Dx, D["stack"] & ~cond, g1 & ~cond) if lab.startswith("H1 rez") or lab.startswith("H6") or lab.startswith("H7") else None
            res[f"{lab} [{bname}]"] = dict(summary=r, compare=c, bb=K.betabin_ci(t) if t is not None else None, base=bname,
                                         kind=kind, complement=E.summ(comp, "complemento") if comp is not None else None)
            print(ens, bname, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"cond {r.get('cond_wr', np.nan)*100:.1f}",
                  f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", flush=True)
    return res


if __name__ == "__main__":
    ens_list = ["ENS13", "ENS12", "ENS12U"]
    res = {e: run(e) for e in ens_list}
    E.jdump(res, os.path.join(K.OUT2, "be2b_sel.json"))
    L_ = ["# R2A reglas de selección del Investigador B (H1, H6, H7, H10)\n",
          f"Umbrales G5 por pliegue (ENS13): {res['ENS13']['_info']['thr_G5']}; fracción de operaciones-vela de la pila con L = 1 (ENS13): {res['ENS13']['_info']['frac_L1_stack']:.2f}\n",
          K.HEAD, K.HEAD2]
    keys = [k for k in res["ENS13"] if k != "_info"]
    for k in keys:
        for e in ens_list:
            o = res[e][k]
            L_.append(K.row(e, o["base"], o["summary"], o.get("compare"), o.get("bb")))
    L_.append("\n## Tamiz (criterio del laboratorio con bootstrap por episodio + azar condicionado ≤ 1/2 de la mejora)\n")
    for k in keys:
        if k.startswith("pila"):
            continue
        base = res["ENS13"][k]["base"]
        cmp_by = {e: res[e][k]["compare"] for e in ens_list}
        ok, why = K.screen(res["ENS13"][k]["summary"], res["ENS13"][f"pila {base}"]["summary"], res["ENS13"][k]["compare"], cmp_by)
        L_.append(f"- {k} ({res['ENS13'][k]['kind']}): {'PASA' if ok else 'no'} — {why}")
        comp = res["ENS13"][k].get("complement")
        if comp and comp.get("n"):
            L_.append(f"  - complemento ENS13: n {comp['n']}, WR {comp['wr']*100:.1f} %, E {comp['E_pct']:+.2f} %")
        for e in ens_list:
            L_.append("  " + E.detail(e, res[e][k]["summary"], res[e][k]["compare"]))
    with open(os.path.join(K.OUT2, "be2b_sel.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L_) + "\n")
