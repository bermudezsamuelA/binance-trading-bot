"""Contraste verify.py vs harness.py en DISENO (BTCUSDT y ETHUSDT 2023-01..2025-06, datos no reservados)."""
import os, sys, csv, subprocess, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import numpy as np
import harness as H
rows = []
for sym in ("BTCUSDT", "ETHUSDT"):
    bars = H.load(sym)
    i0, i1 = H.bounds(bars, "design")
    mu, sd = H.rolling_mean(bars.c, 20), H.rolling_std(bars.c, 20)
    sig = bars.c < mu - 2 * sd
    for mode in ("close", "next_open"):
        tr = H.simulate(bars, sig, tp=bars.c * 1.006, sl=bars.c * 0.98, period=(i0, i1), max_hold=48, entry_mode=mode, levels="relative")
        m = H.metrics(tr)
        print(sym, mode, "harness: n", m["n"], "wr %.4f" % m["wr"], "E %.4f" % m["E_pct"], "pf %.3f" % m["pf"], "b_eff %.4f" % m["b_eff"])
        for k in range(len(tr)):
            rows.append([sym, int(tr.entry_t[k]), int(tr.exit_t[k]), tr.entry_px[k], tr.exit_px[k], tr.tp[k], tr.sl[k], 48, mode])
p = os.path.join(HERE, "crosscheck_trades.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["symbol", "entry_t", "exit_t", "entry_px", "exit_px", "tp", "sl", "H", "entry_mode"]); w.writerows(rows)
print("total filas", len(rows))
