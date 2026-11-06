"""Descargas incrementales para el canal sombra de la v3 (doc/estrategia-v3-hacia-el-80.md, secciones 7.3 y 7.6).

  * Velas spot de 15 min (data.binance.vision): meses completos con el archivo mensual y el mes en curso con los
    diarios, que llegan con ~1 dia de retraso. Se fusionan en <data>/klines/{SYM}_15m.npy (formato de harness.py).
  * Futuros USD-M (data.binance.vision), con los parsers de nn/nn_download_futures.py: metrics diarios; prima y velas
    de futuros mensuales y, en el mes en curso, diarias; funding solo mensual (Binance no publica diarios), asi que el
    mes en curso no tiene funding hasta que sale su archivo y run_daily.py no evalua mas alla.
  * DVOL de Deribit (BTC y ETH, 1 h) para el brazo S3 (D1): <v3_research>/cache/deribit/dvol_{CUR}_1h.json.

Con la VPN activa las descargas pueden fallar (ver CLAUDE.md). Nada aqui opera ni lee claves.
"""
import datetime as dt
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(RESEARCH, "nn"))
import nn_download_futures as NF  # noqa: E402

SPOT = "https://data.binance.vision/data/spot"
DERIBIT = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
DVOL_DIR = os.path.join(RESEARCH, "cache", "deribit")
HOUR_MS = 3_600_000


def days_between(d0: dt.date, d1: dt.date) -> list:
    return [d0 + dt.timedelta(days=k) for k in range((d1 - d0).days + 1)]


def split_months(d0: dt.date, d1: dt.date, today: dt.date) -> tuple:
    """(meses completos con archivo mensual, dias sueltos): un mes va completo si ya termino antes de `today`; los dias
    de los meses que no (el mes en curso) se piden con los archivos diarios."""
    months, days = [], []
    for d in days_between(d0, d1):
        if (d.year, d.month) < (today.year, today.month):
            if (d.year, d.month) not in months:
                months.append((d.year, d.month))
        else:
            days.append(d)
    return months, days


def last_date(path: str, col: int = 0):
    """Fecha UTC del ultimo registro de un .npy (None si no existe o esta vacio)."""
    if not os.path.exists(path):
        return None
    a = np.load(path)
    if not len(a):
        return None
    return dt.datetime.fromtimestamp(float(a[:, col].max()) / 1000, dt.timezone.utc).date()


def resume_from(path: str, start: dt.date) -> dt.date:
    """Primer dia a descargar: el ultimo guardado (se repite, por si estaba incompleto) o `start` si no hay archivo o
    si el archivo empieza despues de `start` (falta historia al principio)."""
    if not os.path.exists(path) or not len(a := np.load(path)):
        return start
    first = dt.datetime.fromtimestamp(float(a[:, 0].min()) / 1000, dt.timezone.utc).date()
    if first > start:
        return start
    return max(start, last_date(path))


def parse_spot(txt: str) -> list:
    rows = []
    for line in txt.splitlines():
        p = line.split(",")
        if len(p) < 10 or not p[0].strip().isdigit():
            continue
        t = int(p[0])
        if t > 10**14:  # desde 2025 los CSV de spot vienen en microsegundos
            t //= 1000
        rows.append((t, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[9])))
    return rows


def _fetch_all(urls: list, threads: int) -> list:
    with ThreadPoolExecutor(threads) as ex:
        return list(ex.map(NF.fetch, urls))


