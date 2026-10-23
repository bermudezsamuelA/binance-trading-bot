# walk_forward.py
"""
Seleccion honesta de estrategias: walk-forward (ventana rodante) + validacion final reservada.

Protocolo (fijado antes de mirar los resultados; ver doc/matematica-del-bot.md, Parte 4):
1. Datos: todas las velas de 15 min descargadas (2023-01 -> ultimo dia), una serie continua por moneda.
2. Validacion final reservada: el ultimo mes completo + los dias del mes en curso. Ninguna decision la ve.
3. Pliegues de desarrollo: para cada mes de prueba M (desde el 7.o mes hasta el anterior a la reserva),
   se entrena con los TRAIN_MONTHS meses anteriores y se prueba en M (fuera de muestra, OOS).
4. En cada pliegue y para cada estrategia se elige (n, k) SOLO con el entrenamiento: maximo del score
   (PnL - 10 * MDD %) promediado con sus 8 vecinos de la rejilla (zona estable, no picos aislados), entre las
   combinaciones con al menos MIN_TRADES_TRAIN operaciones. Si esa combinacion no gana dinero en el
   entrenamiento, ese mes no se opera.
5. Se concatenan los meses de prueba: es el resultado OOS del procedimiento completo (re-optimizar cada mes).
6. Una estrategia pasa el walk-forward para una moneda solo si su OOS: tiene >= MIN_TRADES_OOS operaciones, PnL
   neto > 0, al menos la mitad de los meses con operaciones en positivo y una prueba t por dia con p < ALPHA /
   numero de pares (moneda, estrategia) probados (correccion de Bonferroni).
7. Los parametros que se cargan en vivo se eligen igual, con los TRAIN_MONTHS meses mas recientes.
8. La validacion final aplica el mismo procedimiento a la reserva. No elige parametros ni estrategia, pero VETA:
   una estrategia que pasa el walk-forward y pierde dinero (PnL < 0) en la reserva queda rechazada (en modo normal
   no se carga; el modo experimental de strategy_engine.py si puede cargarla, marcada).
9. Filtros de entrada (config.py, strategy_filters.py; los mismos del bot en vivo): riesgo minimo y co-senal se aplican
   al elegir (n, k) y al probar cada mes; el interruptor de momentum apaga los meses cuyo PnL en sombra de los 12 meses
   anteriores no es > 0, y su estado actual decide si el bot abre hoy.

Simulacion: fast_backtest.FastSymbol, con paridad exacta con optimize.simulate_live (mismas reglas que el bot).
- Entrenamiento: cada combinacion se simula una sola vez sobre toda la serie y se toman las operaciones que
  entran y salen dentro de la ventana.
- Mes de prueba: se simula aparte, como lo viviria el bot al arrancar con los parametros elegidos: instancia
  nueva precargada con preseed_candles(n) velas (pre_seed_engine), entradas solo durante el mes y cada operacion
  seguida hasta su salida real (salvo las que saldrian en la reserva). Una posicion por moneda, como el bot: si la
  operacion de un mes anterior sigue abierta, el mes nuevo no abre hasta la vela siguiente a su salida (el bot
  conserva la posicion del ledger e ignora los BUY mientras tanto).
"""
import os
import sys
import time
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import strategy_filters as SF
from config import COSIGNAL_CANDLES, ENTRY_MIN_RISK_PCT, MOMENTUM_MONTHS, PRESEED_MARGIN, PRESEED_MIN
from fast_backtest import CANDLE_MS, INTERVAL_MS, STRATEGY_CLASSES, FastSymbol, load_history, set_interval
from optimize import INITIAL_CAPITAL, trades_to_metrics

WINDOWS = list(range(8, 100, 4))                          # 23 ventanas
MULTIPLIERS = [round(0.8 + 0.2 * i, 2) for i in range(13)]  # 0.8 ... 3.2 (los mismos valores que se cargan en vivo)
TRAIN_MONTHS = 6
MIN_TRADES_TRAIN = 30        # ~5 operaciones por mes de entrenamiento
MIN_TRADES_OOS = 30
MIN_POSITIVE_FOLDS = 0.5     # al menos la mitad de los meses con operaciones en positivo
ALPHA = 0.05
DD_PENALTY = 10.0            # score = PnL - 10 * MDD %, como QuantCalculator
STRATEGIES = list(STRATEGY_CLASSES)
DAY_MS = 86_400_000


def preseed_candles(window: int) -> int:
    """Velas con las que server.pre_seed_engine calienta la estrategia al arrancar: max(n + margen, minimo)."""
    return max(window + PRESEED_MARGIN, PRESEED_MIN)


