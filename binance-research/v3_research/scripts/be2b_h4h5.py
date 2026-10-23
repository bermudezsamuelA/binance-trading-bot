"""R2A H4 meta-etiquetado bayesiano y H5 prioridad por antiguedad bajo cupo (DISENO). Pre-registro (de investigador_B.md):

H4 (regla de SELECCION; mezcla de episodio y dentro del episodio). Variables (signo declarado +): g = -dd_96 (brecha, en
   s_d), dispersion (desviacion) de las probabilidades calibradas de los miembros del ensamble, funding_z_2016 en ii - 96.
   Entrenamiento del pliegue k: velas de la pila de los pliegues < k con purga (t < inicio del pliegue - 289 velas).
   Pesos que suman 1 por (episodio de mercado, moneda); episodio = racha de senales de cualquier moneda con huecos <= 48
   velas. Variables estandarizadas; prior N(0, 0.5^2) => regresion logistica L2 con C = 0.25 sobre la verosimilitud
   ponderada. Si un coeficiente sale con signo contrario al declarado, esa variable se quita y se re-ajusta.
   Regla: saltar si p_meta < cuantil 0.20 de p_meta en el entrenamiento. Pliegue 0: sin filtro.
H5 (regla DENTRO del episodio). Con cupo MAX2 (principal) y MAX3 (informativo), cuando en la misma vela hay mas candidatas
   que cupos, se prioriza la moneda cuya PRIMERA senal propia en el episodio es mas antigua (empates: mayor p).
   Se compara con el orden por p (R2-E9), con 200 ordenes al azar y sin cupo.
Bases: pila X5 y pila con H 384. Bootstrap por episodio.
Registro (antes de correr): H4 x 2 bases = 2; H5 MAX2 y MAX3 x 2 bases = 4. Total 6.
"""
import os, sys
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2b_common as K
import be2b_sel as S
B, H, C, R, V = E.B, E.H, E.C, E.R, E.V

E.log_once("r2a_h4h5", 6, "R2A H4 meta-etiquetado bayesiano (g, dispersion, funding previo; pesos por episodio; q20) x2 bases; H5 prioridad por antiguedad MAX2/MAX3 x2 bases")


def member_std(ens):
    tags, pdirs = E.ENSEMBLES[ens]

    def _p(tg):
        for d in (pdirs or []) + [R.PRED]:
            f = os.path.join(d, f"{tg}.npz")
            if os.path.exists(f):
                return f
    P = [np.load(_p(t)) for t in tags]
    yG3 = (P[0]["net"] > 0).astype(float)
    out = []
    for k in range(6):
        vr = P[0][f"f{k}_val_rows"]
        M = []
        for p in P:
            ab = R.platt_fit(p[f"f{k}_val_s"], yG3[vr])
            M.append(R.platt_apply(p[f"f{k}_tst_s"], ab))
        out.append(np.std(np.array(M), 0))
    return np.concatenate(out)


def episode_ids(D):
    """Id de episodio de mercado por fila (-1 fuera de episodio) y primera senal propia del episodio por fila."""
    N = len(D["tg"])
    Sg = E.to_grid(D, D["sig"], False, bool)
    anyb = np.where(Sg.any(0))[0]
    epg = np.full(N, -1)
    first = np.full((4, N), -1)
    starts = [0] + [k for k in range(1, len(anyb)) if anyb[k] - anyb[k - 1] > E.W] + [len(anyb)]
    for e in range(len(starts) - 1):
        bars = anyb[starts[e]:starts[e + 1]]
        t0, t1 = bars[0], min(N, bars[-1] + E.W + 1)
        epg[t0:t1] = e
        for i in range(4):
            bi = bars[Sg[i, bars]]
            if len(bi):
                first[i, t0:t1] = bi[0]
    return epg[D["jrow"]], E.from_grid(D, first)


