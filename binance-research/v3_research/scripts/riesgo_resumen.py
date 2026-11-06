"""riesgo_resumen.py - resume frontera_<tf>.csv: bandas de win rate, mejores configuraciones, control aleatorio.
Uso: PYTHONIOENCODING=utf-8 python -I riesgo_resumen.py [tf]"""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.stats import norm
import riesgo_sim as S

tf = sys.argv[1] if len(sys.argv) > 1 else "15m"
rows = list(csv.DictReader(open(os.path.join(S.OUTDIR, f"frontera_{tf}.csv"), encoding="utf-8")))
for r in rows:
    for k, v in r.items():
        if k not in ("tf", "entry", "fam", "params"):
            r[k] = float(v)
sig = [r for r in rows if r["entry"] != "RND"]
rnd = {(r["fam"], r["params"]): r for r in rows if r["entry"] == "RND"}
M = len(sig)
zB = norm.ppf(1 - 0.05 / M)
print(f"[{tf}] configuraciones con senal: {M}; umbral Bonferroni unilateral (5 %): t > {zB:.2f}")

def show(r, extra=""):
    c = rnd.get((r["fam"], r["params"]))
    ctrl = f" | RND: WR {c['WR']*100:.1f} E_R {c['E_R']:+.3f}" if c else ""
    print(f"  {r['entry']:<16}{r['fam']:<6}{r['params']:<22} N={r['N']:<5.0f} WR={r['WR']*100:5.1f} [{r['WR_lo']*100:4.1f},{r['WR_hi']*100:4.1f}] "
          f"tp={r['tp_rate']*100:4.1f} b={r['b_eff']:.2f} p*={r['pstar']*100:4.1f} E={r['E_pct']:+.3f}% E_R={r['E_R']:+.3f} "
          f"Eg_R={r['Eg_R']:+.3f} c/R={r['cR_med']:.2f} R={r['R_med']:.2f}% PF={r['PF']:.2f} MDD={r['MDD_R']:.1f}R "
          f"t={r['t_trade']:+.2f} tm={r['t_month']:+.2f} yrs=({r['E_R_2023']:+.2f},{r['E_R_2024']:+.2f},{r['E_R_2025']:+.2f}) "
          f"coins=({r['E_R_BTC']:+.2f},{r['E_R_ETH']:+.2f},{r['E_R_SOL']:+.2f},{r['E_R_DOG']:+.2f}){ctrl}{extra}")

print("\nBandas de win rate (N>=200): cuantas configs, cuantas con E>0, mejor E_R")
for lo in np.arange(0.3, 1.0, 0.1):
    b = [r for r in sig if lo <= r["WR"] < lo + 0.1 and r["N"] >= 200]
    pos = [r for r in b if r["E_R"] > 0]
    sg = [r for r in b if r["t_month"] > 2]
    best = max(b, key=lambda r: r["E_R"]) if b else None
    print(f" WR {lo*100:.0f}-{lo*100+10:.0f}%: {len(b):4d} configs, E>0: {len(pos):4d}, t_mes>2: {len(sg):3d}, t>Bonf: {sum(r['t_month']>zB for r in b)}",
          f" mejor E_R={best['E_R']:+.3f} ({best['entry']} {best['fam']} {best['params']})" if best else "")

print("\nTop 12 por E_R con 70 % <= WR < 80 % y N >= 200")
for r in sorted([r for r in sig if 0.7 <= r["WR"] < 0.8 and r["N"] >= 200], key=lambda r: -r["E_R"])[:12]:
    show(r)
print("\nTop 12 por t mensual (N >= 200), cualquier WR")
for r in sorted([r for r in sig if r["N"] >= 200], key=lambda r: -r["t_month"])[:12]:
    show(r)
print("\nMejor E_R por familia y tipo de entrada (N >= 200)")
for typ in ("MR", "BO"):
    for fam in ("ATR", "PATH", "MEAN", "CHAN", "PART", "BOT_MR", "BOT_BO"):
        b = [r for r in sig if r["entry"].startswith(typ) and r["fam"] == fam and r["N"] >= 200]
        if b:
            show(max(b, key=lambda r: r["E_R"]))
print("\nGeometrias actuales del bot")
for r in sig:
    if r["fam"].startswith("BOT"):
        show(r)
print("\nControl aleatorio (RND): mejores y la frontera WR-E")
for r in sorted(rnd.values(), key=lambda r: -r["E_R"])[:5]:
    show(r)
