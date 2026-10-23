"""Ronda 2 - Crítica de calidad de señal de la ruptura BO(96, 2.5) en 1h del Gestor de Riesgo (solo DISEÑO).
Velas de 1h agregadas desde 15m (como riesgo_sim.load). z = (C - SMA96)/std96 > 2.5. ATR14 = media simple de TR.
Salidas del Gestor: (a) chandelier m=3 ATR, H=192; (b) TP=1.5 ATR, SL=4 ATR, H=48. Simulación con harness.simulate.
1) Reproducción.  2) Azar emparejado: por cada operación, 30 entradas en velas aleatorias de 1h del mismo mes y
moneda con la MISMA regla de salida (ATR de esa vela): Δ por operación (pareado) con t iid y agrupado por mes.
3) Régimen: BTC sobre/bajo su SMA de 30 días al entrar; meses alcistas/bajistas de BTC; por año."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import harness as H
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

lines = []
P = lambda s: (print(s), lines.append(s))
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT")


def bars_1h(sym):
    b = H.load(sym)
    i0, i1 = H.bounds(b, "design")
    t, o, h, l, c, v, tb = b.t[i0:i1], b.o[i0:i1], b.h[i0:i1], b.l[i0:i1], b.c[i0:i1], b.v[i0:i1], b.tbv[i0:i1]
    key = t // 3600000
    st = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    en = np.r_[st[1:] - 1, len(t) - 1]
    arr = np.column_stack([t[st].astype(float), o[st], np.maximum.reduceat(h, st), np.minimum.reduceat(l, st), c[en],
                           np.add.reduceat(v, st), np.add.reduceat(tb, st)])
    return H.Bars(arr, sym, "1h")


def atr_simple(b, n=14):
    pc = np.r_[b.c[0], b.c[:-1]]
    tr = np.maximum(b.h - b.l, np.maximum(np.abs(b.h - pc), np.abs(b.l - pc)))
    return H.rolling_mean(tr, n)


EXITS = {"CHAN m=3 H=192": dict(kind="chan", m=3.0, H=192), "ATR a=1.5 m=4 H=48": dict(kind="atr", a=1.5, m=4.0, H=48)}


def sim(b, ent, A, ex):
    if ex["kind"] == "chan":
        return H.simulate(b, ent, None, b.c - ex["m"] * A, trail=ex["m"] * A, max_hold=ex["H"], risk=ex["m"] * A)
    return H.simulate(b, ent, b.c + ex["a"] * A, b.c - ex["m"] * A, max_hold=ex["H"])


def main():
    rng = np.random.default_rng(11)
    B = {s: bars_1h(s) for s in SYMS}
    btc = B["BTCUSDT"]
    sma30 = H.rolling_mean(btc.c, 720)
    n_cfg = 0
    for exname, ex in EXITS.items():
        P(f"\n=== BO(96, 2.5) 1h, salida {exname} ===")
        trs, rnd_mean, rnd_wr = [], [], []
        for s in SYMS:
            b = B[s]
            mu, sd = H.rolling_mean(b.c, 96), H.rolling_std(b.c, 96)
            A = atr_simple(b)
            with np.errstate(invalid="ignore"):
                ent = (b.c - mu) / sd > 2.5
            ent &= np.isfinite(A)
            ent[len(b) - 1 - 960:] = False   # igual que riesgo_sim (HMAX=960 velas)
            tr = sim(b, ent, A, ex)
            trs.append(tr)
            # azar emparejado
            mon = b.month
            rm, rw = [], []
            for k in range(len(tr)):
                cand = np.flatnonzero((mon == mon[tr.entry_idx[k]]) & np.isfinite(A))
                cand = cand[cand < len(b) - 2]
                js = rng.choice(cand, 30)
                e2 = np.zeros(len(b), bool)
                vals = []
                for j in js:   # una por una (la regla de una posición no aplica al control)
                    e2[:] = False; e2[j] = True
                    t2 = sim(b, e2, A, ex)
                    vals.append(t2.net_ret[0] if len(t2) else np.nan)
                vals = np.array(vals)
                rm.append(np.nanmean(vals)); rw.append(np.nanmean(vals > 0))
            rnd_mean.append(np.array(rm)); rnd_wr.append(np.array(rw))
        T = H.Trades.concat(trs)
        order = np.argsort(np.concatenate([t.entry_t for t in trs]), kind="stable")
        rmean = np.concatenate(rnd_mean)[order]; rwr = np.concatenate(rnd_wr)[order]
        m = H.metrics(T)
        n_cfg += 1
        P(f"Reproducción: N={m['n']} WR={m['wr']*100:.1f}% [{m['wr_lo']*100:.1f},{m['wr_hi']*100:.1f}] b={m['b_eff']:.2f} "
          f"E={m['E_pct']:+.3f}% (t={m['t']:+.2f}) E_R={m['E_R']:+.3f} PF={m['pf']:.2f}")
        d = T.net_ret - rmean
        mon = T.entry_t.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)
        u, inv = np.unique(mon, return_inverse=True)
        res = np.bincount(inv, weights=d - d.mean())
        se_c = np.sqrt((res ** 2).sum()) / len(d) * np.sqrt(len(u) / (len(u) - 1))
        P(f"Azar emparejado (mismo mes/moneda/salida): WR azar={np.nanmean(rwr)*100:.1f}%  E azar={np.nanmean(rmean)*100:+.3f}% | "
          f"Δp={(m['wr']-np.nanmean(rwr))*100:+.1f}pp  ΔE={np.nanmean(d)*100:+.3f}% (t pareado={np.nanmean(d)/(np.nanstd(d,ddof=1)/np.sqrt(len(d))):+.2f}, "
          f"t agrupado por mes={np.nanmean(d)/se_c:+.2f})")
        # régimen
        pos = np.searchsorted(btc.t, T.entry_t)
        up = btc.c[pos] > sma30[pos]
        mret = {}
        for uu in np.unique(mon):
            sel = btc.month == int((1970 + uu // 12) * 100 + (uu % 12) + 1)
            ii = np.flatnonzero(sel)
            mret[uu] = btc.c[ii[-1]] / btc.o[ii[0]] - 1
        bull = np.array([mret[x] > 0 for x in mon])
        yr = (1970 + mon // 12)
        for lab, mk in (("BTC > SMA30d", up), ("BTC < SMA30d", ~up), ("mes BTC alcista", bull), ("mes BTC bajista", ~bull)) + \
                tuple((f"año {y}", yr == y) for y in np.unique(yr)):
            mm = H.metrics(T.subset(mk))
            dd = d[mk]
            P(f"   {lab:16s}: N={mm['n']:4d} WR={mm['wr']*100:4.1f}% E={mm['E_pct']:+.3f}% (t={mm['t']:+.2f}) E_R={mm['E_R']:+.3f} | "
              f"ΔE vs azar={np.nanmean(dd)*100:+.3f}% (t={np.nanmean(dd)/(np.nanstd(dd,ddof=1)/np.sqrt(max(2,len(dd)))):+.2f})")
    H.log_trials("analista", n_cfg, "R2 critica BO(96,2.5) 1h del Gestor: reproduccion + azar emparejado + regimen", "design")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", "analista", "14_bo1h.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
