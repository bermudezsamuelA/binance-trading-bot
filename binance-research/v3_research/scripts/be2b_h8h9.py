"""R2A H8 calibracion beta / theta con pesos por episodio y H9 recalibracion mensual de Platt (DISENO; reglas DENTRO del
episodio, porque cambian que velas pasan el umbral). Pre-registro (de investigador_B.md, escrito antes de correr):

H8a Calibracion beta (Kull et al. 2017) por miembro: z = puntaje crudo estandarizado con media y desviacion de validacion,
    q = sigmoide(z); regresion logistica (sin penalizar) de la etiqueta G3 sobre [ln q, -ln(1 - q)] en validacion;
    promedio de los miembros; theta con la regla v2.
H8b Platt como la v2, pero theta elegido con cada vela de validacion pesada por 1/n de su episodio (velas seleccionadas
    agrupadas en episodios con huecos <= 48 velas): WR_w >= 0.75, max E_w > 0, mismos minimos (150 velas, 15 dias).
H9  Platt re-ajustado al inicio del 2.o y 3.er mes de cada trimestre de prueba con la validacion del pliegue mas las velas de
    prueba con etiqueta ya cerrada (t < inicio del mes - 289 velas); theta fijo (el de la v2 del pliegue).
En todas: compuerta A >= 1 recalculada con las nuevas senales. Bases X5 y H 384. Bootstrap por episodio.
Registro (antes de correr): 3 x 2 bases = 6.
"""
import os, sys
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2b_common as K
B, H, C, R, V = E.B, E.H, E.C, E.R, E.V

E.log_once("r2a_h8h9", 6, "R2A H8a calibracion beta, H8b theta con pesos por episodio, H9 Platt mensual; x2 bases")


def _P(ens):
    tags, pdirs = E.ENSEMBLES[ens]
    out = []
    for tg in tags:
        for d in (pdirs or []) + [R.PRED]:
            f = os.path.join(d, f"{tg}.npz")
            if os.path.exists(f):
                out.append(np.load(f)); break
    return out


def beta_fit(s, y):
    mu, sd = s.mean(), s.std() + 1e-12
    def feats(x):
        q = np.clip(1 / (1 + np.exp(-(x - mu) / sd)), 1e-9, 1 - 1e-9)
        return np.column_stack([np.log(q), -np.log(1 - q)])
    m = LogisticRegression(C=1e6, max_iter=5000).fit(feats(s), y.astype(int))
    return lambda x: m.predict_proba(feats(x))[:, 1]


