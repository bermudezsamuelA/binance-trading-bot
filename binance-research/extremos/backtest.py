"""Backtest de la estrategia de extremos con datos reales de Binance spot.

Periodos: diseño (inicio de los datos a 2024-12-31), donde se eligen los parámetros, y validación (2025-01-01 al final),
donde se juzga la combinación elegida una sola vez. Criterio para usarla: ganancia media neta E > 0 en validación con
t >= 2 y al menos 100 operaciones (el mismo de doc/resultados-analogos.md), y además t >= 2 contando cada día de
señal una sola vez (promedio de las monedas que dieron señal ese día), porque las caídas de mercado dan señal en muchas
monedas a la vez y esas operaciones no son independientes.

Con --walk-forward, los parámetros se eligen por bloques: con datos hasta 2023 se juzga 2024, hasta 2024 se juzga 2025 y
hasta 2025 se juzga 2026; se juntan los tres bloques. Se evalúan la estrategia completa y la señal diaria sola.

Uso:
    python backtest.py                  # rejilla completa, todas las monedas con datos
    python backtest.py --rapido         # solo la configuración del video
    python backtest.py --monedas BTCUSDT ETHUSDT
    python backtest.py --tf 15m         # usar velas de 15 min (si no descargaste las de 5 min)
    python backtest.py --walk-forward   # elegir parámetros por bloques anuales (2024, 2025, 2026)

Datos: velas de 5 min de descargar_5m.py (v3_research/tmp/k5m/klines). Con --tf 15m usa las de 15 min de la v3
(v3_research/tmp/data2022, v3_research/tmp/new20, v3_research). Otras carpetas: variable EXTREMOS_DATA_DIRS (con ';').
Salidas en output/: rejilla.csv, operaciones.csv (de la combinación elegida y de la del video) y resumen.json.
"""
import argparse
import csv
import dataclasses
import datetime as dt
import itertools
import json
import math
import os
import time

import numpy as np

import estrategia as E

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.join(os.path.dirname(HERE), "v3_research")
OUT = os.path.join(HERE, "output")
STAKE = 15.0
SPLIT = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
DIRS = {"5m": [os.path.join(RESEARCH, "tmp", "k5m")],
        "15m": [os.path.join(RESEARCH, "tmp", "data2022"), os.path.join(RESEARCH, "tmp", "new20"), RESEARCH]}
VIDEO = E.Params()                       # valores por defecto = lectura literal del video
GRID = dict(toques=[2, 3], theta=[1.5, 2.0], usar_c3=[True, False], c_conf=[1.0, 2.0],
            gatillo=["ema", "ambas"], objetivo=["maximo", "rb"])


def iso(ms):
    return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def load(symbol: str, tf: str, dirs) -> dict:
    parts = [np.load(p) for p in (os.path.join(x, "klines", f"{symbol}_{tf}.npy") for x in dirs) if os.path.exists(p)]
    if not parts:
        return None
    a = np.vstack(parts)
    a = a[np.argsort(a[:, 0], kind="stable")]
    a = a[np.r_[True, np.diff(a[:, 0]) > 0]]
    return {"T": a[:, 0].astype(np.int64), "O": a[:, 1], "H": a[:, 2], "L": a[:, 3], "C": a[:, 4]}


def stats(tr) -> dict:
    if not tr:
        return {"n": 0}
    r = np.array([t.ret for t in tr])
    R = np.array([t.r_mult for t in tr])
    n = len(r)
    sd = r.std(ddof=1) if n > 1 else float("nan")
    mon = {}
    for t, x in zip(tr, r):
        k = iso(t.t_entrada)[:7]
        mon[k] = mon.get(k, 0) + x
    eq = np.cumsum(r * STAKE)
    by = {}
    for t, x in zip(tr, r):                       # varias monedas el mismo día no son casos independientes
        by.setdefault(t.dia_senal, []).append(x)
    dm = np.array([np.mean(v) for v in by.values()])
    t_dia = float(dm.mean() / (dm.std(ddof=1) / math.sqrt(len(dm)))) if len(dm) > 1 and dm.std(ddof=1) > 0 else None
    return {"n": n, "acierto": round(float((r > 0).mean()), 3), "e": round(float(r.mean()) * 100, 3),
            "t": round(float(r.mean() / (sd / math.sqrt(n))), 2) if n > 1 and sd > 0 else None,
            "dias_distintos": len(dm), "e_por_dia": round(float(dm.mean()) * 100, 3),
            "t_por_dia": round(t_dia, 2) if t_dia is not None else None,
            "r_medio": round(float(R.mean()), 3), "pnl_usdt": round(float(eq[-1]), 2),
            "max_dd_usdt": round(float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()), 2),
            "meses_pos": f"{sum(v > 0 for v in mon.values())}/{len(mon)}",
            "por_motivo": {m: sum(t.motivo == m for t in tr) for m in ("objetivo", "stop", "tiempo")}}


