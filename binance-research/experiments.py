# experiments.py
"""
Experimentos PRE-REGISTRADOS (2026-10-22) con las sugerencias A y B de doc/agente-rl-y-esperanza-positiva.md, usando el
MISMO walk-forward de ml_evaluator.py: 6 meses de entrenamiento -> 1 mes de prueba, 38 pliegues, validacion final
reservada, eleccion de (n, k) solo con el entrenamiento, una posicion por moneda y 15 USDT por operacion. Las reglas de
cada brazo se fijaron ANTES de ver resultados y no se ajustan despues (el umbral de P7 se eligio solo por cantidad de
senales: con imb_z < -2 quedaban 13-107 senales en 46 meses, insuficientes para 30 operaciones por entrenamiento).

Brazos (cada uno sobre las 5 estrategias; P7 solo sobre Capitulation):
  P0   base: el protocolo de ml_evaluator.py sin filtros de entrada (reproduce el ml_results.json del 2026-10-22, antes
       de que config.py activara los filtros, moneda por moneda).
  P3   riesgo minimo 1.5 % del precio: se descarta la senal si entrada - SL < 1.5 % (con 0.5 % el costo es 0.48 R).
  P4   costos con BNB: 0.095 % por lado (0.075 % comision + 0.02 % deslizamiento) = 0.19 % ida y vuelta.
  P34  P3 + P4 (la recomendacion #1 + #3, con BNB).
  P5   momentum de 12 meses: un mes solo se opera si el PnL OOS en sombra del mismo par en los 12 meses anteriores
       es > 0 (el primer mes no opera). En sombra = lo que habria dado el walk-forward aunque ese mes no se operara.
  P6   co-senal: solo entra si la misma regla (misma estrategia y mismos n, k) dio senal en otra de las 4 monedas en
       las ultimas 48 velas (12 h), incluida la actual.
  P7   flujo taker (solo Capitulation): la vela de la senal tiene imb_z < -1, imb = 2 * taker_buy / volumen - 1 y
       z sobre 96 velas (24 h).
  P8   sin lunes ni martes (UTC, por la hora de entrada = cierre de la vela de senal).
  TODO P3 + P4 + P5 + P6 + P8 (+ P7 en Capitulation).

Prueba (A1): por brazo y estrategia se AGRUPAN las operaciones OOS de las 4 monedas (cada moneda con su propia seleccion
walk-forward, como en el bot) y se hace UNA prueba t de una cola sobre el PnL sumado por dia. Pasa si tiene >= 30
operaciones, PnL > 0, >= 50 % de meses positivos y p < alfa, y si la validacion final agrupada no pierde (PnL >= 0).
Se reportan dos alfas (A2): el del brazo (0.05 / estrategias del brazo: vale si ese brazo fuera la unica hipotesis) y el
global (0.05 / todas las pruebas de este lote): el honesto para elegir el mejor brazo despues de ver todos.
Aproximacion de P5: el encadenamiento de una posicion por moneda se toma de la sombra (una operacion de un mes apagado
puede haber retrasado la primera del mes siguiente).

Uso (desde binance-research, sin red):
  .venv\\Scripts\\python experiments.py
Resultado: machine_learning_strategies/experiments_results.json y las tablas por consola.
"""
import datetime
import json
import os
import sys
import time
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import walk_forward as wf
from config import ACTIVE_ROSTER
from fast_backtest import CANDLE_MS, STRATEGY_CLASSES, FastSymbol, load_history
from optimize import NOTIONAL_USDT, SLIPPAGE_PER_SIDE

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "machine_learning_strategies",
                            "experiments_results.json")
DAY_MS = 86_400_000
BNB_COST = 0.00075 + SLIPPAGE_PER_SIDE
STRATEGIES = list(STRATEGY_CLASSES)

