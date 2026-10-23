"""
harness.py - Arnes de backtest compartido del equipo (custodio: Agente 3, Validador).

Uso (desde la carpeta scripts):
    import harness as H
    bars = H.load("BTCUSDT")                       # velas 15m 2023-01 .. 2026-09
    i0, i1 = H.bounds(bars, "design")              # particion DISENO (in-sample)
    mu, sd = H.rolling_mean(bars.c, 20), H.rolling_std(bars.c, 20)
    sig = bars.c < mu - 2 * sd
    tp, sl = mu, bars.c - (mu - bars.c)
    tr = H.simulate(bars, sig, tp, sl, period=(i0, i1), max_hold=96)
    print(H.fmt(H.metrics(tr, n_configs=1)))

Convenciones (ver HARNESS.md para el detalle):
  * Todo indicador en el indice i usa solo datos <= i (cierre de la vela i). Sin mirar al futuro.
  * Entrada: al cierre de la vela de senal (entry_mode="close") o a la apertura de la siguiente
    ("next_open"). TP/SL se evaluan con high/low de las velas POSTERIORES a la entrada.
  * Si en una misma vela se tocan TP y SL -> cuenta como SL (regla conservadora).
  * Stop con hueco (open <= SL) se llena al open; TP se llena exactamente al TP.
  * Solo largos, una posicion a la vez: una senal solo se toma si su vela es > vela de salida previa.
  * Costos por lado: comision 0.10 % + deslizamiento 0.02 % (c ida y vuelta ~ 0.24 %).
  * El HOLDOUT (2025-07-01 .. 2026-09-30) solo se abre con bounds(..., reason="...") y queda registrado.
"""
from __future__ import annotations

import csv
import datetime as _dt
import itertools
import math
import os
import sys

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as _swv
from scipy import stats as _st
from scipy.signal import lfilter as _lfilter

# --------------------------------------------------------------------------------------------
# Rutas y constantes
# --------------------------------------------------------------------------------------------
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
RESEARCH_DIR = os.path.dirname(SCRIPTS_DIR)
KLINES_DIR = os.path.join(RESEARCH_DIR, "klines")
OUTPUT_DIR = os.path.join(RESEARCH_DIR, "output")
VALIDADOR_DIR = os.path.join(OUTPUT_DIR, "validador")
HOLDOUT_LOG = os.path.join(VALIDADOR_DIR, "holdout_log.csv")
TRIALS_LOG = os.path.join(VALIDADOR_DIR, "trials_log.csv")

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT")
COLS = ("t", "o", "h", "l", "c", "v", "tbv")  # open_time_ms, open, high, low, close, volume, taker_buy_base


def ms(y: int, m: int, d: int = 1) -> int:
    """Timestamp UTC en milisegundos."""
    return int(_dt.datetime(y, m, d, tzinfo=_dt.timezone.utc).timestamp() * 1000)


DESIGN = (ms(2023, 1, 1), ms(2025, 7, 1))     # [inicio, fin)  DISENO / in-sample
HOLDOUT = (ms(2025, 7, 1), ms(2026, 10, 1))   # [inicio, fin)  HOLDOUT / fuera de muestra

FEE = 0.0010   # comision por lado
SLIP = 0.0002  # spread + deslizamiento por lado
COST_RT = 2 * (FEE + SLIP)  # 0.24 % ida y vuelta (aprox.)

BARS_PER_DAY = {"1s": 86400, "1m": 1440, "5m": 288, "15m": 96, "1h": 24, "4h": 6}

# Codigos de motivo de salida
TP, SL, TIME, END, TRAIL, INVALID = 0, 1, 2, 3, 4, 5
REASONS = {TP: "tp", SL: "sl", TIME: "time", END: "end", TRAIL: "trail", INVALID: "invalid"}


