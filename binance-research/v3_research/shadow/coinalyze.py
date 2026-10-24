"""Fuente sustituta de datos de futuros para la v3 en vivo (doc/estrategia-v3-hacia-el-80.md, seccion 7.6, salida 2).

data.binance.vision publica los futuros al dia siguiente y fapi.binance.com responde HTTP 451 desde la ubicacion del
usuario, asi que el dia en curso no tiene datos de futuros. Coinalyze (api.coinalyze.net, clave gratuita en la variable
COINALYZE_API_KEY) da los de Binance USD-M con ~7 dias de historia a 5 min:

  Binance (metrics, 5 min)                  Coinalyze
  sum_open_interest                         open-interest-history (5min, en la moneda base)
  sum_open_interest_value                   OI x cierre de la vela de 5 min del perpetuo (aproximacion del precio mark)
  count_toptrader_long_short_ratio          NO EXISTE: se arrastra el ultimo valor real
  sum_toptrader_long_short_ratio            NO EXISTE: se arrastra el ultimo valor real
  count_long_short_ratio                    long-short-ratio-history (5min, r)
  sum_taker_long_short_vol_ratio            ohlcv-history (5min): bv / (v - bv)
  fut15m (velas del perpetuo)               ohlcv-history (15min): o, h, l, c, v, bv
  funding (cada 8 h)                        funding-rate-history (1hour, en %): el valor en la hora de liquidacion
  premium15m (prima del perpetuo)           NO EXISTE: base futuro/spot (cierre del perpetuo / cierre spot - 1)

Las marcas de tiempo de Coinalyze se alinean con las de Binance con el desfase que mejor las hace coincidir en los dias
en que hay las dos (align_offset). Antes de usar esto para operar, equivalence_coinalyze.py mide si el modelo da las
mismas senales con estos datos que con los reales; si no, no se usa.
"""
import json
import os
import time
import urllib.parse
import urllib.request

import numpy as np

BASE = "https://api.coinalyze.net/v1"
MIN_GAP_S = 1.6           # 40 llamadas por minuto como maximo
MAX_SYMBOLS = 20


ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".env")


def env_file_value(name: str, path: str = None) -> str:
    """Valor de una variable del .env de la raiz del repo (donde estan las demas claves del bot), sin comillas."""
    path = path or ENV_FILE
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.strip().split("=", 1)
                if key.strip() == name:
                    return value.strip().strip('"\'')
    return ""


class Coinalyze:
    def __init__(self, api_key: str = None, opener=urllib.request.urlopen, sleep=time.sleep):
        self.api_key = api_key or os.environ.get("COINALYZE_API_KEY", "") or env_file_value("COINALYZE_API_KEY")
        if not self.api_key:
            raise RuntimeError("Falta COINALYZE_API_KEY (clave gratuita de coinalyze.net) en el entorno.")
        self.opener, self.sleep, self.last = opener, sleep, 0.0

    def get(self, endpoint: str, **params) -> list:
        wait = MIN_GAP_S - (time.monotonic() - self.last)
        if wait > 0:
            self.sleep(wait)
        url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"api_key": self.api_key})
        for attempt in range(4):
            try:
                self.last = time.monotonic()
                with self.opener(req, timeout=60) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 3:      # limite de llamadas: espera lo que pida y reintenta
                    self.sleep(float(e.headers.get("Retry-After", 10)) + 1)
                    continue
                raise
        return []

    def history(self, endpoint: str, symbols: list, interval: str, t0_s: int, t1_s: int, **extra) -> dict:
        """{simbolo de Binance: lista de puntos} para varios simbolos (de a 20 por llamada)."""
        out = {}
        for k in range(0, len(symbols), MAX_SYMBOLS):
            chunk = symbols[k:k + MAX_SYMBOLS]
            data = self.get(endpoint, symbols=",".join(f"{s}_PERP.A" for s in chunk), interval=interval,
                            **{"from": int(t0_s), "to": int(t1_s)}, **extra)
            for item in data:
                out[item["symbol"].split("_PERP")[0]] = item.get("history") or []
        return out


def raw_series(cz: Coinalyze, symbols: list, t0_ms: int, t1_ms: int) -> dict:
    """Series crudas de Coinalyze por moneda (marcas en ms, como vienen)."""
    a, b = t0_ms // 1000, t1_ms // 1000
    oi = cz.history("open-interest-history", symbols, "5min", a, b)
    ls = cz.history("long-short-ratio-history", symbols, "5min", a, b)
    k5 = cz.history("ohlcv-history", symbols, "5min", a, b)
    k15 = cz.history("ohlcv-history", symbols, "15min", a, b)
    fr = cz.history("funding-rate-history", symbols, "1hour", a - 86400, b)
    out = {}
    for s in symbols:
        arr = lambda rows, keys: np.array([[r["t"] * 1000] + [float(r.get(k, np.nan)) for k in keys] for r in rows],
                                          dtype=np.float64).reshape(-1, 1 + len(keys))
        out[s] = {"oi": arr(oi.get(s, []), ["c"]), "ls": arr(ls.get(s, []), ["r"]),
                  "k5": arr(k5.get(s, []), ["c", "v", "bv"]), "k15": arr(k15.get(s, []), ["o", "h", "l", "c", "v", "bv"]),
                  "fr": arr(fr.get(s, []), ["c"])}
    return out


