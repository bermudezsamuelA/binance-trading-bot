"""Sonda 3: huecos de futures/um/daily/metrics para un simbolo (todos los dias 2023-01-01..2026-09-30)."""
import io, sys, zipfile, urllib.request, os, datetime, json
from concurrent.futures import ThreadPoolExecutor
import numpy as np
OUT, SYM = sys.argv[1], sys.argv[2]
d0, d1 = datetime.date(2023, 1, 1), datetime.date(2026, 9, 30)
days = [d0 + datetime.timedelta(k) for k in range((d1 - d0).days + 1)]
def ms(s): return int(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
def fetch(d):
    url = f"https://data.binance.vision/data/futures/um/daily/metrics/{SYM}/{SYM}-metrics-{d}.zip"
    for _ in range(4):
        try:
            data = urllib.request.urlopen(url, timeout=60).read(); break
        except urllib.error.HTTPError as e:
            if e.code == 404: return d, None
        except Exception: pass
    else: return d, None
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        txt = z.read(z.namelist()[0]).decode()
    rows, empty = [], 0
    for r in txt.strip().splitlines()[1:]:
        p = r.split(",")
        vals = []
        for x in p[2:8]:
            try: vals.append(float(x))
            except ValueError: vals.append(np.nan); empty += 1
        rows.append([ms(p[0])] + vals)
    return d, (rows, empty, txt.strip().splitlines()[1:] != sorted(txt.strip().splitlines()[1:]))
with ThreadPoolExecutor(16) as ex:
    res = list(ex.map(fetch, days))
missing_days = [str(d) for d, r in res if r is None]
allrows, empty, unsorted_days = [], 0, 0
for d, r in res:
    if r is None: continue
    allrows += r[0]; empty += r[1]; unsorted_days += int(r[2])
a = np.array(allrows, dtype=np.float64)
a = a[np.argsort(a[:, 0], kind="stable")]
t = a[:, 0].astype(np.int64)
dup = int((np.diff(t) == 0).sum())
u = np.unique(t)
offgrid = int((u % 300000 != 0).sum())
grid = np.arange(ms("2023-01-01 00:00:00"), ms("2026-09-30 23:55:00") + 1, 300000)
miss = np.setdiff1d(grid, u)
# rachas de huecos
runs = []
if len(miss):
    s = miss[0]; prev = miss[0]
    for x in miss[1:]:
        if x != prev + 300000: runs.append((s, prev)); s = x
        prev = x
    runs.append((s, prev))
runs_len = sorted((int((e - s) // 300000 + 1), datetime.datetime.utcfromtimestamp(s / 1000).isoformat()) for s, e in runs)[::-1]
nan_by_col = np.isnan(a[:, 1:]).sum(0).tolist()
# huecos por 15m: velas de 15m sin ningun registro utilizable en [t0-?]
out = {"symbol": SYM, "days_expected": len(days), "missing_days": len(missing_days), "missing_days_list": missing_days[:50],
       "rows": int(len(a)), "duplicates": dup, "offgrid": offgrid, "grid_expected": int(len(grid)),
       "grid_missing": int(len(miss)), "grid_missing_frac": float(len(miss) / len(grid)), "gap_runs": len(runs),
       "longest_runs": runs_len[:10], "nan_cells_by_col": nan_by_col, "empty_cells": empty, "unsorted_days": unsorted_days,
       "missing_by_year": {y: int(sum(1 for x in miss if datetime.datetime.utcfromtimestamp(x / 1000).year == y)) for y in (2023, 2024, 2025, 2026)}}
np.save(os.path.join(OUT, f"{SYM}_metrics5m.npy"), a)
json.dump(out, open(os.path.join(OUT, f"{SYM}_metrics_gaps.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "missing_days_list"}, indent=0))
print("missing_days_list", missing_days[:30])
