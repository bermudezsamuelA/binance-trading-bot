"""Ronda 1 - Paso 10: línea base EMPAREJADA. Para cada operación del candidato (moneda, mes, R) se simulan
K = 30 entradas en velas aleatorias del MISMO mes y moneda con la MISMA geometría relativa
(TP = e(1+R), SL = e(1-m R), H). Así se descuentan la deriva del mercado y el efecto mecánico de b.
Δp = WR_señal - WR_azar ;  ΔE = E_señal - E_azar  (en % por operación, neto de costos)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac
import analista_features as af
import analista_09_robustez as rb
import harness as Hh

K = 30
GEOM = {"T48": (None, 48), "G1H48": (1.0, 48), "G2H96": (2.0, 96), "G3H96": (3.0, 96)}


def matched(b, tr, m_sl, H, rng):
    """Simula K entradas aleatorias por operación con su misma R y geometría, en el mismo mes."""
    mon = b.month
    wr, ex = [], []
    for k in range(len(tr)):
        e_idx = tr.entry_idx[k]
        R = (tr.tp[k] / tr.entry_px[k] - 1) if np.isfinite(tr.tp[k]) else np.nan
        Rm = R if np.isfinite(R) else (tr.risk_pct[k])
        cand = np.flatnonzero(mon == mon[e_idx])
        cand = cand[cand + H + 1 < len(b)]
        js = rng.choice(cand, size=K, replace=True)
        for j in js:
            e = b.c[j]
            tp = e * (1 + Rm) if m_sl is not None else np.nan
            sl = e * (1 - m_sl * Rm) if m_sl is not None else np.nan
            jj, px, why = Hh.resolve_exit(b.o, b.h, b.l, b.c, j + 1, len(b), e, tp, sl, None, H)
            r = float(Hh.net_return(e, px))
            wr.append(r > 0); ex.append(r)
    return np.array(wr), np.array(ex)


def main():
    lines = []
    P = lambda s: (print(s), lines.append(s))
    rng = np.random.default_rng(12345)
    data = {s: ac.load(s) for s in ac.SYMS}
    Fs = af.add_cross({s: af.build(data[s], 20) for s in ac.SYMS}, ac.SYMS)
    bars = {s: Hh.load(s) for s in ac.SYMS}
    S, I, take = rb.scores(data, Fs, 96, rb.FULL, 0.1)
    allsig = np.ones(len(take), bool)
    START = Hh.ms(2023, 10, 1)
    for label, tk in (("MR20 base (sin filtro)", allsig), ("MR20 + ridge h96 decil sup.", take)):
        P(f"\n=== {label} ===")
        for g, (m_sl, H) in GEOM.items():
            for part, (a0, a1) in (("A", (START, ac.SPLIT_AB_MS)), ("B", (ac.SPLIT_AB_MS, ac.DESIGN_END_MS))):
                ws, es, wb, eb = [], [], [], []
                for si, s in enumerate(ac.SYMS):
                    b = bars[s]
                    ent = np.zeros(len(b), bool); ent[I[(S == si) & tk]] = True
                    mu = Hh.rolling_mean(b.c, 20); R = mu - b.c
                    tr = Hh.simulate(b, ent, (mu if m_sl else None), ((b.c - m_sl * R) if m_sl else None),
                                     period=(b.idx(a0), b.idx(a1)), max_hold=H, risk=(None if m_sl else R))
                    if label.startswith("MR20 base") and len(tr) > 400:   # submuestra para acotar el costo
                        sel = np.sort(rng.choice(len(tr), 400, replace=False))
                        tr = tr.subset(sel)
                    if m_sl is None:   # para T48, R = distancia a la media (solo define la escala, no hay barreras)
                        tr.tp[:] = tr.entry_px * (1 + tr.risk_pct)
                    w_, e_ = matched(b, tr, m_sl, H, rng)
                    ws.append(tr.net_ret > 0); es.append(tr.net_ret); wb.append(w_); eb.append(e_)
                ws = np.concatenate(ws); es = np.concatenate(es); wb = np.concatenate(wb); eb = np.concatenate(eb)
                dp = ws.mean() - wb.mean()
                se_dp = np.sqrt(ws.var() / len(ws) + wb.var() / len(wb))
                dE = es.mean() - eb.mean()
                se_dE = np.sqrt(es.var(ddof=1) / len(es) + eb.var(ddof=1) / len(eb))
                P(f"  {g:6s} {part}: N={len(ws):4d}  WR señal={ws.mean()*100:5.1f}%  WR azar={wb.mean()*100:5.1f}%  "
                  f"Δp={dp*100:+5.1f}pp (z={dp/se_dp:+.1f}) | E señal={es.mean()*100:+.3f}%  E azar={eb.mean()*100:+.3f}%  "
                  f"ΔE={dE*100:+.3f}% (z={dE/se_dE:+.1f})")
    with open(os.path.join(ac.OUTDIR, "10_baseline.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