def _shift(a: np.ndarray, offset_ms: int) -> np.ndarray:
    a = a.copy()
    a[:, 0] += offset_ms
    return a


def to_binance(raw: dict, offsets: dict) -> dict:
    """Series con el formato de nn_download_futures.py (las que lee nn_common.load_fut), sin top traders (NaN) ni
    prima (la pone with_substitute con la base futuro/spot). offsets: desfase en ms por serie (align_offset)."""
    oi, ls, k5 = _shift(raw["oi"], offsets["oi"]), _shift(raw["ls"], offsets["ls"]), _shift(raw["k5"], offsets["k5"])
    t = oi[:, 0]
    exact = lambda src, col: _exact(t, src, col)
    close5, v5, bv5 = exact(k5, 1), exact(k5, 2), exact(k5, 3)
    with np.errstate(divide="ignore", invalid="ignore"):
        taker = np.where(v5 - bv5 > 0, bv5 / (v5 - bv5), np.nan)
    metrics = np.column_stack([t, oi[:, 1], oi[:, 1] * close5, np.full(len(t), np.nan), np.full(len(t), np.nan),
                               exact(ls, 1), taker])
    k15 = _shift(raw["k15"], offsets["k15"])
    fut15m = np.column_stack([k15[:, 0], k15[:, 1:5], k15[:, 5], k15[:, 6]]) if len(k15) else np.zeros((0, 7))
    fr = _shift(raw["fr"], offsets["fr"])
    settle = fr[(fr[:, 0].astype(np.int64) % (8 * 3_600_000)) == 0] if len(fr) else np.zeros((0, 2))
    funding = np.column_stack([settle[:, 0], settle[:, 1] / 100.0]) if len(settle) else np.zeros((0, 2))
    return {"metrics": metrics, "fut15m": fut15m, "funding": funding}


def _exact(t: np.ndarray, src: np.ndarray, col: int) -> np.ndarray:
    if not len(src):
        return np.full(len(t), np.nan)
    j = np.searchsorted(src[:, 0], t)
    j = np.minimum(j, len(src) - 1)
    return np.where(src[j, 0] == t, src[j, col], np.nan)


def align_offset(ref_t, ref_x, sub_t, sub_x, step_ms: int, max_steps: int = 3, log_diff: bool = True) -> tuple:
    """Desfase (multiplo de step_ms) que mejor alinea la serie de Coinalyze con la de Binance: maxima correlacion de los
    cambios (o de los niveles con log_diff False). Devuelve (desfase_ms, correlacion)."""
    ref = dict(zip(np.asarray(ref_t, np.int64).tolist(), np.asarray(ref_x, float)))
    best = (0, -2.0)
    for k in range(-max_steps, max_steps + 1):
        off = k * step_ms
        pairs = [(ref[t + off], x) for t, x in zip(np.asarray(sub_t, np.int64).tolist(), np.asarray(sub_x, float))
                 if t + off in ref]
        if len(pairs) < 50:
            continue
        a, b = np.array(pairs).T
        ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0) if log_diff else np.isfinite(a) & np.isfinite(b)
        a, b = a[ok], b[ok]
        if log_diff:
            a, b = np.diff(np.log(a)), np.diff(np.log(b))
        if len(a) < 50 or np.std(a) == 0 or np.std(b) == 0:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if c > best[1]:
            best = (off, c)
    return best


CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "coinalyze")


def update_cache(cz: Coinalyze, symbols: list, now_ms: int, cache_dir: str = CACHE_DIR, days: int = 8) -> dict:
    """Coinalyze guarda solo ~7 dias a 5 min: cada corrida anade lo nuevo a <cache>/{SYM}.npz para que la historia (y la
    prueba de equivalencia) crezca con el tiempo. Devuelve las series crudas con toda la historia guardada."""
    os.makedirs(cache_dir, exist_ok=True)
    fresh = raw_series(cz, symbols, now_ms - days * 86_400_000, now_ms)
    out = {}
    for s in symbols:
        path = os.path.join(cache_dir, f"{s}.npz")
        old = dict(np.load(path)) if os.path.exists(path) else {}
        merged = {}
        for key, new in fresh[s].items():
            a = np.vstack([old[key], new]) if key in old and len(old[key]) else new
            if len(a):
                _, idx = np.unique(a[:, 0], return_index=True)   # una fila por marca de tiempo (la primera guardada)
                a = a[idx]
            merged[key] = a
        np.savez(path, **merged)
        out[s] = merged
    return out