def _ts(ms: int) -> pd.Timestamp:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC")


def _month_floor(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.normalize().replace(day=1)


def build_periods(open_time: np.ndarray, train_months: int = TRAIN_MONTHS, holdout_start: str = None,
                  candle_ms: int = CANDLE_MS) -> dict:
    """Pliegues de desarrollo, de validacion final y la ventana de entrenamiento en vivo (fechas UTC)."""
    start = _month_floor(_ts(open_time[0]))
    end = _ts(open_time[-1] + candle_ms)                      # fin exclusivo (cierre de la ultima vela)
    current = _month_floor(end - pd.Timedelta(milliseconds=1))
    if holdout_start is not None:
        hold = pd.Timestamp(holdout_start, tz="UTC")
    elif end == current + pd.DateOffset(months=1):
        hold = current                                        # el ultimo mes esta completo
    else:
        hold = current - pd.DateOffset(months=1)              # ultimo mes completo + dias del mes en curso
    train = pd.DateOffset(months=train_months)

    def fold(test_start, test_end, limit, kind):
        return {"name": test_start.strftime("%Y-%m"), "kind": kind, "train": (test_start - train, test_start),
                "test": (test_start, test_end), "limit": limit}

    dev, month = [], start + train
    while month < hold:
        dev.append(fold(month, month + pd.DateOffset(months=1), hold, "dev"))
        month = month + pd.DateOffset(months=1)
    holdout, month = [], hold
    while month < end:
        holdout.append(fold(month, min(month + pd.DateOffset(months=1), end), end, "holdout"))
        month = month + pd.DateOffset(months=1)
    live = {"name": "vivo", "kind": "live", "train": (end - train, end), "test": (end, end), "limit": end}
    return {"start": start, "end": end, "holdout_start": hold, "dev": dev, "holdout": holdout, "live": live}


def _smooth3x3(grid: np.ndarray) -> np.ndarray:
    """Media de cada celda con sus vecinas (n +- 4, k +- 0.2); en los bordes, solo las que existen."""
    rows, cols = grid.shape
    vals = np.pad(grid, 1, constant_values=0.0)
    ones = np.pad(np.ones_like(grid), 1, constant_values=0.0)
    total = np.zeros_like(grid)
    count = np.zeros_like(grid)
    for dr in (0, 1, 2):
        for dc in (0, 1, 2):
            total += vals[dr:dr + rows, dc:dc + cols]
            count += ones[dr:dr + rows, dc:dc + cols]
    return total / count


def _slice_stats(pnl: np.ndarray):
    """(operaciones, ganadas, PnL, MDD %) de una secuencia de operaciones, con la curva de capital de calculate_metrics."""
    if len(pnl) == 0:
        return 0, 0, 0.0, 0.0
    cap = INITIAL_CAPITAL + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.maximum(cap, INITIAL_CAPITAL))
    return len(pnl), int((pnl > 0).sum()), float(cap[-1] - INITIAL_CAPITAL), float(((peak - cap) / peak).max() * 100)