# --------------------------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------------------------
class Bars:
    """Velas OHLCV de una moneda. Atributos: t (ms, int64), o, h, l, c, v, tbv (float64)."""

    __slots__ = ("symbol", "tf", "t", "o", "h", "l", "c", "v", "tbv")

    def __init__(self, arr: np.ndarray, symbol: str = "", tf: str = "15m"):
        self.symbol, self.tf = symbol, tf
        self.t = arr[:, 0].astype(np.int64)
        self.o, self.h, self.l, self.c = (np.ascontiguousarray(arr[:, j]) for j in (1, 2, 3, 4))
        self.v = np.ascontiguousarray(arr[:, 5])
        self.tbv = np.ascontiguousarray(arr[:, 6]) if arr.shape[1] > 6 else np.full(len(arr), np.nan)

    def __len__(self):
        return len(self.t)

    def __repr__(self):
        return f"Bars({self.symbol} {self.tf}, n={len(self)}, {iso(self.t[0])} .. {iso(self.t[-1])})"

    def slice(self, i0: int, i1: int) -> "Bars":
        """Copia de las velas [i0, i1). OJO: los indicadores pierden su calentamiento; preferir
        calcular indicadores sobre toda la serie y restringir con period=(i0, i1)."""
        arr = np.column_stack([self.t[i0:i1].astype(np.float64), self.o[i0:i1], self.h[i0:i1],
                               self.l[i0:i1], self.c[i0:i1], self.v[i0:i1], self.tbv[i0:i1]])
        return Bars(arr, self.symbol, self.tf)

    def idx(self, ts_ms: int) -> int:
        """Primer indice con t >= ts_ms."""
        return int(np.searchsorted(self.t, ts_ms, side="left"))

    @property
    def month(self) -> np.ndarray:
        """Mes calendario UTC de cada vela como entero AAAAMM."""
        m = self.t.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)  # meses desde 1970
        return (1970 + m // 12) * 100 + (m % 12) + 1

    @property
    def hour(self) -> np.ndarray:
        return (self.t // 3_600_000) % 24

    @property
    def weekday(self) -> np.ndarray:
        """0 = lunes ... 6 = domingo."""
        return ((self.t // 86_400_000) + 3) % 7


_CACHE: dict = {}


def load(symbol: str, tf: str = "15m") -> Bars:
    """Carga klines/{symbol}_{tf}.npy (forma (N,7)). Cachea en memoria."""
    key = (symbol, tf)
    if key not in _CACHE:
        path = os.path.join(KLINES_DIR, f"{symbol}_{tf}.npy")
        arr = np.load(path)
        if arr.ndim != 2 or arr.shape[1] < 6:
            raise ValueError(f"{path}: forma inesperada {arr.shape}")
        if np.any(np.diff(arr[:, 0]) <= 0):
            raise ValueError(f"{path}: timestamps no estrictamente crecientes")
        _CACHE[key] = Bars(arr, symbol, tf)
    return _CACHE[key]


def iso(ts_ms) -> str:
    return _dt.datetime.fromtimestamp(int(ts_ms) / 1000, tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------------------------
# Particiones y custodia del holdout
# --------------------------------------------------------------------------------------------
_LOGGED: set = set()


def _caller() -> str:
    try:
        return os.path.basename(sys.argv[0]) or "interactive"
    except Exception:
        return "?"


def log_holdout(reason: str, who: str = "", detail: str = "") -> None:
    """Registra una consulta del holdout (una linea por (script, reason) y proceso)."""
    key = (_caller(), reason)
    if key in _LOGGED:
        return
    _LOGGED.add(key)
    os.makedirs(VALIDADOR_DIR, exist_ok=True)
    new = not os.path.exists(HOLDOUT_LOG)
    with open(HOLDOUT_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc", "script", "who", "reason", "detail"])
        w.writerow([_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), _caller(), who, reason, detail])


def bounds(bars: Bars, part="design", reason: str | None = None, who: str = "") -> tuple:
    """Indices [i0, i1) de una particion.

    part: "design" | "holdout" | "all" | (ms_inicio, ms_fin).
    Abrir el holdout (o cualquier rango que lo toque) EXIGE reason y queda registrado en
    output/validador/holdout_log.csv.
    """
    if isinstance(part, str):
        rng = {"design": DESIGN, "holdout": HOLDOUT, "all": (DESIGN[0], HOLDOUT[1])}.get(part)
        if rng is None:
            raise ValueError(f"particion desconocida: {part}")
    else:
        rng = (int(part[0]), int(part[1]))
    touches_holdout = rng[1] > HOLDOUT[0] and rng[0] < HOLDOUT[1]
    if touches_holdout:
        if not reason:
            raise PermissionError("El rango toca el HOLDOUT: pase reason='...' (queda registrado).")
        log_holdout(reason, who, f"{bars.symbol} {iso(rng[0])}..{iso(rng[1])}")
    return bars.idx(rng[0]), bars.idx(rng[1])


def log_trials(agent: str, n_configs: int, description: str, part: str = "design") -> None:
    """Registro de configuraciones probadas (para correccion por comparaciones multiples)."""
    os.makedirs(VALIDADOR_DIR, exist_ok=True)
    new = not os.path.exists(TRIALS_LOG)
    with open(TRIALS_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc", "script", "agent", "n_configs", "part", "description"])
        w.writerow([_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), _caller(), agent,
                    int(n_configs), part, description])


def walk_forward(bars: Bars, part="design", train_months=12, test_months=3, step_months=3,
                 embargo_bars=0, reason=None) -> list:
    """Particiones walk-forward por meses calendario dentro de `part`.

    Devuelve lista de dicts {train:(i0,i1), test:(j0,j1), train_months:(m_ini,m_fin), test_months:(...)}.
    embargo_bars: velas que se descartan al inicio del test (>= duracion maxima de una operacion).
    """
    i0, i1 = bounds(bars, part, reason=reason)
    mon = bars.month[i0:i1]
    months = np.unique(mon)
    out = []
    s = 0
    while s + train_months + test_months <= len(months):
        tr_m = months[s:s + train_months]
        te_m = months[s + train_months:s + train_months + test_months]
        a = i0 + int(np.searchsorted(mon, tr_m[0], "left"))
        b = i0 + int(np.searchsorted(mon, tr_m[-1], "right"))
        c = i0 + int(np.searchsorted(mon, te_m[0], "left"))
        d = i0 + int(np.searchsorted(mon, te_m[-1], "right"))
        out.append({"train": (a, b), "test": (min(c + embargo_bars, d), d),
                    "train_months": (int(tr_m[0]), int(tr_m[-1])), "test_months": (int(te_m[0]), int(te_m[-1]))})
        s += step_months
    return out


# --------------------------------------------------------------------------------------------
# Indicadores vectorizados (valor en i usa datos <= i; los primeros n-1 valores son NaN)
# --------------------------------------------------------------------------------------------
def shift(x: np.ndarray, k: int = 1) -> np.ndarray:
    """x desplazado k posiciones hacia el futuro (x_{i-k} en i), relleno con NaN."""
    x = np.asarray(x, dtype=np.float64)
    out = np.full_like(x, np.nan)
    if k == 0:
        return x.copy()
    if k > 0:
        out[k:] = x[:-k]
    else:
        out[:k] = x[-k:]
    return out


def rolling_mean(x: np.ndarray, n: int) -> np.ndarray:
    """Media simple de las ultimas n muestras (incluida la actual)."""
    x = np.asarray(x, dtype=np.float64)
    out = np.full(len(x), np.nan)
    if n <= 0 or n > len(x):
        return out
    out[n - 1:] = _swv(x, n).mean(axis=1) if n <= 8 else _cum_mean(x, n)
    return out


def _cum_mean(x, n):
    # cumsum centrado en x[0] para reducir error numerico; equivalente a la media de la ventana
    x0 = x[0]
    cs = np.concatenate(([0.0], np.cumsum(x - x0)))
    return (cs[n:] - cs[:-n]) / n + x0


def _rolling_reduce(x, n, fn, chunk=20000):
    x = np.asarray(x, dtype=np.float64)
    out = np.full(len(x), np.nan)
    if n <= 0 or n > len(x):
        return out
    w = _swv(x, n)
    for a in range(0, len(w), chunk):
        out[n - 1 + a:n - 1 + a + len(w[a:a + chunk])] = fn(w[a:a + chunk])
    return out


def rolling_std(x: np.ndarray, n: int, ddof: int = 1) -> np.ndarray:
    """Desviacion estandar de las ultimas n muestras (ddof=1 como pandas .std(); exacta, dos pasadas)."""
    return _rolling_reduce(x, n, lambda w: w.std(axis=1, ddof=ddof))


def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    return _rolling_reduce(x, n, lambda w: w.max(axis=1))


def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    return _rolling_reduce(x, n, lambda w: w.min(axis=1))


def rolling_sum(x: np.ndarray, n: int) -> np.ndarray:
    return _rolling_reduce(x, n, lambda w: w.sum(axis=1))


def log_returns(c: np.ndarray) -> np.ndarray:
    """r_i = ln(c_i / c_{i-1}); r_0 = NaN."""
    c = np.asarray(c, dtype=np.float64)
    r = np.full(len(c), np.nan)
    r[1:] = np.log(c[1:] / c[:-1])
    return r


def simple_returns(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64)
    r = np.full(len(c), np.nan)
    r[1:] = c[1:] / c[:-1] - 1.0
    return r


def rolling_std_returns(c: np.ndarray, n: int, log: bool = True) -> np.ndarray:
    """Volatilidad por vela: desviacion estandar de los ultimos n retornos (fraccion, no %)."""
    r = log_returns(c) if log else simple_returns(c)
    out = np.full(len(c), np.nan)
    out[1:] = rolling_std(r[1:], n)
    return out


def ewma_vol(c: np.ndarray, lam: float = 0.94, log: bool = True) -> np.ndarray:
    """sigma_t^2 = lam*sigma_{t-1}^2 + (1-lam)*r_t^2 (RiskMetrics). Devuelve sigma por vela (fraccion)."""
    r = log_returns(c) if log else simple_returns(c)
    r2 = np.nan_to_num(r) ** 2
    init = np.nanmean(r2[1:min(len(r2), 100)])
    y, _ = _lfilter([1 - lam], [1, -lam], r2, zi=[lam * init])
    y[0] = np.nan
    return np.sqrt(y)


def ema(x: np.ndarray, span: float | None = None, alpha: float | None = None) -> np.ndarray:
    """Media movil exponencial: e_i = a*x_i + (1-a)*e_{i-1}, e_0 = x_0; a = 2/(span+1)."""
    x = np.asarray(x, dtype=np.float64)
    a = alpha if alpha is not None else 2.0 / (span + 1.0)
    y, _ = _lfilter([a], [1, -(1 - a)], x, zi=[(1 - a) * x[0]])
    return y


def true_range(h, l, c) -> np.ndarray:
    pc = shift(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    return tr


def atr(h, l, c, n: int = 14, method: str = "wilder") -> np.ndarray:
    """Average True Range. method="wilder" (RMA, alpha=1/n, sembrada con la SMA de n) o "sma"."""
    tr = true_range(np.asarray(h, float), np.asarray(l, float), np.asarray(c, float))
    if method == "sma":
        return rolling_mean(tr, n)
    out = np.full(len(tr), np.nan)
    if len(tr) < n:
        return out
    seed = tr[:n].mean()
    a = 1.0 / n
    y, _ = _lfilter([a], [1, -(1 - a)], tr[n:], zi=[(1 - a) * seed])
    out[n - 1] = seed
    out[n:] = y
    return out


def zscore(x: np.ndarray, n: int, ddof: int = 1) -> np.ndarray:
    """(x_i - media_n) / sigma_n sobre la ventana que incluye x_i (como las bandas del bot)."""
    return (np.asarray(x, float) - rolling_mean(x, n)) / rolling_std(x, n, ddof)


def rolling_vwap(c, v, n: int) -> np.ndarray:
    """VWAP de las ultimas n velas (precio de cierre ponderado por volumen)."""
    num = rolling_sum(np.asarray(c, float) * v, n)
    den = rolling_sum(v, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


# --------------------------------------------------------------------------------------------
# Simulador
# --------------------------------------------------------------------------------------------
def resolve_exit(o, h, l, c, j0: int, j_end: int, entry: float, tp: float, sl: float,
                 trail: float | None = None, max_hold: int | None = None):
    """Primera barrera tocada desde la vela j0 (incluida) hasta j_end (excluida).

    tp / sl: precios absolutos (NaN o inf = sin barrera).
    trail: distancia absoluta del trailing stop (stop_j = max(sl, max(entry, H_{j0..j-1}) - trail)).
           El maximo de la propia vela j NO sube el stop de la vela j (no se conoce el orden intra-vela).
    max_hold: maximo de velas evaluadas; si se agota, sale al cierre de la ultima (TIME).
    Reglas: TP y stop en la misma vela -> stop. Stop con hueco (open <= stop) -> sale al open.
    Devuelve (j_salida, precio_salida, motivo).
    """
    has_tp = tp is not None and np.isfinite(tp)
    has_sl = sl is not None and np.isfinite(sl)
    has_tr = trail is not None and np.isfinite(trail) and trail > 0
    jlim = j_end if max_hold is None else min(j_end, j0 + int(max_hold))
    if j0 >= jlim:
        return j0 - 1, entry, END
    sl_v = sl if has_sl else -np.inf
    run_max = entry
    k, step = j0, 64
    while k < jlim:
        k2 = min(jlim, k + step)
        hh, ll = h[k:k2], l[k:k2]
        if has_tr:
            prev = np.empty(len(hh))
            prev[0] = run_max
            if len(hh) > 1:
                prev[1:] = np.maximum(run_max, np.maximum.accumulate(hh[:-1]))
            stop = np.maximum(prev - trail, sl_v)
            hit_sl = ll <= stop
        else:
            stop = sl_v
            hit_sl = ll <= sl_v
        hit = hit_sl | (hh >= tp) if has_tp else hit_sl
        if hit.any():
            m = int(np.argmax(hit))
            j = k + m
            if hit_sl[m]:
                st = float(stop[m]) if has_tr else float(sl_v)
                px = min(st, float(o[j]))
                reason = TRAIL if (has_tr and st > sl_v) else SL
                return j, px, reason
            return j, float(tp), TP
        if has_tr:
            run_max = max(run_max, float(hh.max()))
        k, step = k2, min(step * 4, 16384)
    j = jlim - 1
    reason = TIME if (max_hold is not None and jlim == j0 + int(max_hold)) else END
    return j, float(c[j]), reason


class Trades:
    """Resultado de simulate(). Arrays alineados por operacion (orden cronologico)."""

    FIELDS = ("sig_idx", "entry_idx", "exit_idx", "entry_px", "exit_px", "tp", "sl", "reason",
              "gross_ret", "net_ret", "risk_pct", "r_mult", "entry_t", "exit_t")

    def __init__(self, rows: dict, meta: dict):
        for f in self.FIELDS:
            setattr(self, f, rows[f])
        self.meta = meta

    def __len__(self):
        return len(self.net_ret)

    @property
    def hold(self):
        """Velas en posicion (salida - entrada)."""
        return self.exit_idx - self.entry_idx

    def subset(self, mask) -> "Trades":
        return Trades({f: getattr(self, f)[mask] for f in self.FIELDS}, dict(self.meta))

    def between(self, ts0: int, ts1: int) -> "Trades":
        """Operaciones cuya ENTRADA cae en [ts0, ts1)."""
        return self.subset((self.entry_t >= ts0) & (self.entry_t < ts1))

    def to_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(self.FIELDS)
            for i in range(len(self)):
                w.writerow([getattr(self, fl)[i] for fl in self.FIELDS])

    @staticmethod
    def concat(lst) -> "Trades":
        lst = [x for x in lst if x is not None]
        rows = {f: np.concatenate([getattr(x, f) for x in lst]) if lst else np.array([]) for f in Trades.FIELDS}
        order = np.argsort(rows["entry_t"], kind="stable")
        rows = {f: v[order] for f, v in rows.items()}
        meta = {"concat": [x.meta for x in lst]}
        return Trades(rows, meta)


def net_return(entry, exit_, fee=FEE, slip=SLIP):
    """Retorno neto de un largo: (exit/entry - 1) - (fee+slip)*(1 + exit/entry).
    (comision y deslizamiento sobre el nocional de compra y sobre el de venta) ~= gross - 0.24 %."""
    g = np.asarray(exit_, float) / np.asarray(entry, float)
    return (g - 1.0) - (fee + slip) * (1.0 + g)


def simulate(bars: Bars, entries, tp=None, sl=None, *, period=None, entry_mode: str = "close",
             levels: str = "absolute", max_hold: int | None = None, trail=None,
             fee: float = FEE, slip: float = SLIP, invalid: str = "skip", cooldown: int = 0,
             risk=None) -> Trades:
    """Simula largos con barreras TP / SL / tiempo, una posicion a la vez.

    entries: bool (N,)  senal en el CIERRE de la vela i (solo usa datos <= i).
    tp, sl : float (N,) o escalar o None. Precios absolutos fijados en la vela de senal. NaN = sin barrera.
    period : (i0, i1). Solo se toman senales con i0 <= i < i1 y la salida nunca usa velas >= i1
             (si sigue abierta, se cierra al cierre de i1-1, motivo END). Por defecto toda la serie.
    entry_mode: "close" (precio = c[i], barreras desde la vela i+1) o "next_open" (precio = o[i+1],
             barreras desde la vela i+1, incluida).
    levels : "absolute" (TP/SL tal cual) o "relative" (se re-anclan al precio real de entrada:
             tp_e = entry*tp/c[i]); solo importa con next_open.
    max_hold: maximo de velas en posicion (barrera de tiempo). None = sin limite.
    trail  : distancia absoluta (array (N,) o escalar) para trailing stop (Chandelier). None = sin trailing.
    invalid: que hacer si la entrada no queda estrictamente entre SL y TP: "skip" (no operar) o
             "immediate" (abrir y cerrar al mismo precio: pierde solo costos; modela al bot en vivo,
             que cierra en el siguiente tick si precio >= TP o <= SL).
    cooldown: velas extra de espera tras una salida (por defecto la senal debe ser posterior a la vela de salida).
    risk   : distancia de riesgo absoluta (N,) para r_mult cuando no hay SL (p. ej. trailing). Por defecto entry-sl.
    """
    N = len(bars)
    o, h, l, c = bars.o, bars.h, bars.l, bars.c
    entries = np.asarray(entries, dtype=bool)
    if entries.shape != (N,):
        raise ValueError("entries debe tener la misma longitud que bars")
    i0, i1 = (0, N) if period is None else (int(period[0]), int(period[1]))

    def _arr(x):
        if x is None:
            return np.full(N, np.nan)
        x = np.asarray(x, dtype=np.float64)
        return np.full(N, float(x)) if x.ndim == 0 else x

    TPa, SLa, TRa = _arr(tp), _arr(sl), (None if trail is None else _arr(trail))
    RKa = None if risk is None else _arr(risk)
    cand = np.flatnonzero(entries[i0:i1]) + i0
    rows = {f: [] for f in Trades.FIELDS}
    last_exit = -1
    n_sig, n_skip_busy, n_invalid = len(cand), 0, 0
    for i in cand:
        if i <= last_exit + cooldown:
            n_skip_busy += 1
            continue
        if entry_mode == "close":
            e_idx, entry, j0 = i, float(c[i]), i + 1
        elif entry_mode == "next_open":
            if i + 1 >= i1:
                continue
            e_idx, entry, j0 = i + 1, float(o[i + 1]), i + 1
        else:
            raise ValueError(entry_mode)
        tpi, sli = TPa[i], SLa[i]
        if levels == "relative" and entry_mode != "close":
            scale = entry / c[i]
            tpi, sli = tpi * scale, sli * scale
        trv = None if TRa is None else TRa[i]
        bad = (np.isfinite(sli) and sli >= entry) or (np.isfinite(tpi) and tpi <= entry)
        if bad:
            n_invalid += 1
            if invalid == "skip":
                continue
            j, px, why = e_idx, entry, INVALID
        else:
            j, px, why = resolve_exit(o, h, l, c, j0, i1, entry, tpi, sli, trv, max_hold)
            if j < e_idx:  # sin velas posteriores dentro del periodo
                j, px, why = e_idx, entry, END
        g = px / entry - 1.0
        net = float(net_return(entry, px, fee, slip))
        if RKa is not None and np.isfinite(RKa[i]):
            rp = RKa[i] / entry
        elif np.isfinite(sli) and sli < entry:
            rp = (entry - sli) / entry
        else:
            rp = np.nan
        for f, v in (("sig_idx", i), ("entry_idx", e_idx), ("exit_idx", j), ("entry_px", entry),
                     ("exit_px", px), ("tp", tpi), ("sl", sli), ("reason", why), ("gross_ret", g),
                     ("net_ret", net), ("risk_pct", rp), ("r_mult", net / rp if rp and np.isfinite(rp) else np.nan),
                     ("entry_t", bars.t[e_idx]), ("exit_t", bars.t[j])):
            rows[f].append(v)
        last_exit = j
    dtypes = {"sig_idx": np.int64, "entry_idx": np.int64, "exit_idx": np.int64, "reason": np.int64,
              "entry_t": np.int64, "exit_t": np.int64}
    rows = {f: np.asarray(v, dtype=dtypes.get(f, np.float64)) for f, v in rows.items()}
    meta = {"symbol": bars.symbol, "tf": bars.tf, "period": (i0, i1), "t0": int(bars.t[i0]) if i0 < N else None,
            "t1": int(bars.t[i1 - 1]) if i1 > 0 else None, "entry_mode": entry_mode, "levels": levels,
            "max_hold": max_hold, "fee": fee, "slip": slip, "n_signals": int(n_sig),
            "n_skipped_busy": int(n_skip_busy), "n_invalid": int(n_invalid), "invalid": invalid}
    return Trades(rows, meta)


# --------------------------------------------------------------------------------------------
# Estadistica
# --------------------------------------------------------------------------------------------
def wilson(k, n, z: float = 1.959963984540054):
    """Intervalo de Wilson para una proporcion. Devuelve (p_hat, lo, hi)."""
    if n == 0:
        return float("nan"), 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, centre - half), min(1.0, centre + half)


def min_n_wilson(p_obs: float, p0: float, z: float = 1.959963984540054, n_max: int = 10 ** 7) -> int:
    """Menor n tal que el limite inferior de Wilson con proporcion observada p_obs supera p0."""
    if p_obs <= p0:
        return -1
    lo_n, hi_n = 1, 1
    while wilson(p_obs * hi_n, hi_n, z)[1] <= p0:
        hi_n *= 2
        if hi_n > n_max:
            return -1
    while lo_n < hi_n:
        mid = (lo_n + hi_n) // 2
        if wilson(p_obs * mid, mid, z)[1] > p0:
            hi_n = mid
        else:
            lo_n = mid + 1
    return lo_n


def two_outcome_moments(p: float, b: float, R: float, c: float):
    """Media y desviacion por operacion si se gana b*R o se pierde R, con costo c (mismas unidades)."""
    mu = p * b * R - (1 - p) * R - c
    sd = (b + 1) * R * math.sqrt(p * (1 - p))
    return mu, sd


def breakeven_p(b: float, R: float, c: float) -> float:
    """p* = (1 + c/R) / (1 + b)."""
    return (1 + c / R) / (1 + b)


def min_n_mean(mu: float, sd: float, alpha: float = 0.05, power: float = 0.80, n_tests: int = 1) -> float:
    """Operaciones necesarias para que E>0 sea significativa (unilateral, Bonferroni n_tests) con potencia dada:
    n = ((z_{1-alpha/n_tests} + z_{power}) * sd / mu)^2."""
    if mu <= 0:
        return float("inf")
    za = _st.norm.ppf(1 - alpha / n_tests)
    zb = _st.norm.ppf(power) if power else 0.0
    return ((za + zb) * sd / mu) ** 2


def bootstrap(x, stat=np.mean, B: int = 5000, block: int = 1, seed: int = 0, ci: float = 0.95):
    """Bootstrap (por bloques moviles si block>1). Devuelve dict(est, lo, hi, p_le0)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return {"est": float("nan"), "lo": float("nan"), "hi": float("nan"), "p_le0": float("nan")}
    rng = np.random.default_rng(seed)
    if block <= 1:
        idx = rng.integers(0, n, size=(B, n))
    else:
        nb = int(math.ceil(n / block))
        starts = rng.integers(0, n - block + 1, size=(B, nb))
        idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(B, -1)[:, :n]
    s = np.array([stat(x[r]) for r in idx]) if stat is not np.mean else x[idx].mean(axis=1)
    a = (1 - ci) / 2
    return {"est": float(stat(x)), "lo": float(np.quantile(s, a)), "hi": float(np.quantile(s, 1 - a)),
            "p_le0": float(np.mean(s <= 0))}


def sharpe(x) -> float:
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1)) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan")


def psr(sr: float, n: int, sr0: float = 0.0, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Probabilistic Sharpe Ratio (Bailey y Lopez de Prado): P(SR verdadero > sr0). sr por operacion."""
    den = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr * sr))
    return float(_st.norm.cdf((sr - sr0) * math.sqrt(n - 1) / den))


def expected_max_sr(n_trials: int, var_sr: float) -> float:
    """SR0 = E[max SR] de n_trials estrategias sin habilidad (varianza var_sr entre pruebas)."""
    if n_trials <= 1:
        return 0.0
    g = 0.5772156649015329
    return math.sqrt(var_sr) * ((1 - g) * _st.norm.ppf(1 - 1 / n_trials) + g * _st.norm.ppf(1 - 1 / (n_trials * math.e)))


def deflated_sharpe(x, n_trials: int, var_sr: float | None = None, sr_trials=None) -> dict:
    """Deflated Sharpe Ratio de la serie de retornos por operacion x, dado que se probaron n_trials
    configuraciones. var_sr: varianza de los SR de las pruebas (o sr_trials para estimarla).
    Si no se da, se usa 1/(n-1) (varianza del SR bajo H0 con n operaciones)."""
    x = np.asarray(x, float)
    n = len(x)
    sr = sharpe(x)
    if var_sr is None:
        var_sr = float(np.var(sr_trials, ddof=1)) if sr_trials is not None and len(sr_trials) > 1 else 1.0 / max(1, n - 1)
    sr0 = expected_max_sr(n_trials, var_sr)
    sk = float(_st.skew(x)) if n > 2 else 0.0
    ku = float(_st.kurtosis(x, fisher=False)) if n > 3 else 3.0
    return {"sr": sr, "sr0": sr0, "dsr": psr(sr, n, sr0, sk, ku), "psr0": psr(sr, n, 0.0, sk, ku),
            "skew": sk, "kurt": ku, "n": n, "n_trials": n_trials}


def bonferroni(p: float, n_tests: int) -> float:
    return min(1.0, p * n_tests)


def pbo_cscv(M: np.ndarray, S: int = 16, stat: str = "mean") -> dict:
    """Probability of Backtest Overfitting por Combinatorially Symmetric Cross-Validation.

    M: matriz (T periodos x N configuraciones) de rendimiento por periodo (p. ej. suma de R netos del mes).
    S: numero (par) de bloques contiguos. Para cada combinacion de S/2 bloques como IS:
       n* = argmax rendimiento IS; w = rango relativo OOS de n*; lambda = ln(w/(1-w)).
    PBO = P(lambda <= 0). Devuelve tambien la perdida OOS del elegido y la regresion OOS~IS.
    stat: "mean" (media por periodo) o "sharpe" (media/desv. por periodo).
    """
    M = np.asarray(M, float)
    T, N = M.shape
    blocks = np.array_split(np.arange(T), S)
    comb = list(itertools.combinations(range(S), S // 2))
    sums = np.array([M[b].sum(axis=0) for b in blocks])        # S x N
    sq = np.array([(M[b] ** 2).sum(axis=0) for b in blocks])
    cnt = np.array([len(b) for b in blocks], float)
    lam, is_best, oos_of_best = [], [], []
    for cmb in comb:
        isb = np.zeros(S, bool)
        isb[list(cmb)] = True
        s_is, s_oos = sums[isb].sum(0), sums[~isb].sum(0)
        n_is, n_oos = cnt[isb].sum(), cnt[~isb].sum()
        if stat == "sharpe":
            q_is, q_oos = sq[isb].sum(0), sq[~isb].sum(0)
            m_is, m_oos = s_is / n_is, s_oos / n_oos
            sd_is = np.sqrt(np.maximum(q_is / n_is - m_is ** 2, 1e-18))
            sd_oos = np.sqrt(np.maximum(q_oos / n_oos - m_oos ** 2, 1e-18))
            p_is, p_oos = m_is / sd_is, m_oos / sd_oos
        else:
            p_is, p_oos = s_is / n_is, s_oos / n_oos
        best = int(np.argmax(p_is))
        r = _st.rankdata(p_oos)[best]
        w = r / (N + 1)
        lam.append(math.log(w / (1 - w)))
        is_best.append(p_is[best])
        oos_of_best.append(p_oos[best])
    lam = np.array(lam)
    is_best, oos_of_best = np.array(is_best), np.array(oos_of_best)
    slope = float(np.polyfit(is_best, oos_of_best, 1)[0]) if len(set(is_best)) > 1 else float("nan")
    return {"pbo": float(np.mean(lam <= 0)), "lambda_median": float(np.median(lam)),
            "p_oos_loss": float(np.mean(oos_of_best < 0)), "oos_best_mean": float(oos_of_best.mean()),
            "is_best_mean": float(is_best.mean()), "slope_oos_on_is": slope, "n_combinations": len(comb),
            "T": T, "N": N, "S": S}


# --------------------------------------------------------------------------------------------
# Metricas
# --------------------------------------------------------------------------------------------
def equity_curve(net_ret, frac: float = 1.0, capital0: float = 1.0) -> np.ndarray:
    """Capital compuesto invirtiendo la fraccion `frac` del capital en cada operacion (secuencial)."""
    return capital0 * np.concatenate(([1.0], np.cumprod(1.0 + frac * np.asarray(net_ret, float))))


def max_drawdown(curve, additive: bool = False) -> float:
    """MDD de una curva. additive=False: fraccion del pico (curva multiplicativa); True: diferencia absoluta."""
    curve = np.asarray(curve, float)
    if len(curve) == 0:
        return 0.0
    peak = np.maximum.accumulate(curve)
    return float(np.max(peak - curve)) if additive else float(np.max((peak - curve) / peak))


def max_streak(mask) -> int:
    best = cur = 0
    for m in np.asarray(mask, bool):
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def metrics(tr: Trades, n_configs: int = 1, frac: float = 1.0, boot: int = 0, block: int = 1,
            years: float | None = None) -> dict:
    """Resumen estandar del equipo.

    WR = P(retorno neto > 0) con IC de Wilson 95 %. tp_rate = fraccion que salio por TP.
    b_eff = ganancia media neta / perdida media neta. E en % del nocional y en R (R = entrada - SL).
    PF = suma ganancias / suma perdidas (netas). MDD_pct: curva compuesta con `frac` del capital por
    operacion; MDD_R: curva aditiva en R. p_value: t unilateral H0: E<=0; p_bonf = p * n_configs.
    """
    x = np.asarray(tr.net_ret, float)
    n = len(x)
    out = {"n": n, "n_configs": int(n_configs)}
    if n == 0:
        out.update({k: float("nan") for k in ("wr", "wr_lo", "wr_hi", "tp_rate", "b_eff", "E_pct", "E_R", "pf",
                                              "mdd_pct", "mdd_R", "p_value", "p_bonf", "sd_pct")})
        return out
    win = x > 0
    k = int(win.sum())
    p, lo, hi = wilson(k, n)
    aw = float(x[win].mean()) if k else 0.0
    al = float(-x[~win].mean()) if k < n else 0.0
    sd = float(x.std(ddof=1)) if n > 1 else float("nan")
    tstat = float(x.mean() / (sd / math.sqrt(n))) if n > 1 and sd > 0 else float("nan")
    pval = float(1 - _st.t.cdf(tstat, n - 1)) if np.isfinite(tstat) else float("nan")
    rm = np.asarray(tr.r_mult, float)
    rmf = np.where(np.isfinite(rm), rm, 0.0)
    gp, gl = float(x[win].sum()), float(-x[~win].sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        b_des = (tr.tp - tr.entry_px) / (tr.entry_px - tr.sl)
    b_des = b_des[np.isfinite(b_des) & (tr.reason != INVALID)]
    g = np.asarray(tr.gross_ret, float)
    if years is None and tr.meta.get("t0") is not None and tr.meta.get("t1") is not None:
        years = (tr.meta["t1"] - tr.meta["t0"]) / (365.25 * 86400e3)
    out.update({
        "wr": p, "wr_lo": lo, "wr_hi": hi,
        "tp_rate": float(np.mean(tr.reason == TP)), "sl_rate": float(np.mean(tr.reason == SL)),
        "time_rate": float(np.mean((tr.reason == TIME) | (tr.reason == END))),
        "invalid_rate": float(np.mean(tr.reason == INVALID)),
        "avg_win_pct": aw * 100, "avg_loss_pct": al * 100,
        "b_eff": aw / al if al > 0 else float("inf"),
        "b_design_med": float(np.median(b_des)) if len(b_des) else float("nan"),
        "wr_breakeven": al / (aw + al) if (aw + al) > 0 else float("nan"),
        "E_gross_pct": float(g.mean() * 100), "wr_gross": float(np.mean(g > 0)),
        "E_pct": float(x.mean() * 100), "E_R": float(np.nanmean(rm)) if np.isfinite(rm).any() else float("nan"),
        "sd_pct": sd * 100, "t": tstat, "p_value": pval, "p_bonf": bonferroni(pval, n_configs) if np.isfinite(pval) else float("nan"),
        "pf": gp / gl if gl > 0 else float("inf"),
        "mdd_pct": max_drawdown(equity_curve(x, frac)) * 100,
        "mdd_R": max_drawdown(np.concatenate(([0.0], np.cumsum(rmf))), additive=True),
        "max_loss_streak": max_streak(~win),
        "total_ret_pct": float((np.prod(1 + frac * x) - 1) * 100),
        "risk_med_pct": float(np.nanmedian(tr.risk_pct) * 100) if np.isfinite(tr.risk_pct).any() else float("nan"),
        "hold_med_bars": float(np.median(tr.hold)),
        "trades_per_year": n / years if years else float("nan"),
        "sharpe_trade": sharpe(x),
    })
    if boot:
        bs = bootstrap(x, B=boot, block=block)
        out.update({"E_boot_lo_pct": bs["lo"] * 100, "E_boot_hi_pct": bs["hi"] * 100, "E_boot_p_le0": bs["p_le0"]})
    return out


def fmt(m: dict, label: str = "") -> str:
    """Una linea legible con las cifras obligatorias del equipo."""
    if m["n"] == 0:
        return f"{label:<28} n=0"
    return (f"{label:<28} n={m['n']:>5}  WR={m['wr']*100:5.1f}% [{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}]"
            f"  TP%={m['tp_rate']*100:5.1f}  b_eff={m['b_eff']:5.2f}  E={m['E_pct']:+.3f}% ({m['E_R']:+.3f}R)"
            f"  PF={m['pf']:5.2f}  MDD={m['mdd_pct']:5.1f}% ({m['mdd_R']:.1f}R)  p={m['p_value']:.3g}"
            f"  pBonf={m['p_bonf']:.3g} (N={m['n_configs']})")


MD_COLS = [("n", "n", "{:d}"), ("WR %", "wr", "{:.1%}"), ("IC Wilson 95 %", None, None), ("TP %", "tp_rate", "{:.1%}"),
           ("b_eff", "b_eff", "{:.2f}"), ("E neta %", "E_pct", "{:+.3f}"), ("E neta R", "E_R", "{:+.3f}"),
           ("PF", "pf", "{:.2f}"), ("MDD %", "mdd_pct", "{:.1f}"), ("MDD R", "mdd_R", "{:.1f}"),
           ("p (E>0)", "p_value", "{:.3g}"), ("E bruta %", "E_gross_pct", "{:+.3f}"),
           ("R med %", "risk_med_pct", "{:.2f}"), ("IC95 E boot %", "BOOT", None)]


def md_row(label: str, m: dict) -> str:
    cells = [label]
    for _, key, f in MD_COLS:
        if key is None:
            cells.append("-" if m["n"] == 0 else f"[{m['wr_lo']*100:.1f}, {m['wr_hi']*100:.1f}]")
        elif key == "BOOT":
            cells.append(f"[{m['E_boot_lo_pct']:+.3f}, {m['E_boot_hi_pct']:+.3f}]" if "E_boot_lo_pct" in m and m["n"] else "-")
        else:
            v = m.get(key, float("nan"))
            try:
                cells.append(f.format(v) if m["n"] else "-")
            except (ValueError, TypeError):
                cells.append(str(v))
    return "| " + " | ".join(cells) + " |"


def md_header(first: str = "Caso") -> str:
    names = [first] + [c[0] for c in MD_COLS]
    return "| " + " | ".join(names) + " |\n|" + "---|" * len(names)


def monthly_matrix(trades_list, months, value: str = "r_mult") -> np.ndarray:
    """Matriz (len(months) x len(trades_list)) con la suma mensual (por mes de entrada) de `value`
    ("r_mult" o "net_ret"). Para PBO/CSCV y walk-forward."""
    months = np.asarray(months)
    M = np.zeros((len(months), len(trades_list)))
    for j, tr in enumerate(trades_list):
        if tr is None or len(tr) == 0:
            continue
        mm = tr.entry_t.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)
        mm = (1970 + mm // 12) * 100 + (mm % 12) + 1
        vals = np.nan_to_num(getattr(tr, value))
        pos = np.searchsorted(months, mm)
        ok = (pos < len(months)) & (months[np.minimum(pos, len(months) - 1)] == mm)
        np.add.at(M[:, j], pos[ok], vals[ok])
    return M
