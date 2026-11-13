"""Descarga datos de futuros USD-M desde data.binance.vision y los guarda como .npy.

Uso:
  python -I nn_download_futures.py --symbols BTCUSDT,ETHUSDT --start 2023-01-01 --end 2025-06-30 \
      --out E:/.../data/research/futures

Por moneda genera (el script de evaluacion los necesita todos):
  {SYM}_metrics.npy  N x 7: create_time_ms, sum_open_interest, sum_open_interest_value,
                     count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
                     count_long_short_ratio, sum_taker_long_short_vol_ratio  (cada 5 min, diario)
  {SYM}_funding.npy  N x 2: calc_time_ms, last_funding_rate              (mensual)
  {SYM}_premium15m.npy N x 5: open_time_ms, open, high, low, close         (premiumIndexKlines 15m, mensual)
  {SYM}_fut15m.npy   N x 7: open_time_ms, open, high, low, close, volume, taker_buy_volume (klines UM 15m, mensual)
Si ya existe un archivo de salida, se FUSIONA con lo nuevo (union por marca de tiempo).
"""
import argparse, datetime as dt, io, os, sys, zipfile, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np

BASE = "https://data.binance.vision/data/futures/um"


def fetch(url, tries=4):
    for k in range(tries):
        try:
            data = urllib.request.urlopen(url, timeout=60).read()
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return z.read(z.namelist()[0]).decode()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
    return None


def ts_ms(s):
    s = s.strip()
    if s[:4].isdigit() and "-" in s:
        return int(dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    t = int(float(s))
    if t > 10**14:
        t //= 1000
    return t


def fl(x):
    try:
        return float(x)
    except Exception:
        return np.nan


def parse_metrics(txt):
    rows = []
    for line in txt.splitlines():
        p = line.split(",")
        if len(p) < 8 or not p[0][:1].isdigit():
            continue
        rows.append((ts_ms(p[0]), fl(p[2]), fl(p[3]), fl(p[4]), fl(p[5]), fl(p[6]), fl(p[7])))
    return rows


def parse_funding(txt):
    rows = []
    for line in txt.splitlines():
        p = line.split(",")
        if len(p) < 3 or not p[0][:1].isdigit():
            continue
        rows.append((ts_ms(p[0]), fl(p[2])))
    return rows


def parse_kl(txt, ncol):
    rows = []
    for line in txt.splitlines():
        p = line.split(",")
        if len(p) < 10 or not p[0][:1].isdigit():
            continue
        r = (ts_ms(p[0]), fl(p[1]), fl(p[2]), fl(p[3]), fl(p[4]), fl(p[5]), fl(p[9]))
        rows.append(r[:ncol])
    return rows


def merge_save(path, rows, ncol):
    a = np.array(rows, dtype=np.float64).reshape(-1, ncol)
    if os.path.exists(path):
        old = np.load(path)
        a = np.vstack([old, a])
    if len(a):
        _, idx = np.unique(a[:, 0], return_index=True)
        a = a[idx]
    np.save(path, a)
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=32)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    d0 = dt.date.fromisoformat(a.start); d1 = dt.date.fromisoformat(a.end)
    days = [d0 + dt.timedelta(days=k) for k in range((d1 - d0).days + 1)]
    months = sorted({(d.year, d.month) for d in days})
    for sym in a.symbols.split(","):
        jobs = []
        for d in days:
            jobs.append(("m", f"{BASE}/daily/metrics/{sym}/{sym}-metrics-{d.isoformat()}.zip"))
        for y, m in months:
            jobs.append(("f", f"{BASE}/monthly/fundingRate/{sym}/{sym}-fundingRate-{y}-{m:02d}.zip"))
            jobs.append(("p", f"{BASE}/monthly/premiumIndexKlines/{sym}/15m/{sym}-15m-{y}-{m:02d}.zip"))
            jobs.append(("k", f"{BASE}/monthly/klines/{sym}/15m/{sym}-15m-{y}-{m:02d}.zip"))
        with ThreadPoolExecutor(a.threads) as ex:
            res = list(ex.map(lambda j: (j[0], j[1], fetch(j[1])), jobs))
        out = {"m": [], "f": [], "p": [], "k": []}
        miss = 0
        for kind, url, txt in res:
            if txt is None:
                miss += 1
                print("FALTA", url.split("/")[-1]); continue
            if kind == "m": out["m"] += parse_metrics(txt)
            elif kind == "f": out["f"] += parse_funding(txt)
            elif kind == "p": out["p"] += parse_kl(txt, 5)
            else: out["k"] += parse_kl(txt, 7)
        A = merge_save(os.path.join(a.out, f"{sym}_metrics.npy"), out["m"], 7)
        F = merge_save(os.path.join(a.out, f"{sym}_funding.npy"), out["f"], 2)
        P = merge_save(os.path.join(a.out, f"{sym}_premium15m.npy"), out["p"], 5)
        K = merge_save(os.path.join(a.out, f"{sym}_fut15m.npy"), out["k"], 7)
        print(sym, "metrics", A.shape, "funding", F.shape, "premium", P.shape, "fut15m", K.shape, "faltantes", miss, flush=True)


if __name__ == "__main__":
    main()
