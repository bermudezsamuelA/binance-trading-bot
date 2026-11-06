"""R2-E12 TP decreciente para las operaciones lentas (DISENO). Pre-registro (escrito antes de correr):

Motivo: con deriva favorable (nu ~ 0.4 s_d/dia en las operaciones del modelo), las operaciones que no tocaron el TP en
36 h suelen terminar por tiempo o por SL. Bajar el objetivo de esas operaciones convierte parte en ganancias pequenas.
Distinto de lo ya rechazado: no se mueve el SL (no es "stop a equilibrio") ni se vende una parte (no es toma parcial).
Reglas (salida X5; desde la vela 145 tras la entrada el TP pasa a TP2, SL y H = 288 sin cambios):
  D1: TP2 = entrada * (1 + 0.35 s_d)  (la mitad de a);
  D2: TP2 = entrada * (1 + 0.006)     (equilibrio + costos, ~ +0.36 % neto).
Ademas se re-mide E7 (H = 384 y 576) con el mismo simulador como control cruzado.
Registro: 2.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2_joint as J
B, H, C, R = E.B, E.H, E.C, E.R


def sim(D, mask, a=0.7, m=1.75, Hh=288, decay_at=None, tp2_fn=None, fee=H.FEE, slip=H.SLIP):
    bars = {s: R.coin_bars(s, len(D["cache"][s]["c"])) for s in H.SYMBOLS}
    sdv = {s: D["cache"][s]["s15"] * np.sqrt(96) for s in H.SYMBOLS}
    per = J.fold_periods(D)
    idx = np.where(mask)[0]
    idx = idx[np.lexsort((-D["p"][idx], D["jrow"][idx]))]
    busy = np.full(4, -1)
    out = []
    for r in idx:
        i = int(D["ci"][r]); b = int(D["ii"][r]); k = int(D["fold"][r])
        if busy[i] >= b:
            continue
        s = H.SYMBOLS[i]; Bs = bars[s]
        i0, i1 = per[(i, k)]
        entry = float(Bs.c[b]); sd = float(sdv[s][b])
        if not np.isfinite(sd):
            continue
        tp, sl = entry * (1 + a * sd), entry * (1 - m * sd)
        if decay_at is None:
            j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, b + 1, i1, entry, tp, sl, None, Hh)
        else:
            j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, b + 1, min(i1, b + 1 + decay_at), entry, tp, sl, None, None)
            if why == H.END and j == min(i1, b + 1 + decay_at) - 1 and b + 1 + decay_at < i1:
                tp2 = tp2_fn(entry, sd)
                j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, b + 1 + decay_at, i1, entry, tp2, sl, None, Hh - decay_at)
                if why == H.TP and Bs.o[j] > tp2 and j == b + 1 + decay_at:
                    px = float(Bs.o[j])  # al activar TP2 con el precio ya por encima, se vende a la apertura
        if why == H.END and j < b + 1:
            continue
        net = float(H.net_return(entry, px, fee, slip))
        out.append((i, b, int(j), net, int(why), k, (entry - sl) / entry, int(D["t"][r])))
        busy[i] = j
    T = np.array([x[:7] for x in out], float)
    et = np.array([x[7] for x in out], np.int64)
    o = np.argsort(et, kind="stable"); T, et = T[o], et[o]
    _, base = B.rand_base(D)
    sidx = T[:, 0].astype(int)
    key = sidx * 1_000_000 + B.month_of(et)
    return dict(x=T[:, 3], et=et, sidx=sidx, fold=T[:, 5].astype(int), reason=T[:, 4].astype(int),
                r_mult=T[:, 3] / T[:, 6], risk=T[:, 6], sig_idx=T[:, 1].astype(int), exit_idx=T[:, 2].astype(int),
                bw=np.array([base[int(kk)][0] for kk in key]), be=np.array([base[int(kk)][1] for kk in key]))


def rand_decay(D, tp2_mult=None, tp2_abs=None, decay_at=144, a=0.7, m=1.75, Hh=288):
    """Azar con la misma regla de salida (todas las velas de prueba con compuerta A >= 1), muestreo 1 de cada 8 velas."""
    sel = np.where((D["A"] >= 1) & np.isfinite(D["netX"]))[0][::8]
    mk = np.zeros(len(D["rows"]), bool)
    xs, ws = [], []
    bars = {s: R.coin_bars(s, len(D["cache"][s]["c"])) for s in H.SYMBOLS}
    sdv = {s: D["cache"][s]["s15"] * np.sqrt(96) for s in H.SYMBOLS}
    per = J.fold_periods(D)
    for r in sel:
        i = int(D["ci"][r]); b = int(D["ii"][r]); k = int(D["fold"][r]); s = H.SYMBOLS[i]; Bs = bars[s]
        i0, i1 = per[(i, k)]
        entry = float(Bs.c[b]); sd = float(sdv[s][b])
        tp, sl = entry * (1 + a * sd), entry * (1 - m * sd)
        if tp2_mult is None and tp2_abs is None:
            j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, b + 1, i1, entry, tp, sl, None, Hh)
        else:
            j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, b + 1, min(i1, b + 1 + decay_at), entry, tp, sl, None, None)
            if why == H.END and j == min(i1, b + 1 + decay_at) - 1 and b + 1 + decay_at < i1:
                tp2 = entry * (1 + tp2_mult * sd) if tp2_mult is not None else entry * (1 + tp2_abs)
                j, px, why = H.resolve_exit(Bs.o, Bs.h, Bs.l, Bs.c, b + 1 + decay_at, i1, entry, tp2, sl, None, Hh - decay_at)
                if why == H.TP and Bs.o[j] > tp2 and j == b + 1 + decay_at:
                    px = float(Bs.o[j])
        if j < b + 1:
            continue
        xs.append(float(H.net_return(entry, px)))
    x = np.array(xs)
    return float(np.mean(x > 0)), float(x.mean() * 100), len(x)


def run(ens):
    D = E.load(ens)
    ref = E.trade_table(D, D["stack"], D["A"] >= 1)
    ctl = sim(D, D["stack"])
    res = {"pila": dict(summary=E.summ(ref, "pila v2 + A≥1")), "control": dict(summary=E.summ(ctl, "control (simulador propio)"))}
    rr0 = rand_decay(D)
    res["control"]["rand_gate"] = rr0
    print(ens, "control", res["control"]["summary"]["n"], f"{res['control']['summary']['wr']*100:.1f}",
          f"{res['control']['summary']['E_pct']:+.3f}", "azar compuerta X5", rr0, flush=True)
    for lab, kw, rk in (("D1 TP2 = 0.35 s_d desde 36 h", dict(decay_at=144, tp2_fn=lambda e, sd: e * (1 + 0.35 * sd)), dict(tp2_mult=0.35)),
                        ("D2 TP2 = +0.6 % desde 36 h", dict(decay_at=144, tp2_fn=lambda e, sd: e * 1.006), dict(tp2_abs=0.006)),
                        ("E7 control H=384", dict(Hh=384), None), ("E7 control H=576", dict(Hh=576), None)):
        t = sim(D, D["stack"], **kw)
        r = E.summ(t, lab); c = E.compare(t, ctl)
        rr = rand_decay(D, **rk) if rk is not None else None
        res[lab] = dict(summary=r, compare=c, rand_gate=rr)
        print(ens, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} "
              f"P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", "azar compuerta misma salida", rr, flush=True)
    return res


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    res = {ens: run(ens) for ens in ens_list}
    E.log_once("tpdecay", 2, "R2-E12 TP decreciente desde 36 h: 0.35 s_d y +0.6 % (SL y H sin cambio)")
    E.jdump(res, os.path.join(E.OUT2, "be2_tpdecay.json"))
    L = ["# R2-E12 TP decreciente para operaciones lentas (y control cruzado de E7)\n",
         "Comparación contra el control del simulador propio (reproduce la pila). 'Azar compuerta' = entradas en 1 de cada 8 velas con A ≥ 1, misma salida.\n",
         E.HEAD, E.HEAD2]
    labs = list(res[ens_list[0]].keys())
    for lab in labs:
        for ens in ens_list:
            L.append(E.row(ens, res[ens][lab]["summary"], res[ens][lab].get("compare")))
    L.append("")
    for lab in labs[2:]:
        ok, why = E.candidate({ens: res[ens][lab]["compare"] for ens in ens_list})
        L.append(f"- {lab}: {'CANDIDATA' if ok else 'no'} — {why}; azar con compuerta y misma salida (WR, E %, n): "
                 + ", ".join(f"{e} {res[e][lab]['rand_gate']}" for e in ens_list) + f"; X5: " + ", ".join(f"{e} {res[e]['control']['rand_gate']}" for e in ens_list))
        for ens in ens_list:
            L.append(E.detail(ens, res[ens][lab]["summary"], res[ens][lab]["compare"]))
    with open(os.path.join(E.OUT2, "be2_tpdecay.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
