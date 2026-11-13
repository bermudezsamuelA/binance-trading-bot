"""Estrategia de extremos (video de YouTube) como reglas exactas y simulación sin mirar el futuro.

Tres temporalidades:
  1. Diario: el precio está en un soporte con varios toques y en la parte baja del rango de 90 días (condición 1), llegó con una caída fuerte para su
     volatilidad (condición 2), y frena y gira (condición 3). Si se cumplen las tres al cierre del día d, se abre una
     ventana de `ventana_dias` días para buscar la entrada.
  2. 1 h: la estructura pasa a alcista (un cierre por encima del último máximo local confirmado, después del mínimo de
     la caída). Se traza Fibonacci desde ese mínimo hasta el máximo del impulso y se espera que el precio toque el 0.618
     con la EMA 50 de 1 h cerca (confluencia). Si toca el 0.75 antes, la idea se descarta.
  3. Gatillo (5 min, o 15 min si no hay velas de 5 min): después del toque, la primera vela que cierra por encima de la
     diagonal de los dos últimos máximos decrecientes y/o de la EMA 20. Se compra a ese cierre.
Salida: stop en el 0.75 de Fibonacci; objetivo en el máximo del impulso o en `rb` veces el riesgo; si no toca ninguno
en `max_dias`, se vende al cierre. Solo compras (spot) y una operación a la vez por moneda.

Todo lo que decide en un momento usa solo velas ya cerradas en ese momento (ver test_estrategia.py).
"""
from dataclasses import dataclass, field, asdict

import numpy as np
from scipy.signal import lfilter

MIN = 60_000
HOUR = 3_600_000
DAY = 86_400_000
COST = 0.0024        # ida y vuelta: 0.1 % de comisión por lado más 0.02 % de deslizamiento por lado


@dataclass
class Params:
    # diario
    piv_n: int = 3              # velas a cada lado de un pivote diario
    tol_atr: float = 0.5        # tolerancia del nivel, en ATR diario
    toques: int = 2             # toques mínimos del soporte
    lookback_dias: int = 365    # antigüedad máxima de los toques
    rango_dias: int = 90        # el extremo se mide dentro del rango de estos días
    pos_max: float = 0.25       # mínimo de hoy en el 25 % inferior del rango (0 = abajo del todo, 1 = arriba)
    k: int = 5                  # velas del tramo de caída
    theta: float = 2.0          # umbral de la caída, en desviaciones
    freno: float = 0.6          # cuerpos recientes / cuerpos anteriores < freno
    mecha: float = 0.3          # mecha inferior media >= mecha
    usar_c3: bool = True        # exigir la condición 3 (freno y giro)
    ventana_dias: int = 3       # días para encontrar la entrada tras la señal diaria
    # 1 h
    piv_n_1h: int = 3
    busca_min_dias: int = 5     # el mínimo de la caída se busca en estos días antes de la señal
    c_conf: float = 1.0         # |EMA50 - P0.618| <= c_conf * ATR 1 h
    tol_fib: float = 0.25       # el toque vale si el mínimo llega a P0.618 + tol_fib * ATR 1 h
    # gatillo
    gatillo: str = "ambas"      # "diagonal", "ema" o "ambas"
    piv_n_g: int = 3            # velas a cada lado de un pivote en la temporalidad del gatillo
    gatillo_horas: float = 6.0  # tiempo máximo entre el toque y el gatillo
    # salida
    objetivo: str = "maximo"    # "maximo" (máximo del impulso) o "rb" (rb veces el riesgo)
    rb: float = 1.6
    max_dias: float = 7.0


# --------------------------------------------------------------------------------------------- utilidades de velas
def resample(b: dict, bar: int, full: int = None) -> dict:
    """Agrega velas (T, O, H, L, C) a velas de `bar` ms. Descarta la última si está incompleta."""
    key = b["T"] // bar * bar
    idx = np.flatnonzero(np.r_[True, np.diff(key) > 0])
    ends = np.r_[idx[1:], len(key)] - 1
    out = {"T": key[idx], "O": b["O"][idx], "C": b["C"][ends],
           "H": np.maximum.reduceat(b["H"], idx), "L": np.minimum.reduceat(b["L"], idx)}
    if full and len(idx) and ends[-1] - idx[-1] + 1 < full:
        out = {k: v[:-1] for k, v in out.items()}
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2.0 / (n + 1)
    y, _ = lfilter([a], [1, -(1 - a)], x, zi=[(1 - a) * x[0]])
    return y


