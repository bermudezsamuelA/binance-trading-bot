"""Sonda 4: convencion de create_time dia por dia (BTCUSDT) usando klines 5m mensuales de futuros UM.
 taker ratio: compara con la vela 5m [T-5m,T) ('fin') y [T,T+5m) ('inicio').
 OI: precio implicito vs precio en el instante T-5m, T, T+5m, T+10m (open de la vela 5m que empieza ahi)."""
import io, sys, zipfile, urllib.request, os, datetime, json
from concurrent.futures import ThreadPoolExecutor
import numpy as np
OUT, SYM = sys.argv[1], sys.argv[2]
months = [(y, m) for y in range(2023, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]
def fetch(ym):
    y, m = ym
    url = f"https://data.binance.vision/data/futures/um/monthly/klines/{SYM}/5m/{SYM}-5m-{y}-{m:02d}.zip"
    data = urllib.request.urlopen(url, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        txt = z.read(z.namelist()[0]).decode()
    rows = []
    for line in txt.splitlines():
        p = line.split(",")
        if not p[0].isdigit(): continue
        rows.append((int(p[0]), float(p[1]), float(p[5]), float(p[9])))
    return rows
kp = os.path.join(OUT, f"{SYM}_fut5m.npy")
if os.path.exists(kp):
    k = np.load(kp)
else:
    with ThreadPoolExecutor(8) as ex:
        k = np.array(sorted(set(sum(ex.map(fetch, months), []))), dtype=np.float64)
    np.save(kp, k)
a = np.load(os.path.join(OUT, f"{SYM}_metrics5m.npy"))  # t, oi, oiv, top_acc, top_pos, glob_acc, taker
kt = k[:, 0].astype(np.int64); pos = {int(t): i for i, t in enumerate(kt)}
T = a[:, 0].astype(np.int64)
def idx(off):
    return np.array([pos.get(int(t) + off, -1) for t in T])
taker = a[:, 6]
res = {}
for lab, off in [("fin", -300000), ("inicio", 0)]:
    j = idx(off); ok = j >= 0
    b = np.where(ok, k[np.maximum(j, 0), 3], np.nan); v = np.where(ok, k[np.maximum(j, 0), 2], np.nan)
    res["tk_" + lab] = np.abs(np.log(taker / (b / (v - b))))
imp = a[:, 2] / a[:, 1]
for lab, off in [("T-5", -300000), ("T", 0), ("T+5", 300000), ("T+10", 600000)]:
    j = idx(off); ok = j >= 0
    res["oi_" + lab] = np.where(ok, np.abs(imp / k[np.maximum(j, 0), 1] - 1), np.nan)
day = (T // 86400000)
out = []
for d in np.unique(day):
    s = day == d
    r = {kk: float(np.nanmedian(vv[s])) for kk, vv in res.items()}
    tk = "fin" if r["tk_fin"] < r["tk_inicio"] else "inicio"
    oi = min(["T-5", "T", "T+5", "T+10"], key=lambda x: r["oi_" + x])
    out.append((str(datetime.date(1970, 1, 1) + datetime.timedelta(int(d))), tk, oi, round(min(r["tk_fin"], r["tk_inicio"]), 5), round(r["oi_" + oi] * 1e4, 2)))
# resumen por rachas
runs = []
for row in out:
    key = (row[1], row[2])
    if runs and runs[-1][0] == key: runs[-1][2] = row[0]; runs[-1][3] += 1
    else: runs.append([key, row[0], row[0], 1])
for key, s, e, n in runs:
    print(f"{s} .. {e} ({n} dias): taker={key[0]}  OI_instante={key[1]}")
bad = [r for r in out if r[3] > 0.01]
print("dias con taker sin coincidencia clara (mediana |log err|>1%):", len(bad), bad[:5])
json.dump(out, open(os.path.join(OUT, f"{SYM}_metrics_convention.json"), "w"))
