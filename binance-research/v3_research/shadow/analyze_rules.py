"""Analisis de reglas de cartera sobre las operaciones de explore_rules.py (15 USDT por operacion, costo 0.24 %)."""
import glob
import sys

import numpy as np
import pandas as pd

DAY = 86_400_000
ANCHORS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"}


def load(pattern, drop_anchors=False):
    d = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(pattern))], ignore_index=True)
    if drop_anchors:
        d = d[~d.symbol.isin(ANCHORS)]
    d["pnl"] = d.neto * 15
    d["e"] = pd.to_datetime(d.entrada_ms, unit="ms")
    d["x"] = pd.to_datetime(d.salida_ms, unit="ms")
    return d


def stats(d):
    if not len(d):
        return dict(n=0, E=np.nan, pnl=0.0, t=np.nan, meses_pos="0/0", peor=0.0, caida=0.0, wr=np.nan)
    day = d.groupby(d.x.dt.date).pnl.sum()
    t = day.mean() / (day.std(ddof=1) / np.sqrt(len(day))) if len(day) > 2 and day.std() > 0 else np.nan
    m = d.groupby(d.x.dt.to_period("M")).pnl.sum()
    cur = d.sort_values("x").pnl.cumsum()
    return dict(n=len(d), E=100 * d.neto.mean(), pnl=d.pnl.sum(), t=t, meses_pos=f"{(m > 0).sum()}/{len(m)}",
                peor=m.min(), caida=(cur.cummax().clip(lower=0) - cur).max(), wr=(d.neto > 0).mean())


def cap_positions(d, n):
    """Tope de posiciones abiertas: se toma la senal solo si hay menos de n abiertas (por orden de entrada; empate -> p mayor)."""
    d = d.sort_values(["entrada_ms", "p"], ascending=[True, False])
    open_x, keep = [], []
    for e, x in zip(d.entrada_ms, d.salida_ms):
        open_x = [v for v in open_x if v > e]
        if len(open_x) < n:
            open_x.append(x)
            keep.append(True)
        else:
            keep.append(False)
    return d[np.array(keep)]


def kill_switch(d, months, thr=0.0):
    """Interruptor mensual: se opera un mes solo si el PnL (en sombra) de los `months` meses anteriores es > thr."""
    m = d.groupby(d.x.dt.to_period("M")).pnl.sum()
    allm = pd.period_range(m.index.min(), m.index.max(), freq="M")
    m = m.reindex(allm, fill_value=0.0)
    on = {p: (m.shift(1).rolling(months, min_periods=months).sum().get(p, np.nan) > thr) for p in allm}
    return d[d.e.dt.to_period("M").map(lambda p: bool(on.get(p, False)))]


def row(label, d):
    s = stats(d)
    return (f"{label:<26}{s['n']:>6}{s['wr'] * 100:>7.1f}{s['E']:>8.3f}{s['pnl']:>9.1f}{s['t']:>7.2f}"
            f"{s['meses_pos']:>8}{s['peor']:>8.1f}{s['caida']:>8.1f}")


HEAD = f"{'':<26}{'n':>6}{'WR%':>7}{'E%':>8}{'PnL':>9}{'t':>7}{'meses+':>8}{'peor':>8}{'caida':>8}"
if __name__ == "__main__":
    sets = {"DISEÑO 2023-03..2025-06 (19 nuevas)": ("v3_research/tmp/explore/n*/operaciones.csv", True, "2025-07-01", True),
            "NUEVO 2025-07..2026-09 (19 nuevas)": ("v3_research/tmp/explore/n*/operaciones.csv", True, "2025-07-01", False),
            "ESTRES 2022 (18)": ("v3_research/tmp/explore/s2022/operaciones.csv", False, None, None)}
    for name, (pat, drop, cut, before) in sets.items():
        d = load(pat, drop)
        if cut:
            d = d[(d.e < cut) if before else (d.e >= cut)]
        print(f"\n== {name}\n{HEAD}")
        for k in (0, 1, 2, 3, 5, 8):
            print(row(f"A18>={k}", d[d.regla == f"A18>={k}"]))