def passes(v) -> bool:
    return (v.get("n", 0) >= 100 and v.get("e", -1) > 0 and (v.get("t") or 0) >= 2
            and (v.get("t_por_dia") or 0) >= 2)


def run(coins, p: E.Params):
    des, val, fd, fv = [], [], E.Funnel(), E.Funnel()
    for cn in coins:
        t, f = E.run_coin(cn, p, end_ms=SPLIT)
        des += t
        fd.add(f)
        t, f = E.run_coin(cn, p, start_ms=SPLIT)
        val += t
        fv.add(f)
    return des, val, fd, fv


def baselines(coins, p: E.Params):
    """Comprar al abrir el día siguiente a la señal diaria y vender 3 días después; y comprar todos los días."""
    out = {}
    for name, use_sig in (("solo_diario_3d", True), ("todos_los_dias_3d", False)):
        rs = {"diseno": [], "validacion": []}
        for cn in coins:
            d = cn.d
            c = cn.daily(p)
            sig = (c["c1"] & c["c2"] & (c["c3"] if p.usar_c3 else True)) if use_sig else np.ones(len(d["T"]), bool)
            last = -1
            for i in np.flatnonzero(sig):
                if i + 3 >= len(d["T"]) or i <= last:
                    continue
                last = i + 3
                r = d["C"][i + 3] / d["O"][i + 1] - 1 - E.COST
                rs["diseno" if d["T"][i] < SPLIT else "validacion"].append(r)
        out[name] = {k: {"n": len(v), "e": round(float(np.mean(v)) * 100, 3) if v else None,
                         "t": round(float(np.mean(v) / (np.std(v, ddof=1) / math.sqrt(len(v)))), 2) if len(v) > 1 else None,
                         "acierto": round(float(np.mean(np.array(v) > 0)), 3) if v else None} for k, v in rs.items()}
    return out


def write_trades(path, trades):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["moneda", "dia_senal", "entrada_utc", "salida_utc", "precio_entrada", "precio_salida", "stop",
                    "objetivo", "motivo", "ret_neto_pct", "r_neto"])
        for t in sorted(trades, key=lambda x: x.t_entrada):
            w.writerow([t.symbol, iso(t.dia_senal)[:10], iso(t.t_entrada), iso(t.t_salida), f"{t.entrada:.6g}",
                        f"{t.salida:.6g}", f"{t.stop:.6g}", f"{t.objetivo:.6g}", t.motivo, f"{t.ret * 100:.3f}",
                        f"{t.r_mult:.3f}"])


