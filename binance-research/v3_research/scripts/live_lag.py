"""Cuantifica el desfase en vivo: fotos de ~6 s de la vela de 1m en curso frente a velas cerradas de 15m.

Datos: klines/{SYM}_1s.npy (14 dias, 2025-06-02..2025-06-15, dentro de DISENO).
Modelo del bot en vivo (ws-client.ts + server.py):
  * stream kline_1m: una actualizacion cada 2 s; el precio es k.c = ultimo precio negociado (= cierre de 1 s);
  * evaluacion de Python solo si pasaron > 5 s desde la anterior  => una foto cada 6 s;
  * con posicion abierta: no se evalua (ventana congelada) y se vigila TP/SL en cada actualizacion (2 s),
    cerrando al precio actual (no al nivel de la barrera);
  * arranque: pre_seed_engine con las ultimas 100 velas CERRADAS de 1m;
  * TP/SL redondeados a 2 decimales (round(x, 2)).
Salida: output/validador/live_lag.md / .json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import bot_replica as BR  # noqa: E402

LIVE = {"BTCUSDT": ("MR", 8, 1.4), "ETHUSDT": ("MR", 20, 2.0), "SOLUSDT": ("MR", 88, 0.8), "DOGEUSDT": ("TF", 24, 0.8)}
PHOTO_S, MONITOR_S = 6, 2


def grid_1s(b):
    """Cierres de 1 s en una grilla regular (rellena segundos sin operaciones con el ultimo cierre)."""
    t0 = int(b.t[0])
    n = int((b.t[-1] - t0) // 1000) + 1
    pos = ((b.t - t0) // 1000).astype(np.int64)
    c = np.full(n, np.nan)
    c[pos] = b.c
    idx = np.where(np.isfinite(c), np.arange(n), 0)
    np.maximum.accumulate(idx, out=idx)
    return t0, c[idx]


def window_stats(p, n):
    mu, sd = H.rolling_mean(p, n), H.rolling_std(p, n)
    return mu, sd


def signal_stats(p, code, n, k):
    """Senales con ventana continua (sin restriccion de posicion) y R en % del precio."""
    mu, sd = window_stats(p, n)
    with np.errstate(invalid="ignore"):
        if code == "MR":
            raw = p < mu - k * sd
            R = (mu - p) / p
            ok = raw & (R >= 0.005)
        else:
            raw = p > mu + k * sd
            R = (p - mu) / p
            ok = raw.copy()
    rel = sd / mu
    return {"sigma_rel_med_pct": float(np.nanmedian(rel) * 100), "raw_signals": int(np.nansum(raw)),
            "signals_after_filter": int(np.nansum(ok)),
            "R_med_pct_raw": float(np.nanmedian(R[raw]) * 100) if raw.any() else float("nan"),
            "R_med_pct_ok": float(np.nanmedian(R[ok]) * 100) if ok.any() else float("nan")}


def live_sim(c1s, pre_seed, code, n, k, rounding=True):
    """Simulacion por eventos del bot en vivo sobre la grilla de 1 s."""
    st = BR.BotStrategy(code, n, k, rounding)
    for x in pre_seed:  # 100 velas cerradas de 1m
        st.evaluate(float(x))
    trades = []
    T = len(c1s)
    s = 0
    mon = c1s[::MONITOR_S]
    while s < T:
        price = float(c1s[s])
        sig = st.evaluate(price)
        if sig is None:
            s += PHOTO_S
            continue
        tp, sl = sig
        entry = price
        # vigilancia cada 2 s desde la siguiente actualizacion
        m0 = s // MONITOR_S + 1
        seg = mon[m0:]
        hit = (seg >= tp) | (seg <= sl)
        if not hit.any():
            trades.append((s, T - 1, entry, float(c1s[-1]), tp, sl, "end"))
            break
        j = int(np.argmax(hit))
        px = float(seg[j])
        why = "tp" if px >= tp else "sl"
        e = (m0 + j) * MONITOR_S
        trades.append((s, e, entry, px, tp, sl, why))
        # la siguiente evaluacion: primera actualizacion (cada 2 s) tras el cierre con > 5 s desde la ultima evaluacion
        s = max(e + MONITOR_S, s + PHOTO_S)
    return trades


out = {}
md = ["# Desfase en vivo: fotos de ~6 s frente a velas cerradas de 15m", "",
      "Datos: 14 dias de velas de 1 s (2025-06-02 .. 2025-06-15, DISENO). Configuracion vigente de cada moneda.", "",
      "| Moneda (estrategia n/k) | Ventana en vivo | Ventana en backtest | sigma/precio en vivo | sigma/precio 15m | razon | senales/dia vivo (tras filtro) | senales/dia 15m | R mediano vivo % | R mediano 15m % | p* vivo | p* 15m |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|"]
md_sim = ["", "## Simulacion del bot en vivo (fotos 6 s, vigilancia 2 s, ventana congelada, redondeo) vs. bot fiel con velas de 15m", "",
          "| Moneda | Modo | operaciones | op./dia | WR neto % | TP % | invalidas (TP<=entrada o SL>=entrada) | E neta % | E bruta % | duracion mediana | R mediano % |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
for sym, (code, n, k) in LIVE.items():
    b1 = H.load(sym, "1s")
    t0, c1s = grid_1s(b1)
    days = len(c1s) / 86400
    photos = c1s[::PHOTO_S]
    # 15m del mismo periodo (indicadores con calentamiento de la serie completa)
    b15 = H.load(sym)
    i0, i1 = b15.idx(t0), b15.idx(t0 + len(c1s) * 1000)
    mu15, sd15 = window_stats(b15.c, n)
    sub = b15.c[i0 - n:i1]
    s_live = signal_stats(photos, code, n, k)
    s_15 = signal_stats(sub, code, n, k)
    s_15 = {kk: v for kk, v in s_15.items()}
    sig15_days = (i1 - i0) / 96
    b = BR.B_REAL[code]
    pstar = lambda R: H.breakeven_p(b, R, H.COST_RT * 100) if np.isfinite(R) and R > 0 else float("nan")  # noqa: E731
    row = {"live": s_live, "m15": s_15, "days": days, "window_live_s": n * PHOTO_S, "window_15m_h": n * 15 / 60}
    md.append(f"| {sym} ({code} {n}/{k}) | {n*PHOTO_S} s | {n*15/60:.1f} h | {s_live['sigma_rel_med_pct']:.3f} % | {s_15['sigma_rel_med_pct']:.3f} % | "
              f"{s_live['sigma_rel_med_pct']/s_15['sigma_rel_med_pct']:.3f} | {s_live['signals_after_filter']/days:.0f} ({s_live['raw_signals']/days:.0f} brutas) | "
              f"{s_15['signals_after_filter']/sig15_days:.1f} ({s_15['raw_signals']/sig15_days:.1f}) | {s_live['R_med_pct_ok']:.3f} | {s_15['R_med_pct_ok']:.3f} | "
              f"{pstar(s_live['R_med_pct_ok'])*100:.0f} % | {pstar(s_15['R_med_pct_ok'])*100:.0f} % |")
    # simulacion en vivo
    pre = c1s[:6000][59::60][:100]  # 100 cierres de 1m (primeros 100 minutos) como pre-seed
    start = 6000
    tr = live_sim(c1s[start:], pre, code, n, k, rounding=True)
    ent = np.array([x[2] for x in tr])
    ex = np.array([x[3] for x in tr])
    tps = np.array([x[4] for x in tr])
    sls = np.array([x[5] for x in tr])
    if len(tr) == 0:
        ent = ex = tps = sls = np.array([np.nan])
    net = H.net_return(ent, ex)
    gross = ex / ent - 1
    inval = (tps <= ent) | (sls >= ent)
    dur = np.array([x[1] - x[0] for x in tr])
    Rp = np.where(sls < ent, (ent - sls) / ent * 100, np.nan)
    d_live = (len(c1s) - start) / 86400
    row["sim_live"] = {"n": len(tr), "per_day": len(tr) / d_live, "wr": float(np.mean(net > 0)), "tp_rate": float(np.mean([x[6] == "tp" for x in tr])),
                       "invalid": int(inval.sum()), "E_pct": float(net.mean() * 100), "E_gross_pct": float(gross.mean() * 100),
                       "dur_med_s": float(np.median(dur)), "R_med_pct": float(np.nanmedian(Rp)) if np.isfinite(Rp).any() else float("nan")}
    sl_ = row["sim_live"]
    md_sim.append(f"| {sym} | vivo (6 s) | {sl_['n']} | {sl_['per_day']:.1f} | {sl_['wr']*100:.1f} | {sl_['tp_rate']*100:.1f} | {sl_['invalid']} | "
                  f"{sl_['E_pct']:+.3f} | {sl_['E_gross_pct']:+.3f} | {sl_['dur_med_s']/60:.1f} min | {sl_['R_med_pct']:.3f} |")
    # bot fiel con velas de 15m en los mismos dias
    tr15 = BR.run_frozen(b15, code, n, k, (i0, i1), rounding=True)
    m15 = H.metrics(tr15)
    row["sim_15m"] = m15
    md_sim.append(f"| {sym} | velas 15m | {m15['n']} | {m15['n']/sig15_days:.2f} | {m15['wr']*100 if m15['n'] else float('nan'):.1f} | "
                  f"{m15.get('tp_rate', float('nan'))*100:.1f} | {int(np.sum(tr15.reason == H.INVALID))} | {m15.get('E_pct', float('nan')):+.3f} | "
                  f"{m15.get('E_gross_pct', float('nan')):+.3f} | {m15.get('hold_med_bars', float('nan'))*15:.0f} min | {m15.get('risk_med_pct', float('nan')):.3f} |")
    out[sym] = row
    print(sym, json.dumps({kk: (v if not isinstance(v, dict) else {a: round(c, 4) if isinstance(c, float) else c for a, c in v.items()}) for kk, v in row.items() if kk != "sim_15m"}))
    print("   15m:", H.fmt(m15, "bot fiel 15m"))
md += md_sim
md += ["", "p* = (1 + c/R)/(1 + b) con c = 0.24 % y el R mediano de las senales (tras el filtro del 0.5 % en MR)."]
open(os.path.join(H.VALIDADOR_DIR, "live_lag.md"), "w", encoding="utf-8").write("\n".join(md))
json.dump(out, open(os.path.join(H.VALIDADOR_DIR, "live_lag.json"), "w"), indent=1, default=float)
