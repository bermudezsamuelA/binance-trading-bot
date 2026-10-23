"""Ronda 1 - Paso 3: filtros univariados sobre la señal MeanReversion estándar (n=20, k=2, R>=0.5%).
Para cada variable: acierto por quintil (umbrales fijados en DISEÑO-A = 2023-01..2024-03, por moneda) y su
réplica en DISEÑO-B = 2024-04..2025-06. Simulación secuencial (1 posición por moneda) con dos geometrías fijas:
  G1: TP = mu, SL = c - R (b = 1, la del bot)      G2: TP = mu, SL = c - 2R (b = 0.5)
Sin barrera de tiempo. Costos 0.24 %.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac
import analista_features as af

N_WIN, K_MULT, MINR = 20, 2.0, 0.005
GEOMS = {"G1": 1.0, "G2": 2.0}   # SL a m*R por debajo


def prepare():
    data = {s: ac.load(s) for s in ac.SYMS}
    t0 = data["BTCUSDT"]["t"]
    for s in ac.SYMS:
        assert np.array_equal(data[s]["t"], t0), "timestamps desalineados"
    Fs = {s: af.build(data[s], N_WIN) for s in ac.SYMS}
    Fs = af.add_cross(Fs, ac.SYMS)
    sig = {}
    for s in ac.SYMS:
        d = data[s]
        c = d["c"]
        z = Fs[s]["z"]
        R = Fs[s]["R_pct"]
        with np.errstate(invalid="ignore"):
            cond = (z < -K_MULT) & (R >= MINR)
        idx = np.where(cond)[0]
        mu = c[idx] * (1 + R[idx])
        lab = {}
        for g, m in GEOMS.items():
            sl = c[idx] * (1 - m * R[idx])
            ex_i, ex_p, out = ac.first_touch(d, idx, mu, sl)
            lab[g] = dict(ex_i=ex_i, ex_p=ex_p, out=out, sl=sl)
        sig[s] = dict(idx=idx, tp=mu, lab=lab, A=d["t"][idx] < ac.SPLIT_AB_MS)
    return data, Fs, sig


def eval_mask(data, sig, masks, g, part):
    """masks: dict sym->bool sobre las señales. part: 'A','B','all'. Devuelve métricas agrupadas y por moneda."""
    rn, RR, ii, per = [], [], [], {}
    for s in ac.SYMS:
        S = sig[s]
        m = masks[s].copy()
        if part == "A":
            m &= S["A"]
        elif part == "B":
            m &= ~S["A"]
        sel = np.where(m)[0]
        L = S["lab"][g]
        tk = sel[ac.select_sequential(S["idx"][sel], L["ex_i"][sel])]
        c = data[s]["c"]
        e = c[S["idx"][tk]]
        r = L["ex_p"][tk] / e - 1 - ac.COST
        R = (e - L["sl"][tk]) / e
        rn.append(r); RR.append(R); ii.append(S["idx"][tk])
        per[s] = (len(tk), float((r > 0).mean()) if len(tk) else np.nan)
    r = np.concatenate(rn); R = np.concatenate(RR); t = np.concatenate(ii)
    o = np.argsort(t, kind="stable")
    return ac.metrics(r[o], R[o]), per


def main():
    lines = []
    P = lambda s: (print(s), lines.append(s))
    data, Fs, sig = prepare()
    n_cfg = 0
    months = {"A": 15.0, "B": 15.0, "all": 30.0}
    base = {}
    P(f"Señal base MR(n={N_WIN}, k={K_MULT}, R>={MINR*100:.1f}%). Señales candidatas por moneda: " +
      ", ".join(f"{s}={len(sig[s]['idx'])}" for s in ac.SYMS))
    for g in GEOMS:
        for part in ("A", "B", "all"):
            m, per = eval_mask(data, sig, {s: np.ones(len(sig[s]["idx"]), bool) for s in ac.SYMS}, g, part)
            base[(g, part)] = m
            P(f"BASE {g} {part:3s}: {ac.fmt(m)} ops/mes(4 monedas)={m['N']/months[part]:.0f} | " +
              " ".join(f"{s[:3]}:{per[s][0]}/{per[s][1]*100:.0f}%" for s in ac.SYMS))
    summary = []
    for f in af.FEATURES:
        P(f"\n### {f}")
        vals = {s: Fs[s][f][sig[s]["idx"]] for s in ac.SYMS}
        # umbrales por moneda desde DISEÑO-A
        qs = {s: np.nanpercentile(vals[s][sig[s]["A"]], [20, 40, 60, 80]) for s in ac.SYMS}
        if f in ("hour", "dow", "breadth_dip", "down_run"):
            # discretas: usar bins naturales
            if f == "hour":
                bins = [(0, 6), (6, 12), (12, 18), (18, 24)]
            elif f == "dow":
                bins = [(0, 5), (5, 7)]
            elif f == "breadth_dip":
                bins = [(0, 1.5), (1.5, 2.5), (2.5, 5)]
            else:
                bins = [(0, 1.5), (1.5, 3.5), (3.5, 100)]
            bmasks = [{s: (vals[s] >= a) & (vals[s] < b) for s in ac.SYMS} for (a, b) in bins]
            labels = [f"[{a},{b})" for (a, b) in bins]
        else:
            edges = {s: np.concatenate([[-np.inf], qs[s], [np.inf]]) for s in ac.SYMS}
            bmasks = [{s: (vals[s] >= edges[s][k]) & (vals[s] < edges[s][k + 1]) for s in ac.SYMS} for k in range(5)]
            labels = [f"Q{k+1}" for k in range(5)]
        for g in GEOMS:
            row = []
            res = []
            for lab, bm in zip(labels, bmasks):
                mA, _ = eval_mask(data, sig, bm, g, "A")
                mB, _ = eval_mask(data, sig, bm, g, "B")
                n_cfg += 1
                res.append((lab, mA, mB))
                row.append(f"{lab}: A {mA['WR']*100:4.1f}% ({mA['N']}) E_R {mA['E_R']:+.2f} | B {mB['WR']*100:4.1f}% ({mB['N']}) E_R {mB['E_R']:+.2f}")
            P(f"  {g}: " + "\n      ".join(row))
            # spread entre extremos y consistencia A/B
            wa = [r[1]["WR"] for r in res]
            wb = [r[2]["WR"] for r in res]
            ia, ib = int(np.argmax(wa)), int(np.argmin(wa))
            spreadA = wa[ia] - wa[ib]
            spreadB = wb[ia] - wb[ib]
            corr = float(np.corrcoef(wa, wb)[0, 1]) if len(wa) > 2 else np.nan
            summary.append(dict(f=f, g=g, best_bin=labels[ia], worst_bin=labels[ib], spreadA=spreadA, spreadB=spreadB,
                                corrAB=corr, best_A=res[ia][1], best_B=res[ia][2]))
    P("\n\n=== RESUMEN: separación de acierto entre el mejor y el peor bin (elegidos en A) y su réplica en B ===")
    for g in GEOMS:
        P(f"\n-- {g} (base A: WR={base[(g,'A')]['WR']*100:.1f}% E_R={base[(g,'A')]['E_R']:+.3f}; "
          f"base B: WR={base[(g,'B')]['WR']*100:.1f}% E_R={base[(g,'B')]['E_R']:+.3f}) --")
        rows = sorted([x for x in summary if x["g"] == g], key=lambda x: -x["spreadB"])
        for x in rows:
            bB = x["best_B"]
            P(f"{x['f']:14s} mejor={x['best_bin']:7s} peor={x['worst_bin']:7s} ΔWR_A={x['spreadA']*100:+5.1f}pp "
              f"ΔWR_B={x['spreadB']*100:+5.1f}pp corr(A,B)={x['corrAB']:+.2f} | mejor bin en B: WR={bB['WR']*100:.1f}% "
              f"N={bB['N']} E_R={bB['E_R']:+.3f}")
    P(f"\nConfiguraciones (bins x geometrías, evaluados en A y B) en este script: {n_cfg}")
    with open(os.path.join(ac.OUTDIR, "03_filtros.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
