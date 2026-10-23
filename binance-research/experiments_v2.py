# experiments_v2.py
"""
Segundo lote de experimentos PRE-REGISTRADOS (2026-10-23, antes de ver resultados), con tres mejoras de
doc/agente-rl-y-esperanza-positiva.md: meta-etiquetado con LightGBM (fase 5), nocional proporcional a la E de 12 meses
(fase 4) y TP con orden LIMIT (fase 7). Usa el MISMO walk-forward que ml_evaluator.py con la configuracion actual del
bot: velas de config.KLINE_INTERVAL, filtros de entrada de config.py (riesgo minimo, co-senal e interruptor de momentum),
6 meses de entrenamiento -> 1 mes de prueba, validacion final reservada, una posicion por moneda y 15 USDT por operacion.
Las reglas de cada brazo se fijaron antes de ver resultados y no se ajustan despues.

Brazos (sobre las 20 parejas moneda x estrategia, cada una con su propia seleccion walk-forward):
  BASE    el bot actual: reproduce las operaciones OOS de ml_results.json (se comprueba al correr).
  META    filtro de entradas (meta-etiquetado). Cada mes M se entrena un LightGBM con TODAS las operaciones en sombra de
          las 20 parejas que ya cerraron antes de que empiece M (purgado: la etiqueta se conoce al salir), con etiqueta
          PnL neto > 0. Variables al cierre de la vela de la senal: retornos propios de 1, 24 y 168 velas, retornos de BTC
          de 24 y 168, volatilidad 24/168, efficiency ratio de 24, flujo taker (imb, z de 96, CVD de 24), volumen
          relativo de 24, distancia al maximo de 168, dia de la semana, riesgo en % del precio, b = TP/SL, costo en R,
          E de la pareja en 3 y 12 meses (sombra) y la estrategia (categorica). La moneda NO es variable. Se toma la
          senal si p > p* = (1 + c_R) / (1 + b), con c_R = 2 * costo por lado / riesgo. Sin modelo (menos de 300
          operaciones de entrenamiento o una sola clase) se toman todas. Hiperparametros fijos (META_PARAMS).
          Control antifabricacion: 20 replicas que omiten al azar la misma proporcion de senales en cada mes y pareja.
  TAMANO  nocional = 15 * E12 / costo de ida y vuelta (0.24 %), entre 5 USDT (minimo de Binance) y 30 USDT (2x); 0 si
          E12 <= 0. E12 = PnL en sombra / operaciones en sombra de los 12 meses anteriores, en % del nocional. Abre las
          mismas operaciones que BASE (E12 > 0 es el interruptor de momentum), solo cambia el tamano.
  LIMIT   TP con orden LIMIT puesta desde la entrada (fast_backtest.simulate tp_limit): se llena solo si el maximo de la
          vela SUPERA el TP (tocarlo no basta), al precio del TP y sin deslizamiento en esa pata. El SL sigue a mercado.
          Se usa tambien al elegir (n, k) en el entrenamiento, como lo viviria el bot.
  TODO    LIMIT + META + TAMANO (el modelo se entrena con las operaciones en sombra de LIMIT).

Prueba: por brazo, las operaciones OOS de las 20 parejas se agrupan y se compara con BASE de forma PAREADA: diferencia del
PnL sumado por dia de salida (dias con operaciones en alguno de los dos), prueba t de una cola. El brazo MEJORA el PnL si
la diferencia de desarrollo es > 0 con p < 0.05 / 4 (Bonferroni, 4 brazos contra BASE), si en la validacion final la
diferencia no es negativa y, en META y TODO, si la diferencia supera al percentil 95 de las replicas al azar. Aparte se
informa si el brazo es rentable por si solo (>= 30 ops, PnL > 0, >= 50 % meses +, p < 0.0125 y validacion final >= 0).
Aproximacion (como el interruptor de momentum de walk_forward.py): el encadenamiento de una posicion por moneda sale de
la sombra (una operacion de un mes apagado pudo retrasar la primera del mes siguiente).

Uso (desde binance-research, sin red):
  .venv\\Scripts\\python experiments_v2.py
Resultado: machine_learning_strategies/experiments_v2_results.json y las tablas por consola.
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

import strategy_filters as SF
import walk_forward as wf
from config import ACTIVE_ROSTER, COSIGNAL_CANDLES, ENTRY_MIN_RISK_PCT, KLINE_INTERVAL, MOMENTUM_MONTHS
from fast_backtest import INTERVAL_MS, STRATEGY_CLASSES, load_history, set_interval
from optimize import FEE_PER_SIDE, NOTIONAL_USDT, SLIPPAGE_PER_SIDE

ML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "machine_learning_strategies")
RESULTS_FILE = os.path.join(ML_DIR, "experiments_v2_results.json")
BASE_FILE = os.path.join(ML_DIR, "ml_results.json")
INTERVAL = KLINE_INTERVAL
CANDLE_MS = INTERVAL_MS[INTERVAL]
DAY_MS = 86_400_000
COST = FEE_PER_SIDE + SLIPPAGE_PER_SIDE
STRATEGIES = list(STRATEGY_CLASSES)
WORKERS = max(1, (os.cpu_count() or 3) - 2)

# --- Reglas pre-registradas ---
SIZE_REF = 2 * COST                       # E12 igual al costo de ida y vuelta -> 1x (15 USDT)
SIZE_MIN_USDT, SIZE_MAX_USDT = 5.0, 2 * NOTIONAL_USDT
META_MIN_TRAIN = 300
META_PARAMS = {"n_estimators": 200, "learning_rate": 0.03, "num_leaves": 7, "max_depth": 3, "min_child_samples": 40,
               "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "reg_lambda": 5.0, "random_state": 0,
               "n_jobs": 1, "verbose": -1}
RANDOM_REPLICAS = 20
N_ARMS = 4                                # brazos que se comparan con BASE
ALPHA = wf.ALPHA / N_ARMS

SIMS = {"base": {}, "limit": {"tp_limit": True}}
ARMS = {
    "BASE": {"sim": "base", "meta": False, "size": False, "desc": "bot actual (1 h con filtros de config.py)"},
    "META": {"sim": "base", "meta": True, "size": False, "desc": "filtro LightGBM (meta-etiquetado)"},
    "TAMANO": {"sim": "base", "meta": False, "size": True, "desc": "nocional proporcional a la E de 12 meses (5-30 USDT)"},
    "LIMIT": {"sim": "limit", "meta": False, "size": False, "desc": "TP con orden LIMIT"},
    "TODO": {"sim": "limit", "meta": True, "size": True, "desc": "LIMIT + META + TAMANO"},
}
CANDLE_FEATURES = ["ret_1", "ret_24", "ret_168", "btc_ret_24", "btc_ret_168", "vol_ratio", "er_24", "imb", "imb_z",
                   "cvd_24", "vol_rel", "dd_168", "dow"]
TRADE_FEATURES = ["risk_pct", "b", "c_r", "e3", "e12", "strategy"]
FEATURES = CANDLE_FEATURES + TRADE_FEATURES


class _ArmFS(SF.FilteredFS):
    """FilteredFS (riesgo minimo y co-senal de config.py, como el bot) con las reglas de simulacion del brazo y un filtro
    de entradas extra (el de META en cada mes de prueba). Con SIMS["base"] y sin extra es exactamente FilteredFS."""

    def __init__(self, fs, open_time, others, sim_kw: dict):
        super().__init__(fs, open_time, others, CANDLE_MS, ENTRY_MIN_RISK_PCT, COSIGNAL_CANDLES)
        self.sim_kw, self.extra = sim_kw, None

    def simulate(self, strategy, w, m, first=0, **kw):
        mask = self.cosignal_mask(strategy, w, m, first) if self.cosignal else None
        if self.extra is not None:
            mask = self.extra if mask is None else mask & self.extra
        return self.fs.simulate(strategy, w, m, first=first, min_risk=self.min_risk, entry_mask=mask, **self.sim_kw, **kw)


class _TestOnly(wf.PairEvaluator):
    """PairEvaluator sin la rejilla: solo para repetir los meses de prueba (test_trades) con los (n, k) ya elegidos."""

    def __init__(self, fs, open_time, strategy):
        self.fs, self.open_time, self.strategy, self.sims = fs, open_time, strategy, {}


def _pair_fs(sim: str, symbol: str):
    set_interval(INTERVAL)
    fs, ot = wf._symbol_data(symbol, INTERVAL)
    others = [wf._symbol_data(o, INTERVAL) for o in ACTIVE_ROSTER if o != symbol] if COSIGNAL_CANDLES else []
    return fs, ot, _ArmFS(fs, ot, others, SIMS[sim])


def phase1(task):
    """Walk-forward de una pareja con las reglas de simulacion `sim`: meses, (n, k) elegidos, interruptor de momentum y
    operaciones en sombra (antes del interruptor) con su mes y sus niveles."""
    sim, symbol, strategy = task
    t0 = time.perf_counter()
    fs, ot, afs = _pair_fs(sim, symbol)
    periods = wf.build_periods(ot, wf.TRAIN_MONTHS, None, CANDLE_MS)
    ev = wf.PairEvaluator(afs, ot, strategy)
    dev_rows, de, dx, dp, open_until = wf.run_folds(ev, periods["dev"])
    hold_rows, he, hx, hp, _ = wf.run_folds(ev, periods["holdout"], open_until)
    on = (SF.momentum_gate(dev_rows, [], MOMENTUM_MONTHS)
          + SF.momentum_gate(hold_rows, [r["pnl"] for r in dev_rows], MOMENTUM_MONTHS))
    folds = [{"mes": r["prueba"], "kind": f["kind"], "combo": [r["n"], r["k"]] if r["opera"] else None,
              "a": ev.idx(f["test"][0]), "b": ev.idx(f["test"][1]), "limit": ev.idx(f["limit"]),
              "ops": r["ops"], "pnl": r["pnl"], "on": o}
             for f, r, o in zip(periods["dev"] + periods["holdout"], dev_rows + hold_rows, on)]
    entry, exit_, pnl = np.concatenate([de, he]), np.concatenate([dx, hx]), np.concatenate([dp, hp])
    fold = np.repeat(np.arange(len(folds)), [f["ops"] for f in folds])
    levels = [fs.entry_levels(strategy, folds[j]["combo"][0], int(i)) for i, j in zip(entry, fold)]
    return {"sim": sim, "symbol": symbol, "strategy": strategy, "folds": folds,
            "trades": {"entry": entry.tolist(), "exit": exit_.tolist(), "pnl": pnl.tolist(), "fold": fold.tolist(),
                       "price": [lv[0] for lv in levels], "tp": [lv[1] for lv in levels], "sl": [lv[2] for lv in levels]},
            "segundos": round(time.perf_counter() - t0, 1)}


@lru_cache(maxsize=None)
def candle_features(symbol: str) -> np.ndarray:
    """Variables de cada vela, calculadas solo con velas hasta su cierre (las mismas que veria el bot en vivo)."""
    d = load_history(symbol, interval=INTERVAL)
    btc = load_history("BTCUSDT", interval=INTERVAL)
    c, h, v, ot = d["close"], d["high"], d["volume"], d["open_time"].to_numpy(np.int64)
    btc_c = pd.Series(btc["close"].to_numpy(float), index=btc["open_time"].to_numpy(np.int64))
    bc = pd.Series(btc_c.reindex(ot).to_numpy(), index=d.index)
    r = c.pct_change()
    with np.errstate(divide="ignore", invalid="ignore"):
        imb = 2 * d["taker_buy"] / v - 1
        f = pd.DataFrame({
            "ret_1": r, "ret_24": c / c.shift(24) - 1, "ret_168": c / c.shift(168) - 1,
            "btc_ret_24": bc / bc.shift(24) - 1, "btc_ret_168": bc / bc.shift(168) - 1,
            "vol_ratio": r.rolling(24).std() / r.rolling(168).std(),
            "er_24": (c - c.shift(24)).abs() / c.diff().abs().rolling(24).sum(),
            "imb": imb, "imb_z": (imb - imb.rolling(96).mean()) / imb.rolling(96).std(),
            "cvd_24": (2 * d["taker_buy"] - v).rolling(24).sum() / v.rolling(24).sum(),
            "vol_rel": v / v.rolling(24).mean(), "dd_168": c / h.rolling(168).max() - 1,
            "dow": ((ot + CANDLE_MS) // DAY_MS + 3) % 7})
    return f[CANDLE_FEATURES].replace([np.inf, -np.inf], np.nan).to_numpy(float)


def pair_edge(folds: list, j: int, months: int) -> float:
    """E por operacion (fraccion del nocional) en sombra de los `months` meses anteriores al mes j; NaN sin operaciones."""
    prior = folds[max(0, j - months):j]
    ops = sum(f["ops"] for f in prior)
    return sum(f["pnl"] for f in prior) / ops / NOTIONAL_USDT if ops else np.nan


def size_mult(e12: float) -> float:
    """Regla de TAMANO: 0 si E12 <= 0; si no, 15 * E12 / costo de ida y vuelta, entre 5 y 30 USDT (en multiplos de 15)."""
    if not e12 > 0:
        return 0.0
    return float(np.clip(NOTIONAL_USDT * e12 / SIZE_REF, SIZE_MIN_USDT, SIZE_MAX_USDT)) / NOTIONAL_USDT


def feature_rows(symbol: str, strategy: str, folds: list, j: int, idx, price, tp, sl) -> pd.DataFrame:
    """Matriz de variables de unas senales (velas idx) del mes j de una pareja."""
    price, tp, sl = (np.asarray(x, float) for x in (price, tp, sl))
    risk = (price - sl) / price
    with np.errstate(divide="ignore", invalid="ignore"):
        x = pd.DataFrame(candle_features(symbol)[np.asarray(idx, np.int64)], columns=CANDLE_FEATURES)
        x["risk_pct"] = risk
        x["b"] = (tp - price) / (price - sl)
        x["c_r"] = 2 * COST / risk
    x["e3"] = pair_edge(folds, j, 3)
    x["e12"] = pair_edge(folds, j, 12)
    x["strategy"] = STRATEGIES.index(strategy)
    return x


def p_star(x: pd.DataFrame) -> np.ndarray:
    return ((1 + x["c_r"]) / (1 + x["b"])).to_numpy(float)


def month_start_ms(month: str) -> int:
    return int(pd.Timestamp(month + "-01", tz="UTC").value // 10**6)


def train_models(results: list) -> tuple:
    """Un LightGBM por mes (desarrollo y validacion final) con las operaciones en sombra de todas las parejas que ya
    cerraron antes de que empiece ese mes. Devuelve (modelos por mes, tabla de operaciones con variables y etiqueta)."""
    import lightgbm as lgb
    parts = []
    for res in results:
        t, folds = res["trades"], res["folds"]
        if not t["entry"]:
            continue
        ot = wf._symbol_data(res["symbol"], INTERVAL)[1]
        fold = np.asarray(t["fold"])
        for j in np.unique(fold):
            k = np.flatnonzero(fold == j)
            x = feature_rows(res["symbol"], res["strategy"], folds, int(j), np.asarray(t["entry"])[k],
                             np.asarray(t["price"])[k], np.asarray(t["tp"])[k], np.asarray(t["sl"])[k])
            x["_label"] = (np.asarray(t["pnl"])[k] > 0).astype(int)
            x["_pnl"] = np.asarray(t["pnl"])[k]
            x["_known_ms"] = ot[np.asarray(t["exit"])[k]] + CANDLE_MS
            x["_mes"] = folds[j]["mes"]
            x["_on"] = folds[j]["on"]
            parts.append(x)
    table = pd.concat(parts, ignore_index=True)
    months = sorted({f["mes"] for res in results for f in res["folds"]})
    models = {}
    for month in months:
        train = table[table["_known_ms"] <= month_start_ms(month)]
        if len(train) < META_MIN_TRAIN or train["_label"].nunique() < 2:
            continue
        model = lgb.LGBMClassifier(**META_PARAMS)
        model.fit(train[FEATURES], train["_label"], categorical_feature=["strategy"])
        models[month] = model
    return models, table


def meta_diagnostics(models: dict, table: pd.DataFrame) -> dict:
    """Evaluacion senal a senal: AUC fuera de muestra y PnL de las operaciones en sombra conservadas frente a las
    descartadas (cada una juzgada con el modelo de su mes, que no la vio)."""
    from sklearn.metrics import roc_auc_score
    rows = table[table["_mes"].isin(list(models))].copy()
    if rows.empty:
        return {}
    rows["_p"] = np.nan
    for month, idx in rows.groupby("_mes").groups.items():
        rows.loc[idx, "_p"] = models[month].predict_proba(rows.loc[idx, FEATURES])[:, 1]
    keep = rows["_p"].to_numpy() > p_star(rows)
    pnl = rows["_pnl"].to_numpy()
    half = lambda sel: {"ops": int(sel.sum()), "pnl": round(float(pnl[sel].sum()), 2),
                        "pnl_op_pct": round(100 * float(pnl[sel].mean()) / NOTIONAL_USDT, 3) if sel.any() else 0.0,
                        "win_rate": round(100 * float((pnl[sel] > 0).mean()), 1) if sel.any() else 0.0}
    return {"meses_con_modelo": len(models), "primer_mes_con_modelo": min(models), "operaciones_juzgadas": int(len(rows)),
            "auc_oos": round(float(roc_auc_score(rows["_label"], rows["_p"])), 3),
            "conservadas": half(keep), "descartadas": half(~keep)}


_MODELS = {}


def _init_worker(models):
    global _MODELS
    _MODELS = models


def phase3(task):
    """Repite los meses de prueba de una pareja con el filtro META (y con RANDOM_REPLICAS filtros al azar que omiten la
    misma proporcion de senales en cada mes). Devuelve las operaciones de cada variante, con su mes."""
    sim, symbol, strategy, folds = task
    fs, ot, afs = _pair_fs(sim, symbol)
    ev = _TestOnly(afs, ot, strategy)
    models = _MODELS[sim]
    variants = ["meta"] + [f"azar{s}" for s in range(RANDOM_REPLICAS)]
    out = {v: {"entry": [], "exit": [], "pnl": [], "fold": []} for v in variants}
    open_until = {v: -1 for v in variants}
    skipped = candidates = 0
    for j, f in enumerate(folds):
        if f["combo"] is None:
            continue
        w, m = f["combo"]
        first = max(0, f["a"] - wf.preseed_candles(w))
        cand = fs.buy_indices(strategy, w, m, first, f["b"])
        cand = cand[cand >= f["a"]]
        if afs.cosignal:
            cand = cand[afs.cosignal_mask(strategy, w, m, first)[cand]]
        take = np.ones(len(cand), bool)
        model = models.get(f["mes"])
        if model is not None and len(cand):
            lv = np.array([fs.entry_levels(strategy, w, int(i)) for i in cand])
            x = feature_rows(symbol, strategy, folds, j, cand, lv[:, 0], lv[:, 1], lv[:, 2])
            take = model.predict_proba(x[FEATURES])[:, 1] > p_star(x)
            skipped += int((~take).sum())
            candidates += len(cand)
        q = float((~take).mean()) if len(cand) else 0.0
        for v in variants:
            if v == "meta":
                keep = take
            else:
                rng = np.random.default_rng([int(v[4:]), j, ACTIVE_ROSTER.index(symbol), STRATEGIES.index(strategy)])
                keep = rng.random(len(cand)) >= q
            extra = np.ones(fs.n, bool)
            extra[cand[~keep]] = False
            afs.extra = extra
            e, x_, p, open_until[v] = ev.test_trades((w, m), f["a"], f["b"], f["limit"], open_until[v])
            afs.extra = None
            for key, val in (("entry", e), ("exit", x_), ("pnl", p), ("fold", np.full(len(p), j))):
                out[v][key].extend(np.asarray(val).tolist())
    return {"sim": sim, "symbol": symbol, "strategy": strategy, "variants": out,
            "senales_juzgadas": candidates, "senales_omitidas": skipped}


def arm_parts(arm: str, p1: dict, p3: dict, variant: str = "meta") -> list:
    """Operaciones OOS de un brazo por pareja, despues del interruptor de momentum y del tamano: lista de dicts con
    entrada_t, salida_t, pnl, nocional y kind (dev/hold)."""
    spec = ARMS[arm]
    parts = []
    for symbol in ACTIVE_ROSTER:
        ot = wf._symbol_data(symbol, INTERVAL)[1]
        for st in STRATEGIES:
            res = p1[(spec["sim"], symbol, st)]
            folds = res["folds"]
            t = p3[(spec["sim"], symbol, st)]["variants"][variant] if spec["meta"] else res["trades"]
            fold = np.asarray(t["fold"], np.int64)
            on = np.array([folds[j]["on"] for j in fold], bool) if len(fold) else np.zeros(0, bool)
            mult = (np.array([size_mult(pair_edge(folds, int(j), MOMENTUM_MONTHS)) for j in fold])
                    if spec["size"] and len(fold) else np.ones(len(fold)))
            keep = on & (mult > 0)
            fold = fold[keep]
            parts.append({"symbol": symbol, "strategy": st,
                          "entrada_t": ot[np.asarray(t["entry"], np.int64)[keep]],
                          "salida_t": ot[np.asarray(t["exit"], np.int64)[keep]],
                          "pnl": np.asarray(t["pnl"], float)[keep] * mult[keep],
                          "nocional": NOTIONAL_USDT * mult[keep],
                          "kind": np.array([folds[j]["kind"] for j in fold], dtype=object)})
    return parts


def _select(parts: list, kind: str, strategy: str = None) -> dict:
    sel = [p for p in parts if strategy is None or p["strategy"] == strategy]
    k = [p["kind"] == kind for p in sel]
    cat = lambda key: np.concatenate([p[key][m] for p, m in zip(sel, k)]) if sel else np.zeros(0)
    return {key: cat(key) for key in ("entrada_t", "salida_t", "pnl", "nocional")}


def _daily(t: dict) -> pd.Series:
    return pd.Series(t["pnl"]).groupby(np.asarray(t["salida_t"]) // DAY_MS).sum()


def _t_test(x: np.ndarray) -> tuple:
    if len(x) > 1 and x.std(ddof=1) > 0:
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        return float(t), float(sp_stats.t.sf(t, len(x) - 1))
    return 0.0, 1.0


def stats(t: dict) -> dict:
    """Metricas de un conjunto de operaciones: PnL neto, PnL por USDT invertido, MDD de la curva (por fecha de salida) y
    prueba t de una cola sobre el PnL por dia."""
    pnl = t["pnl"]
    if len(pnl) == 0:
        return {"ops": 0, "win_rate": 0.0, "pnl": 0.0, "pnl_por_100_usdt": 0.0, "nocional_medio": 0.0, "mdd": 0.0,
                "meses_pos_pct": 0.0, "t_dia": 0.0, "p_valor": 1.0}
    cum = np.cumsum(pnl[np.argsort(t["salida_t"], kind="stable")])
    mdd = float((np.maximum.accumulate(np.maximum(cum, 0)) - cum).max())
    tt, p = _t_test(_daily(t).to_numpy())
    month = pd.to_datetime(t["entrada_t"], unit="ms", utc=True).strftime("%Y-%m")
    by_month = pd.Series(pnl).groupby(np.asarray(month)).sum()
    return {"ops": int(len(pnl)), "win_rate": round(100.0 * float((pnl > 0).mean()), 1), "pnl": round(float(pnl.sum()), 2),
            "pnl_por_100_usdt": round(100.0 * float(pnl.sum() / t["nocional"].sum()), 3),
            "nocional_medio": round(float(t["nocional"].mean()), 2), "mdd": round(mdd, 2),
            "meses_pos_pct": round(100.0 * float((by_month > 0).mean()), 1), "t_dia": round(tt, 2),
            "p_valor": float(f"{p:.3g}")}


def paired(arm: dict, base: dict) -> dict:
    """Diferencia pareada brazo - BASE: PnL sumado por dia de salida (dias con operaciones en alguno de los dos)."""
    a, b = _daily(arm), _daily(base)
    days = a.index.union(b.index)
    d = (a.reindex(days, fill_value=0.0) - b.reindex(days, fill_value=0.0)).to_numpy()
    t, p = _t_test(d)
    return {"delta_pnl": round(float(d.sum()), 2), "dias": int(len(d)), "t_dia": round(t, 2), "p_valor": float(f"{p:.3g}")}


def summarize(arm: str, p1: dict, p3: dict, base_parts: list, strategy: str = None) -> dict:
    parts = arm_parts(arm, p1, p3)
    dev, hold = _select(parts, "dev", strategy), _select(parts, "holdout", strategy)
    bdev, bhold = _select(base_parts, "dev", strategy), _select(base_parts, "holdout", strategy)
    entry = {"oos": stats(dev), "validacion_final": stats(hold)}
    if arm == "BASE":
        return entry
    entry["vs_base"] = {"oos": paired(dev, bdev), "validacion_final": paired(hold, bhold)}
    if ARMS[arm]["meta"]:
        rnd = [paired(_select(arm_parts(arm, p1, p3, f"azar{s}"), "dev", strategy), bdev)["delta_pnl"]
               for s in range(RANDOM_REPLICAS)]
        entry["azar"] = {"delta_pnl_media": round(float(np.mean(rnd)), 2),
                         "delta_pnl_p95": round(float(np.percentile(rnd, 95)), 2),
                         "supera_al_pct_del_azar": round(100.0 * float(np.mean(np.array(rnd) < entry["vs_base"]["oos"]["delta_pnl"])), 1)}
    return entry


def decide(arm: str, e: dict) -> dict:
    """Criterios pre-registrados: si el brazo mejora a BASE y si es rentable por si solo."""
    fails = []
    d = e["vs_base"]["oos"]
    if d["delta_pnl"] <= 0:
        fails.append("delta PnL <= 0")
    if d["p_valor"] >= ALPHA:
        fails.append(f"p = {d['p_valor']:.3g} >= {ALPHA:.4g}")
    if e["vs_base"]["validacion_final"]["delta_pnl"] < 0:
        fails.append("empeora en la validacion final")
    if "azar" in e and d["delta_pnl"] <= e["azar"]["delta_pnl_p95"]:
        fails.append("no supera al p95 del azar")
    o, h = e["oos"], e["validacion_final"]
    alone = (o["ops"] >= wf.MIN_TRADES_OOS and o["pnl"] > 0 and o["meses_pos_pct"] >= 100 * wf.MIN_POSITIVE_FOLDS
             and o["p_valor"] < ALPHA and h["pnl"] >= 0)
    return {"mejora_pnl": not fails, "motivo": "; ".join(fails) or "mejora", "rentable_por_si_solo": alone}


def check_base(p1: dict) -> list:
    """BASE tiene que dar las mismas operaciones OOS de desarrollo que ml_results.json (mismo protocolo y filtros)."""
    with open(BASE_FILE, encoding="utf-8") as f:
        ref = json.load(f)
    diffs = []
    for symbol in ACTIVE_ROSTER:
        for st in STRATEGIES:
            res = p1[("base", symbol, st)]
            fold = np.asarray(res["trades"]["fold"], np.int64)
            keep = np.array([res["folds"][j]["on"] and res["folds"][j]["kind"] == "dev" for j in fold], bool)
            ops, pnl = int(keep.sum()), float(np.asarray(res["trades"]["pnl"])[keep].sum()) if len(keep) else 0.0
            r = ref[symbol][st]["oos"]
            if ops != r["trades"] or abs(pnl - r["pnl"]) > 1e-3:
                diffs.append(f"{symbol} {st}: {ops} ops {pnl:+.4f} frente a {r['trades']} ops {r['pnl']:+.4f}")
    return diffs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t_start = time.perf_counter()
    tasks = [(sim, s, st) for sim in SIMS for s in ACTIVE_ROSTER for st in STRATEGIES]
    print(f"[EXPERIMENTOS V2] Velas de {INTERVAL}. Fase 1: {len(tasks)} walk-forwards ({WORKERS} procesos).")
    p1 = {}
    with Pool(processes=WORKERS) as pool:
        for k, res in enumerate(pool.imap_unordered(phase1, tasks), 1):
            p1[(res["sim"], res["symbol"], res["strategy"])] = res
            print(f"  [{k}/{len(tasks)}] {res['sim']:<5} {res['symbol']:<9} {res['strategy']:<17} {res['segundos']} s",
                  flush=True)

    diffs = check_base(p1)
    print("[EXPERIMENTOS V2] " + ("✅ BASE reproduce ml_results.json (OOS de desarrollo)." if not diffs else
                                  "⚠️ BASE no coincide con ml_results.json:\n    " + "\n    ".join(diffs)))

    print("[EXPERIMENTOS V2] Fase 2: modelos LightGBM mensuales (purgados).")
    models, diagnostics = {}, {}
    for sim in sorted({a["sim"] for a in ARMS.values() if a["meta"]}):
        models[sim], table = train_models([r for key, r in p1.items() if key[0] == sim])
        diagnostics[sim] = meta_diagnostics(models[sim], table)
        print(f"  {sim}: {len(models[sim])} modelos; diagnostico {json.dumps(diagnostics[sim], ensure_ascii=False)}")

    print("[EXPERIMENTOS V2] Fase 3: meses de prueba con el filtro META y sus replicas al azar.")
    tasks3 = [(sim, s, st, p1[(sim, s, st)]["folds"]) for sim in models for s in ACTIVE_ROSTER for st in STRATEGIES]
    p3 = {}
    with Pool(processes=WORKERS, initializer=_init_worker, initargs=(models,)) as pool:
        for res in pool.imap_unordered(phase3, tasks3):
            p3[(res["sim"], res["symbol"], res["strategy"])] = res
    for sim in models:
        judged = sum(r["senales_juzgadas"] for k, r in p3.items() if k[0] == sim)
        dropped = sum(r["senales_omitidas"] for k, r in p3.items() if k[0] == sim)
        diagnostics[sim]["senales_juzgadas_en_vivo"] = judged
        diagnostics[sim]["senales_omitidas_pct"] = round(100.0 * dropped / judged, 1) if judged else 0.0

    base_parts = arm_parts("BASE", p1, p3)
    out = {"_protocolo": {
        "preregistro": "2026-10-23, antes de ver resultados (ver docstring de experiments_v2.py)",
        "generado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vela": INTERVAL, "filtros": {"riesgo_minimo_pct": ENTRY_MIN_RISK_PCT, "cosenal_velas": COSIGNAL_CANDLES,
                                      "momentum_meses": MOMENTUM_MONTHS},
        "brazos": {a: ARMS[a]["desc"] for a in ARMS},
        "tamano": f"nocional = 15 * E12 / {SIZE_REF:.4f}, entre {SIZE_MIN_USDT:g} y {SIZE_MAX_USDT:g} USDT; 0 si E12 <= 0",
        "meta": {"min_entrenamiento": META_MIN_TRAIN, "lightgbm": META_PARAMS, "variables": FEATURES,
                 "regla": "toma si p > (1 + c_R) / (1 + b)", "replicas_azar": RANDOM_REPLICAS},
        "prueba": f"pareada contra BASE, t de una cola sobre la diferencia diaria; alfa = 0.05 / {N_ARMS} = {ALPHA}",
        "costos": "0.12 % por lado (0.10 % comision + 0.02 % deslizamiento); LIMIT: 0.10 % en la pata del TP",
        "base_reproduce_ml_results": not diffs, "diferencias_base": diffs},
        "diagnostico_meta": diagnostics}
    for arm in ARMS:
        e = summarize(arm, p1, p3, base_parts)
        if arm != "BASE":
            e.update(decide(arm, e))
        e["por_estrategia"] = {st: summarize(arm, p1, p3, base_parts, st) for st in STRATEGIES}
        out[arm] = e

    with open(RESULTS_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("\n" + "=" * 140)
    print(f"{'Brazo':<8}| {'OOS (20 parejas, desarrollo)':<58}| {'vs BASE':<26}| {'Val. final':<20}| Estado")
    print(f"{'':<8}| {'ops   WR %   PnL USDT  PnL/100 USDT  MDD    meses+  t/dia':<58}| {'dPnL     t     p':<26}| "
          f"{'ops   PnL    dPnL':<20}|")
    print("-" * 140)
    for arm, e in out.items():
        if arm.startswith("_") or arm == "diagnostico_meta":
            continue
        o, h = e["oos"], e["validacion_final"]
        vs = e.get("vs_base")
        cmp_ = f"{vs['oos']['delta_pnl']:>+7.2f} {vs['oos']['t_dia']:>+5.2f} {vs['oos']['p_valor']:<8.3g}" if vs else ""
        hd = f"{vs['validacion_final']['delta_pnl']:>+6.2f}" if vs else ""
        state = "" if arm == "BASE" else ("MEJORA" if e["mejora_pnl"] else f"no mejora ({e['motivo']})")
        print(f"{arm:<8}| {o['ops']:>4} {o['win_rate']:>5.1f} {o['pnl']:>+9.2f} {o['pnl_por_100_usdt']:>+10.3f} "
              f"{o['mdd']:>8.2f} {o['meses_pos_pct']:>6.0f}% {o['t_dia']:>+6.2f} | {cmp_:<24} | {h['ops']:>3} "
              f"{h['pnl']:>+7.2f} {hd:<7} | {state}")
    print("=" * 140)
    print(f"\n[EXPERIMENTOS V2] ✅ {time.perf_counter() - t_start:.0f} s. Resultado: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
