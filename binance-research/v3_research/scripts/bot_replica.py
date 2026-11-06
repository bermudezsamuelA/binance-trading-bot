"""
bot_replica.py - Replicas exactas de las estrategias del bot (sin pandas) para evaluarlas con el arnes.

Tres niveles de replica:
  1) original_optimizer(): copia literal de QuantCalculator.evaluate_strategy (optimize.py): solo cierres,
     paga siempre 2R al acertar, sin costos, la ventana NO recibe precios mientras hay posicion,
     TP/SL redondeados a 2 decimales (round(x, 2) como en las estrategias). Sirve para reproducir ml_results.json.
  2) run_frozen(): misma logica de senales y ventana congelada que el bot (en vivo tambien se congela:
     Node no manda precios a Python con posicion abierta), pero con salida realista: high/low,
     b real, costos y regla conservadora. Es "el bot fiel" alimentado con velas cerradas de 15m.
  3) signals_*(): senales vectorizadas con ventana continua (la idea de la estrategia "limpia").

Estrategias: "MR" (MeanReversion), "TF" (RollingVolatility = TrendFollowing), "SQ" (VolatilitySqueeze),
"VWAP" (identica a MR en el bot porque el volumen siempre llega como 1).
"""
from __future__ import annotations

import math

import numpy as np

import harness as H

B_REAL = {"MR": 1.0, "VWAP": 1.0, "TF": 2.0, "SQ": 2.5}
NAME2CODE = {"MeanReversion": "MR", "TrendFollowing": "TF", "VWAP": "VWAP", "VolatilitySqueeze": "SQ"}


class BotStrategy:
    """Replica de evaluate() de las clases del bot (estado incluido)."""

    def __init__(self, code: str, window: int, mult: float, rounding: bool = True, squeeze_threshold: float = 0.05):
        self.code, self.n, self.k, self.rounding, self.th = code, int(window), float(mult), rounding, squeeze_threshold
        self.prices: list = []
        self.armed = False

    def _r(self, x):
        return round(x, 2) if self.rounding else x

    def evaluate(self, price: float):
        """Devuelve None (HOLD) o (tp, sl)."""
        p = self.prices
        p.append(price)
        if len(p) > self.n:
            p.pop(0)
        if len(p) < self.n:
            return None
        a = np.asarray(p)
        mu = float(a.mean())
        sd = float(a.std(ddof=1))
        k = self.k
        if self.code in ("MR", "VWAP"):
            if price < mu - sd * k:
                tp = mu
                risk = tp - price
                sl = price - risk
                if risk < price * 0.005:
                    return None
                return self._r(tp), self._r(sl)
            return None
        if self.code == "TF":
            if price > mu + sd * k:
                sl = mu
                risk = price - sl
                tp = price + risk * 2.0
                return self._r(tp), self._r(sl)
            return None
        if self.code == "SQ":
            upper, lower = mu + sd * k, mu - sd * k
            bw = (upper - lower) / mu
            if bw < self.th and not self.armed:
                self.armed = True
            elif self.armed and price > upper:
                self.armed = False
                sl = mu
                risk = price - sl
                tp = price + risk * 2.5
                if risk < price * 0.005:
                    return None
                return self._r(tp), self._r(sl)
            return None
        raise ValueError(self.code)


def original_optimizer(closes, code: str, window: int, mult: float) -> dict:
    """Copia de QuantCalculator.evaluate_strategy para UNA configuracion (capital 1000, riesgo 15).
    Devuelve las metricas de calculate_metrics y el detalle de cada operacion."""
    st = BotStrategy(code, window, mult, rounding=True)
    capital, curve = 1000.0, [1000.0]
    pos = None
    w = l_ = 0
    gp = gl = 0.0
    detail = []
    for i, price in enumerate(closes):
        price = float(price)
        if pos:
            if price >= pos["tp"]:
                capital += 30.0
                gp += 30.0
                w += 1
                curve.append(capital)
                detail.append({**pos, "exit_i": i, "exit": price, "win": True})
                pos = None
            elif price <= pos["sl"]:
                capital -= 15.0
                gl += 15.0
                l_ += 1
                curve.append(capital)
                detail.append({**pos, "exit_i": i, "exit": price, "win": False})
                pos = None
            continue
        s = st.evaluate(price)
        if s is not None:
            pos = {"entry_i": i, "entry": price, "tp": s[0], "sl": s[1]}
    n = w + l_
    if n == 0:
        return {"trades": 0, "detail": detail}
    peak, mdd = 1000.0, 0.0
    for cap in curve:
        peak = max(peak, cap)
        mdd = max(mdd, (peak - cap) / peak)
    pnl = curve[-1] - 1000.0
    return {"trades": n, "win_rate": round(w / n * 100, 2), "max_drawdown_pct": round(mdd * 100, 2),
            "profit_factor": round(gp / gl, 2) if gl > 0 else round(gp, 2), "expected_payoff": round(pnl / n, 2),
            "pnl": round(pnl, 2), "detail": detail}


