"""
meta_filter.py sin red ni datos descargados: las variables en vivo (bufer de velas) son las mismas que en el backtest,
la E de 3 y 12 meses sale de los pliegues de ml_results.json, el BUY espera su vela de BTC, la decision es p > p* y el
filtro solo anota (nunca cambia la senal del bot).
"""
import contextlib
import csv
import io
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

import ledger
import meta_filter as M
import server
from config import KLINE_INTERVAL, KLINE_INTERVAL_MS
from strategy_engine import StrategyEngine

T0 = 1_700_000_000_000
COST = 0.0012


def candles(n, seed, start=T0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    v = rng.uniform(50, 150, n)
    return pd.DataFrame({"open_time": start + np.arange(n) * KLINE_INTERVAL_MS, "close": c,
                         "high": c * (1 + rng.uniform(0, 0.01, n)), "volume": v, "taker_buy": v * rng.uniform(0.3, 0.7, n)})


def market_data(row):
    return {"open_time": int(row.open_time), "open": float(row.close), "high": float(row.high), "low": float(row.close),
            "close": float(row.close), "volume": float(row.volume), "taker_buy": float(row.taker_buy)}


def tiny_model():
    """LightGBM entrenado con datos sinteticos: p alta cuando ret_1 > 0 (basta para probar la decision)."""
    import lightgbm as lgb
    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.normal(0, 1, (600, len(M.FEATURES))), columns=M.FEATURES)
    x["strategy"] = rng.integers(0, 5, 600)
    y = (x["ret_1"] > 0).astype(int)
    model = lgb.LGBMClassifier(n_estimators=30, num_leaves=4, min_child_samples=10, verbose=-1)
    model.fit(x, y, categorical_feature=["strategy"])
    return model.booster_


INFO = {"vela": KLINE_INTERVAL, "variables": M.FEATURES, "estrategias": ["MeanReversion", "TrendFollowing"],
        "entrenado_hasta": "2026-10-01 00:00", "operaciones": 600}


def make_filter(model=None):
    return M.MetaFilter(KLINE_INTERVAL, KLINE_INTERVAL_MS, COST, 15.0, model=model or tiny_model(), info=dict(INFO))


def buy(symbol, open_time, close):
    return {"symbol": symbol, "open_time": open_time, "strategy": "TrendFollowing", "entry_price": close,
            "take_profit": close * 1.03, "stop_loss": close * 0.98, "decision": "BUY", "market": "testnet"}


class FeatureParityTest(unittest.TestCase):
    def test_bufer_en_vivo_igual_que_backtest(self):
        coin, btc = candles(400, 1), candles(400, 2)
        full = M.candle_feature_frame(coin, btc, KLINE_INTERVAL_MS)
        f = make_filter()
        for i in range(400):
            f.add_candle("BTCUSDT", market_data(btc.iloc[i]))
            f.add_candle("SOLUSDT", market_data(coin.iloc[i]))
        for i in (300, 399):
            # el bufer solo guarda las ultimas BUFFER_CANDLES velas: la ultima es la que se juzga
            f2 = make_filter()
            for k in range(i + 1):
                f2.add_candle("BTCUSDT", market_data(btc.iloc[k]))
                f2.add_candle("SOLUSDT", market_data(coin.iloc[k]))
            own = f2._frame("SOLUSDT")
            live = M.candle_feature_frame(own, f2._frame("BTCUSDT"), KLINE_INTERVAL_MS).iloc[-1]
            np.testing.assert_allclose(live.to_numpy(float), full.iloc[i].to_numpy(float), rtol=1e-9, equal_nan=True)
            self.assertTrue(np.isfinite(live.to_numpy(float)).all())

    def test_vela_repetida_no_entra_dos_veces(self):
        f = make_filter()
        row = candles(1, 3).iloc[0]
        f.add_candle("SOLUSDT", market_data(row))
        f.add_candle("SOLUSDT", market_data(row))
        self.assertEqual(len(f.candles["SOLUSDT"]), 1)


