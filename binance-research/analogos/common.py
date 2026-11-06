"""Marco común de la predicción por análogos (doc/plan-analogos.md, sección 0).

Datos, periodos, búsqueda de vecinos sin fuga de futuro, regla de operación y métricas. Lo usan las 5 sugerencias
(s1_knn.py ... s5_multi.py). Proyecto aparte: no toca las estrategias del bot.

Datos: velas spot de 15 min y futuros en formato .npy (las mismas que descarga la v3). Se buscan en DATA_DIRS en orden y
se concatenan; por defecto, v3_research/tmp/data2022 (2021-10 a 2022-12), v3_research/tmp/new20 (2023-01 a 2026-10) y
v3_research (2025-04 en adelante). Otra lista: variable de entorno ANALOGOS_DATA_DIRS (separada por ';').
"""
import datetime as dt
import math
import os

import numpy as np
from scipy.stats import rankdata

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.join(os.path.dirname(HERE), "v3_research")
DATA_DIRS = [p for p in os.environ.get("ANALOGOS_DATA_DIRS", "").split(";") if p] or [
    os.path.join(RESEARCH, "tmp", "data2022"), os.path.join(RESEARCH, "tmp", "new20"), RESEARCH]
OUT_DIR = os.path.join(HERE, "output")

HOUR = 3_600_000
BASE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
COST = 0.0024            # ida y vuelta
STAKE = 15.0             # USDT por operación
MARGIN = 24              # horas: un vecino s solo vale si s <= t - MARGIN (su futuro ya terminó)
SEP = 12                 # como máximo un vecino por bloque de SEP horas y moneda (no contar el mismo episodio)