# Reglas de simulacion de cada brazo (P5 reutiliza la simulacion de P0; TODO aplica el momentum sobre la suya)
SIMS = {
    "P0": {},
    "P3": {"min_risk": 0.015},
    "P4": {"cost": BNB_COST},
    "P34": {"min_risk": 0.015, "cost": BNB_COST},
    "P6": {"cosignal": 48},
    "P7": {"taker_z": -1.0},
    "P8": {"weekdays_off": [0, 1]},
    "TODO": {"min_risk": 0.015, "cost": BNB_COST, "cosignal": 48, "weekdays_off": [0, 1], "taker_z": -1.0},
}
ARMS = {
    "P0": {"sim": "P0", "desc": "base (ml_evaluator, agrupado)"},
    "P3": {"sim": "P3", "desc": "riesgo minimo 1.5 %"},
    "P4": {"sim": "P4", "desc": "costos con BNB (0.19 %)"},
    "P34": {"sim": "P34", "desc": "riesgo 1.5 % + BNB"},
    "P5": {"sim": "P0", "momentum": 12, "desc": "momentum 12 meses"},
    "P6": {"sim": "P6", "desc": "co-senal 12 h"},
    "P7": {"sim": "P7", "only": ["Capitulation"], "desc": "flujo taker (Capitulation)"},
    "P8": {"sim": "P8", "desc": "sin lunes ni martes"},
    "TODO": {"sim": "TODO", "momentum": 12, "desc": "todo junto"},
}


def arm_strategies(arm: str) -> list:
    return ARMS[arm].get("only", STRATEGIES)


@lru_cache(maxsize=None)
def history(symbol: str) -> pd.DataFrame:
    return load_history(symbol)


@lru_cache(maxsize=None)
def fast(symbol: str) -> FastSymbol:
    return FastSymbol(history(symbol))