def run_frozen(bars: H.Bars, code: str, window: int, mult: float, period, rounding: bool = True,
               fee: float = H.FEE, slip: float = H.SLIP, max_hold=None, warmup: bool = True) -> H.Trades:
    """Bot fiel con velas cerradas de 15m: la ventana solo recibe el cierre cuando NO hay posicion
    (igual que optimize.py y que el bot en vivo). Entrada al cierre de la vela de senal; salida por
    high/low de las velas siguientes (regla conservadora); costos; niveles invalidos (TP<=entrada o
    SL>=entrada, efecto del redondeo) cierran de inmediato al precio de entrada (pierden solo costos),
    como haria Node en el siguiente tick."""
    i0, i1 = period
    st = BotStrategy(code, window, mult, rounding)
    o, h, l, c = bars.o, bars.h, bars.l, bars.c
    start = max(0, i0 - window) if warmup else i0
    rows = {f: [] for f in H.Trades.FIELDS}
    i = start
    n_sig = n_inv = 0
    while i < i1:
        s = st.evaluate(float(c[i]))
        if s is None or i < i0:
            i += 1
            continue
        n_sig += 1
        entry, tp, sl = float(c[i]), s[0], s[1]
        if tp <= entry or sl >= entry:
            n_inv += 1
            j, px, why = i, entry, H.INVALID
        else:
            j, px, why = H.resolve_exit(o, h, l, c, i + 1, i1, entry, tp, sl, None, max_hold)
            if j < i:
                j, px, why = i, entry, H.END
        net = float(H.net_return(entry, px, fee, slip))
        rp = (entry - sl) / entry if sl < entry else np.nan
        for f, v in (("sig_idx", i), ("entry_idx", i), ("exit_idx", j), ("entry_px", entry), ("exit_px", px),
                     ("tp", tp), ("sl", sl), ("reason", why), ("gross_ret", px / entry - 1), ("net_ret", net),
                     ("risk_pct", rp), ("r_mult", net / rp if np.isfinite(rp) else np.nan),
                     ("entry_t", bars.t[i]), ("exit_t", bars.t[j])):
            rows[f].append(v)
        i = j + 1  # la vela de salida no se le pasa a la estrategia (como optimize.py)
    ints = {"sig_idx", "entry_idx", "exit_idx", "reason", "entry_t", "exit_t"}
    rows = {f: np.asarray(v, dtype=np.int64 if f in ints else np.float64) for f, v in rows.items()}
    meta = {"symbol": bars.symbol, "period": (i0, i1), "t0": int(bars.t[i0]), "t1": int(bars.t[i1 - 1]),
            "mode": "frozen", "code": code, "window": window, "mult": mult, "rounding": rounding,
            "n_signals": n_sig, "n_invalid": n_inv}
    return H.Trades(rows, meta)


# ------------------------------------------------------------------------------------------------
# Senales vectorizadas (ventana continua: cada cierre de 15m entra a la ventana, haya o no posicion)
# ------------------------------------------------------------------------------------------------
def _round2(x):
    return np.round(x, 2)


def signals(bars: H.Bars, code: str, window: int, mult: float, rounding: bool = False,
            squeeze_threshold: float = 0.05, cache: dict | None = None):
    """Devuelve (entries, tp, sl) para la estrategia `code` con ventana continua."""
    c = bars.c
    key_m, key_s = ("m", bars.symbol, window), ("s", bars.symbol, window)
    if cache is not None and key_m in cache:
        mu, sd = cache[key_m], cache[key_s]
    else:
        mu, sd = H.rolling_mean(c, window), H.rolling_std(c, window)
        if cache is not None:
            cache[key_m], cache[key_s] = mu, sd
    with np.errstate(invalid="ignore"):
        if code in ("MR", "VWAP"):
            sig = c < mu - mult * sd
            tp = mu
            risk = tp - c
            sl = c - risk
            sig &= ~(risk < c * 0.005)
        elif code == "TF":
            sig = c > mu + mult * sd
            sl = mu
            risk = c - sl
            tp = c + 2.0 * risk
        elif code == "SQ":
            upper = mu + mult * sd
            bw = 2 * mult * sd / mu
            squeezed = bw < squeeze_threshold
            brk = c > upper
            sig = np.zeros(len(c), bool)
            armed = False
            for i in np.flatnonzero(squeezed | brk):  # estado "armado" de la clase original
                if squeezed[i] and not armed:
                    armed = True
                elif armed and brk[i]:
                    armed = False
                    sig[i] = True
            sl = mu
            risk = c - sl
            tp = c + 2.5 * risk
            sig &= ~(risk < c * 0.005)
        else:
            raise ValueError(code)
    sig &= np.isfinite(mu) & np.isfinite(sd)
    if rounding:
        tp, sl = _round2(tp), _round2(sl)
    return sig, tp, sl