def to_ms(day: str) -> int:
    return int(dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


TRAIN_END = to_ms("2023-01-01")     # antes: solo entrenamiento (pesos, cortes, PCA)
SPLIT = to_ms("2025-01-01")         # diseño [TRAIN_END, SPLIT) | validación [SPLIT, fin]


def iso(ms) -> str:
    return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


# ----------------------------------------------------------------------------------------------------------- datos
def _concat(name: str, dirs) -> np.ndarray:
    parts = [np.load(p) for p in (os.path.join(d, name) for d in dirs) if os.path.exists(p)]
    if not parts:
        raise FileNotFoundError(f"{name} no está en {dirs}")
    a = np.vstack(parts)
    a = a[np.argsort(a[:, 0], kind="stable")]
    return a[np.r_[True, np.diff(a[:, 0]) > 0]]


def load_hourly(symbols=BASE, dirs=None, start=None, futures=False, step=1):
    """Velas de `step` horas alineadas para todas las monedas.

    Índice t = vela que empieza en T[t] y cierra en T[t] + step h. Devuelve dict con T (ms), close, volume, taker
    (matrices monedas x tiempo) y, si futures=True, funding y oi con el último dato publicado hasta el cierre de la vela.
    """
    dirs = dirs or DATA_DIRS
    bar = step * HOUR
    raw = {s: _concat(f"klines/{s}_15m.npy", dirs) for s in symbols}
    t0 = max(int(r[0, 0]) // bar * bar for r in raw.values())
    if start is not None:
        t0 = max(t0, start)
    t1 = min(int(r[-1, 0]) // bar * bar for r in raw.values())
    T = np.arange(t0, t1, bar, dtype=np.int64)
    n = len(T)
    close, vol, taker = (np.empty((len(symbols), n)) for _ in range(3))
    for i, s in enumerate(symbols):
        a = raw[s]
        b = (a[:, 0] // bar).astype(np.int64) * bar
        j = np.searchsorted(T, b)
        ok = (j < n) & (T[np.minimum(j, n - 1)] == b)
        v = np.bincount(j[ok], weights=a[ok, 5], minlength=n)
        k = np.bincount(j[ok], weights=a[ok, 6], minlength=n)
        last = np.full(n, np.nan)
        last[j[ok]] = a[ok, 4]                                  # el último de la vela gana (orden temporal)
        idx = np.where(np.isfinite(last), np.arange(n), 0)
        np.maximum.accumulate(idx, out=idx)
        close[i], vol[i], taker[i] = last[idx], v, k
    out = {"symbols": list(symbols), "T": T, "step": step, "close": close, "volume": vol, "taker": taker}
    if futures:
        end = T + bar                                          # cierre de cada vela
        fund, oi = np.full((len(symbols), n), np.nan), np.full((len(symbols), n), np.nan)
        for i, s in enumerate(symbols):
            f = _concat(f"futures/{s}_funding.npy", dirs)
            j = np.searchsorted(f[:, 0], end, "right") - 1
            fund[i] = np.where(j >= 0, f[np.maximum(j, 0), 1], np.nan)
            m = _concat(f"futures/{s}_metrics.npy", dirs)
            m = m[np.isfinite(m[:, 1]) & (m[:, 1] > 0)]
            j = np.searchsorted(m[:, 0], end, "right") - 1
            oi[i] = np.where(j >= 0, m[np.maximum(j, 0), 1], np.nan)
        out["funding"], out["oi"] = fund, oi
    return out


def future_returns(close: np.ndarray, h: int) -> np.ndarray:
    lp = np.log(close)
    y = np.full_like(lp, np.nan)
    y[:, :-h] = lp[:, h:] - lp[:, :-h]
    return y


# ------------------------------------------------------------------------------------------------- búsqueda k-NN
class Library:
    """Filas (moneda, t) con su vector, ordenadas por tiempo. `lag` = margen en velas."""

    def __init__(self, X: np.ndarray, coin: np.ndarray, t: np.ndarray):
        o = np.lexsort((coin, t))
        self.X = np.ascontiguousarray(X[o], dtype=np.float32)
        self.coin, self.t = coin[o].astype(np.int32), t[o].astype(np.int64)
        self.n2 = (self.X.astype(np.float64) ** 2).sum(1).astype(np.float32)


def knn(lib: Library, Q: np.ndarray, qt: np.ndarray, k: int, lag: int = MARGIN, sep: int = SEP, cand: int = None,
        block: int = 256, return_cand: bool = False):
    """Los k vecinos más cercanos de cada consulta entre las filas de la biblioteca con t <= qt - lag.

    Distancia euclidiana. Para no repetir el mismo episodio, se queda con el más cercano de cada bloque de `sep` velas y
    moneda. Devuelve (idx, dist) de forma (nq, k) con índices de fila de la biblioteca (-1 si no hay suficientes).
    Con return_cand=True devuelve los `cand` candidatos sin filtrar (para re-ordenarlos con otra distancia).
    """
    Q = np.ascontiguousarray(Q, dtype=np.float32)
    nq = len(Q)
    cand = cand or max(6 * k, 60)
    q2 = (Q.astype(np.float64) ** 2).sum(1).astype(np.float32)
    allowed = np.searchsorted(lib.t, qt - lag, "right")
    order = np.argsort(qt, kind="stable")
    width = cand if return_cand else k
    I = np.full((nq, width), -1, np.int64)
    Dd = np.full((nq, width), np.inf, np.float32)
    for s in range(0, nq, block):
        rows = order[s:s + block]
        m = int(allowed[rows].max())
        if m == 0:
            continue
        G = q2[rows, None] + lib.n2[None, :m] - 2.0 * (Q[rows] @ lib.X[:m].T)
        G[np.arange(m)[None, :] >= allowed[rows, None]] = np.inf
        c = min(cand, m)
        p = np.argpartition(G, c - 1, axis=1)[:, :c] if c < m else np.tile(np.arange(m), (len(rows), 1))
        g = np.take_along_axis(G, p, 1)
        o = np.argsort(g, 1, kind="stable")
        p, g = np.take_along_axis(p, o, 1), np.take_along_axis(g, o, 1)
        if return_cand:
            I[rows, :c], Dd[rows, :c] = np.where(np.isfinite(g), p, -1), g
            continue
        p, g = episode_filter(lib, p, g, sep, k)
        I[rows, :p.shape[1]], Dd[rows, :p.shape[1]] = p, g
    return I, np.sqrt(np.maximum(Dd, 0))


def episode_filter(lib: Library, p: np.ndarray, g: np.ndarray, sep: int, k: int):
    """Por fila: el candidato más cercano de cada (moneda, bloque de sep velas), en orden de distancia; los k primeros."""
    valid = (p >= 0) & np.isfinite(g)
    pp = np.where(valid, p, 0)
    key = lib.coin[pp].astype(np.int64) * 10**9 + lib.t[pp] // max(sep, 1)
    key = np.where(valid, key, -1 - np.arange(p.shape[1])[None, :])          # inválidos: claves únicas (se descartan)
    rank = np.tile(np.arange(p.shape[1]), (p.shape[0], 1))
    o = np.argsort(key * p.shape[1] + rank, axis=1, kind="stable")
    ks = np.take_along_axis(key, o, 1)
    first = np.ones_like(ks, bool)
    first[:, 1:] = ks[:, 1:] != ks[:, :-1]
    keep = np.zeros_like(first)
    np.put_along_axis(keep, o, first, 1)
    keep &= valid
    score = np.where(keep, rank, p.shape[1] + rank)
    o = np.argsort(score, 1, kind="stable")[:, :k]
    ok = np.take_along_axis(keep, o, 1)
    return np.where(ok, np.take_along_axis(p, o, 1), -1), np.where(ok, np.take_along_axis(g, o, 1), np.inf)


def predict(lib_y: np.ndarray, idx: np.ndarray, dist: np.ndarray, k: int, weighted: bool):
    """ŷ (promedio, opcionalmente pesado por 1/(d+ε)) y consenso π (fracción de vecinos que subió)."""
    I, Dd = idx[:, :k], dist[:, :k].astype(np.float64)
    ok = I >= 0
    F = np.where(ok, lib_y[np.maximum(I, 0)], np.nan)
    ok &= np.isfinite(F)
    W = np.where(ok, 1.0 / (Dd + 1e-6) if weighted else 1.0, 0.0)
    F = np.nan_to_num(F)
    sw = W.sum(1)
    yhat = np.where(sw > 0, (W * F).sum(1) / np.where(sw > 0, sw, 1), np.nan)
    frac = np.where(ok.sum(1) > 0, (ok & (F > 0)).sum(1) / np.maximum(ok.sum(1), 1), np.nan)
    return yhat, frac


# --------------------------------------------------------------------------------------- operaciones y métricas
def trades(qt_ms: np.ndarray, qcoin: np.ndarray, yhat, frac, y, h: int, q: float, bar_ms: int = HOUR, cost=COST):
    """Compra si ŷ > costo y π >= q; vende a las h velas; sin solapar operaciones en la misma moneda."""
    out_t, out_c, out_net = [], [], []
    sig = (yhat > cost) & (frac >= q) & np.isfinite(y)
    for c in np.unique(qcoin):
        sel = np.flatnonzero((qcoin == c) & sig)
        sel = sel[np.argsort(qt_ms[sel], kind="stable")]
        nxt = -np.inf
        for i in sel:
            if qt_ms[i] >= nxt:
                out_t.append(qt_ms[i]); out_c.append(c); out_net.append(math.exp(y[i]) - 1 - cost)
                nxt = qt_ms[i] + h * bar_ms
    o = np.argsort(out_t, kind="stable")
    return np.array(out_t, np.int64)[o], np.array(out_c, np.int64)[o], np.array(out_net)[o]


def months(ms: np.ndarray) -> np.ndarray:
    d = np.array([dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc) for x in ms])
    return np.array([x.year * 12 + x.month - 1 for x in d], np.int64) if len(d) else np.array([], np.int64)


def trade_stats(t_ms, net, lo, hi) -> dict:
    m = (t_ms >= lo) & (t_ms < hi)
    g = net[m]
    n = len(g)
    if n == 0:
        return {"n": 0, "wr": None, "e": None, "pnl": 0.0, "t": None, "meses_pos": None}
    sd = g.std(ddof=1) if n > 1 else 0.0
    mon = months(t_ms[m])
    per = {u: g[mon == u].sum() for u in np.unique(mon)}
    first, last = months(np.array([lo]))[0], months(np.array([hi - 1]))[0]
    return {"n": int(n), "wr": round(float((g > 0).mean() * 100), 1), "e": round(float(g.mean() * 100), 3),
            "pnl": round(float(g.sum() * STAKE), 1), "t": round(float(g.mean() / sd * math.sqrt(n)), 2) if sd > 0 else None,
            "meses_pos": f"{sum(v > 0 for v in per.values())}/{last - first + 1}"}


def pred_stats(yhat, y) -> dict:
    ok = np.isfinite(yhat) & np.isfinite(y)
    if ok.sum() < 20 or np.std(yhat[ok]) == 0:
        return {"ic": None, "acierto": None}
    a, b = yhat[ok], y[ok]
    ic = np.corrcoef(rankdata(a), rankdata(b))[0, 1]
    return {"ic": round(float(ic), 4), "acierto": round(float((np.sign(a) == np.sign(b)).mean() * 100), 2)}


def evaluate(qt_ms, qcoin, yhat, frac, y, h, q, end_ms, bar_ms=HOUR) -> dict:
    """Métricas de predicción y de operaciones en diseño y validación."""
    tt, _, net = trades(qt_ms, qcoin, yhat, frac, y, h, q, bar_ms)
    res = {}
    for name, lo, hi in (("dis", TRAIN_END, SPLIT), ("val", SPLIT, end_ms)):
        m = (qt_ms >= lo) & (qt_ms < hi)
        res[name] = {**pred_stats(yhat[m], y[m]), **trade_stats(tt, net, lo, hi)}
    return res


def always_buy(T, close, h, end_ms) -> dict:
    """Referencia: comprar cada h velas en todas las monedas, sin mirar nada."""
    y = future_returns(close, h)
    t_all, net_all = [], []
    for c in range(close.shape[0]):
        for i in range(0, len(T) - h, h):
            if T[i] >= TRAIN_END and np.isfinite(y[c, i]):
                t_all.append(T[i]); net_all.append(math.exp(y[c, i]) - 1 - COST)
    t_all, net_all = np.array(t_all), np.array(net_all)
    return {name: trade_stats(t_all, net_all, lo, hi) for name, lo, hi in (("dis", TRAIN_END, SPLIT), ("val", SPLIT, end_ms))}


def best_on_design(rows: list, min_n: int = 100, key: str = "e"):
    """La fila con mayor E (u otra métrica) en diseño con al menos min_n operaciones. Validación no interviene."""
    ok = [r for r in rows if r["dis"]["n"] >= min_n and r["dis"][key] is not None]
    return max(ok, key=lambda r: r["dis"][key]) if ok else None


def passes(r) -> bool:
    """Criterio del plan: E neta > 0 en validación, t >= 2 y al menos 100 operaciones."""
    v = r["val"]
    return bool(v["n"] >= 100 and v["e"] is not None and v["e"] > 0 and v["t"] is not None and v["t"] >= 2)


# ------------------------------------------------------------------------------------------- ventanas de forma
def shape_windows(close: np.ndarray, L: int, norm: str = "forma") -> np.ndarray:
    """Ventanas (monedas, tiempo, L): 'forma' = log precio z-normalizado; 'retornos' = log retornos; 'precio' = crudo."""
    lp = np.log(close)
    nc, n = lp.shape
    W = np.full((nc, n, L), np.nan, np.float32)
    for c in range(nc):
        sw = np.lib.stride_tricks.sliding_window_view(lp[c], L + 1)
        if norm == "precio":
            X = np.exp(sw[:, 1:])
        elif norm == "retornos":
            X = np.diff(sw, axis=1)
        else:
            w = sw[:, 1:]
            X = (w - w.mean(1, keepdims=True)) / (w.std(1, keepdims=True) + 1e-12)
        W[c, L:] = X
    return W


def queries(T, nc, start_ms, end_ms, stride: int):
    """Consultas (moneda, t) cada `stride` velas en [start_ms, end_ms)."""
    ts = np.flatnonzero((T >= start_ms) & (T < end_ms))[::stride]
    return np.repeat(np.arange(nc), len(ts)), np.tile(ts, nc)


def save_json(obj, name: str):
    import json
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x))