def mask_builder(symbol: str, strategy: str, opts: dict):
    """Filtro de entradas del brazo como funcion (n, k) -> mascara bool por vela (None = sin filtro)."""
    candles = history(symbol)
    ot = candles["open_time"].to_numpy(np.int64)
    n = len(ot)
    static = np.ones(n, bool)
    if opts.get("weekdays_off"):
        weekday = ((ot + CANDLE_MS) // DAY_MS + 3) % 7     # 1970-01-01 fue jueves; lunes = 0
        static &= ~np.isin(weekday, opts["weekdays_off"])
    if opts.get("taker_z") is not None and strategy == "Capitulation":
        v = candles["volume"].to_numpy(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            imb = pd.Series(2 * candles["taker_buy"].to_numpy(float) / v - 1)
        z = ((imb - imb.rolling(96).mean()) / imb.rolling(96).std()).to_numpy()
        with np.errstate(invalid="ignore"):
            static &= z < opts["taker_z"]
    window = opts.get("cosignal")
    if not window:
        return (lambda w, m: None) if static.all() else (lambda w, m: static)
    others = [(fast(o), history(o)["open_time"].to_numpy(np.int64)) for o in ACTIVE_ROSTER if o != symbol]
    cache = {}

    def fn(w, m):
        if (w, m) not in cache:
            hit = np.zeros(n, np.int64)
            for ofs, oot in others:
                t = oot[ofs.buy_indices(strategy, w, m)]
                idx = np.searchsorted(ot, t)
                ok = idx < n
                ok[ok] = ot[idx[ok]] == t[ok]
                hit[idx[ok]] = 1
            c = np.cumsum(hit)
            recent = (c - np.concatenate([np.zeros(window, np.int64), c[:-window]])) > 0
            cache[(w, m)] = static & recent
        return cache[(w, m)]
    return fn


class _ArmFS:
    """FastSymbol con las reglas del brazo en cada simulate (costo, riesgo minimo y filtro de entradas): asi el
    walk-forward de walk_forward.PairEvaluator elige y prueba con las mismas reglas, sin tocar su codigo."""

    def __init__(self, fs: FastSymbol, opts: dict, mask_fn):
        self.fs, self.mask_fn = fs, mask_fn
        self.kw = {k: opts[k] for k in ("cost", "min_risk") if opts.get(k) is not None}

    def simulate(self, strategy, w, m, **kw):
        return self.fs.simulate(strategy, w, m, entry_mask=self.mask_fn(w, m), **self.kw, **kw)


def evaluate(task):
    """Un proceso: una simulacion de brazo, una moneda y una estrategia, con el walk-forward de ml_evaluator.py."""
    sim, symbol, strategy = task
    t0 = time.perf_counter()
    candles = history(symbol)
    ot = candles["open_time"].to_numpy(np.int64)
    periods = wf.build_periods(ot)
    ev = wf.PairEvaluator(_ArmFS(fast(symbol), SIMS[sim], mask_builder(symbol, strategy, SIMS[sim])), ot, strategy)
    dev_rows, de, dx, dp, open_until = wf.run_folds(ev, periods["dev"])
    hold_rows, he, hx, hp, _ = wf.run_folds(ev, periods["holdout"], open_until)
    live = ev.select(periods["live"]["train"])
    part = lambda rows, e, x, p: {"meses": [r["prueba"] for r in rows], "pnl_mes": [r["pnl"] for r in rows],
                                  "entrada_t": ot[e].tolist(), "salida_t": ot[x].tolist(), "pnl": p.tolist()}
    return {"sim": sim, "symbol": symbol, "strategy": strategy, "dev": part(dev_rows, de, dx, dp),
            "hold": part(hold_rows, he, hx, hp), "vivo_opera": bool(live.get("operar")),
            "vivo_combo": list(live["combo"]) if live["combo"] else None, "segundos": round(time.perf_counter() - t0, 1)}


def momentum_months(months: list, pnl_month: list, lookback: int) -> set:
    """Meses que se operan: los que tienen PnL en sombra > 0 en los `lookback` meses anteriores (el primero no)."""
    return {mo for j, mo in enumerate(months) if j > 0 and sum(pnl_month[max(0, j - lookback):j]) > 0}


def trades_of(res: dict, arm: dict) -> tuple:
    """(dev, hold, vivo): operaciones del par despues de aplicar el momentum del brazo, como dicts de arreglos."""
    def pick(part, allowed):
        month = [datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).strftime("%Y-%m") for t in part["entrada_t"]]
        keep = np.array([allowed is None or mo in allowed for mo in month], bool)
        return {k: np.asarray(part[k])[keep] if len(keep) else np.asarray(part[k]) for k in ("entrada_t", "salida_t", "pnl")}
    lookback = arm.get("momentum")
    if not lookback:
        return pick(res["dev"], None), pick(res["hold"], None), res["vivo_opera"]
    months = res["dev"]["meses"] + res["hold"]["meses"]
    pnl_month = res["dev"]["pnl_mes"] + res["hold"]["pnl_mes"]
    on = momentum_months(months, pnl_month, lookback)
    live_on = sum(pnl_month[-lookback:]) > 0
    return pick(res["dev"], on), pick(res["hold"], on), res["vivo_opera"] and live_on


def pooled_stats(parts: list) -> dict:
    """Metricas de las operaciones agrupadas de varias monedas: prueba t de una cola sobre el PnL sumado por dia."""
    pnl = np.concatenate([p["pnl"] for p in parts]) if parts else np.zeros(0)
    if len(pnl) == 0:
        return {"ops": 0, "win_rate": 0.0, "pnl": 0.0, "pnl_op_pct": 0.0, "meses_pos_pct": 0.0, "t_dia": 0.0, "p_valor": 1.0}
    exit_t = np.concatenate([p["salida_t"] for p in parts])
    entry_t = np.concatenate([p["entrada_t"] for p in parts])
    _, inv = np.unique(exit_t // DAY_MS, return_inverse=True)
    daily = np.bincount(inv, weights=pnl)
    if len(daily) > 1 and daily.std(ddof=1) > 0:
        t = daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily)))
        p = float(sp_stats.t.sf(t, len(daily) - 1))
    else:
        t, p = 0.0, 1.0
    month = pd.to_datetime(entry_t, unit="ms", utc=True).strftime("%Y-%m")
    by_month = pd.Series(pnl).groupby(np.asarray(month)).sum()
    return {"ops": int(len(pnl)), "win_rate": round(100.0 * float((pnl > 0).mean()), 1), "pnl": round(float(pnl.sum()), 2),
            "pnl_op_pct": round(100.0 * float(pnl.mean()) / NOTIONAL_USDT, 3),
            "meses_pos_pct": round(100.0 * float((by_month > 0).mean()), 1), "t_dia": round(float(t), 2),
            "p_valor": float(f"{p:.3g}")}


