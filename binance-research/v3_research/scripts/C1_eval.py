"""C1_eval.py - evaluación PRE-REGISTRADA de la señal C1 (Analista, ronda 2). Sin parámetros libres.

Uso (desde research/scripts):
    python -I C1_eval.py --start 2023-10-01 --end 2025-07-01                       # OOS de DISEÑO
    python -I C1_eval.py --start 2025-07-01 --end 2026-10-01 --reason "C1 prueba única pre-registrada"  # HOLDOUT

Especificación (copiada en output/analista/C1_spec.json):
  Datos   : velas CERRADAS de 15m de BTC, ETH, SOL y DOGE (klines/*.npy). Se cargan desde 2023-01-01 y se
            truncan en --end: nada posterior a --end entra al cálculo.
  Señal   : z = (C - SMA20)/std20 (precios, ddof=1) < -2  y  R = (SMA20 - C)/C >= 0.005, índice >= 900.
  Variables: las 39 de analista_features.FEATURES (las 41 menos 'hour' y 'dow', incluidas las 5 que cruzan monedas)
            + sin/cos(2*pi*hora/24) + 4 indicadoras de moneda = 45 columnas. Todas causales (dato <= cierre de la vela).
  Modelo  : ridge con intercepto no penalizado, lambda = 0.1*N_train, objetivo clip(C[i+96]/C[i]-1, ±0.20).
            Re-ajuste al inicio de cada mes calendario UTC con TODAS las señales de las 4 monedas desde 2023-01-01
            cuyo objetivo ya se conocía: cierre de la vela i+96 <= inicio del mes (purga de 96 velas).
            Estandarización (media, desv.) y umbral calculados SOLO con el entrenamiento; z-scores recortados a ±5,
            NaN -> 0.
  Regla   : BUY si score >= cuantil 0.90 de los scores del entrenamiento de ese mes.
  Salida PRIMARIA  (G3H96): entrada al cierre C; TP = SMA20 de la vela de señal; SL = C - 3*(SMA20 - C);
            barrera de tiempo 96 velas (24 h); TP y SL en la misma vela = SL; hueco bajo SL = apertura.
  Salida SECUNDARIA (T48) : entrada al cierre; salida solo por tiempo al cierre de la vela i+48 (12 h).
  Ejecución: harness.simulate (una posición por moneda, costos 0.10 % + 0.02 % por lado).
  Prueba pre-registrada (holdout): APRUEBA si, en la geometría PRIMARIA con las 4 monedas juntas,
            (1) p unilateral de E>0 por operación (harness.metrics p_value) < 0.05 Y
            (2) t con errores agrupados por día UTC > 1.645.
            Se informan además el WR y su IC de Wilson (criterio P5 del Validador), la secundaria y las pruebas
            de estrés (costos 0.30 %, entrada en apertura siguiente) como información, sin poder de veto propio.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import harness as H
import analista_features as af

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT")
T0 = H.ms(2023, 1, 1)
HZ = 96          # horizonte del objetivo (velas)
Q = 0.90         # cuantil del umbral
LAM = 0.1        # lambda = LAM * N_train
FEATS = [f for f in af.FEATURES if f not in ("hour", "dow")]
GEOMS = {"PRIMARIA_G3H96": dict(m_sl=3.0, max_hold=96), "SECUNDARIA_T48": dict(m_sl=None, max_hold=48)}
SPEC_PATH = os.path.abspath(os.path.join(HERE, "..", "output", "analista", "C1_spec.json"))
FROZEN_FILES = ("analista_features.py", "analista_common.py", "C1_eval.py")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_frozen(strict=True):
    if not os.path.exists(SPEC_PATH):
        return
    spec = json.load(open(SPEC_PATH, encoding="utf-8"))
    for fn, h in spec.get("sha256", {}).items():
        cur = sha(os.path.join(HERE, fn))
        if cur != h:
            msg = f"ARCHIVO MODIFICADO tras el pre-registro: {fn} ({cur[:12]} != {h[:12]})"
            if strict:
                raise SystemExit(msg)
            print("AVISO:", msg)


def month_start(t_ms):
    d = dt.datetime.fromtimestamp(t_ms / 1000, dt.timezone.utc)
    return H.ms(d.year, d.month, 1)


def next_month(t_ms):
    d = dt.datetime.fromtimestamp(t_ms / 1000, dt.timezone.utc)
    return H.ms(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)


def load_until(end_ms, reason=None, start_ms=None):
    """Barras completas truncadas en end_ms. Si el rango toca el holdout, exige reason (queda registrado)."""
    bars, data = {}, {}
    for s in SYMS:
        b = H.load(s)
        if end_ms > H.HOLDOUT[0]:
            H.bounds(b, (start_ms if start_ms is not None else T0, end_ms), reason=reason, who="C1_eval")
        i1 = b.idx(end_ms)
        i0 = b.idx(T0)
        bb = b.slice(i0, i1)
        bars[s] = bb
        data[s] = dict(t=bb.t, o=bb.o, h=bb.h, l=bb.l, c=bb.c, v=bb.v, tb=bb.tbv, sym=s)
    t_ref = bars[SYMS[0]].t
    for s in SYMS[1:]:
        assert np.array_equal(bars[s].t, t_ref), "timestamps desalineados entre monedas"
    return bars, data


def signal_table(data, Fs):
    rows = []
    for si, s in enumerate(SYMS):
        F = Fs[s]; c = data[s]["c"]; t = data[s]["t"]
        with np.errstate(invalid="ignore"):
            idx = np.flatnonzero((F["z"] < -2) & (F["R_pct"] >= 0.005))
        idx = idx[idx >= 900]
        X = np.column_stack([F[f][idx] for f in FEATS] +
                            [np.sin(2 * np.pi * F["hour"][idx] / 24), np.cos(2 * np.pi * F["hour"][idx] / 24)] +
                            [np.full(len(idx), 1.0 if j == si else 0.0) for j in range(4)])
        y = np.full(len(idx), np.nan)
        t_known = np.full(len(idx), np.inf)          # instante en que el objetivo se conoce (cierre de i+HZ)
        ok = idx + HZ < len(c)
        y[ok] = c[idx[ok] + HZ] / c[idx[ok]] - 1
        t_known[ok] = t[idx[ok] + HZ] + 900000
        rows.append(dict(si=np.full(len(idx), si), idx=idx, X=X, y=y, t=t[idx], t_known=t_known))
    return {k: np.concatenate([r[k] for r in rows]) for k in rows[0]}


def fit_predict(Xtr, ytr, Xte, lam=LAM, q=Q):
    mu = np.nanmean(Xtr, 0)
    sd = np.nanstd(Xtr, 0)
    sd[~(sd > 0)] = 1.0
    mu = np.nan_to_num(mu)

    def Z(A):
        return np.hstack([np.ones((len(A), 1)), np.nan_to_num(np.clip((A - mu) / sd, -5, 5))])

    Zt = Z(Xtr)
    L = lam * len(Xtr) * np.eye(Zt.shape[1])
    L[0, 0] = 0.0
    w = np.linalg.solve(Zt.T @ Zt + L, Zt.T @ np.clip(ytr, -0.2, 0.2))
    ptr = Zt @ w
    return Z(Xte) @ w, float(np.quantile(ptr, q)), w


def scores(ST, start_ms, end_ms, train_window_months=None, lam=LAM, q=Q):
    """Puntúa las señales con t en [start, end). Re-ajuste mensual. train_window_months=None -> expansivo
    desde 2023-01 (ESPECIFICACIÓN); un entero -> ventana móvil (solo para pruebas de protocolo)."""
    take = np.zeros(len(ST["t"]), bool)
    score = np.full(len(ST["t"]), np.nan)
    thr = np.full(len(ST["t"]), np.nan)
    m = month_start(start_ms)
    log = []
    while m < end_ms:
        m2 = next_month(m)
        te = (ST["t"] >= max(m, start_ms)) & (ST["t"] < min(m2, end_ms))
        tr = (ST["t_known"] <= m) & np.isfinite(ST["y"])
        if train_window_months is not None:
            lo = m
            for _ in range(train_window_months):
                d = dt.datetime.fromtimestamp(lo / 1000, dt.timezone.utc)
                lo = H.ms(d.year - (d.month == 1), 12 if d.month == 1 else d.month - 1, 1)
            tr &= ST["t"] >= lo
        if te.any() and tr.sum() > 100:
            p, th, _ = fit_predict(ST["X"][tr], ST["y"][tr], ST["X"][te], lam, q)
            score[te] = p
            thr[te] = th
            take[te] = p >= th
            log.append((m, int(tr.sum()), int(te.sum()), int(take[te].sum()),
                        float(ST["t_known"][tr].max()) if tr.any() else None))
        m = m2
    return take, score, thr, log


def simulate_all(bars, data, ST, take, start_ms, end_ms, geom, fee=H.FEE, slip=H.SLIP, entry_mode="close"):
    out = []
    for si, s in enumerate(SYMS):
        b = bars[s]
        ent = np.zeros(len(b), bool)
        ent[ST["idx"][(ST["si"] == si) & take]] = True
        mu = H.rolling_mean(b.c, 20)
        R = mu - b.c
        g = GEOMS[geom] if isinstance(geom, str) else geom
        tp = mu if g["m_sl"] else None
        sl = (b.c - g["m_sl"] * R) if g["m_sl"] else None
        tr = H.simulate(b, ent, tp, sl, period=(b.idx(start_ms), b.idx(end_ms)), max_hold=g["max_hold"],
                        risk=(None if g["m_sl"] else R), fee=fee, slip=slip, entry_mode=entry_mode,
                        levels="relative")
        out.append(tr)
    return out


def clustered_t(tr, unit="day"):
    x = np.asarray(tr.net_ret, float)
    if len(x) < 3:
        return float("nan"), 0
    key = tr.entry_t // 86400000 if unit == "day" else tr.entry_t.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)
    u, inv = np.unique(key, return_inverse=True)
    mu = x.mean()
    resid = np.bincount(inv, weights=x - mu)
    G = len(u)
    se = np.sqrt((resid ** 2).sum()) / len(x) * np.sqrt(G / max(1, G - 1))
    return float(mu / se) if se > 0 else float("nan"), G


def summarize(trs, label, years=None):
    T = H.Trades.concat(trs)
    m = H.metrics(T, boot=4000, block=10, years=years)
    td, nd = clustered_t(T, "day")
    tm, nm = clustered_t(T, "month")
    m.update({"t_cluster_day": td, "n_days": nd, "t_cluster_month": tm, "n_months": nm,
              "per_coin": {s: {k: H.metrics(t)[k] for k in ("n", "wr", "E_pct", "t", "pf")} for s, t in zip(SYMS, trs)}})
    return m


def run(start_ms, end_ms, reason=None, verbose=True):
    bars, data = load_until(end_ms, reason, start_ms)
    Fs = af.add_cross({s: af.build(data[s], 20) for s in SYMS}, list(SYMS))
    ST = signal_table(data, Fs)
    take, score, thr, log = scores(ST, start_ms, end_ms)
    yrs = (end_ms - start_ms) / (365.25 * 86400e3)
    res = {"start": H.iso(start_ms), "end": H.iso(end_ms), "n_signals": int(((ST["t"] >= start_ms) & (ST["t"] < end_ms)).sum()),
           "n_taken_signals": int(take.sum()),
           "purge_ok": all(r[4] is None or r[4] <= r[0] for r in log), "refits": len(log)}
    for g in GEOMS:
        res[g] = summarize(simulate_all(bars, data, ST, take, start_ms, end_ms, g), g, yrs)
    res["ESTRES_costos_0.30_primaria"] = summarize(simulate_all(bars, data, ST, take, start_ms, end_ms, "PRIMARIA_G3H96", slip=0.0005), "c030", yrs)
    res["ESTRES_next_open_primaria"] = summarize(simulate_all(bars, data, ST, take, start_ms, end_ms, "PRIMARIA_G3H96", entry_mode="next_open"), "next_open", yrs)
    p = res["PRIMARIA_G3H96"]
    q = res["SECUNDARIA_T48"]
    ok1 = bool(p["p_value"] < 0.05 and p["t_cluster_day"] > 1.645)
    # procedimiento de secuencia fija (gatekeeping): la secundaria solo se prueba si la primaria aprueba (FWER = 0.05)
    ok2 = bool(ok1 and q["p_value"] < 0.05 and q["t_cluster_day"] > 1.645)
    res["DECISION"] = {"p_value_iid": p["p_value"], "t_cluster_day": p["t_cluster_day"], "APRUEBA": ok1,
                       "WR_dentro_IC_diseño_[68.2,76.2]": bool(0.682 <= p["wr"] <= 0.762),
                       "SECUNDARIA_APRUEBA_(solo si la primaria aprueba)": ok2}
    if verbose:
        for k in ("PRIMARIA_G3H96", "SECUNDARIA_T48", "ESTRES_costos_0.30_primaria", "ESTRES_next_open_primaria"):
            m = res[k]
            print(f"{k:28s} N={m['n']:4d} WR={m['wr']*100:5.1f}% [{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}] "
                  f"b={m['b_eff']:.2f} E={m['E_pct']:+.3f}% (t={m['t']:+.2f}, p={m['p_value']:.4f}; t_día={m['t_cluster_day']:+.2f}, "
                  f"t_mes={m['t_cluster_month']:+.2f}) E_R={m['E_R']:+.3f} PF={m['pf']:.2f} MDD={m['mdd_pct']:.1f}% "
                  f"MDD_R={m['mdd_R']:.1f} rachaP={m['max_loss_streak']} R_med={m['risk_med_pct']:.2f}% "
                  f"ops/año={m['trades_per_year']:.0f} IC_boot=[{m.get('E_boot_lo_pct', float('nan')):+.3f},{m.get('E_boot_hi_pct', float('nan')):+.3f}]")
            if k in ("PRIMARIA_G3H96", "SECUNDARIA_T48"):
                print("      por moneda: " + "  ".join(f"{s[:4]} n={v['n']} WR={v['wr']*100:.0f}% E={v['E_pct']:+.2f}%"
                                                    for s, v in m["per_coin"].items()))
        print(f"señales={res['n_signals']} tomadas por el filtro={res['n_taken_signals']} reajustes={res['refits']} purga_ok={res['purge_ok']}")
        print("DECISIÓN PRE-REGISTRADA:", res["DECISION"])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--reason", default=None, help="obligatorio si el rango toca el holdout (queda registrado)")
    a = ap.parse_args()
    check_frozen(strict=True)
    s = dt.datetime.strptime(a.start, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    e = dt.datetime.strptime(a.end, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    res = run(int(s.timestamp() * 1000), int(e.timestamp() * 1000), a.reason)
    out = os.path.join(HERE, "..", "output", "analista", f"C1_eval_{a.start}_{a.end}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
    print("guardado:", os.path.abspath(out))


if __name__ == "__main__":
    main()
