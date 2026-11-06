"""riesgo_frontera.py - frontera empirica win rate / b / E neta en DISENO (ronda 1, Gestor de Riesgo).
Uso: PYTHONIOENCODING=utf-8 python -I riesgo_frontera.py [agg]   (agg=1 -> 15m, 4 -> 1h)
Salida: output/riesgo/frontera_<tf>.csv (una fila por configuracion entrada x salida).
"""
import sys, os, time, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import riesgo_sim as S

agg = int(sys.argv[1]) if len(sys.argv) > 1 else 1
tf = {1: "15m", 4: "1h", 16: "4h"}[agg]
DS = S.datasets(agg)

A_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
M_GRID = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
H_GRID = [16, 48, 96]


def cfgs_for(typ):
    c = [dict(fam="ATR", a=a, m=m, H=H) for a in A_GRID for m in M_GRID for H in H_GRID]
    if typ == "MR":
        c += [dict(fam="PATH", f=f, m=m, H=H) for f in [0.25, 0.5, 0.75, 1.0] for m in M_GRID for H in H_GRID]
        c += [dict(fam="MEAN", m=m, H=H) for m in [1.0, 2.0, 3.0, 4.0, 6.0] for H in H_GRID]
    c += [dict(fam="CHAN", m=m, H=H) for m in [1.0, 2.0, 3.0] for H in [48, 96, 192]]
    c += [dict(fam="PART", a1=a1, a2=a2, m=m, H=96) for a1 in [0.5, 1.0] for a2 in [2.0, 3.0] for m in [1.5, 2.0, 3.0]]
    return c


ENTRIES = [("RND", 0, 0)] + [(t, n, k) for t in ("MR", "BO") for n in (20, 48, 96) for k in (1.5, 2.0, 2.5)]
YEARS = [2023, 2024, 2025]
COLS = ["tf", "entry", "fam", "params", "N", "WR", "WR_lo", "WR_hi", "tp_rate", "sl_rate", "avgW", "avgL", "b_eff",
        "pstar", "margin", "z_margin", "E_pct", "E_R", "Eg_R", "t_trade", "t_month", "PF", "MDD_R", "R_med", "cR_med",
        "n_months"] + [f"E_R_{y}" for y in YEARS] + [f"E_R_{s[:3]}" for s in S.SYMS] + ["hold_med"]
os.makedirs(S.OUTDIR, exist_ok=True)
path = os.path.join(S.OUTDIR, f"frontera_{tf}.csv")
n_cfg = 0
t0 = time.time()
with open(path, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(COLS)
    for entry in ENTRIES:
        typ = entry[0]
        groups = [cfgs_for(typ)]
        if typ == "MR":
            groups.append([dict(fam="BOT_MR", H=960)])
        if typ == "BO":
            groups.append([dict(fam="BOT_BO", H=960)])
        for cfgs in groups:
            chunk = 1500 if cfgs[0]["H"] == 960 else (4000 if typ == "RND" else 6000)
            res = S.pooled_trades(DS, entry, cfgs, chunk)
            for cfg, tr in zip(cfgs, res):
                m = S.metrics(tr)
                if m.get("N", 0) < 2:
                    continue
                n_cfg += (typ != "RND")
                yr = S.year_of(tr["t_in"])
                ey = S.by_group_ER(tr, yr)
                ec = S.by_group_ER(tr, tr["coin"])
                params = ";".join(f"{k}={v}" for k, v in cfg.items() if k != "fam")
                row = [tf, f"{typ}(n={entry[1]},k={entry[2]})" if typ != "RND" else "RND", cfg["fam"], params] + \
                      [m[c] for c in COLS[4:26]] + [ey.get(y, (np.nan, 0))[0] for y in YEARS] + \
                      [ec.get(i, (np.nan, 0))[0] for i in range(4)] + [float(np.median(tr["hold"]))]
                w.writerow([f"{x:.6g}" if isinstance(x, (float, np.floating)) else x for x in row])
        print(entry, "ok", f"{time.time() - t0:.0f}s", flush=True)
print("configuraciones (sin contar control RND):", n_cfg)