def h4_mask(D, X, ep):
    keep = D["stack"].copy()
    y = (D["netX"] > 0).astype(int)
    info = []
    for k in range(1, 6):
        t0 = H.ms(*B.TESTS[k][0], 1)
        tr = D["stack"] & (D["fold"] < k) & np.isfinite(D["netX"]) & (D["t"] < t0 - 289 * C.MS15) & np.all(np.isfinite(X), 1)
        te = D["stack"] & (D["fold"] == k)
        if tr.sum() < 30 or te.sum() == 0 or len(np.unique(y[tr])) < 2:
            info.append(None); continue
        key = ep[tr] * 10 + D["ci"][tr]
        u, inv = np.unique(key, return_inverse=True)
        w = 1.0 / np.bincount(inv)[inv]
        cols = [0, 1, 2]
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-12
        Z = (X - mu) / sd
        while cols:
            m = LogisticRegression(C=0.25, max_iter=2000).fit(Z[tr][:, cols], y[tr], sample_weight=w)
            bad = [c for c, b in zip(cols, m.coef_[0]) if b < 0]
            if not bad:
                break
            cols = [c for c in cols if c not in bad]
        if not cols:
            info.append(dict(cols=[], n_ep=len(u))); continue
        ptr = m.predict_proba(Z[tr][:, cols])[:, 1]
        thr = np.quantile(ptr, 0.20)
        pte = m.predict_proba(np.nan_to_num(Z[te][:, cols]))[:, 1]
        kk = np.zeros(len(keep), bool); kk[np.where(te)[0][pte >= thr]] = True
        keep = np.where(te, kk, keep)
        info.append(dict(cols=cols, coef=m.coef_[0].round(3).tolist(), n_groups=len(u), keep=float(np.mean(pte >= thr))))
    return keep, info


def joint_sim_order(D, mask, geom, maxpos, sec_key):
    a, m, Hh = geom
    if "_bars" not in D:
        D["_bars"] = {s: R.coin_bars(s, len(D["cache"][s]["c"])) for s in H.SYMBOLS}
        D["_per"] = K.fold_periods(D)
    bars = D["_bars"]
    sdv = {s: D["cache"][s]["s15"] * np.sqrt(96) for s in H.SYMBOLS}
    per = D["_per"]
    idx = np.where(mask)[0]
    idx = idx[np.lexsort((sec_key[idx], D["jrow"][idx]))]
    busy = np.full(4, -1); trades = []
    for r in idx:
        i = int(D["ci"][r]); b = int(D["ii"][r]); k = int(D["fold"][r])
        if busy[i] >= b:
            continue
        if maxpos is not None:
            open_ = [tr for tr in trades[-8:] if tr[1] < b <= tr[2]]
            if len(open_) >= maxpos:
                continue
        s = H.SYMBOLS[i]; Bs = bars[s]
        entry = float(Bs.c[b]); sd = float(sdv[s][b])
        if not np.isfinite(sd):
            continue
        tp, sl = entry * (1 + a * sd), entry * (1 - m * sd)
        j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, b + 1, per[(i, k)][1], entry, tp, sl, None, Hh)
        if why == H.END and j < b + 1:
            continue
        trades.append((i, b, int(j), float(H.net_return(entry, px)), int(why), k, (entry - sl) / entry, int(D["t"][r])))
        busy[i] = j
    return trades


