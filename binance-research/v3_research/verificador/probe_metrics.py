"""Sonda de semantica temporal de futures/um/daily/metrics (BTCUSDT)."""
import io, sys, zipfile, urllib.request, os
OUT = sys.argv[1]
days = sys.argv[2].split(",")
for d in days:
    url = f"https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-{d}.zip"
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
    except Exception as e:
        print(d, "FALTA", e); continue
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = z.namelist()[0]
        txt = z.read(name).decode()
        info = z.getinfo(name)
    open(os.path.join(OUT, f"BTCUSDT-metrics-{d}.csv"), "w").write(txt)
    lines = txt.strip().splitlines()
    print(d, name, "zip_mtime", info.date_time, "rows", len(lines) - 1)
    print("  ", lines[0]); print("  ", lines[1]); print("  ", lines[2]); print("  ", lines[-1])