class FoldEdgeTest(unittest.TestCase):
    COLS = ["prueba", "n", "k", "ops_ent", "pnl_ent", "ops", "pnl", "ops_sombra", "pnl_sombra", "encendido"]

    def row(self, month, ops, pnl):
        return [month, 20, 1.0, 50, 1.0, 0, 0.0, ops, pnl, 1]

    def test_solo_meses_anteriores(self):
        rows = [self.row("2026-07", 10, 1.5), self.row("2026-08", 5, -0.75), self.row("2026-09", 5, 3.0),
                self.row("2026-10", 100, -50.0)]
        e3 = M.fold_edge(rows, self.COLS, "2026-10", 3, 15.0)
        self.assertAlmostEqual(e3, (1.5 - 0.75 + 3.0) / 20 / 15.0)
        self.assertAlmostEqual(M.fold_edge(rows, self.COLS, "2026-10", 1, 15.0), 3.0 / 5 / 15.0)

    def test_sin_operaciones_o_sin_columnas_es_nan(self):
        self.assertTrue(np.isnan(M.fold_edge([self.row("2026-09", 0, 0.0)], self.COLS, "2026-10", 3, 15.0)))
        self.assertTrue(np.isnan(M.fold_edge([["2026-09", 1]], ["prueba", "ops"], "2026-10", 3, 15.0)))


