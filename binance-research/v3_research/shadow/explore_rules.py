"""Exploracion de reglas de CARTERA sobre el modelo congelado (no cambia el modelo, el umbral ni la salida X5 384).

Genera, por tramo de fechas, las operaciones de varias reglas de entrada basadas en la co-senal (A18 >= k, k = 0..8) y
las guarda en CSV; el analisis de la cartera (tope de posiciones, interruptor por rachas) se hace sobre esos CSV con
analyze_rules.py. Las reglas se eligen SOLO con el periodo de diseno y se validan en el periodo nuevo y en 2022.

Uso (desde binance-research):
  python v3_research/shadow/explore_rules.py --data-dir v3_research/tmp/new20 --monedas <lista> --start A --end B --out <dir>
"""
import argparse
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_daily as RD  # noqa: E402

C, H = RD.C, RD.H
KS = [0, 3, 8]
PMINS = [0.7143, 0.725, 0.733, 0.745, 0.76]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--monedas", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--dvol", default=RD.DVOL_FILE)
    ap.add_argument("--reason", default=None)
    ap.add_argument("--proxy", action="store_true", help="funding del mes en curso reconstruido con la prima")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    symbols = a.monedas.split(",")
    if a.proxy:
        with RD.ProxyFunding():
            ev = RD.evaluate(a.data_dir, a.start, RD.to_ms(a.end), a.reason, dvol_file=a.dvol, symbols=symbols)
    else:
        ev = RD.evaluate(a.data_dir, a.start, RD.to_ms(a.end), a.reason, dvol_file=a.dvol, symbols=symbols)
    D = ev["D"]
    ga, gm, gH = C.GEOMS["X5_384"]
    os.makedirs(a.out, exist_ok=True)
    fee, slip = RD.COSTS["0.24 %"][:2]
    with open(os.path.join(a.out, "operaciones.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["regla", "symbol", "entrada_ms", "salida_ms", "motivo", "neto", "A18", "p", "z30"])
        for k in KS:
          for pmin in PMINS:
            for sym in symbols:
                d, S = D[sym], D[sym]["S"]
                sd = S["s15"] * np.sqrt(96)
                tr = H.simulate(d["bars"], d["sig"] & (d["p"] >= pmin) & (d["A18"] >= k), S["c"] * (1 + ga * sd), S["c"] * (1 - gm * sd),
                                period=(d["i0"], d["i1"]), max_hold=gH, fee=fee, slip=slip)
                for j in range(len(tr)):
                    if tr.reason[j] == H.END:
                        continue
                    i = int(tr.sig_idx[j])
                    z = d["z30"][i]
                    w.writerow([f"A18>={k}|p>={pmin}", sym, int(tr.entry_t[j]), int(tr.exit_t[j]), H.REASONS[int(tr.reason[j])],
                                float(tr.net_ret[j]), int(d["A18"][i]), round(float(d["p"][i]), 4),
                                "" if np.isnan(z) else round(float(z), 3)])
    print("ok", a.out)


if __name__ == "__main__":
    main()
