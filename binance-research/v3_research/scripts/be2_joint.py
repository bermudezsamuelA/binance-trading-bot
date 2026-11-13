"""R2-E7/E8/E9 (DISENO). Ideas anadidas por el laboratorio (pre-registro escrito antes de correr):

E8 Cortacircuitos tras SL (motivo: si un panico no rebota, las senales siguientes del mismo panico tienden a fallar juntas):
   CB_coin96 : tras una salida por SL de la moneda i en la vela e, no abrir i en (e, e+96].
   CB_mkt48  : tras CUALQUIER salida por SL en la vela e, no abrir ninguna moneda en (e, e+48].
E9 Tope de posiciones simultaneas (regla de riesgo de la seccion 3.3; aqui se mide su efecto en WR y E):
   MAX2 y MAX3; en la misma vela se prioriza el mayor p.
E7 Barrera de tiempo mas larga con a = 0.7 y m = 1.75 (OJO: idea sugerida al ver que 288 > 192 en la rejilla R2-E1, es
   decir, con la prueba; se elige H en walk-forward con los pliegues anteriores entre {192, 288, 384, 576}, pliegue 0 = 288).
Simulador conjunto por eventos con harness.resolve_exit (entrada al cierre, barreras desde la vela siguiente, una posicion
por moneda, salida nunca usa velas >= fin del pliegue); se verifica que reproduce la pila sin restricciones.
Registro: 4 (E8, E9) + 4 (E7: H in {192, 288, 384, 576} con un selector).
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H, C, R = E.B, E.H, E.C, E.R


def fold_periods(D):
    per = {}
    for k in range(6):
        for ci_ in range(4):
            m = (D["fold"] == k) & (D["ci"] == ci_)
            if m.any():
                per[(ci_, k)] = (int(D["ii"][m].min()), int(D["ii"][m].max()) + 1)
    return per


def joint_sim(D, mask, geom=(0.7, 1.75, 288), cb_coin=0, cb_mkt=0, maxpos=None, fee=H.FEE, slip=H.SLIP):
    a, m, Hh = geom
    bars = {s: R.coin_bars(s, len(D["cache"][s]["c"])) for s in H.SYMBOLS}
    sdv = {s: D["cache"][s]["s15"] * np.sqrt(96) for s in H.SYMBOLS}
    per = fold_periods(D)
    idx = np.where(mask)[0]
    order = np.lexsort((-D["p"][idx], D["jrow"][idx]))
    idx = idx[order]
    busy = np.full(4, -1)
    trades = []  # (ci, b, e, net, reason, fold, risk)
    for r in idx:
        i = int(D["ci"][r]); b = int(D["ii"][r]); k = int(D["fold"][r])
        if busy[i] >= b:
            continue
        if cb_coin and any(tr[0] == i and tr[4] == H.SL and tr[2] < b <= tr[2] + cb_coin for tr in trades):
            continue
        if cb_mkt and any(tr[4] == H.SL and tr[2] < b <= tr[2] + cb_mkt for tr in trades):
            continue
        if maxpos is not None and sum(1 for tr in trades if tr[1] < b <= tr[2]) >= maxpos:
            continue
        s = H.SYMBOLS[i]; Bs = bars[s]
        i0, i1 = per[(i, k)]
        entry = float(Bs.c[b]); sd = float(sdv[s][b])
        if not np.isfinite(sd):
            continue
        tp, sl = entry * (1 + a * sd), entry * (1 - m * sd)
        j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, b + 1, i1, entry, tp, sl, None, Hh)
        if why == H.END and j < b + 1:
            continue
        net = float(H.net_return(entry, px, fee, slip))
        trades.append((i, b, int(j), net, int(why), k, (entry - sl) / entry, int(D["t"][r])))
        busy[i] = j
    T = np.array([tr[:7] for tr in trades], float)
    et = np.array([tr[7] for tr in trades], np.int64)
    o = np.argsort(et, kind="stable")
    T, et = T[o], et[o]
    _, base = B.rand_base(D)
    cb = B.cond_base(D, D["A"] >= 1)
    sidx = T[:, 0].astype(int)
    key = sidx * 1_000_000 + B.month_of(et)
    tab = dict(x=T[:, 3], et=et, sidx=sidx, fold=T[:, 5].astype(int), reason=T[:, 4].astype(int),
               r_mult=T[:, 3] / T[:, 6], risk=T[:, 6], sig_idx=T[:, 1].astype(int), exit_idx=T[:, 2].astype(int),
               bw=np.array([base[int(kk)][0] for kk in key]), be=np.array([base[int(kk)][1] for kk in key]),
               cw=np.array([cb.get(int(kk), (np.nan, np.nan))[0] for kk in key]),
               ce=np.array([cb.get(int(kk), (np.nan, np.nan))[1] for kk in key]))
    return tab


def run(ens):
    D = E.load(ens)
    ref = E.trade_table(D, D["stack"], D["A"] >= 1)
    res = {"pila": dict(summary=E.summ(ref, "pila v2 + A≥1"))}
    chk = joint_sim(D, D["stack"])
    rc = E.summ(chk, "simulador conjunto sin restricciones (control)")
    res["control"] = dict(summary=rc, compare=E.compare(chk, ref))
    print(ens, "control", rc["n"], f"{rc['wr']*100:.1f}", f"{rc['E_pct']:+.3f}", "vs pila", res["pila"]["summary"]["n"],
          f"{res['pila']['summary']['E_pct']:+.3f}", flush=True)
    for lab, kw in (("CB_coin96 (sin la misma moneda 24 h tras SL)", dict(cb_coin=96)),
                    ("CB_mkt48 (sin entradas 12 h tras cualquier SL)", dict(cb_mkt=48)),
                    ("MAX2 posiciones simultáneas", dict(maxpos=2)),
                    ("MAX3 posiciones simultáneas", dict(maxpos=3))):
        t = joint_sim(D, D["stack"], **kw)
        r = E.summ(t, lab); c = E.compare(t, chk)
        res[lab] = dict(summary=r, compare=c)
        print(ens, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} "
              f"P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", flush=True)
    # E7: H en walk-forward
    tabs = {}
    for Hh in (192, 288, 384, 576):
        Dg = E.with_geom(D, 0.7, 1.75, Hh)
        tabs[Hh] = E.trade_table(Dg, D["stack"], D["A"] >= 1)
        r = E.summ(tabs[Hh], f"X5 con H={Hh} (descriptivo, toda la prueba)")
        res[f"H{Hh}"] = dict(summary=r, compare=E.compare(tabs[Hh], ref))
    pieces, chosen = [], []
    for k in range(6):
        if k == 0:
            hk = 288
        else:
            s5 = tabs[288]["fold"] < k
            e5 = tabs[288]["x"][s5].mean()
            best, bkey = 288, None
            for Hh, t in tabs.items():
                s = t["fold"] < k
                if not s.any() or t["x"][s].mean() < e5 - 1e-12:
                    continue
                key = (float(np.mean(t["x"][s] > 0)), float(t["x"][s].mean()))
                if bkey is None or key > bkey:
                    best, bkey = Hh, key
            hk = best
        chosen.append(hk)
        pieces.append(E.sub_table(tabs[hk], tabs[hk]["fold"] == k))
    comp = E.cat_tables(pieces)
    r = E.summ(comp, "E7 H elegido en WF (WR con guarda de E)")
    c = E.compare(comp, ref)
    res["E7 WF"] = dict(summary=r, compare=c, chosen=chosen)
    print(ens, "E7", chosen, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} "
          f"P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", flush=True)
    return res


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    res = {ens: run(ens) for ens in ens_list}
    E.log_once("joint", 8, "R2-E7/E8/E9 cortacircuitos tras SL (coin96, mkt48), tope de posiciones (2, 3), H en WF {192,288,384,576}")
    E.jdump(res, os.path.join(E.OUT2, "be2_joint.json"))
    L = ["# R2-E7/E8/E9 cortacircuitos, tope de posiciones y barrera de tiempo\n",
         "Las filas E8/E9 se comparan con el control del simulador conjunto (que reproduce la pila); E7 con la pila.\n",
         E.HEAD, E.HEAD2]
    labs = list(res[ens_list[0]].keys())
    for lab in labs:
        for ens in ens_list:
            L.append(E.row(ens, res[ens][lab]["summary"], res[ens][lab].get("compare") if lab != "control" else None))
    L.append("")
    for lab in labs[2:]:
        if lab.startswith("H"):
            continue
        ok, why = E.candidate({ens: res[ens][lab]["compare"] for ens in ens_list})
        L.append(f"- {lab}: {'CANDIDATA' if ok else 'no'} — {why}" + (f"; H elegidos {[res[e][lab]['chosen'] for e in ens_list]}" if lab == "E7 WF" else ""))
        for ens in ens_list:
            L.append(E.detail(ens, res[ens][lab]["summary"], res[ens][lab]["compare"]))
    with open(os.path.join(E.OUT2, "be2_joint.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