class PairEvaluator:
    """Todas las combinaciones (n, k) de una estrategia en una moneda, simuladas una vez sobre toda la serie."""

    def __init__(self, fs: FastSymbol, open_time: np.ndarray, strategy: str):
        self.fs = fs
        self.open_time = open_time
        self.strategy = strategy
        self.sims = {}
        for w in WINDOWS:
            for m in MULTIPLIERS:
                self.sims[(w, m)] = fs.simulate(strategy, w, m)

    def idx(self, ts: pd.Timestamp) -> int:
        return int(np.searchsorted(self.open_time, ts.value // 10**6, side="left"))

    def train_trades(self, combo, a: int, b: int) -> np.ndarray:
        """PnL de las operaciones que entran y salen dentro de [a, b)."""
        entry, exit_, pnl = self.sims[combo]
        lo = np.searchsorted(entry, a, side="left")
        hi = np.searchsorted(exit_, b, side="left")
        return pnl[lo:hi] if hi > lo else pnl[:0]

    def test_trades(self, combo, a: int, b: int, limit: int, open_until: int = -1):
        """(entrada, salida, PnL, ultima_salida) del mes de prueba [a, b) como lo vive el bot al arrancar con esta
        combinacion: instancia nueva precargada con preseed_candles(n) velas, entradas solo en [a, b) y cada operacion
        seguida hasta su salida real; las que saldrian en limit o despues (la reserva) no cuentan.
        Una posicion por moneda, como el bot (canOpenPosition): si la operacion de un mes anterior sigue abierta hasta
        la vela open_until, este mes no abre otra hasta la vela siguiente (la estrategia ve esas velas, pero su BUY se
        ignora). ultima_salida = vela de salida de la ultima operacion abierta (aunque salga en la reserva), para que
        el mes siguiente tampoco abra mientras siga abierta."""
        w, m = combo
        entry, exit_, pnl = self.fs.simulate(self.strategy, w, m, first=max(0, a - preseed_candles(w)),
                                             start=max(a, open_until + 1), entry_end=b)
        keep = exit_ < limit
        last = int(exit_[-1]) if len(exit_) else -1
        return entry[keep], exit_[keep], pnl[keep], max(open_until, last)

    def select(self, train: tuple) -> dict:
        """Eleccion de (n, k) con SOLO el periodo de entrenamiento (zona estable de la rejilla)."""
        a, b = self.idx(train[0]), self.idx(train[1])
        shape = (len(WINDOWS), len(MULTIPLIERS))
        trades = np.zeros(shape, dtype=np.int64)
        wins = np.zeros(shape, dtype=np.int64)
        pnl = np.zeros(shape)
        score = np.zeros(shape)
        for r, w in enumerate(WINDOWS):
            for c, m in enumerate(MULTIPLIERS):
                n, g, p, dd = _slice_stats(self.train_trades((w, m), a, b))
                trades[r, c], wins[r, c], pnl[r, c], score[r, c] = n, g, p, p - DD_PENALTY * dd
        smooth = _smooth3x3(score)
        eligible = trades >= MIN_TRADES_TRAIN
        if not eligible.any():
            return {"combo": None, "motivo": f"ninguna combinacion con >= {MIN_TRADES_TRAIN} operaciones"}
        r, c = np.unravel_index(np.argmax(np.where(eligible, smooth, -np.inf)), shape)
        combo = (WINDOWS[r], MULTIPLIERS[c])
        info = {"combo": combo, "trades": int(trades[r, c]), "wins": int(wins[r, c]), "pnl": float(pnl[r, c]),
                "score": float(score[r, c]), "score_suavizado": float(smooth[r, c])}
        if pnl[r, c] <= 0:
            info["motivo"] = "la zona elegida no gana dinero en el entrenamiento: ese periodo no opera"
            info["operar"] = False
        else:
            info["operar"] = True
        return info


def _daily_t(exit_idx: np.ndarray, pnl: np.ndarray, open_time: np.ndarray):
    """Prueba t de una cola sobre el PnL sumado por dia (dias con al menos una operacion cerrada)."""
    if len(pnl) == 0:
        return 0, 0.0, 1.0
    days = open_time[exit_idx] // DAY_MS
    _, inv = np.unique(days, return_inverse=True)
    daily = np.bincount(inv, weights=pnl)
    if len(daily) < 2 or daily.std(ddof=1) == 0:
        return len(daily), 0.0, 1.0
    t = daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily)))
    return len(daily), float(t), float(sp_stats.t.sf(t, len(daily) - 1))


def _metrics(pnl: np.ndarray) -> dict:
    return trades_to_metrics([{"pnl": float(p)} for p in pnl])


def run_folds(ev: PairEvaluator, folds: list, open_until: int = -1):
    """Aplica el procedimiento a cada pliegue, en orden. Devuelve las filas por pliegue, las operaciones OOS
    concatenadas y la vela de salida de la ultima operacion (open_until): un mes no abre mientras siga abierta la
    operacion de un mes anterior, como el bot (una posicion por moneda). La validacion final recibe el open_until
    del desarrollo."""
    rows, entries, exits, pnls = [], [], [], []
    for f in folds:
        sel = ev.select(f["train"])
        row = {"prueba": f["name"], "n": None, "k": None, "ops_ent": 0, "pnl_ent": 0.0, "ops": 0, "pnl": 0.0,
               "gan_ent": 0, "opera": bool(sel.get("operar"))}
        if sel["combo"] is not None:
            row.update(n=sel["combo"][0], k=sel["combo"][1], ops_ent=sel["trades"], pnl_ent=sel["pnl"],
                       gan_ent=sel["wins"])
        if sel.get("operar"):
            e, x, p, open_until = ev.test_trades(sel["combo"], ev.idx(f["test"][0]), ev.idx(f["test"][1]),
                                                 ev.idx(f["limit"]), open_until)
            row.update(ops=int(len(p)), pnl=float(p.sum()))
            entries.append(e)
            exits.append(x)
            pnls.append(p)
        rows.append(row)
    cat = lambda xs, dt: np.concatenate(xs).astype(dt) if xs else np.zeros(0, dtype=dt)
    return rows, cat(entries, np.int64), cat(exits, np.int64), cat(pnls, np.float64), open_until