def run(ens):
    D = E.load(ens)
    g1 = D["A"] >= 1
    bases = K.bases(D)
    gall = np.concatenate([K.gap_g(s) for s in H.SYMBOLS])[D["rows"]]
    disp = member_std(ens)
    fpre = E.from_grid(D, S.Xcol(D, "funding_z_2016", lag=96))
    X = np.column_stack([gall, disp, fpre])
    ep, first = episode_ids(D)
    res = {}
    for bname, (Dx, ref) in bases.items():
        res[f"pila {bname}"] = dict(summary=E.summ(ref, f"pila {bname}"), bb=K.betabin_ci(ref), base=bname)
        # H4
        Dlab = dict(D); Dlab["netX"] = Dx["netX"]  # etiqueta de entrenamiento con la salida de la base
        keep, info = h4_mask(Dlab, X, ep)
        t = E.trade_table(Dx, keep, g1)
        lab = "H4 meta-etiquetado bayesiano (q20)"
        r = E.summ(t, lab); c = K.compare_ep(t, ref)
        res[f"{lab} [{bname}]"] = dict(summary=r, compare=c, bb=K.betabin_ci(t), base=bname, kind="selección", info=info)
        print(ens, bname, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} "
              f"P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", info, flush=True)
        # H5
        geom = (0.7, 1.75, 288 if bname == "X5" else 384)
        for cap in (2, 3):
            seni = first.astype(float) + 1e-6 * (1 - D["p"])  # antiguedad, desempate por p
            tr_s = K.table_from_list(Dx, joint_sim_order(D, D["stack"], geom, cap, seni), g1)
            tr_p = K.table_from_list(Dx, joint_sim_order(D, D["stack"], geom, cap, -D["p"]), g1)
            rng = np.random.default_rng(7)
            rnd = []
            for _ in range(200):
                tt = K.table_from_list(Dx, joint_sim_order(D, D["stack"], geom, cap, rng.random(len(D["p"]))), None)
                rnd.append((np.mean(tt["x"] > 0), tt["x"].mean() * 100))
            rnd = np.array(rnd)
            lab_s = f"H5 MAX{cap} prioridad por antigüedad"
            r_s = E.summ(tr_s, lab_s); r_p = E.summ(tr_p, f"MAX{cap} prioridad por p̂")
            c_s = K.compare_ep(tr_s, ref); c_sp = K.compare_ep(tr_s, tr_p)
            pct_wr = float(np.mean(rnd[:, 0] < r_s["wr"])); pct_e = float(np.mean(rnd[:, 1] < r_s["E_pct"]))
            res[f"{lab_s} [{bname}]"] = dict(summary=r_s, compare=c_s, bb=K.betabin_ci(tr_s), base=bname, kind="dentro",
                                           vs_p=c_sp, by_p=r_p, rand=dict(wr_mean=float(rnd[:, 0].mean()), E_mean=float(rnd[:, 1].mean()),
                                                                           pct_wr=pct_wr, pct_E=pct_e,
                                                                           wr_q=(float(np.quantile(rnd[:, 0], .05)), float(np.quantile(rnd[:, 0], .95)))))
            print(ens, bname, lab_s, r_s["n"], f"{r_s['wr']*100:.1f}", f"{r_s['E_pct']:+.2f}", "| por p", r_p["n"], f"{r_p['wr']*100:.1f}",
                  f"{r_p['E_pct']:+.2f}", f"| vs p dWR {c_sp['dWR']*100:+.1f} dE {c_sp['dE']:+.2f}", "| azar WR medio",
                  f"{rnd[:, 0].mean()*100:.1f}", "percentil", pct_wr, flush=True)
    return res


if __name__ == "__main__":
    ens_list = ["ENS13", "ENS12", "ENS12U"]
    res = {e: run(e) for e in ens_list}
    E.jdump(res, os.path.join(K.OUT2, "be2b_h4h5.json"))
    L = ["# R2A H4 meta-etiquetado bayesiano y H5 prioridad por antigüedad bajo cupo\n", K.HEAD, K.HEAD2]
    keys = list(res["ENS13"].keys())
    for k in keys:
        for e in ens_list:
            o = res[e][k]
            L.append(K.row(e, o["base"], o["summary"], o.get("compare"), o.get("bb")))
            if "by_p" in o:
                L.append(K.row(e, o["base"], o["by_p"], None, None))
    L.append("\n## Tamiz y detalle\n")
    for k in keys:
        if k.startswith("pila"):
            continue
        base = res["ENS13"][k]["base"]
        ok, why = K.screen(res["ENS13"][k]["summary"], res["ENS13"][f"pila {base}"]["summary"], res["ENS13"][k]["compare"],
                           {e: res[e][k]["compare"] for e in ens_list})
        L.append(f"- {k}: {'PASA' if ok else 'no'} — {why}")
        for e in ens_list:
            o = res[e][k]
            if "vs_p" in o:
                L.append(f"  - {e}: frente al orden por p̂ ΔWR {o['vs_p']['dWR']*100:+.1f} / ΔE {o['vs_p']['dE']:+.2f} "
                         f"(P {o['vs_p']['p_dWR_le0']:.2f}/{o['vs_p']['p_dE_le0']:.2f}); 200 órdenes al azar: WR medio "
                         f"{o['rand']['wr_mean']*100:.1f} % [{o['rand']['wr_q'][0]*100:.1f}, {o['rand']['wr_q'][1]*100:.1f}], "
                         f"percentil de la regla {o['rand']['pct_wr']*100:.0f} (WR) y {o['rand']['pct_E']*100:.0f} (E)")
            if "info" in o:
                L.append(f"  - {e} coeficientes por pliegue (columnas 0 g, 1 dispersión, 2 funding previo): {o['info']}")
            L.append("  " + E.detail(e, o["summary"], o["compare"]))
    with open(os.path.join(K.OUT2, "be2b_h4h5.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
