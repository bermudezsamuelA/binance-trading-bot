"""Sonda 2: a que instante corresponde create_time T en metrics.
 (a) precio implicito OI_value/OI vs klines 1m de futuros (open/close de cada minuto)
 (b) sum_taker_long_short_vol_ratio vs taker_buy/(vol-taker_buy) de klines 5m de futuros en [T-5m,T) y [T,T+5m)"""
import io, sys, zipfile, urllib.request, os, datetime
import numpy as np
OUT = sys.argv[1]; days = sys.argv[2].split(",")
def get(url):
    data = urllib.request.urlopen(url, timeout=60).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return z.read(z.namelist()[0]).decode()
def kl(txt):
    rows = []
    for line in txt.splitlines():
        p = line.split(",")
        if not p[0].isdigit(): continue
        rows.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[9])))
    return np.array(rows)
def ms(s): return int(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
for d in days:
    m = get(f"https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-{d}.zip").strip().splitlines()[1:]
    rec = sorted((ms(r.split(",")[0]), float(r.split(",")[2]), float(r.split(",")[3]), float(r.split(",")[7])) for r in m)
    rec = np.array(rec)
    k1 = kl(get(f"https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-{d}.zip"))
    k5 = kl(get(f"https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/5m/BTCUSDT-5m-{d}.zip"))
    imp = rec[:, 2] / rec[:, 1]
    # (a) para cada T, error relativo del precio implicito vs open del minuto que empieza en T+k*60s (k=-5..5)
    t1 = {int(t): i for i, t in enumerate(k1[:, 0])}
    print(d, "registros", len(rec), "unicos", len(set(rec[:, 0])))
    for k in range(-6, 7):
        errs = []
        for T, p in zip(rec[:, 0], imp):
            j = t1.get(int(T) + k * 60000)
            if j is not None: errs.append(abs(p / k1[j, 1] - 1))
        print(f"  (a) open del minuto T{k:+d}m: mediana |err| = {np.median(errs)*1e4:.2f} pb (n={len(errs)})")
    # (b) taker ratio
    t5 = {int(t): i for i, t in enumerate(k5[:, 0])}
    for lab, off in [("[T-10m,T-5m)", -600000), ("[T-5m,T)", -300000), ("[T,T+5m)", 0), ("[T+5m,T+10m)", 300000)]:
        errs = []
        for T, r in zip(rec[:, 0], rec[:, 3]):
            j = t5.get(int(T) + off)
            if j is not None:
                b = k5[j, 6]; s = k5[j, 5] - b
                if s > 0: errs.append(abs(np.log(r / (b / s))))
        print(f"  (b) taker ratio vs kline 5m {lab}: mediana |log err| = {np.median(errs):.4f}, frac<1% = {np.mean(np.array(errs)<0.01):.2f}")