# --------------------------------------------------------------------------------------------------- walk-forward
def ms(day: str) -> int:
    return int(dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


FOLDS = [("2024-01-01", "2025-01-01"), ("2025-01-01", "2026-01-01"), ("2026-01-01", "2100-01-01")]
GRID_DIARIO = dict(toques=[2, 3], theta=[1.5, 2.0], usar_c3=[True, False], hold_dias=[2, 3, 5])
WF_MIN_N = 20


def daily_trades(coins, p: E.Params, hold: int, todos: bool = False):
    """Solo la señal diaria: comprar al abrir el día siguiente y vender al cierre `hold` días después (sin stop)."""
    out = []
    for cn in coins:
        d = cn.d
        if todos:
            sig = np.ones(len(d["T"]), bool)
        else:
            c = cn.daily(p)
            sig = c["c1"] & c["c2"] & (c["c3"] if p.usar_c3 else True)
        last = -1
        for i in np.flatnonzero(sig):
            if i + hold >= len(d["T"]) or i < last:
                continue
            last = i + hold
            en, ex = float(d["O"][i + 1]), float(d["C"][i + hold])
            r = ex / en - 1 - E.COST
            out.append(E.Trade(cn.symbol, int(d["T"][i]), int(d["T"][i + 1]), int(d["T"][i + hold]) + E.DAY, en, ex,
                               float("nan"), float("nan"), "tiempo", r, float("nan")))
    return out


def walk_forward(coins, families, t0):
    """Para cada bloque: elige la combinación con mayor E en todo lo anterior (n >= WF_MIN_N) y la juzga en el bloque.

    families: {nombre: [(etiqueta, operaciones de toda la historia), ...]}. Las operaciones se asignan a un periodo por
    el día de la señal. Devuelve el resumen por familia.
    """
    res = {}
    for fam, combos in families.items():
        folds, oos = [], []
        for start, end in FOLDS:
            a, b = ms(start), ms(end)
            best, best_e = None, -np.inf
            for lab, tr in combos:
                des = [t for t in tr if t.dia_senal < a]
                if len(des) >= WF_MIN_N:
                    e = float(np.mean([t.ret for t in des]))
                    if e > best_e:
                        best, best_e = (lab, tr), e
            if best is None:
                folds.append({"prueba": start[:4], "elegida": None})
                continue
            lab, tr = best
            test = [t for t in tr if a <= t.dia_senal < b]
            oos += test
            folds.append({"prueba": start[:4], "elegida": lab,
                          "diseno": stats([t for t in tr if t.dia_senal < a]), "prueba_res": stats(test)})
            print(f"[WF {fam}] prueba {start[:4]}: {lab} -> {stats(test)} ({time.time() - t0:.0f} s)", flush=True)
        res[fam] = {"bloques": folds, "fuera_de_muestra": stats(oos), "pasa_criterio": passes(stats(oos))}
        res[fam]["_ops"] = oos
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", choices=["5m", "15m"], default="5m")
    ap.add_argument("--monedas", nargs="*")
    ap.add_argument("--rapido", action="store_true")
    ap.add_argument("--walk-forward", action="store_true", help="elegir parámetros por bloques anuales (2024, 2025, 2026)")
    a = ap.parse_args(argv)
    dirs = [x for x in os.environ.get("EXTREMOS_DATA_DIRS", "").split(";") if x] or DIRS[a.tf]
    import descargar_5m
    symbols = a.monedas or descargar_5m.COINS
    t0 = time.time()
    coins = []
    for s in symbols:
        b = load(s, a.tf, dirs)
        if b is None:
            print(f"{s}: sin velas de {a.tf} en {dirs}", flush=True)
            continue
        coins.append(E.Coin(s, b, 5 * E.MIN if a.tf == "5m" else 15 * E.MIN))
    if not coins:
        raise SystemExit("No hay datos. Corre primero: python descargar_5m.py (o usa --tf 15m)")
    print(f"{len(coins)} monedas con velas de {a.tf}: {iso(min(c.b['T'][0] for c in coins))[:10]} a "
          f"{iso(max(c.b['T'][-1] for c in coins))[:10]} ({time.time() - t0:.0f} s)", flush=True)
    os.makedirs(OUT, exist_ok=True)
    if a.walk_forward:
        fam = {"completa": [], "solo_diario": []}
        for v in itertools.product(*GRID.values()):
            p = dataclasses.replace(VIDEO, **dict(zip(GRID, v)))
            tr = []
            for cn in coins:
                tr += E.run_coin(cn, p)[0]
            fam["completa"].append(({k: getattr(p, k) for k in GRID}, tr))
        print(f"rejilla completa simulada ({time.time() - t0:.0f} s)", flush=True)
        for v in itertools.product(*GRID_DIARIO.values()):
            kw = dict(zip(GRID_DIARIO, v))
            hold = kw.pop("hold_dias")
            p = dataclasses.replace(VIDEO, **kw)
            fam["solo_diario"].append(({**kw, "hold_dias": hold}, daily_trades(coins, p, hold)))
        ref = [({"todos_los_dias": True}, daily_trades(coins, VIDEO, 3, todos=True))]
        res = walk_forward(coins, fam, t0)
        allday = ref[0][1]
        res["referencia_todos_los_dias_3d"] = {f[0][:4]: stats([t for t in allday if ms(f[0]) <= t.dia_senal < ms(f[1])])
                                               for f in FOLDS}
        for k in ("completa", "solo_diario"):
            write_trades(os.path.join(OUT, f"wf_operaciones_{k}_{a.tf}.csv"), res[k].pop("_ops"))
        res["bloques"] = FOLDS
        res["min_operaciones_diseno"] = WF_MIN_N
        with open(os.path.join(OUT, f"resumen_wf_{a.tf}.json"), "w") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2, default=str)
        for k in ("completa", "solo_diario"):
            print(f"{k}: fuera de muestra {res[k]['fuera_de_muestra']} | pasa: {res[k]['pasa_criterio']}")
        print(f"Referencia: {res['referencia_todos_los_dias_3d']}")
        print(f"Listo en {time.time() - t0:.0f} s. Salidas en {OUT}")
        return

    combos = [VIDEO] if a.rapido else [dataclasses.replace(VIDEO, **dict(zip(GRID, v)))
                                       for v in itertools.product(*GRID.values())]
    rows, keep = [], {}
    for i, p in enumerate(combos, 1):
        des, val, fd, fv = run(coins, p)
        sd, sv = stats(des), stats(val)
        key = {k: getattr(p, k) for k in GRID}
        rows.append({**key, **{f"dis_{k}": v for k, v in sd.items() if k != "por_motivo"},
                     **{f"val_{k}": v for k, v in sv.items() if k != "por_motivo"}})
        keep[i - 1] = (p, des, val, fd, fv, sd, sv)
        print(f"[{i}/{len(combos)}] {key} -> diseño n={sd['n']} E={sd.get('e')} | validación n={sv['n']} "
              f"E={sv.get('e')} t={sv.get('t')} ({time.time() - t0:.0f} s)", flush=True)
    with open(os.path.join(OUT, f"rejilla_{a.tf}.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k)
                                                 if k in rows[0] else 999))
        w.writeheader()
        w.writerows(rows)

    def pick():
        ok = [i for i, r in enumerate(rows) if r.get("dis_n", 0) >= 30]
        return max(ok, key=lambda i: rows[i]["dis_e"]) if ok else None

    def describe(i):
        p, des, val, fd, fv, sd, sv = keep[i]
        return {"parametros": dataclasses.asdict(p), "diseno": sd, "validacion": sv, "pasa_criterio": passes(sv),
                "embudo_diseno": dataclasses.asdict(fd), "embudo_validacion": dataclasses.asdict(fv)}

    vid = next(i for i in keep if keep[i][0] == VIDEO) if VIDEO in [k[0] for k in keep.values()] else 0
    best = pick()
    res = {"temporalidad_gatillo": a.tf, "monedas": [c.symbol for c in coins], "corte_validacion": "2025-01-01",
           "costo_ida_vuelta": E.COST, "configuracion_video": describe(vid),
           "mejor_en_diseno": describe(best) if best is not None else None,
           "referencias": baselines(coins, VIDEO), "segundos": round(time.time() - t0)}
    with open(os.path.join(OUT, f"resumen_{a.tf}.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    write_trades(os.path.join(OUT, f"operaciones_video_{a.tf}.csv"), keep[vid][1] + keep[vid][2])
    if best is not None:
        write_trades(os.path.join(OUT, f"operaciones_mejor_{a.tf}.csv"), keep[best][1] + keep[best][2])
    for name, i in (("Video", vid), ("Mejor en diseño", best)):
        if i is None:
            continue
        p, *_r, sd, sv = keep[i]
        print(f"{name}: diseño {sd} | validación {sv} | pasa: {passes(sv)}")
    print(f"Referencias: {res['referencias']}")
    print(f"Listo en {time.time() - t0:.0f} s. Salidas en {OUT}")


if __name__ == "__main__":
    main()
