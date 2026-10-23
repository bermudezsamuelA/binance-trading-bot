# meta_filter.py
"""
Meta-etiquetado EN SOMBRA (sugerencia 3; doc/agente-rl-y-esperanza-positiva.md, fase 5). Un LightGBM estima la
probabilidad de que cada BUY de las estrategias termine con PnL neto > 0 y anota si el filtro lo habria tomado
(p > p* = (1 + c_R) / (1 + b)). NO bloquea ninguna operacion: solo escribe orders/meta_signals.csv para juntar una
muestra prospectiva. En experiments_v2.py el brazo META gano +18.5 USDT frente a BASE (p = 0.186, no significativo),
con AUC fuera de muestra 0.625; por eso se mide en vivo antes de dejarlo decidir.

Las variables y la regla son exactamente las de experiments_v2.py (candle_feature_frame es la misma funcion en el
backtest y en vivo). El modelo vivo se entrena con TODAS las operaciones en sombra del walk-forward (BASE) que ya
cerraron, con los mismos hiperparametros que el experimento, y se guarda con su fecha de corte.

Entrenar (desde binance-research, sin red, con los datos de data/ descargados):
  .venv\\Scripts\\python meta_filter.py --train
Resultado: machine_learning_strategies/meta_model.txt (LightGBM) y meta_model.json (variables, corte, resumen).
"""
import datetime
import json
import os
from collections import deque

import numpy as np
import pandas as pd

ML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "machine_learning_strategies")
MODEL_FILE = os.path.join(ML_DIR, "meta_model.txt")
MODEL_META_FILE = os.path.join(ML_DIR, "meta_model.json")

DAY_MS = 86_400_000
CANDLE_FEATURES = ["ret_1", "ret_24", "ret_168", "btc_ret_24", "btc_ret_168", "vol_ratio", "er_24", "imb", "imb_z",
                   "cvd_24", "vol_rel", "dd_168", "dow"]
TRADE_FEATURES = ["risk_pct", "b", "c_r", "e3", "e12", "strategy"]
FEATURES = CANDLE_FEATURES + TRADE_FEATURES
# Velas que necesita la variable con la ventana mas larga (ret_168 y la volatilidad de 168: 169 velas) mas margen
BUFFER_CANDLES = 240
BTC = "BTCUSDT"


