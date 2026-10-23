"""Descarga velas spot de 1 s (archivos diarios de data.binance.vision) para estudiar el desfase en vivo.
Guarda klines/{SYM}_1s.npy con el mismo formato (N,7): open_time_ms, o, h, l, c, v, taker_buy_base.
Uso: python -I download_1s.py 2025-06-02 14   (fecha inicial y numero de dias)"""
import datetime as dt
import io
import os
import sys
import urllib.request
import zipfile

import numpy as np

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "klines")
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
d0 = dt.date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2025-06-02")
ndays = int(sys.argv[2]) if len(sys.argv) > 2 else 14
for sym in SYMS:
    chunks = []
    for k in range(ndays):
        d = d0 + dt.timedelta(days=k)
        url = f"https://data.binance.vision/data/spot/daily/klines/{sym}/1s/{sym}-1s-{d.isoformat()}.zip"
        try:
            data = urllib.request.urlopen(url, timeout=120).read()
        except Exception as e:  # noqa: BLE001
            print(sym, d, "FALTA", e)
            continue
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            txt = z.read(z.namelist()[0]).decode()
        rows = []
        for line in txt.splitlines():
            p = line.split(",")
            if not p[0].isdigit():
                continue
            t = int(p[0])
            if t > 10 ** 14:  # microsegundos desde 2025
                t //= 1000
            rows.append((t, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[9])))
        chunks.append(np.array(rows, dtype=np.float64))
        print(sym, d, len(rows), flush=True)
    a = np.concatenate(chunks)
    a = a[np.argsort(a[:, 0], kind="stable")]
    a = a[np.concatenate(([True], np.diff(a[:, 0]) > 0))]
    np.save(os.path.join(OUT, f"{sym}_1s.npy"), a)
    print(sym, a.shape, int(a[0, 0]), int(a[-1, 0]))