class PendingTest(unittest.TestCase):
    def setUp(self):
        self.coin, self.btc = candles(260, 4), candles(260, 5)
        self.f = make_filter()
        for i in range(250):
            self.f.add_candle("BTCUSDT", market_data(self.btc.iloc[i]))
            self.f.add_candle("SOLUSDT", market_data(self.coin.iloc[i]))

    def test_espera_la_vela_de_btc(self):
        row = self.coin.iloc[250]
        self.f.add_candle("SOLUSDT", market_data(row))
        self.f.on_buy(buy("SOLUSDT", int(row.open_time), float(row.close)), [], [])
        self.assertEqual(self.f.pop_ready(), [])
        self.f.add_candle("BTCUSDT", market_data(self.btc.iloc[250]))
        ready = self.f.pop_ready()
        self.assertEqual(len(ready), 1)
        self.assertIsNotNone(ready[0]["btc_ret_24"])
        self.assertEqual(self.f.pending, [])

    def test_sin_btc_se_juzga_con_la_vela_siguiente(self):
        for i in (250, 251):
            self.f.add_candle("SOLUSDT", market_data(self.coin.iloc[i]))
            if i == 250:
                row = self.coin.iloc[250]
                self.f.on_buy(buy("SOLUSDT", int(row.open_time), float(row.close)), [], [])
                self.assertEqual(self.f.pop_ready(), [])
        ready = self.f.pop_ready()
        self.assertEqual(len(ready), 1)
        self.assertIsNone(ready[0]["btc_ret_24"])

    def test_decision_es_p_mayor_que_p_estrella(self):
        row = self.coin.iloc[249]
        self.f.on_buy(buy("SOLUSDT", int(row.open_time), float(row.close)), [], [])
        rec = self.f.pop_ready()[0]
        b, c_r = 0.03 / 0.02, 2 * COST / 0.02
        self.assertAlmostEqual(rec["meta_p_min"], round((1 + c_r) / (1 + b), 4))
        self.assertEqual(rec["meta_decision"], "tomaria" if rec["meta_p"] > rec["meta_p_min"] else "omitiria")
        self.assertEqual(rec["strategy"], "TrendFollowing")
        self.assertEqual(rec["strategy_idx"], 1.0)
        self.assertEqual(set(M.META_SIGNALS_COLUMNS) - set(rec), set())

    def test_sin_modelo_no_anota(self):
        f = M.MetaFilter(KLINE_INTERVAL, KLINE_INTERVAL_MS, COST, 15.0, model_file="/no/existe.txt",
                         meta_file="/no/existe.json")
        self.assertFalse(f.enabled)
        f.on_buy(buy("SOLUSDT", T0, 100.0), [], [])
        self.assertEqual(f.pop_ready(), [])
        self.assertIn("sin modelo", f.describe())

    def test_modelo_de_otra_temporalidad_no_se_carga(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_file, meta_file = os.path.join(tmp, "m.txt"), os.path.join(tmp, "m.json")
            tiny_model().save_model(model_file)
            with open(meta_file, "w", encoding="utf-8") as fh:
                fh.write('{"vela": "4h", "variables": []}')
            f = M.MetaFilter(KLINE_INTERVAL, KLINE_INTERVAL_MS, COST, 15.0, model_file=model_file, meta_file=meta_file)
            self.assertFalse(f.enabled)
            with open(meta_file, "w", encoding="utf-8") as fh:
                import json
                json.dump(INFO, fh)
            self.assertTrue(M.MetaFilter(KLINE_INTERVAL, KLINE_INTERVAL_MS, COST, 15.0, model_file=model_file,
                                         meta_file=meta_file).enabled)


class ServerShadowTest(unittest.TestCase):
    """Por el WebSocket: el BUY sigue igual y el juicio del filtro va a meta_signals.csv cuando llega la vela de BTC."""

    def setUp(self):
        self.saved = (server.engine, ledger.SIGNALS_FILE, ledger.META_SIGNALS_FILE)
        self.tmp = tempfile.TemporaryDirectory()
        ledger.SIGNALS_FILE = os.path.join(self.tmp.name, "signals.csv")
        ledger.META_SIGNALS_FILE = os.path.join(self.tmp.name, "meta_signals.csv")

    def tearDown(self):
        server.engine, ledger.SIGNALS_FILE, ledger.META_SIGNALS_FILE = self.saved
        self.tmp.cleanup()

    def test_anota_sin_cambiar_la_senal(self):
        engine = StrategyEngine.__new__(StrategyEngine)
        engine.init_state(min_risk=None, cosignal=None, momentum=None)
        engine.meta = make_filter()
        server.engine = engine
        coin, btc = candles(260, 6), candles(260, 7)
        for i in range(259):
            engine.meta.add_candle("BTCUSDT", market_data(btc.iloc[i]))
            engine.meta.add_candle("SOLUSDT", market_data(coin.iloc[i]))

        class AlwaysBuy:
            window = 10

            def evaluate(self, symbol, candle):
                p = candle["close"]
                return {"action": "BUY", "entry_price": p, "take_profit": p * 1.03, "stop_loss": p * 0.98}
        engine.strategies = {"SOLUSDT": AlwaysBuy()}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            signal = server.handle_request({"type": "evaluate", "payload": {"symbol": "SOLUSDT",
                                                                            "market_data": market_data(coin.iloc[259])}})
            self.assertEqual(signal["action"], "BUY")
            self.assertFalse(os.path.exists(ledger.META_SIGNALS_FILE))       # espera la vela de BTC
            server.handle_request({"type": "evaluate", "payload": {"symbol": "BTCUSDT",
                                                                   "market_data": market_data(btc.iloc[259])}})
        with open(ledger.META_SIGNALS_FILE, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "SOLUSDT")
        self.assertEqual(rows[0]["bot_decision"], "BUY")
        self.assertIn(rows[0]["meta_decision"], ("tomaria", "omitiria"))
        self.assertIn("[META] SOLUSDT", out.getvalue())

    def test_kline_rest_con_taker_buy(self):
        kline = [T0, "1", "2", "0.5", "1.5", "100", T0 + 1, "150", 10, "40", "60", "0"]
        self.assertEqual(server.kline_to_market_data(kline)["taker_buy"], 40.0)
        self.assertIsNone(server.kline_to_market_data(kline[:7])["taker_buy"])


if __name__ == "__main__":
    unittest.main()