def atr(b: dict, n: int = 14) -> np.ndarray:
    pc = np.r_[b["C"][0], b["C"][:-1]]
    tr = np.maximum(b["H"] - b["L"], np.maximum(abs(b["H"] - pc), abs(b["L"] - pc)))
    c = np.r_[0.0, np.cumsum(tr)]
    out = np.full(len(tr), np.nan)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def pivots(x: np.ndarray, n: int, high: bool) -> np.ndarray:
    """Índices i donde x[i] es el máximo (high) o mínimo de x[i-n .. i+n]. Se confirman en i + n."""
    if len(x) < 2 * n + 1:
        return np.zeros(0, np.int64)
    w = np.lib.stride_tricks.sliding_window_view(x, 2 * n + 1)
    m = w.max(1) if high else w.min(1)
    return np.flatnonzero(x[n:-n] == m) + n


def last_confirmed(piv: np.ndarray, n: int, size: int) -> np.ndarray:
    """Para cada vela j, el último pivote ya confirmado (i + n <= j), o -1."""
    out = np.full(size, -1, np.int64)
    c = piv + n
    ok = c < size
    out[c[ok]] = piv[ok]
    return np.maximum.accumulate(out)


# -------------------------------------------------------------------------------------------- condiciones diarias
def daily_conditions(d: dict, p: Params) -> dict:
    """Booleanos por día (evaluados al cierre del día) para las tres condiciones."""
    n = len(d["C"])
    A = atr(d, 14)
    lows = pivots(d["L"], p.piv_n, high=False)
    c1 = np.zeros(n, bool)
    for t in range(n):
        if not np.isfinite(A[t]):
            continue
        pv = lows[(lows + p.piv_n <= t) & (lows >= t - p.lookback_dias)]
        if len(pv) < p.toques:
            continue
        lv, tol = d["L"][pv], p.tol_atr * A[t]
        cnt = (abs(lv[:, None] - lv[None, :]) <= tol).sum(1)
        ok = (cnt >= p.toques) & (d["L"][t] <= lv + tol) & (d["C"][t] >= lv - tol)
        lo, hi = d["L"][max(0, t - p.rango_dias):t + 1].min(), d["H"][max(0, t - p.rango_dias):t + 1].max()
        pos = (d["L"][t] - lo) / max(hi - lo, 1e-12)
        c1[t] = ok.any() and pos <= p.pos_max
    lc = np.log(d["C"])
    r = np.r_[np.nan, np.diff(lc)]
    z = np.full(n, np.nan)
    for j in range(p.k + 31, n):
        sd = np.std(r[j - p.k - 30:j - p.k], ddof=1)
        z[j] = (lc[j] - lc[j - p.k]) / (sd * np.sqrt(p.k))
    zmin = np.full(n, np.nan)
    for t in range(4, n):
        zmin[t] = np.nanmin(z[t - 4:t + 1]) if np.isfinite(z[t - 4:t + 1]).any() else np.nan
    c2 = np.nan_to_num(zmin, nan=0) <= -p.theta
    body = abs(d["C"] - d["O"])
    om = (np.minimum(d["O"], d["C"]) - d["L"]) / np.maximum(d["H"] - d["L"], 1e-12)
    c3 = np.zeros(n, bool)
    for t in range(5, n):
        old = body[t - 5:t - 2].mean()
        brake = old > 0 and body[t - 2:t + 1].mean() / old < p.freno
        wick = om[t - 2:t + 1].mean() >= p.mecha
        turn = d["C"][t] > d["O"][t - 1] and d["C"][t] > d["O"][t - 2] and d["C"][t] > d["C"][t - 3]
        c3[t] = brake and wick and turn
    return {"c1": c1, "c2": c2, "c3": c3, "z": zmin}


