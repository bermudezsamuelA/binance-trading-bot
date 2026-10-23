"""Verificador: descarga velas spot 15m (2023-01..2026-09) de las 6 monedas reservadas.
Guarda {SYM}_15m.npy (N x 7 float64: open_time_ms, o, h, l, c, v, taker_buy_base) y un manifiesto con SHA256.
NO calcula ningun rendimiento."""
import io, os, sys, zipfile, urllib.request, hashlib, json, datetime
from concurrent.futures import ThreadPoolExecutor
import numpy as np

OUT = sys.argv[1]
SYMS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["XRPUSDT", "BNBUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT"]
months = [(y, m) for y in range(2023, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]

def fetch(args):
    sym, y, m = args
    url = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/15m/{sym}-15m-{y}-{m:02d}.zip"
    for attempt in range(4):
        try:
            data = urllib.request.urlopen(url, timeout=60).read()
            break
        except Exception as e:
            err = e
    else:
        return sym, y, m, None, str(err)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        txt = z.read(z.namelist()[0]).decode()
    rows = []
    for line in txt.splitlines():
        p = line.split(",")
        if not p[0].isdigit():
            continue
        t = int(p[0])
        if t > 10**14:
            t //= 1000
        rows.append((t, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[9])))
    return sym, y, m, rows, hashlib.sha256(data).hexdigest()

manifest = {"created_utc": datetime.datetime.utcnow().isoformat(), "files": {}}
for sym in SYMS:
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(fetch, [(sym, y, m) for y, m in months]))
    rows, missing = [], []
    for s, y, m, r, h in res:
        if r is None:
            missing.append(f"{y}-{m:02d}"); print(sym, y, m, "FALTA", h); continue
        rows.extend(r)
    a = np.array(sorted(set(rows)), dtype=np.float64)
    path = os.path.join(OUT, f"{sym}_15m.npy")
    np.save(path, a)
    dt = np.diff(a[:, 0])
    gaps = int((dt != 900_000).sum())
    gap_bars = int(((dt[dt != 900_000] / 900_000) - 1).sum()) if gaps else 0
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    manifest["files"][sym] = {"rows": int(a.shape[0]), "first_ms": int(a[0, 0]), "last_ms": int(a[-1, 0]),
                              "missing_months": missing, "gaps": gaps, "missing_bars": gap_bars, "sha256": sha}
    print(sym, a.shape, "gaps", gaps, "missing_bars", gap_bars, "missing_months", missing, sha[:12], flush=True)
mp = os.path.join(OUT, "manifest.json")
old = json.load(open(mp)) if os.path.exists(mp) else {"files": {}}
old["files"].update(manifest["files"]); old["created_utc"] = manifest["created_utc"]
json.dump(old, open(mp, "w"), indent=1)
