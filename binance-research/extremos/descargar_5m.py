"""Descarga velas spot de 5 min desde el archivo público de Binance (data.binance.vision).

No hace falta API key ni cuenta: son archivos ZIP mensuales con un CSV por mes y moneda. Se guardan en el mismo formato
que las velas de 15 min de la v3: un .npy por moneda con columnas
[open_time_ms, open, high, low, close, volume, taker_buy_volume].

Desde 2025 Binance publica los tiempos de spot en microsegundos; aquí se pasan todos a milisegundos.

Uso:
    python descargar_5m.py                         # 23 monedas, 2021-10 a hoy
    python descargar_5m.py --monedas BTCUSDT ETHUSDT --desde 2024-01
    python descargar_5m.py --salida E:/datos/k5m     # otra carpeta

Por defecto guarda en v3_research/tmp/k5m/klines/. Los ZIP ya descargados se reutilizan (caché en .../k5m/zip/).
"""
import argparse
import csv
import datetime as dt
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(os.path.dirname(HERE), "v3_research", "tmp", "k5m")
URL = "https://data.binance.vision/data/spot/monthly/klines/{s}/5m/{s}-5m-{y:04d}-{m:02d}.zip"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AAVEUSDT", "ALGOUSDT", "APEUSDT", "APTUSDT", "AXSUSDT",
         "CHZUSDT", "CRVUSDT", "EGLDUSDT", "GALAUSDT", "HBARUSDT", "ICPUSDT", "INJUSDT", "KAVAUSDT", "LDOUSDT",
         "MANAUSDT", "OPUSDT", "RUNEUSDT", "SANDUSDT", "XLMUSDT"]


def months(start: str, end: str):
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    while (y, m) <= (ye, me):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch(url: str, path: str, tries: int = 4):
    """Descarga a `path` si no existe. Devuelve False si el mes no existe (404)."""
    if os.path.exists(path):
        return True
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            err = e
        except Exception as e:  # red: reintentar con espera creciente
            err = e
        time.sleep(2 ** (k + 1))
    raise RuntimeError(f"no se pudo descargar {url}: {err}")


def parse(path: str) -> np.ndarray:
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        rows = list(csv.reader(io.TextIOWrapper(z.open(name), "utf-8")))
    if rows and not rows[0][0].isdigit():          # algunos meses traen cabecera
        rows = rows[1:]
    a = np.array([[float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9])]
                  for r in rows], dtype=np.float64)
    if len(a):
        us = a[:, 0] > 1e14                         # microsegundos (2025 en adelante) -> milisegundos
        a[us, 0] = np.floor(a[us, 0] / 1000)
    return a


def main(argv=None):
    today = dt.date.today()
    last = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")   # último mes completo
    ap = argparse.ArgumentParser()
    ap.add_argument("--monedas", nargs="*", default=COINS)
    ap.add_argument("--desde", default="2021-10")
    ap.add_argument("--hasta", default=last)
    ap.add_argument("--salida", default=DEFAULT_OUT)
    ap.add_argument("--hilos", type=int, default=8)
    a = ap.parse_args(argv)
    zdir, kdir = os.path.join(a.salida, "zip"), os.path.join(a.salida, "klines")
    os.makedirs(zdir, exist_ok=True)
    os.makedirs(kdir, exist_ok=True)
    jobs = [(s, y, m) for s in a.monedas for y, m in months(a.desde, a.hasta)]
    print(f"{len(a.monedas)} monedas, {a.desde} a {a.hasta}: {len(jobs)} archivos mensuales", flush=True)

    def one(job):
        s, y, m = job
        p = os.path.join(zdir, f"{s}-5m-{y:04d}-{m:02d}.zip")
        return job, fetch(URL.format(s=s, y=y, m=m), p), p

    t0 = time.time()
    got = {s: [] for s in a.monedas}
    with ThreadPoolExecutor(a.hilos) as ex:
        for i, (job, ok, p) in enumerate(ex.map(one, jobs), 1):
            if ok:
                got[job[0]].append(p)
            if i % 100 == 0:
                print(f"  {i}/{len(jobs)} ({time.time() - t0:.0f} s)", flush=True)
    for s, paths in got.items():
        if not paths:
            print(f"{s}: sin datos", flush=True)
            continue
        a5 = np.vstack([parse(p) for p in sorted(paths)])
        a5 = a5[np.argsort(a5[:, 0], kind="stable")]
        a5 = a5[np.r_[True, np.diff(a5[:, 0]) > 0]]
        np.save(os.path.join(kdir, f"{s}_5m.npy"), a5)
        d0 = dt.datetime.fromtimestamp(a5[0, 0] / 1000, dt.timezone.utc).date()
        d1 = dt.datetime.fromtimestamp(a5[-1, 0] / 1000, dt.timezone.utc).date()
        print(f"{s}: {len(a5)} velas de 5 min, {d0} a {d1}", flush=True)
    print(f"Listo en {time.time() - t0:.0f} s. Carpeta: {kdir}")


if __name__ == "__main__":
    sys.exit(main())