def candle_feature_frame(d: pd.DataFrame, btc: pd.DataFrame, candle_ms: int) -> pd.DataFrame:
    """Variables de cada vela de `d` (open_time, close, high, volume, taker_buy), calculadas solo con velas hasta su
    cierre. `btc`: velas de BTC (open_time, close); se alinean por open_time. Es la funcion que usan el backtest
    (experiments_v2.candle_features) y el filtro en vivo (MetaFilter), para que las dos vean lo mismo."""
    c, h, v = d["close"].astype(float), d["high"].astype(float), d["volume"].astype(float)
    tb = d["taker_buy"].astype(float)
    ot = d["open_time"].to_numpy(np.int64)
    btc_c = pd.Series(btc["close"].to_numpy(float), index=btc["open_time"].to_numpy(np.int64))
    btc_c = btc_c[~btc_c.index.duplicated(keep="last")]
    bc = pd.Series(btc_c.reindex(ot).to_numpy(), index=d.index)
    r = c.pct_change()
    with np.errstate(divide="ignore", invalid="ignore"):
        imb = 2 * tb / v - 1
        f = pd.DataFrame({
            "ret_1": r, "ret_24": c / c.shift(24) - 1, "ret_168": c / c.shift(168) - 1,
            "btc_ret_24": bc / bc.shift(24) - 1, "btc_ret_168": bc / bc.shift(168) - 1,
            "vol_ratio": r.rolling(24).std() / r.rolling(168).std(),
            "er_24": (c - c.shift(24)).abs() / c.diff().abs().rolling(24).sum(),
            "imb": imb, "imb_z": (imb - imb.rolling(96).mean()) / imb.rolling(96).std(),
            "cvd_24": (2 * tb - v).rolling(24).sum() / v.rolling(24).sum(),
            "vol_rel": v / v.rolling(24).mean(), "dd_168": c / h.rolling(168).max() - 1,
            "dow": ((ot + candle_ms) // DAY_MS + 3) % 7})
    return f[CANDLE_FEATURES].replace([np.inf, -np.inf], np.nan)


def trade_features(entry, tp, sl, cost_per_side: float) -> dict:
    """Variables de la geometria de la operacion: riesgo en % del precio, b = TP/SL y costo de ida y vuelta en R."""
    entry, tp, sl = float(entry), float(tp), float(sl)
    risk = (entry - sl) / entry
    with np.errstate(divide="ignore", invalid="ignore"):
        return {"risk_pct": risk, "b": (tp - entry) / (entry - sl) if entry != sl else np.nan,
                "c_r": 2 * cost_per_side / risk if risk else np.nan}


def p_star(b, c_r):
    """Probabilidad minima para que la operacion tenga E > 0: p* = (1 + c_R) / (1 + b)."""
    return (1 + np.asarray(c_r, float)) / (1 + np.asarray(b, float))


def fold_edge(rows: list, columns: list, month: str, months: int, notional: float) -> float:
    """E por operacion (fraccion del nocional) en sombra de los `months` meses del walk-forward anteriores a `month`
    (YYYY-MM), con las filas de ml_results.json (pliegues + pliegues_validacion). NaN sin operaciones. Es pair_edge
    de experiments_v2.py: alli los pliegues son los meses anteriores al de prueba; aqui, los anteriores al mes en curso."""
    if not rows or "ops_sombra" not in columns:
        return np.nan
    m, o, p = columns.index("prueba"), columns.index("ops_sombra"), columns.index("pnl_sombra")
    prior = [r for r in rows if r[m] < month][-months:]
    ops = sum(r[o] for r in prior)
    return sum(r[p] for r in prior) / ops / notional if ops else np.nan


class MetaFilter:
    """Filtro en sombra para el bot en vivo. Guarda las ultimas velas cerradas de cada moneda del roster (y de BTC),
    calcula las variables con candle_feature_frame al llegar un BUY y anota p, p* y la decision. Si la vela de BTC
    de ese mismo open_time aun no llego, espera a que llegue (o a la vela siguiente de la moneda; entonces las
    variables de BTC quedan vacias, como un hueco del backtest)."""

    def __init__(self, interval: str, candle_ms: int, cost_per_side: float, notional: float,
                 model_file: str = MODEL_FILE, meta_file: str = MODEL_META_FILE, model=None, info: dict = None):
        self.interval, self.candle_ms, self.cost, self.notional = interval, candle_ms, cost_per_side, notional
        self.candles = {}
        self.last_open_time = {}
        self.pending = []
        self.warned_taker = False
        self.model, self.info, self.status = model, info or {}, "activo"
        if model is None:
            self.model, self.info, self.status = self._load(model_file, meta_file)

    def _load(self, model_file, meta_file):
        if not (os.path.exists(model_file) and os.path.exists(meta_file)):
            return None, {}, "sin modelo (python meta_filter.py --train)"
        try:
            with open(meta_file, encoding="utf-8") as f:
                info = json.load(f)
            if info.get("vela") != self.interval:
                return None, info, f"modelo de velas de {info.get('vela')} y el bot usa {self.interval}: reentrenar"
            if info.get("variables") != FEATURES:
                return None, info, "el modelo tiene otras variables: reentrenar"
            import lightgbm as lgb
            return lgb.Booster(model_file=model_file), info, "activo"
        except Exception as e:  # el filtro es solo de diagnostico: nunca debe tumbar al bot
            return None, {}, f"no se pudo cargar ({e})"

    @property
    def enabled(self) -> bool:
        return self.model is not None

    def describe(self) -> str:
        if not self.enabled:
            return f"Meta-etiquetado en sombra: {self.status}."
        return (f"Meta-etiquetado en sombra: modelo entrenado hasta {self.info.get('entrenado_hasta')} con "
                f"{self.info.get('operaciones')} operaciones (no bloquea; anota en orders/meta_signals.csv).")

    def add_candle(self, symbol: str, market_data: dict):
        """Una vela cerrada de cualquier moneda del roster (precarga, relleno de huecos o WebSocket)."""
        open_time = market_data.get("open_time")
        if open_time is None:
            return
        open_time = int(open_time)
        if open_time <= self.last_open_time.get(symbol, -1):
            return
        self.last_open_time[symbol] = open_time
        if market_data.get("taker_buy") is None and not self.warned_taker:
            self.warned_taker = True
            print("[META] ⚠️ Las velas llegan sin taker_buy: imb, imb_z y cvd_24 quedan vacias.")
        buf = self.candles.setdefault(symbol, deque(maxlen=BUFFER_CANDLES))
        buf.append((open_time, float(market_data.get("close", np.nan)), float(market_data.get("high", np.nan)),
                    float(market_data.get("volume", np.nan)), float(market_data.get("taker_buy", np.nan))))

    def on_buy(self, journal: dict, fold_rows: list, columns: list):
        """Un BUY de la estrategia (abierto o bloqueado por los filtros) que se juzgara cuando este su vela de BTC."""
        if not self.enabled or journal.get("open_time") is None:
            return
        month = datetime.datetime.fromtimestamp(int(journal["open_time"]) / 1000, datetime.timezone.utc).strftime("%Y-%m")
        name, strategies = journal.get("strategy"), self.info.get("estrategias") or []
        self.pending.append({**journal,
                             "e3": fold_edge(fold_rows, columns, month, 3, self.notional),
                             "e12": fold_edge(fold_rows, columns, month, 12, self.notional),
                             "strategy_idx": strategies.index(name) if name in strategies else np.nan})

    def _frame(self, symbol: str) -> pd.DataFrame:
        cols = ["open_time", "close", "high", "volume", "taker_buy"]
        return pd.DataFrame(list(self.candles.get(symbol, [])), columns=cols)

    def pop_ready(self) -> list:
        """Registros de los BUY pendientes cuya vela de BTC ya llego (o que ya no la esperan), listos para el CSV."""
        ready, still = [], []
        for item in self.pending:
            t, symbol = int(item["open_time"]), str(item["symbol"]).upper()
            btc_last = self.last_open_time.get(BTC, -1)
            if symbol != BTC and btc_last < t and self.last_open_time.get(symbol, -1) <= t:
                still.append(item)
                continue
            ready.append(self.judge(item))
        self.pending = still
        return ready

    def judge(self, item: dict) -> dict:
        symbol = str(item["symbol"]).upper()
        own = self._frame(symbol)
        feats = candle_feature_frame(own, self._frame(BTC), self.candle_ms)
        row = feats[own["open_time"].to_numpy(np.int64) == int(item["open_time"])]
        x = row.iloc[[-1]].reset_index(drop=True) if len(row) else pd.DataFrame([{k: np.nan for k in CANDLE_FEATURES}])
        geo = trade_features(item["entry_price"], item["take_profit"], item["stop_loss"], self.cost)
        for k, val in {**geo, "e3": item["e3"], "e12": item["e12"], "strategy": item["strategy_idx"]}.items():
            x[k] = val
        p = float(self.model.predict(x[FEATURES])[0])
        p_min = float(p_star(geo["b"], geo["c_r"]))
        return {"logged_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "symbol": symbol, "open_time": int(item["open_time"]), "strategy": item.get("strategy"),
                "bot_decision": item.get("decision"), "meta_p": round(p, 4), "meta_p_min": round(p_min, 4),
                "meta_decision": "tomaria" if p > p_min else "omitiria",
                "model_trained_until": self.info.get("entrenado_hasta"), "market": item.get("market"),
                **{("strategy_idx" if k == "strategy" else k): (None if pd.isna(x.at[0, k]) else round(float(x.at[0, k]), 6))
                   for k in FEATURES}}


# Las variables con las que se juzgo cada BUY (la estrategia, como su indice en el modelo: strategy_idx)
META_SIGNALS_COLUMNS = (["logged_at", "symbol", "open_time", "strategy", "bot_decision", "meta_p", "meta_p_min",
                         "meta_decision", "model_trained_until", "market"]
                        + [k for k in FEATURES if k != "strategy"] + ["strategy_idx"])


# --------------------------------------------------------------------------- entrenamiento del modelo vivo
def train(out_model: str = MODEL_FILE, out_meta: str = MODEL_META_FILE) -> dict:
    """Walk-forward BASE de las 20 parejas (fase 1 de experiments_v2.py) y un LightGBM con todas sus operaciones en
    sombra ya cerradas. Mismos hiperparametros, variables y etiqueta que el brazo META."""
    from multiprocessing import Pool
    import lightgbm as lgb
    import experiments_v2 as X
    tasks = [("base", s, st) for s in X.ACTIVE_ROSTER for st in X.STRATEGIES]
    print(f"[META] Walk-forward de {len(tasks)} parejas con velas de {X.INTERVAL} ({X.WORKERS} procesos)...")
    with Pool(processes=X.WORKERS) as pool:
        results = list(pool.imap_unordered(X.phase1, tasks))
    table = X.trade_table(results)
    if len(table) < X.META_MIN_TRAIN or table["_label"].nunique() < 2:
        raise SystemExit(f"[META] Solo hay {len(table)} operaciones en sombra: no se entrena (minimo {X.META_MIN_TRAIN}).")
    model = lgb.LGBMClassifier(**X.META_PARAMS)
    model.fit(table[FEATURES], table["_label"], categorical_feature=["strategy"])
    model.booster_.save_model(out_model)
    until = datetime.datetime.fromtimestamp(int(table["_known_ms"].max()) / 1000, datetime.timezone.utc)
    info = {"vela": X.INTERVAL, "variables": FEATURES, "estrategias": X.STRATEGIES, "lightgbm": X.META_PARAMS,
            "regla": "tomaria si p > (1 + c_R) / (1 + b); en sombra: no bloquea",
            "entrenado_hasta": until.strftime("%Y-%m-%d %H:%M"), "operaciones": int(len(table)),
            "win_rate": round(100 * float(table["_label"].mean()), 1),
            "generado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(out_meta, "w", encoding="utf-8", newline="\n") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print(f"[META] ✅ Modelo con {info['operaciones']} operaciones (WR {info['win_rate']} %), hasta "
          f"{info['entrenado_hasta']}: {out_model}")
    return info


if __name__ == "__main__":
    import sys
    if "--train" not in sys.argv:
        print(__doc__)
        sys.exit(1)
    sys.stdout.reconfigure(encoding="utf-8")
    train()