def summarize_oos(rows, exits, pnl, open_time, start, end) -> dict:
    traded = [r for r in rows if r["ops"] > 0]
    positive = sum(1 for r in traded if r["pnl"] > 0)
    days, t, p = _daily_t(exits, pnl, open_time)
    return {"desde": start.strftime("%Y-%m-%d"), "hasta": (end - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "pliegues": len(rows), "pliegues_con_operaciones": len(traded),
            "pliegues_positivos_pct": round(100.0 * positive / len(traded), 1) if traded else 0.0,
            **_metrics(pnl), "dias_con_operaciones": days, "t_dia": round(t, 3), "p_valor": float(f"{p:.3g}")}


def summarize_train(rows, train_months: int = TRAIN_MONTHS) -> dict:
    """Lo que 'promete' el optimizador: metricas dentro de muestra (en su propio entrenamiento) de la combinacion
    elegida, sumadas sobre los pliegues que si operaron su mes de prueba."""
    used = [r for r in rows if r["opera"]]
    ops = sum(r["ops_ent"] for r in used)
    pnl = sum(r["pnl_ent"] for r in used)
    wins = sum(r["gan_ent"] for r in used)
    return {"pliegues_operados": len(used), "ops_por_mes": round(ops / max(1, len(used)) / train_months, 2),
            "win_rate": round(100.0 * wins / ops, 2) if ops else 0.0,
            "pnl_por_mes": round(pnl / max(1, len(used)) / train_months, 4),
            "expected_payoff": round(pnl / ops, 4) if ops else 0.0}


@lru_cache(maxsize=None)
def _symbol_data(symbol: str, interval: str) -> tuple:
    """(FastSymbol, open_time) de una moneda; cada proceso los carga una vez (la co-senal usa las de las demas)."""
    candles = load_history(symbol, interval=interval)
    return FastSymbol(candles), candles["open_time"].to_numpy(np.int64)


def evaluate_pair(task):
    """Trabajo de un proceso: una moneda y una estrategia, con los filtros de entrada de config.py (los mismos que
    aplica el bot en vivo). Devuelve un dict serializable."""
    symbol, strategy, train_months, holdout_start, interval, roster = task
    t0 = time.perf_counter()
    set_interval(interval)
    fs, open_time = _symbol_data(symbol, interval)
    periods = build_periods(open_time, train_months, holdout_start, INTERVAL_MS[interval])
    others = [_symbol_data(o, interval) for o in roster if o != symbol] if COSIGNAL_CANDLES else []
    ev = PairEvaluator(SF.FilteredFS(fs, open_time, others, INTERVAL_MS[interval], ENTRY_MIN_RISK_PCT, COSIGNAL_CANDLES),
                       open_time, strategy)
    t_sim = time.perf_counter() - t0

    dev_rows, dev_entry, dev_exit, dev_pnl, dev_open_until = run_folds(ev, periods["dev"])
    hold_rows, hold_entry, hold_exit, hold_pnl, _ = run_folds(ev, periods["holdout"], dev_open_until)
    live = ev.select(periods["live"]["train"])
    momentum = None
    if MOMENTUM_MONTHS:
        on_dev = SF.momentum_gate(dev_rows, [], MOMENTUM_MONTHS)
        on_hold = SF.momentum_gate(hold_rows, [r["pnl"] for r in dev_rows], MOMENTUM_MONTHS)
        dev_rows, dev_entry, dev_exit, dev_pnl = SF.gate_trades(dev_rows, dev_entry, dev_exit, dev_pnl, open_time, on_dev)
        hold_rows, hold_entry, hold_exit, hold_pnl = SF.gate_trades(hold_rows, hold_entry, hold_exit, hold_pnl,
                                                                     open_time, on_hold)
        shadow = sum(r["pnl_sombra"] for r in (dev_rows + hold_rows)[-MOMENTUM_MONTHS:])
        momentum = {"meses": MOMENTUM_MONTHS, "pnl_sombra": round(float(shadow), 4), "encendido": bool(shadow > 0)}

    result = {"symbol": symbol, "strategy": strategy, "momentum": momentum,
              "oos": summarize_oos(dev_rows, dev_exit, dev_pnl, open_time, periods["dev"][0]["test"][0],
                                   periods["holdout_start"]) if dev_rows else None,
              "entrenamiento_pliegues": summarize_train(dev_rows, train_months),
              "validacion_final": summarize_oos(hold_rows, hold_exit, hold_pnl, open_time, periods["holdout_start"],
                                                periods["end"]) if hold_rows else None,
              "pliegues": dev_rows, "pliegues_validacion": hold_rows,
              # Operaciones cerradas (vela de salida y PnL), para combinar varias monedas por dia (replication.py)
              "operaciones": {"oos": {"salida_ms": open_time[dev_exit].tolist(), "pnl": dev_pnl.tolist()},
                              "validacion": {"salida_ms": open_time[hold_exit].tolist(), "pnl": hold_pnl.tolist()}},
              "vivo": None, "vivo_motivo": live.get("motivo"),
              "segundos": round(time.perf_counter() - t0, 1), "segundos_simulacion": round(t_sim, 1)}
    if live["combo"] is not None:
        w, m = live["combo"]
        a, b = ev.idx(periods["live"]["train"][0]), ev.idx(periods["live"]["train"][1])
        result["vivo"] = {"window": w, "multiplier": m, "operar": live["operar"],
                          "score_suavizado": round(live["score_suavizado"], 4),
                          **_metrics(ev.train_trades((w, m), a, b))}
    return result


def decide(result: dict, n_tests: int) -> tuple:
    """(estado, motivo, pasa_walk_forward) de un par (moneda, estrategia): el OOS de desarrollo decide y la
    validacion final solo puede vetar (PnL < 0)."""
    oos = result["oos"]
    alpha = ALPHA / n_tests
    if oos is None:
        return "rechazada", "no hay meses de desarrollo suficientes", False
    fails = []
    if oos["trades"] < MIN_TRADES_OOS:
        fails.append(f"{oos['trades']} operaciones OOS < {MIN_TRADES_OOS}")
    if oos["pnl"] <= 0:
        fails.append(f"PnL OOS {oos['pnl']:+.2f} USDT <= 0")
    if oos["pliegues_positivos_pct"] < 100 * MIN_POSITIVE_FOLDS:
        fails.append(f"solo {oos['pliegues_positivos_pct']} % de meses positivos")
    if oos["p_valor"] >= alpha:
        fails.append(f"p = {oos['p_valor']:.3g} >= {alpha:.4g}")
    if fails:
        return "rechazada", "; ".join(fails), False
    passed = f"OOS {oos['trades']} ops, PnL {oos['pnl']:+.2f} USDT, t/dia {oos['t_dia']}, p = {oos['p_valor']:.3g} < {alpha:.4g}"
    hold = result["validacion_final"]
    if hold is not None and hold["pnl"] < 0:
        return "rechazada", f"pasa el walk-forward ({passed}), pero pierde en la validacion final (PnL {hold['pnl']:+.2f} USDT)", True
    if result["vivo"] is None or not result["vivo"]["operar"]:
        return "rechazada", f"pasa el walk-forward ({passed}), pero no tiene parametros rentables en la ventana mas reciente", True
    momentum = result.get("momentum")
    if momentum and not momentum["encendido"]:
        passed += (f"; interruptor de momentum apagado (PnL en sombra de {momentum['meses']} meses "
                   f"{momentum['pnl_sombra']:+.2f} USDT): no abre hasta que vuelva a ser > 0")
    return "validada", passed, True


def run_walk_forward(roster: list, workers: int = None, train_months: int = TRAIN_MONTHS,
                     holdout_start: str = None, interval: str = "15m") -> list:
    """Evalua todos los pares (moneda, estrategia) en paralelo (deja 2 nucleos libres)."""
    from multiprocessing import Pool
    tasks = [(s, st, train_months, holdout_start, interval, tuple(roster)) for s in roster for st in STRATEGIES]
    workers = workers or max(1, (os.cpu_count() or 3) - 2)
    results = []
    with Pool(processes=min(workers, len(tasks))) as pool:
        for res in pool.imap_unordered(evaluate_pair, tasks):
            print(f"[WALK-FORWARD] {res['symbol']:<8} {res['strategy']:<17} listo en {res['segundos']} s "
                  f"(OOS: {res['oos']['trades'] if res['oos'] else 0} ops, PnL {res['oos']['pnl'] if res['oos'] else 0:+.2f})")
            results.append(res)
    order = {(s, st): i for i, (s, st, *_) in enumerate(tasks)}
    return sorted(results, key=lambda r: order[(r["symbol"], r["strategy"])])