def update_spot(data_dir: str, symbols: list, start: dt.date, end: dt.date, today: dt.date = None, threads: int = 16):
    """Velas spot de 15 min de [start, end] (o desde el ultimo dia guardado, si es posterior)."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    out_dir = os.path.join(data_dir, "klines")
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    for sym in symbols:
        path = os.path.join(out_dir, f"{sym}_15m.npy")
        d0 = resume_from(path, start)
        if d0 > end:
            report[sym] = {"nuevas": 0, "faltan": []}
            continue
        months, days = split_months(d0, end, today)
        urls = [f"{SPOT}/monthly/klines/{sym}/15m/{sym}-15m-{y}-{m:02d}.zip" for y, m in months]
        urls += [f"{SPOT}/daily/klines/{sym}/15m/{sym}-15m-{d.isoformat()}.zip" for d in days]
        rows, missing = [], []
        for url, txt in zip(urls, _fetch_all(urls, threads)):
            if txt is None:
                missing.append(url.rsplit("/", 1)[-1])
            else:
                rows += parse_spot(txt)
        before = len(np.load(path)) if os.path.exists(path) else 0
        a = NF.merge_save(path, rows, 7)
        report[sym] = {"nuevas": int(len(a) - before), "faltan": missing}
    return report


def update_futures(data_dir: str, symbols: list, start: dt.date, end: dt.date, today: dt.date = None, threads: int = 16):
    """Series de futuros de [start, end] en <data>/futures (mismo formato que nn_download_futures.py)."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    out_dir = os.path.join(data_dir, "futures")
    os.makedirs(out_dir, exist_ok=True)
    base = NF.BASE
    report = {}
    for sym in symbols:
        files = {k: os.path.join(out_dir, f"{sym}_{k}.npy") for k in ("metrics", "funding", "premium15m", "fut15m")}
        jobs = []
        d0 = resume_from(files["metrics"], start)
        jobs += [("m", f"{base}/daily/metrics/{sym}/{sym}-metrics-{d.isoformat()}.zip") for d in days_between(d0, end)]
        d0 = resume_from(files["funding"], start)
        jobs += [("f", f"{base}/monthly/fundingRate/{sym}/{sym}-fundingRate-{y}-{m:02d}.zip")
                 for y, m in sorted({(d.year, d.month) for d in days_between(d0, end)})]
        for kind, key, folder in (("p", "premium15m", "premiumIndexKlines"), ("k", "fut15m", "klines")):
            d0 = resume_from(files[key], start)
            months, days = split_months(d0, end, today)
            jobs += [(kind, f"{base}/monthly/{folder}/{sym}/15m/{sym}-15m-{y}-{m:02d}.zip") for y, m in months]
            jobs += [(kind, f"{base}/daily/{folder}/{sym}/15m/{sym}-15m-{d.isoformat()}.zip") for d in days]
        out, missing = {"m": [], "f": [], "p": [], "k": []}, []
        for (kind, url), txt in zip(jobs, _fetch_all([u for _, u in jobs], threads)):
            if txt is None:
                missing.append(url.rsplit("/", 1)[-1])
            elif kind == "m":
                out["m"] += NF.parse_metrics(txt)
            elif kind == "f":
                out["f"] += NF.parse_funding(txt)
            else:
                out[kind] += NF.parse_kl(txt, 5 if kind == "p" else 7)
        for kind, key, ncol in (("m", "metrics", 7), ("f", "funding", 2), ("p", "premium15m", 5), ("k", "fut15m", 7)):
            NF.merge_save(files[key], out[kind], ncol)
        # El funding del mes en curso siempre falta (solo hay archivo mensual): no es un hueco de datos
        report[sym] = {"faltan": [m for m in missing if not ("fundingRate" in m and m.endswith(f"{today:%Y-%m}.zip"))]}
    return report


def fetch_dvol(currency: str, start_ms: int, end_ms: int, opener=urllib.request.urlopen) -> list:
    """Velas horarias del DVOL [ts, open, high, low, close] de Deribit entre start_ms y end_ms (pagina hacia atras con
    `continuation`, que es el nuevo end_timestamp)."""
    rows, end = [], end_ms
    while end is not None and end > start_ms:
        url = (f"{DERIBIT}?currency={currency}&resolution=3600&start_timestamp={int(start_ms)}"
               f"&end_timestamp={int(end)}")
        res = json.loads(opener(url, timeout=60).read().decode())["result"]
        data = res.get("data") or []
        rows += [[int(r[0])] + [float(x) for x in r[1:5]] for r in data]
        nxt = res.get("continuation")
        end = None if not data or nxt is None or int(nxt) >= end else int(nxt)
    return rows


def update_dvol(currencies=("BTC", "ETH"), out_dir: str = DVOL_DIR, now_ms: int = None, opener=urllib.request.urlopen):
    """Anade al cache las horas nuevas del DVOL (desde la ultima guardada). Devuelve {moneda: horas nuevas}."""
    now_ms = now_ms or int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    for cur in currencies:
        path = os.path.join(out_dir, f"dvol_{cur}_1h.json")
        old = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
        start = int(old[-1][0]) if old else now_ms - 60 * 24 * HOUR_MS
        new = fetch_dvol(cur, start, now_ms, opener)
        merged = {int(r[0]): r for r in old}
        merged.update({int(r[0]): r for r in new})
        rows = [merged[k] for k in sorted(merged)]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f)
        report[cur] = len(rows) - len(old)
    return report