def choose_w(p, net, t, wr_min):
    best = None
    for q in R.QS + [0.997]:
        thr = float(np.quantile(p, q))
        sel = p >= thr
        n = int(sel.sum())
        if n < R.MIN_VAL or len(np.unique((t[sel] // B.DAY))) < R.MIN_DAYS:
            continue
        ts = np.sort(t[sel]); o = np.argsort(t[sel], kind="stable")
        ep = np.concatenate([[0], np.cumsum(np.diff(ts) > E.W * C.MS15)])
        w = 1.0 / np.bincount(ep)[ep]
        x = net[sel][o]
        wr = float(np.sum(w * (x > 0)) / w.sum()); e = float(np.sum(w * x) / w.sum())
        if e > 0 and wr >= wr_min and (best is None or e > best[2]):
            best = (thr, wr, e)
    return best


def variant(D0, ens, mode):
    P = _P(ens)
    yG3 = (P[0]["net"] > 0).astype(float)
    netX = np.concatenate([D0["cache"][s]["net_X5"] for s in H.SYMBOLS])
    t_all = np.concatenate([D0["cache"][s]["t"] for s in H.SYMBOLS]).astype(np.int64)
    ps, thrs, used = [], [], []
    for k in range(6):
        vr, tr_ = P[0][f"f{k}_val_rows"], P[0][f"f{k}_tst_rows"]
        okv = np.isfinite(netX[vr]) & (t_all[vr] < t_all[tr_].min() - 289 * C.MS15)
        pv = np.zeros(len(vr)); pt = np.zeros(len(tr_))
        if mode == "beta":
            for p in P:
                f = beta_fit(p[f"f{k}_val_s"], yG3[vr])
                pv += f(p[f"f{k}_val_s"]) / len(P); pt += f(p[f"f{k}_tst_s"]) / len(P)
        else:
            for p in P:
                ab = R.platt_fit(p[f"f{k}_val_s"], yG3[vr])
                pv += R.platt_apply(p[f"f{k}_val_s"], ab) / len(P)
                pt += R.platt_apply(p[f"f{k}_tst_s"], ab) / len(P)
        if mode == "monthly":
            tt = t_all[tr_]
            mon = B.month_of(tt)
            for mi, mm in enumerate(sorted(np.unique(mon))):
                if mi == 0:
                    continue
                sel = mon == mm
                t_cut = tt[sel].min() - 289 * C.MS15
                closed = tt < t_cut
                newp = np.zeros(int(sel.sum()))
                for p in P:
                    s_tr = np.concatenate([p[f"f{k}_val_s"], p[f"f{k}_tst_s"][closed]])
                    y_tr = np.concatenate([yG3[vr], yG3[tr_][closed]])
                    ab = R.platt_fit(s_tr, y_tr)
                    newp += R.platt_apply(p[f"f{k}_tst_s"][sel], ab) / len(P)
                pt[sel] = newp
            thr = float(D0["vals"][k]["thr"]); used.append(thr)
        elif mode == "epw":
            ch = choose_w(pv[okv], netX[vr][okv], t_all[vr][okv], 0.75)
            thr = np.inf if ch is None else ch[0]; used.append((thr, float(D0["vals"][k]["thr"])))
        else:
            ch = V.choose(pv[okv], netX[vr][okv], (t_all[vr] // B.DAY)[okv], 0.75)
            thr = np.inf if ch is None else ch[0]; used.append(thr)
        ps.append(pt); thrs.append(np.full(len(tr_), thr))
    D = dict(D0)
    D["p"] = np.concatenate(ps); D["thr"] = np.concatenate(thrs)
    assert len(D["p"]) == len(D0["p"])
    D["sig"] = D["p"] >= D["thr"]
    D["A"] = E.gate_count(D, D["sig"])
    D["stack"] = D["sig"] & (D["A"] >= 1)
    return D, used


def run(ens):
    D0 = E.load(ens)
    bases = K.bases(D0)
    res = {}
    for bname, (Dx0, ref) in bases.items():
        res[f"pila {bname}"] = dict(summary=E.summ(ref, f"pila {bname}"), bb=K.betabin_ci(ref), base=bname)
    for mode, lab in (("beta", "H8a calibración beta"), ("epw", "H8b θ con pesos por episodio"), ("monthly", "H9 Platt mensual")):
        Dv, used = variant(D0, ens, mode)
        for bname, (Dx0, ref) in bases.items():
            Dx = dict(Dv)
            Dx["netX"], Dx["cache"], Dx["exit_geom"] = Dx0["netX"], Dx0["cache"], Dx0["exit_geom"]
            t = E.trade_table(Dx, Dv["stack"], Dv["A"] >= 1)
            r = E.summ(t, lab); c = K.compare_ep(t, ref)
            res[f"{lab} [{bname}]"] = dict(summary=r, compare=c, bb=K.betabin_ci(t) if t is not None else None, base=bname,
                                         kind="dentro", thr=used)
            print(ens, bname, lab, r.get("n"), f"{r.get('wr', np.nan)*100:.1f}", f"{r.get('E_pct', np.nan):+.2f}",
                  f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", used, flush=True)
    return res


if __name__ == "__main__":
    ens_list = ["ENS13", "ENS12", "ENS12U"]
    res = {e: run(e) for e in ens_list}
    E.jdump(res, os.path.join(K.OUT2, "be2b_h8h9.json"))
    L = ["# R2A H8 (calibración beta, θ con pesos por episodio) y H9 (Platt mensual)\n", K.HEAD, K.HEAD2]
    keys = list(res["ENS13"].keys())
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
        L.append(f"- {k}: {'PASA' if ok else 'no'} — {why}; θ ENS13 {res['ENS13'][k]['thr']}")
        for e in ens_list:
            L.append("  " + E.detail(e, res[e][k]["summary"], res[e][k]["compare"]))
    with open(os.path.join(K.OUT2, "be2b_h8h9.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
