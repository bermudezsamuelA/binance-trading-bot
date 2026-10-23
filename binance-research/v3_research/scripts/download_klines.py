"""Descarga velas mensuales de 15m desde data.binance.vision y las guarda como .npy por moneda."""
import io, os, sys, zipfile, urllib.request
import numpy as np

OUT = sys.argv[1]
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
months = [(y, m) for y in range(2023, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]
for sym in SYMS:
    rows = []
    for y, m in months:
        url = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/15m/{sym}-15m-{y}-{m:02d}.zip"
        try:
            data = urllib.request.urlopen(url, timeout=60).read()
        except Exception as e:
            print(sym, y, m, "FALTA", e); continue
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            txt = z.read(z.namelist()[0]).decode()
        for line in txt.splitlines():
            p = line.split(",")
            if not p[0].isdigit():
                continue
            t = int(p[0])
            if t > 10**14:  # desde 2025 los CSV de spot vienen en microsegundos
                t //= 1000
            rows.append((t, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[9])))
    a = np.array(sorted(set(rows)), dtype=np.float64)
    np.save(os.path.join(OUT, f"{sym}_15m.npy"), a)
    print(sym, a.shape, "desde", int(a[0, 0]), "hasta", int(a[-1, 0]))