def decide(dev: dict, hold: dict, alpha: float) -> tuple:
    fails = []
    if dev["ops"] < wf.MIN_TRADES_OOS:
        fails.append(f"{dev['ops']} ops < {wf.MIN_TRADES_OOS}")
    if dev["pnl"] <= 0:
        fails.append("PnL <= 0")
    if dev["meses_pos_pct"] < 100 * wf.MIN_POSITIVE_FOLDS:
        fails.append(f"{dev['meses_pos_pct']} % meses +")
    if dev["p_valor"] >= alpha:
        fails.append(f"p >= {alpha:.4g}")
    if not fails and hold["pnl"] < 0:
        fails.append("pierde en la validacion final")
    return (not fails), "; ".join(fails) or "pasa"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t_start = time.perf_counter()
    needed = {}
    for arm, spec in ARMS.items():
        for st in arm_strategies(arm):
            needed[(spec["sim"], st)] = True
    tasks = [(sim, sym, st) for (sim, st) in needed for sym in ACTIVE_ROSTER]
    n_tests = sum(len(arm_strategies(a)) for a in ARMS)
    alpha_global = wf.ALPHA / n_tests
    print(f"[EXPERIMENTOS] {len(ARMS)} brazos, {n_tests} pruebas agrupadas (alfa global {alpha_global:.5f}); "
          f"{len(tasks)} walk-forwards de moneda y estrategia.")
    results = {}
    with Pool(processes=max(1, (os.cpu_count() or 3) - 2)) as pool:
        for k, res in enumerate(pool.imap_unordered(evaluate, tasks), 1):
            results[(res["sim"], res["symbol"], res["strategy"])] = res
            print(f"  [{k}/{len(tasks)}] {res['sim']:<5} {res['symbol']:<9} {res['strategy']:<17} {res['segundos']} s", flush=True)

    out = {"_protocolo": {"preregistro": "2026-10-22, antes de ver resultados (ver docstring de experiments.py)",
                          "generado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "brazos": {a: {**ARMS[a], "reglas": SIMS[ARMS[a]["sim"]]} for a in ARMS},
                          "pruebas": n_tests, "alfa_global": alpha_global,
                          "criterios": "agrupado 4 monedas: >= 30 ops, PnL > 0, >= 50 % meses +, p < alfa, validacion final >= 0",
                          "costos_base": "0.12 % por lado; P4/P34/TODO 0.095 % por lado (BNB)", "nocional_usdt": NOTIONAL_USDT}}
    rows = []
    for arm, spec in ARMS.items():
        alpha_arm = wf.ALPHA / len(arm_strategies(arm))
        for st in arm_strategies(arm):
            per_coin, devs, holds, live_coins = {}, [], [], []
            for sym in ACTIVE_ROSTER:
                d, h, live = trades_of(results[(spec["sim"], sym, st)], spec)
                devs.append(d); holds.append(h)
                if live:
                    live_coins.append(sym)
                per_coin[sym] = {"oos": pooled_stats([d]), "validacion_final": pooled_stats([h]), "vivo_opera": live}
            dev, hold = pooled_stats(devs), pooled_stats(holds)
            ok_arm, why_arm = decide(dev, hold, alpha_arm)
            ok_glob, why_glob = decide(dev, hold, alpha_global)
            entry = {"brazo": arm, "estrategia": st, "oos": dev, "validacion_final": hold, "alfa_brazo": alpha_arm,
                     "pasa_hipotesis_unica": ok_arm, "pasa_global": ok_glob, "motivo": why_glob,
                     "monedas_vivo": live_coins, "por_moneda": per_coin}
            out.setdefault(arm, {})[st] = entry
            rows.append(entry)

    with open(RESULTS_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("\n" + "=" * 128)
    print(f"{'Brazo':<6}{'Estrategia':<18}| {'OOS agrupado (4 monedas, 38 meses)':<52}| {'Val. final':<15}| Estado")
    print(f"{'':<24}| {'ops   WR %    PnL USDT  PnL/op %  meses+  t/dia  p':<52}| {'ops   PnL':<15}|")
    print("-" * 128)
    for e in rows:
        d, h = e["oos"], e["validacion_final"]
        state = "PASA" if e["pasa_global"] else ("pasa solo como hipotesis unica" if e["pasa_hipotesis_unica"] else "rechazada")
        print(f"{e['brazo']:<6}{e['estrategia']:<18}| {d['ops']:>4} {d['win_rate']:>5.1f} {d['pnl']:>+9.2f} {d['pnl_op_pct']:>+8.3f}"
              f" {d['meses_pos_pct']:>6.0f}% {d['t_dia']:>+6.2f} {d['p_valor']:<8.3g}| {h['ops']:>3} {h['pnl']:>+8.2f}  | {state}")
    print("=" * 128)
    print(f"\n[EXPERIMENTOS] ✅ {time.perf_counter() - t_start:.0f} s. Resultado: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