# ---------------------------------------------------------------------------------------------------- simulación
@dataclass
class Trade:
    symbol: str
    dia_senal: int          # ms de inicio del día de la señal diaria
    t_entrada: int
    t_salida: int
    entrada: float
    salida: float
    stop: float
    objetivo: float
    motivo: str             # objetivo | stop | tiempo
    ret: float              # neto de COST
    r_mult: float           # resultado en unidades de riesgo (neto)


@dataclass
class Funnel:
    dias: int = 0
    c1: int = 0
    c12: int = 0
    senales: int = 0
    ventanas: int = 0
    sin_ruptura: int = 0
    rompe_075: int = 0
    sin_toque: int = 0
    sin_confluencia: int = 0
    sin_gatillo: int = 0
    stop_antes: int = 0
    operaciones: int = 0

    def add(self, o):
        for k, v in asdict(o).items():
            setattr(self, k, getattr(self, k) + v)


class Coin:
    """Velas de una moneda en las tres temporalidades y los indicadores que no dependen de los parámetros."""

    def __init__(self, symbol: str, base: dict, base_ms: int):
        self.symbol, self.bms = symbol, base_ms
        self.b = base
        self.h = resample(base, HOUR, HOUR // base_ms)
        self.d = resample(base, DAY, DAY // base_ms)
        self.e50 = ema(self.h["C"], 50)
        self.a1 = atr(self.h, 14)
        self.e20 = ema(base["C"], 20)
        self.h_end = self.h["T"] + HOUR
        self._cache = {}

    def lastph_1h(self, n):
        k = ("ph1", n)
        if k not in self._cache:
            self._cache[k] = last_confirmed(pivots(self.h["H"], n, True), n, len(self.h["H"]))
        return self._cache[k]

    def piv_base(self, n):
        k = ("phb", n)
        if k not in self._cache:
            self._cache[k] = pivots(self.b["H"], n, True)
        return self._cache[k]

    def daily(self, p: Params):
        k = ("d", p.piv_n, p.tol_atr, p.toques, p.lookback_dias, p.rango_dias, p.pos_max, p.k, p.theta, p.freno, p.mecha)
        if k not in self._cache:
            self._cache[k] = daily_conditions(self.d, p)
        return self._cache[k]


def run_coin(cn: Coin, p: Params, start_ms: int = None, end_ms: int = None):
    """Simula la estrategia en una moneda. Devuelve (operaciones, embudo)."""
    b, h, d = cn.b, cn.h, cn.d
    cond = cn.daily(p)
    sig = cond["c1"] & cond["c2"] & (cond["c3"] if p.usar_c3 else True)
    f = Funnel()
    dsel = np.ones(len(d["T"]), bool)
    if start_ms is not None:
        dsel &= d["T"] >= start_ms
    if end_ms is not None:
        dsel &= d["T"] < end_ms
    f.dias = int(dsel.sum())
    f.c1 = int((cond["c1"] & dsel).sum())
    f.c12 = int((cond["c1"] & cond["c2"] & dsel).sum())
    f.senales = int((sig & dsel).sum())
    lastph = cn.lastph_1h(p.piv_n_1h)
    phb = cn.piv_base(p.piv_n_g)
    trig_bars = int(p.gatillo_horas * HOUR // cn.bms)
    hold_bars = int(p.max_dias * DAY // cn.bms)
    trades, busy_until = [], -1
    for di in np.flatnonzero(sig & dsel):
        s0 = int(d["T"][di]) + DAY
        if s0 < busy_until:
            continue
        f.ventanas += 1
        s1 = s0 + p.ventana_dias * DAY
        q, qend = np.searchsorted(b["T"], s0), np.searchsorted(b["T"], s1)
        hstart = np.searchsorted(h["T"], s0 - p.busca_min_dias * DAY)
        state, last_hc, lv = "ruptura", -2, None
        touched = -1
        out = "sin_ruptura"
        while q < min(qend, len(b["T"])) or (state == "gatillo" and q < len(b["T"])):
            tq = int(b["T"][q]) + cn.bms                         # cierre de la vela base q
            if state == "ruptura":
                hc = int(np.searchsorted(cn.h_end, tq, "right")) - 1
                if hc != last_hc and hc > hstart:
                    last_hc = hc
                    lv = None
                    bI = hstart + int(np.argmin(h["L"][hstart:hc + 1]))
                    js = np.arange(bI + 1, hc + 1)
                    if len(js):
                        pj = lastph[js]
                        ok = (pj >= 0) & (h["C"][js] > h["H"][np.maximum(pj, 0)])
                        if ok.any():
                            bk = int(js[np.argmax(ok)])
                            hI = bk + int(np.argmax(h["H"][bk:hc + 1]))
                            Lv, Hv = h["L"][bI], h["H"][hI]
                            lv = dict(L=Lv, H=Hv, p618=Hv - 0.618 * (Hv - Lv), p075=Hv - 0.75 * (Hv - Lv),
                                      tol=p.tol_fib * cn.a1[hc], e50=cn.e50[hc], a=cn.a1[hc], hI=hI)
                if lv is not None and np.isfinite(lv["a"]):
                    out = "sin_toque"
                    lo = b["L"][q]
                    if lo <= lv["p075"]:
                        out = "rompe_075"
                        break
                    if lo <= lv["p618"] + lv["tol"]:
                        if abs(lv["e50"] - lv["p618"]) > p.c_conf * lv["a"]:
                            out = "sin_confluencia"
                            break
                        state, touched, out = "gatillo", q, "sin_gatillo"
                        hI_start = np.searchsorted(b["T"], h["T"][lv["hI"]])
            else:
                if q > touched + trig_bars:
                    break
                if b["L"][q] <= lv["p075"]:
                    out = "stop_antes"
                    break
                okE = b["C"][q] > cn.e20[q]
                conf = phb[(phb + p.piv_n_g <= q) & (phb >= hI_start)]
                okD = False
                if len(conf) >= 2:
                    i0, i1 = conf[-2], conf[-1]
                    if b["H"][i1] < b["H"][i0]:
                        line = b["H"][i0] + (b["H"][i1] - b["H"][i0]) / (i1 - i0) * (q - i0)
                        okD = b["C"][q] > line
                go = okD if p.gatillo == "diagonal" else okE if p.gatillo == "ema" else (okD and okE)
                if go:
                    tr = _exit(cn, q, lv, p, hold_bars, int(d["T"][di]))
                    if tr is not None:
                        trades.append(tr)
                        busy_until = tr.t_salida
                        out = "operaciones"
                    else:
                        out = "sin_gatillo"
                    break
            q += 1
        setattr(f, out, getattr(f, out) + 1)
    return trades, f


def _exit(cn: Coin, q: int, lv: dict, p: Params, hold_bars: int, day_ms: int):
    b = cn.b
    entry, stop = float(b["C"][q]), float(lv["p075"])
    risk = entry - stop
    if risk <= 0:
        return None
    tp = float(lv["H"]) if p.objetivo == "maximo" else entry + p.rb * risk
    if tp <= entry:
        return None
    e = min(len(b["T"]), q + 1 + hold_bars)
    L, H = b["L"][q + 1:e], b["H"][q + 1:e]
    hit_s, hit_t = np.flatnonzero(L <= stop), np.flatnonzero(H >= tp)
    i_s = hit_s[0] if len(hit_s) else np.inf
    i_t = hit_t[0] if len(hit_t) else np.inf
    if i_s == np.inf and i_t == np.inf:
        if e - (q + 1) < hold_bars:                         # se acabaron los datos: no se cuenta
            return None
        j, px, why = e - 1, float(b["C"][e - 1]), "tiempo"
    elif i_s <= i_t:                                         # si tocan los dos en la misma vela, se asume el stop
        j = q + 1 + int(i_s)
        px, why = min(float(b["O"][j]), stop), "stop"
    else:
        j = q + 1 + int(i_t)
        px, why = tp, "objetivo"
    ret = px / entry - 1 - COST
    return Trade(cn.symbol, day_ms, int(b["T"][q]) + cn.bms, int(b["T"][j]) + cn.bms, entry, px, stop, tp, why,
                 ret, ret * entry / risk)
