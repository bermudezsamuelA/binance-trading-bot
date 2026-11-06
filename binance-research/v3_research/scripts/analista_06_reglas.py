"""Ronda 1 - Paso 6: rejilla PRE-DECLARADA de reglas simples sobre MeanReversion (64 configuraciones).
Señal: z_n = (c - SMA_n)/std_n < -2 (precio, como el bot), n in {20, 48}.
Filtros: R_min in {0.5,1.0,1.5,2.0}% (R = SMA_n - c, palanca de costos c/R)
         tendencia: ninguna | pendiente SMA800 (≈ SMA50 de 4h) > 0 en las últimas 16 velas
         régimen:   ninguno | VR16 (7 días) >= 0.9
Geometría fija (no se optimiza aquí; es tarea del Gestor de Riesgo):
         G1: TP = SMA_n, SL = c - R, H = 48 velas (12 h)   (b = 1)
         G2: TP = SMA_n, SL = c - 2R, H = 96 velas (24 h)  (b = 0.5)
Selección: se ordena por E_R en DISEÑO-A; DISEÑO-B es la réplica. Todo dentro de DISEÑO."""
import os, sys, json, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac
import analista_features as af


def main():
    lines = []
    P = lambda s: (print(s), lines.append(s))
    data = {s: ac.load(s) for s in ac.SYMS}
    Fs = {s: af.build(data[s], 20) for s in ac.SYMS}
    extra = {}
    for s in ac.SYMS:
        c = data[s]["c"]
        extra[s] = {}
        for n in (20, 48):
            mu, sd = ac.roll_mean_std(c, n)
            extra[s][n] = (mu, (c - mu) / sd, (mu - c) / c)
    grid = list(itertools.product((20, 48), (0.005, 0.01, 0.015, 0.02), (False, True), (False, True), ("G1", "G2")))
    res = []
    labcache = {}
    for (n, minR, trend, reg, g) in grid:
        m_sl, H = (1.0, 48) if g == "G1" else (2.0, 96)
        out = {}
        for part in ("A", "B", "all"):
            rn, RR, tt, per = [], [], [], {}
            for s in ac.SYMS:
                d = data[s]; c = d["c"]; F = Fs[s]
                mu, z, Rp = extra[s][n]
                key = (s, n, g)
                if key not in labcache:
                    with np.errstate(invalid="ignore"):
                        idx = np.where((z < -2) & (Rp >= 0.005))[0]
                    idx = idx[idx >= 900]
                    tp = mu[idx]; sl = c[idx] * (1 - m_sl * Rp[idx])
                    ex_i, ex_p, o = ac.first_touch(d, idx, tp, sl, H)
                    labcache[key] = (idx, tp, sl, ex_i, ex_p)
                idx, tp, sl, ex_i, ex_p = labcache[key]
                with np.errstate(invalid="ignore"):
                    mk = Rp[idx] >= minR
                    if trend:
                        mk &= F["slope_sma800"][idx] > 0
                    if reg:
                        mk &= F["VR16"][idx] >= 0.9
                pa = d["t"][idx] < ac.SPLIT_AB_MS
                if part == "A":
                    mk &= pa
                elif part == "B":
                    mk &= ~pa
                sel = np.where(mk)[0]
                tk = sel[ac.select_sequential(idx[sel], ex_i[sel])]
                e = c[idx[tk]]
                r = ex_p[tk] / e - 1 - ac.COST
                rn.append(r); RR.append((e - sl[tk]) / e); tt.append(idx[tk])
                per[s] = ac.metrics(r, (e - sl[tk]) / e) if len(tk) else dict(N=0)
            r = np.concatenate(rn); R = np.concatenate(RR); t = np.concatenate(tt)
            o = np.argsort(t, kind="stable")
            out[part] = (ac.metrics(r[o], R[o]) if len(r) else dict(N=0), per)
        res.append(dict(cfg=(n, minR, trend, reg, g), out=out))
    P("Rejilla pre-declarada: 64 configuraciones (2 n x 4 R_min x 2 tendencia x 2 régimen x 2 geometrías).")
    P("Columnas: config | DISEÑO-A (ordenado por E_R en A) | DISEÑO-B (réplica) | ops/mes en B (4 monedas)\n")
    for g in ("G1", "G2"):
        P(f"===== Geometría {g} =====")
        rows = [x for x in res if x["cfg"][4] == g]
        rows.sort(key=lambda x: -(x["out"]["A"][0].get("E_R", -9) if x["out"]["A"][0].get("N", 0) >= 30 else -9))
        for x in rows:
            n, minR, trend, reg, _ = x["cfg"]
            a = x["out"]["A"][0]; b = x["out"]["B"][0]
            lab = f"n={n} Rmin={minR*100:.1f}% tend={'S' if trend else '-'} VR={'S' if reg else '-'}"
            if a.get("N", 0) == 0 or b.get("N", 0) == 0:
                P(f"{lab}: sin operaciones"); continue
            P(f"{lab:38s} A: N={a['N']:4d} WR={a['WR']*100:4.1f}% E={a['E_pct']:+.3f}% E_R={a['E_R']:+.3f} | "
              f"B: N={b['N']:4d} WR={b['WR']*100:4.1f}% [{b['WR_lo']*100:4.1f},{b['WR_hi']*100:4.1f}] b={b['b_eff']:.2f} "
              f"E={b['E_pct']:+.3f}%(t={b['t_E_pct']:+.1f}) E_R={b['E_R']:+.3f}(t={b['t_E_R']:+.1f}) PF={b['PF']:.2f} "
              f"MDD={b['MDD_R']:.1f}R | {b['N']/15:.1f}/mes")
        P("")
    # detalle por moneda de las 4 mejores en A por geometría
    P("===== Detalle por moneda (DISEÑO completo) de las 3 mejores configuraciones en A por geometría =====")
    for g in ("G1", "G2"):
        rows = [x for x in res if x["cfg"][4] == g and x["out"]["A"][0].get("N", 0) >= 30]
        rows.sort(key=lambda x: -x["out"]["A"][0]["E_R"])
        for x in rows[:3]:
            P(f"{g} {x['cfg'][:4]}: TOTAL {ac.fmt(x['out']['all'][0])}")
            for s in ac.SYMS:
                m = x["out"]["all"][1][s]
                P(f"     {s}: {ac.fmt(m) if m.get('N',0) else 'N=0'}")
    with open(os.path.join(ac.OUTDIR, "06_reglas.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    try:
        import harness as Hh
        Hh.log_trials("analista", 64, "R1 rejilla MR n{20,48} x Rmin{0.5..2%} x tend x VR16 x {G1,G2}", "design")
    except Exception as e:
        print("no se pudo registrar en trials_log:", e)


if __name__ == "__main__":
    main()
