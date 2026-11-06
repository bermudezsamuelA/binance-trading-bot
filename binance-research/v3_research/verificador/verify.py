#!/usr/bin/env python
"""verify.py -- verificacion independiente de una lista de operaciones (Agente Verificador).

Independiente del arnes: solo numpy + scipy; NO importa harness.py (reimplementa salidas, costos y metricas).

ENTRADA (CSV, una fila por operacion; acepta el CSV de harness.Trades.to_csv + columnas extra):
  symbol        moneda (p. ej. XRPUSDT)                          [o --symbol si todo el CSV es de una moneda]
  entry_t       open_time (ms) de la vela de ENTRADA e            (alias: entry_time_ms)
  entry_mode    "close"  -> entra a c[e], barreras desde e+1      [o --entry-mode; por defecto close]
                "next_open" -> entra a o[e], barreras desde e (incluida)
  entry_px, exit_px, exit_t (open_time ms de la vela de salida)
  tp, sl        precios absolutos (vacio/NaN = sin barrera)
  H             barrera de tiempo en velas (vacio = sin limite)   [o --H]
Reglas de salida (pesimistas, iguales a las del protocolo): high/low; TP y SL en la misma vela -> SL;
stop con hueco (open <= SL) -> sale al open; TP exacto; tiempo -> cierre de la vela j0+H-1; nunca usa velas
>= fin del periodo (sale al cierre de la ultima, END).  Costos: net = g-1 - k*(1+g), k = fee+slip por lado
(0.0012 -> ~0.24 % ida y vuelta; estres 0.0015 -> ~0.30 %).

SALIDA: n, WR (Wilson 95 %), b efectivo, WR de equilibrio, E neta (% y R), E con 0.30 %, PF, MDD, t i.i.d.
y t agrupado por dia UTC (CR1), CONTROL ALEATORIO emparejado (misma moneda, mismo mes, misma geometria
relativa, entradas al azar, R repeticiones) con dWR y dE y su significancia (pareada agrupada por dia y por
repeticiones), DSR con el numero total de configuraciones, y evaluacion de los criterios pre-registrados
(research/output/verificador/preregistro_nn.md).

USO
  python -I verify.py trades.csv --period 2025-07-01 2026-10-01 [--reps 200] [--extra-trials N]
                       [--audit-ok|--audit-fail] [--json out.json]
  python -I verify.py trades.csv ... --final primaria --reason "ejecucion unica NN v1"   (registro unico)
  python -I verify.py --selftest
"""
import argparse, csv, datetime as dt, hashlib, json, math, os, sys
import numpy as np
from scipy import stats

BAR = 900_000
COST = 0.0012          # fee 0.10 % + slip 0.02 % por lado
COST_STRESS = 0.0015   # ~0.30 % ida y vuelta
HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.dirname(HERE)
DATA_DIRS = [os.path.join(HERE, "data"), os.path.join(RESEARCH, "klines")]
OUT_DIR = os.path.join(RESEARCH, "output", "verificador")
TRIALS_LOG = os.path.join(RESEARCH, "output", "validador", "trials_log.csv")
EXEC_LOG = os.path.join(OUT_DIR, "ejecuciones_log.csv")
Z95 = 1.959963984540054


# ----------------------------------------------------------------------------------------- datos
_BARS = {}


