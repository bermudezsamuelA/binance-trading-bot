"""Estadisticas extra del candidato en el walk-forward: t agrupado por semana y mes, meses, DSR."""
import os, sys, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_report as R
H = R.H
tags = sys.argv[1].split(","); geom = sys.argv[2]; ntr = int(sys.argv[3])
o = R.run(tags, geom, verbose=False)
T = o["_T"]; x = T.net_ret
wk = T.entry_t // (7 * 86_400_000)
mo = np.array([int(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y%m")) for t in T.entry_t])
print("n", len(x), "E%", round(x.mean() * 100, 3), "t_dia", round(R.cluster_t(x, T.entry_t // 86_400_000), 2),
      "t_semana", round(R.cluster_t(x, wk), 2), "t_mes", round(R.cluster_t(x, mo), 2))
um = np.unique(mo)
print("meses con operaciones", len(um), "de 18; meses con E>0:", int(sum(x[mo == m].mean() > 0 for m in um)))
print("por mes (n, E%):", [(int(m), int((mo == m).sum()), round(float(x[mo == m].mean() * 100), 2)) for m in um])
d = H.deflated_sharpe(x, n_trials=ntr)
print("DSR (n_trials=%d):" % ntr, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()})
d2 = H.deflated_sharpe(x, n_trials=70)
print("DSR (n_trials=70, solo este agente):", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d2.items()})
print("operaciones por moneda y anio:", round(len(x) / (4 * 1.5), 1), "| reason TP/SL/TIME:",
      [round(float(np.mean(T.reason == r)), 3) for r in (0, 1, 2)], "| hold mediano velas", float(np.median(T.hold)))