def load_bars(sym):
    if sym in _BARS:
        return _BARS[sym]
    for d in DATA_DIRS:
        p = os.path.join(d, f"{sym}_15m.npy")
        if os.path.exists(p):
            a = np.load(p)
            b = {"t": a[:, 0].astype(np.int64), "o": a[:, 1], "h": a[:, 2], "l": a[:, 3], "c": a[:, 4], "path": p}
            _BARS[sym] = b
            return b
    raise FileNotFoundError(sym)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def to_ms(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


# ----------------------------------------------------------------------------------------- salidas
def net_of(entry, exit_, k=COST):
    g = np.asarray(exit_, float) / np.asarray(entry, float)
    return (g - 1.0) - k * (1.0 + g)


def first_exit(b, j0, jlim, entry, tp, sl):
    """(j, precio, motivo) con motivo 0 TP, 1 SL, 2 TIME/END. Barreras desde j0 (incluida) hasta jlim (excluida)."""
    if jlim <= j0:
        return j0 - 1, entry, 2
    h, l, o, c = b["h"], b["l"], b["o"], b["c"]
    has_tp, has_sl = np.isfinite(tp), np.isfinite(sl)
    k, step = j0, 96
    while k < jlim:
        k2 = min(jlim, k + step)
        hs = (l[k:k2] <= sl) if has_sl else np.zeros(k2 - k, bool)
        ht = (h[k:k2] >= tp) if has_tp else np.zeros(k2 - k, bool)
        any_ = hs | ht
        if any_.any():
            m = int(np.argmax(any_))
            j = k + m
            if hs[m]:
                return j, float(min(sl, o[j])), 1
            return j, float(tp), 0
        k, step = k2, step * 4
    return jlim - 1, float(c[jlim - 1]), 2


def replay(tr, period_end_ms):
    """Re-simula cada operacion con los datos; devuelve exit_px y exit_t recalculados y discrepancias."""
    n = len(tr["symbol"])
    px = np.full(n, np.nan); jt = np.zeros(n, np.int64); why = np.zeros(n, np.int64)
    bad_entry = np.zeros(n, bool)
    for i in range(n):
        b = load_bars(tr["symbol"][i])
        e = int(np.searchsorted(b["t"], tr["entry_t"][i]))
        if e >= len(b["t"]) or b["t"][e] != tr["entry_t"][i]:
            bad_entry[i] = True; continue
        close_mode = tr["entry_mode"][i] == "close"
        ent = b["c"][e] if close_mode else b["o"][e]
        if abs(ent / tr["entry_px"][i] - 1) > 1e-9:
            bad_entry[i] = True
        j0 = e + 1 if close_mode else e
        iend = int(np.searchsorted(b["t"], period_end_ms))
        H = tr["H"][i]
        jlim = iend if not np.isfinite(H) else min(iend, j0 + int(H))
        j, p, r = first_exit(b, j0, jlim, tr["entry_px"][i], tr["tp"][i], tr["sl"][i])
        j = max(j, e)
        px[i], jt[i], why[i] = p, b["t"][j], r
    mism = (~bad_entry) & ((np.abs(px / tr["exit_px"] - 1) > 1e-7) | (jt != tr["exit_t"]))
    return {"exit_px": px, "exit_t": jt, "reason": why, "bad_entry": bad_entry, "mismatch": mism}


# ----------------------------------------------------------------------------------------- estadistica
def wilson(k, n, z=Z95):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    cen = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, cen - half, cen + half


def t_cluster(x, groups):
    """t de la media con varianza robusta por conglomerados (CR1). Devuelve (t, G)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return float("nan"), 0
    m = x.mean()
    _, inv = np.unique(groups, return_inverse=True)
    G = inv.max() + 1
    s = np.bincount(inv, weights=x - m)
    if G < 2:
        return float("nan"), G
    v = (s ** 2).sum() / n ** 2 * G / (G - 1)
    return (m / math.sqrt(v) if v > 0 else float("nan")), int(G)


def max_dd(curve, additive):
    peak = np.maximum.accumulate(curve)
    return float(((peak - curve) if additive else (1 - curve / peak)).max()) if len(curve) else float("nan")


def expected_max_sr(n_trials, var_sr):
    if n_trials <= 1:
        return 0.0
    g = 0.5772156649015329
    return math.sqrt(var_sr) * ((1 - g) * stats.norm.ppf(1 - 1 / n_trials) + g * stats.norm.ppf(1 - 1 / (n_trials * math.e)))


def dsr(x, n_trials):
    x = np.asarray(x, float); n = len(x)
    if n < 4 or x.std(ddof=1) == 0:
        return {"sr": float("nan"), "sr0": float("nan"), "dsr": float("nan"), "n_trials": n_trials}
    sr = x.mean() / x.std(ddof=1)
    sr0 = expected_max_sr(n_trials, 1.0 / (n - 1))
    sk, ku = float(stats.skew(x)), float(stats.kurtosis(x, fisher=False))
    den = math.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr * sr))
    return {"sr": float(sr), "sr0": float(sr0), "dsr": float(stats.norm.cdf((sr - sr0) * math.sqrt(n - 1) / den)),
            "psr0": float(stats.norm.cdf(sr * math.sqrt(n - 1) / den)), "n_trials": int(n_trials)}


def trials_total(extra=0):
    tot = 0
    if os.path.exists(TRIALS_LOG):
        with open(TRIALS_LOG, encoding="utf-8") as f:
            tot = sum(int(r["n_configs"]) for r in csv.DictReader(f))
    return tot + int(extra)


def day_of(ms):
    return np.asarray(ms, np.int64) // 86_400_000


def block_stats(net, net030, gross, entry_t, exit_t, risk):
    n = len(net)
    out = {"n": int(n)}
    if n == 0:
        return out
    win = net > 0
    p, lo, hi = wilson(int(win.sum()), n)
    aw = net[win].mean() if win.any() else float("nan")
    al = -net[~win].mean() if (~win).any() else float("nan")
    b_eff = aw / al if al and np.isfinite(al) and al > 0 else float("nan")
    t_day, G = t_cluster(net, day_of(entry_t))
    sd = net.std(ddof=1) if n > 1 else float("nan")
    order = np.argsort(exit_t, kind="stable")
    eR = net / risk
    out.update({
        "wr": p, "wr_lo": lo, "wr_hi": hi, "wr_gross": float((gross > 0).mean()),
        "b_eff": float(b_eff), "wr_breakeven": float(1 / (1 + b_eff)) if np.isfinite(b_eff) else float("nan"),
        "E_pct": float(net.mean() * 100), "E_R": float(np.nanmean(eR)) if np.isfinite(eR).any() else float("nan"),
        "E030_pct": float(net030.mean() * 100), "sd_pct": float(sd * 100),
        "risk_med_pct": float(np.nanmedian(risk) * 100) if np.isfinite(risk).any() else float("nan"),
        "pf": float(net[win].sum() / -net[~win].sum()) if (~win).any() and net[~win].sum() < 0 else float("inf"),
        "mdd_comp_pct": max_dd(np.cumprod(1 + net[order]), False) * 100,
        "mdd_add_pct": max_dd(np.cumsum(net[order]), True) * 100,
        "t_iid": float(net.mean() / (sd / math.sqrt(n))) if n > 1 and sd > 0 else float("nan"),
        "t_day": float(t_day), "days": G,
        "p_day": float(1 - stats.norm.cdf(t_day)) if np.isfinite(t_day) else float("nan"),
        "E030_t_day": float(t_cluster(net030, day_of(entry_t))[0]),
    })
    # efecto de diseno del WR por agrupamiento diario (operaciones simultaneas correlacionadas)
    _, inv = np.unique(day_of(entry_t), return_inverse=True)
    Gw = inv.max() + 1
    sw = np.bincount(inv, weights=win - p)
    var_cl = (sw ** 2).sum() / n ** 2 * Gw / max(1, Gw - 1)
    var_iid = max(p * (1 - p), 1e-12) / n
    deff = max(1.0, var_cl / var_iid) if Gw > 1 else 1.0
    n_eff = max(1, int(n / deff))
    out["wr_deff"] = float(deff); out["wr_lo_neff"] = wilson(round(p * n_eff), n_eff)[1]
    return out


# ----------------------------------------------------------------------------------------- control aleatorio
def random_control(tr, period, reps, seed=12345):
    """Para cada operacion k y repeticion r: entrada al azar en la misma moneda y el mismo mes calendario (UTC)
    dentro del periodo, misma geometria relativa (tp/entrada, sl/entrada, H, modo).  Devuelve bruto[k, r]."""
    rng = np.random.default_rng(seed)
    n = len(tr["symbol"])
    G = np.full((n, reps), np.nan)
    p0, p1 = period
    for i in range(n):
        b = load_bars(tr["symbol"][i])
        t = b["t"]
        d = dt.datetime.fromtimestamp(tr["entry_t"][i] / 1000, dt.timezone.utc)
        m0 = int(dt.datetime(d.year, d.month, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        m1 = int(dt.datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        a0 = int(np.searchsorted(t, max(m0, p0))); a1 = int(np.searchsorted(t, min(m1, p1)))
        iend = int(np.searchsorted(t, p1))
        close_mode = tr["entry_mode"][i] == "close"
        if close_mode:
            a1 = min(a1, iend - 1)
        ent0 = tr["entry_px"][i]
        tp_rel = tr["tp"][i] / ent0 if np.isfinite(tr["tp"][i]) else np.nan
        sl_rel = tr["sl"][i] / ent0 if np.isfinite(tr["sl"][i]) else np.nan
        H = tr["H"][i]
        if a1 <= a0:
            continue
        es = rng.integers(a0, a1, size=reps)
        for r, e in enumerate(es):
            ent = b["c"][e] if close_mode else b["o"][e]
            j0 = e + 1 if close_mode else e
            jlim = iend if not np.isfinite(H) else min(iend, j0 + int(H))
            _, px, _ = first_exit(b, j0, jlim, ent, ent * tp_rel, ent * sl_rel)
            G[i, r] = px / ent - 1
    return G


def control_compare(net, entry_t, G, k=COST):
    netc = (G) - k * (2 + G)            # net = g-1 - k(1+g) con g = 1+G
    valid = np.isfinite(netc).all(1)
    net, entry_t, netc = net[valid], entry_t[valid], netc[valid]
    reps = netc.shape[1]
    Ec = netc.mean(0); WRc = (netc > 0).mean(0)
    d = net - netc.mean(1)
    dw = (net > 0).astype(float) - (netc > 0).mean(1)
    tE, Gd = t_cluster(d, day_of(entry_t)); tW, _ = t_cluster(dw, day_of(entry_t))
    E_m, W_m = net.mean(), (net > 0).mean()
    return {"reps": int(reps), "n_matched": int(valid.sum()),
            "E_rand_pct": float(Ec.mean() * 100), "E_rand_sd_pct": float(Ec.std(ddof=1) * 100),
            "WR_rand": float(WRc.mean()), "WR_rand_sd": float(WRc.std(ddof=1)),
            "dE_pct": float((E_m - Ec.mean()) * 100), "dWR": float(W_m - WRc.mean()),
            "dE_t_day": float(tE), "dE_p_day": float(1 - stats.norm.cdf(tE)) if np.isfinite(tE) else float("nan"),
            "dWR_t_day": float(tW), "dWR_p_day": float(1 - stats.norm.cdf(tW)) if np.isfinite(tW) else float("nan"),
            "dE_p_reps": float((1 + (Ec >= E_m).sum()) / (reps + 1)),
            "dWR_p_reps": float((1 + (WRc >= W_m).sum()) / (reps + 1))}


# ----------------------------------------------------------------------------------------- criterios
def criteria(m, ctrl, audit):
    a = (m["E_pct"] > 0) and (m["t_day"] > 1.645) and (m["E030_pct"] > 0)
    b = m["wr_lo"] >= 0.70
    c = (ctrl["dE_pct"] > 0) and (ctrl["dE_p_day"] < 0.05) and (ctrl["dE_p_reps"] < 0.05)
    d = {True: True, False: False, None: None}[audit]
    res = {"a_E_pos_tday_cost030": bool(a), "b_wilson_lo_ge_070": bool(b), "c_dE_vs_random": bool(c),
           "d_audit_no_leak": "PENDIENTE" if d is None else bool(d)}
    res["VEREDICTO"] = "ACEPTA" if (a and b and c and d is True) else ("PENDIENTE_AUDITORIA" if (a and b and c and d is None) else "RECHAZA")
    return res


# ----------------------------------------------------------------------------------------- E/S
def read_trades(path, sym_default=None, mode_default="close", H_default=None):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    def col(r, *names, default=None):
        for nm in names:
            if nm in r and r[nm] not in ("", None):
                return r[nm]
        return default
    fl = lambda x: float(x) if x not in (None, "", "nan", "NaN") else np.nan
    tr = {"symbol": np.array([col(r, "symbol", default=sym_default) for r in rows]),
          "entry_t": np.array([int(float(col(r, "entry_t", "entry_time_ms"))) for r in rows], np.int64),
          "exit_t": np.array([int(float(col(r, "exit_t", "exit_time_ms"))) for r in rows], np.int64),
          "entry_px": np.array([fl(col(r, "entry_px")) for r in rows]),
          "exit_px": np.array([fl(col(r, "exit_px")) for r in rows]),
          "tp": np.array([fl(col(r, "tp")) for r in rows]), "sl": np.array([fl(col(r, "sl")) for r in rows]),
          "H": np.array([fl(col(r, "H", "max_hold", default=H_default)) for r in rows]),
          "entry_mode": np.array([col(r, "entry_mode", default=mode_default) for r in rows])}
    if any(s is None for s in tr["symbol"]):
        raise ValueError("falta la columna symbol (o --symbol)")
    return tr


def verify(tr, period, reps=200, extra_trials=0, audit=None, seed=12345):
    rp = replay(tr, period[1])
    in_per = (tr["entry_t"] >= period[0]) & (tr["entry_t"] < period[1])
    gross = tr["exit_px"] / tr["entry_px"] - 1
    net = net_of(tr["entry_px"], tr["exit_px"]); net030 = net_of(tr["entry_px"], tr["exit_px"], COST_STRESS)
    risk = np.where(np.isfinite(tr["sl"]), (tr["entry_px"] - tr["sl"]) / tr["entry_px"], np.nan)
    rep = {"n_input": int(len(net)), "fuera_de_periodo": int((~in_per).sum()),
           "entrada_no_coincide": int(rp["bad_entry"].sum()), "salida_no_coincide": int(rp["mismatch"].sum()),
           "ejemplos_discrepancia": [int(i) for i in np.flatnonzero(rp["mismatch"] | rp["bad_entry"])[:10]]}
    # solapamiento por moneda (una posicion a la vez)
    ov = 0
    for s in np.unique(tr["symbol"]):
        k = np.flatnonzero(tr["symbol"] == s); k = k[np.argsort(tr["entry_t"][k])]
        ov += int((tr["entry_t"][k][1:] <= tr["exit_t"][k][:-1]).sum())
    rep["solapadas_misma_moneda"] = ov
    m = block_stats(net, net030, gross, tr["entry_t"], tr["exit_t"], risk)
    m["tp_rate"] = float((rp["reason"] == 0).mean()); m["sl_rate"] = float((rp["reason"] == 1).mean())
    m["time_rate"] = float((rp["reason"] == 2).mean())
    m["por_moneda"] = {}
    for s in np.unique(tr["symbol"]):
        k = tr["symbol"] == s
        mm = block_stats(net[k], net030[k], gross[k], tr["entry_t"][k], tr["exit_t"][k], risk[k])
        m["por_moneda"][str(s)] = {x: mm.get(x) for x in ("n", "wr", "wr_lo", "E_pct", "pf", "t_day")}
    G = random_control(tr, period, reps, seed)
    ctrl = control_compare(net, tr["entry_t"], G)
    ctrl030 = control_compare(net030, tr["entry_t"], G, COST_STRESS)
    ctrl["dE030_pct"] = ctrl030["dE_pct"]
    N = trials_total(extra_trials)
    d = dsr(net, N)
    return {"replay": rep, "metrics": m, "control": ctrl, "dsr": d, "criterios": criteria(m, ctrl, audit)}


def summary(res):
    m, c, d, k, r = res["metrics"], res["control"], res["dsr"], res["criterios"], res["replay"]
    f = lambda x, s="{:.3f}": s.format(x) if x is not None and np.isfinite(x) else "nan"
    lines = [
        f"replay: n={r['n_input']} fuera_periodo={r['fuera_de_periodo']} entrada_mal={r['entrada_no_coincide']} "
        f"salida_mal={r['salida_no_coincide']} solapadas={r['solapadas_misma_moneda']}",
        f"n={m['n']} WR={f(m['wr'])} [{f(m['wr_lo'])},{f(m['wr_hi'])}] (DEFF {f(m.get('wr_deff', float('nan')),'{:.2f}')}, lo_neff {f(m.get('wr_lo_neff', float('nan')))}) b_eff={f(m['b_eff'])} WR*={f(m['wr_breakeven'])} "
        f"E={f(m['E_pct'],'{:+.3f}')}% E_R={f(m['E_R'],'{:+.3f}')} E030={f(m['E030_pct'],'{:+.3f}')}% PF={f(m['pf'],'{:.2f}')} "
        f"MDD={f(m['mdd_comp_pct'],'{:.1f}')}% t_dia={f(m['t_day'],'{:.2f}')} (dias={m['days']}) t_iid={f(m['t_iid'],'{:.2f}')}",
        f"azar emparejado ({c['reps']} rep): WR_azar={f(c['WR_rand'])} E_azar={f(c['E_rand_pct'],'{:+.3f}')}% | "
        f"dWR={f(c['dWR'],'{:+.3f}')} (t_dia {f(c['dWR_t_day'],'{:.2f}')}, p_rep {f(c['dWR_p_reps'])}) "
        f"dE={f(c['dE_pct'],'{:+.3f}')}% (t_dia {f(c['dE_t_day'],'{:.2f}')}, p_dia {f(c['dE_p_day'])}, p_rep {f(c['dE_p_reps'])})",
        f"DSR={f(d['dsr'])} (SR={f(d['sr'],'{:.4f}')} SR0={f(d['sr0'],'{:.4f}')} N={d['n_trials']})",
        "criterios: " + " ".join(f"{a}={b}" for a, b in k.items()),
    ]
    return "\n".join(lines)


def log_execution(test_id, reason, trades_path, res, force=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(EXEC_LOG):
        with open(EXEC_LOG, encoding="utf-8") as f:
            prev = [r for r in csv.DictReader(f) if r["test_id"] == test_id]
        if prev and not force:
            raise PermissionError(f"La prueba '{test_id}' ya se ejecuto ({prev[0]['utc']}). Ejecucion unica.")
    new = not os.path.exists(EXEC_LOG)
    data_h = {s: sha256(load_bars(s)["path"])[:16] for s in sorted(_BARS)}
    with open(EXEC_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc", "local", "test_id", "reason", "trades_sha256", "verify_sha256", "data_sha256",
                        "n", "E_pct", "wr", "wr_lo", "t_day", "dE_pct", "veredicto"])
        m = res["metrics"]
        w.writerow([dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    test_id, reason, sha256(trades_path), sha256(os.path.abspath(__file__)), json.dumps(data_h),
                    m["n"], m.get("E_pct"), m.get("wr"), m.get("wr_lo"), m.get("t_day"), res["control"]["dE_pct"],
                    res["criterios"]["VEREDICTO"]])


# ----------------------------------------------------------------------------------------- autoprueba
def selftest():
    """Datos sinteticos (paseo aleatorio, sin ventaja posible): (1) geometria de TP corto -> WR alto, E<0,
    dWR~0 -> RECHAZA; (2) 'oraculo' con fuga (mira H velas adelante) -> dWR enorme (el control lo detecta;
    la auditoria de fugas es la que debe atraparlo); (3) replay exacto de operaciones propias."""
    rng = np.random.default_rng(7)
    N = 60_000
    t = to_ms("2024-01-01") + BAR * np.arange(N, dtype=np.int64)
    r = rng.standard_t(4, N) * 0.004
    c = 100 * np.exp(np.cumsum(r)); o = np.r_[100, c[:-1]]
    sp = np.abs(rng.normal(0, 0.002, N)) * c
    h = np.maximum(o, c) + sp; l = np.minimum(o, c) - sp
    _BARS["SYNUSDT"] = {"t": t, "o": o, "h": h, "l": l, "c": c, "path": __file__}
    period = (int(t[1000]), int(t[-1] + BAR))
    def make(entries, tp_rel, sl_rel, H):
        b = _BARS["SYNUSDT"]; rows = {k: [] for k in ("symbol", "entry_t", "exit_t", "entry_px", "exit_px", "tp", "sl", "H", "entry_mode")}
        last = -1; iend = int(np.searchsorted(t, period[1]))
        for e in entries:
            if e <= last:
                continue
            ent = c[e]; tp, sl = ent * tp_rel, ent * sl_rel
            j, px, _ = first_exit(b, e + 1, min(iend, e + 1 + H), ent, tp, sl)
            for kk, v in (("symbol", "SYNUSDT"), ("entry_t", t[e]), ("exit_t", t[j]), ("entry_px", ent), ("exit_px", px),
                          ("tp", tp), ("sl", sl), ("H", H), ("entry_mode", "close")):
                rows[kk].append(v)
            last = j
        return {k: np.array(v) if k in ("symbol", "entry_mode") else np.array(v, float if k not in ("entry_t", "exit_t") else np.int64)
                for k, v in rows.items()}
    ent1 = np.sort(rng.choice(np.arange(1000, N - 200), 900, replace=False))
    tr1 = make(ent1, 1.005, 0.975, 96)
    res1 = verify(tr1, period, reps=50, audit=True)
    print("[1] geometria (TP +0.5 %, SL -2.5 %, H 96) con entradas al azar:\n" + summary(res1))
    # oraculo: entra solo si el TP se toca antes que el SL en las proximas 96 velas (fuga deliberada)
    b = _BARS["SYNUSDT"]; ok = []
    for e in ent1:
        _, _, why = first_exit(b, e + 1, e + 97, c[e], c[e] * 1.005, c[e] * 0.975)
        if why == 0:
            ok.append(e)
    tr2 = make(np.array(ok), 1.005, 0.975, 96)
    res2 = verify(tr2, period, reps=50, audit=None)
    print("[2] oraculo con fuga (misma geometria):\n" + summary(res2))
    assert res1["replay"]["salida_no_coincide"] == 0 and res2["replay"]["salida_no_coincide"] == 0
    assert res1["criterios"]["VEREDICTO"] == "RECHAZA" and abs(res1["control"]["dWR"]) < 0.06
    assert res2["control"]["dWR"] > 0.1
    print("AUTOPRUEBA OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trades", nargs="?")
    ap.add_argument("--period", nargs=2, metavar=("INI", "FIN"), help="AAAA-MM-DD AAAA-MM-DD (semiabierto)")
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--extra-trials", type=int, default=0)
    ap.add_argument("--symbol"); ap.add_argument("--entry-mode", default="close"); ap.add_argument("--H")
    g = ap.add_mutually_exclusive_group(); g.add_argument("--audit-ok", action="store_true"); g.add_argument("--audit-fail", action="store_true")
    ap.add_argument("--json"); ap.add_argument("--final"); ap.add_argument("--reason"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.final and not a.reason:
        sys.exit("--final exige --reason")
    if a.final and os.path.exists(EXEC_LOG):  # comprobar antes de calcular nada
        with open(EXEC_LOG, encoding="utf-8") as f:
            if any(r["test_id"] == a.final for r in csv.DictReader(f)):
                sys.exit(f"La prueba '{a.final}' ya se ejecuto. Ejecucion unica.")
    tr = read_trades(a.trades, a.symbol, a.entry_mode, a.H)
    period = (to_ms(a.period[0]), to_ms(a.period[1]))
    audit = True if a.audit_ok else (False if a.audit_fail else None)
    res = verify(tr, period, a.reps, a.extra_trials, audit)
    print(summary(res))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, default=float)
    if a.final:
        log_execution(a.final, a.reason, a.trades, res)


if __name__ == "__main__":
    main()
