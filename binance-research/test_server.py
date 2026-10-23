"""
server.handle_request sin red: handshake 'market' (Node aborta si el mercado o el tamaño por operación no cuadran,
y compra exactamente notional_usdt, el NOTIONAL_USDT del backtest de optimize.py) y ledger_open/ledger_close sobre
un ledger temporal (nunca orders/trades.csv).
"""
import contextlib
import csv
import io
import json
import math
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

import ledger
import optimize
import server
import walk_forward
from config import BINANCE_MARKET, KLINE_INTERVAL, KLINE_INTERVAL_MS
from fast_backtest import FastSymbol
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from quantitative_strategies.volatility_squeeze import VolatilitySqueezeStrategy
from strategy_engine import StrategyEngine


class HandshakeTest(unittest.TestCase):
    def test_market_devuelve_mercado_y_nocional_del_backtest(self):
        response = server.handle_request({"type": "market"})
        self.assertEqual(response, {"market": BINANCE_MARKET, "notional_usdt": float(optimize.NOTIONAL_USDT),
                                    "kline_interval": KLINE_INTERVAL})
        json.dumps(response, allow_nan=False)
        self.assertGreater(response["notional_usdt"], 0)


class LedgerRequestsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = ledger.LEDGER_FILE
        ledger.LEDGER_FILE = os.path.join(self.tmp.name, "trades.csv")

    def tearDown(self):
        ledger.LEDGER_FILE = self.original
        self.tmp.cleanup()

    def ask(self, req_type, payload):
        with contextlib.redirect_stdout(io.StringIO()):
            return server.handle_request({"type": req_type, "payload": payload})

    def rows(self):
        with open(ledger.LEDGER_FILE, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def open_trade(self, order_id, symbol):
        return self.ask("ledger_open", {"order_id": order_id, "symbol": symbol, "entry_price": 1.0, "take_profit": 2.0,
                                        "stop_loss": 0.5, "quantity": 10.0, "net_quantity": 9.99, "entry_quote": 10.0,
                                        "entry_fee_usdt": 0.01, "entry_fees": "0.01 X", "signal_price": 1.0})

    def test_ledger_close_cierra_solo_la_moneda_indicada(self):
        # Mismo orderId en dos monedas abiertas a la vez (Binance numera las órdenes por símbolo)
        self.assertEqual(self.open_trade(1000, "BTCUSDT"), {"status": "logged"})
        self.assertEqual(self.open_trade(1000, "ETHUSDT"), {"status": "logged"})
        response = self.ask("ledger_close", {"order_id": 1000, "symbol": "ETHUSDT", "exit_price": 2.0, "exit_quantity": 9.0,
                                             "exit_quote": 18.0, "exit_fee_usdt": 0.018, "exit_fees": "0.018 USDT",
                                             "exit_order_id": 1001, "exit_trigger_price": 2.0, "residual_quantity": 0.99,
                                             "pnl": 9.952, "reason": "TAKE PROFIT ✅"})
        self.assertEqual(response, {"status": "updated"})
        by_symbol = {r["symbol"]: r for r in self.rows()}
        self.assertEqual(by_symbol["BTCUSDT"]["status"], "OPEN")
        self.assertEqual(by_symbol["BTCUSDT"]["pnl"], "")
        self.assertEqual(by_symbol["ETHUSDT"]["status"], "CLOSED")
        self.assertEqual(by_symbol["ETHUSDT"]["residual_quantity"], "0.99")
        self.assertEqual(by_symbol["ETHUSDT"]["exit_reason"], "TAKE PROFIT ✅")
        # Un segundo cierre de la misma orden (ya CLOSED) no la sobrescribe
        again = self.ask("ledger_close", {"order_id": 1000, "symbol": "ETHUSDT", "pnl": -5, "reason": "X"})
        self.assertEqual(again["status"], "error")
        self.assertEqual({r["symbol"]: r["pnl"] for r in self.rows()}, {"BTCUSDT": "", "ETHUSDT": "9.952"})
        self.assertEqual([t["symbol"] for t in self.ask("sync_positions", {})], ["BTCUSDT"])

    def test_compra_pending_pasa_a_open_en_la_misma_fila_o_a_cancelled(self):
        pending = {"client_order_id": "bot_b_1", "symbol": "dogeusdt", "signal_price": 0.0815, "take_profit": 0.0825,
                   "stop_loss": 0.0805}
        self.assertEqual(self.ask("ledger_pending", pending), {"status": "logged"})
        self.assertEqual(self.ask("ledger_pending", {**pending, "client_order_id": "bot_b_2", "symbol": "ETHUSDT"}),
                         {"status": "logged"})
        self.assertEqual([t["client_order_id"] for t in self.ask("sync_pending", {})], ["bot_b_1", "bot_b_2"])
        self.assertEqual(self.ask("sync_positions", {}), [])
        self.assertIn("DOGEUSDT", self.ask("roster", {}))          # el WebSocket vigila la moneda pendiente
        first = {r["client_order_id"]: r for r in self.rows()}["bot_b_1"]
        self.assertEqual((first["status"], first["order_id"], first["signal_price"]), ("PENDING", "", "0.0815"))

        # Confirmada: la fila PENDING pasa a OPEN con los fills reales (no se añade otra)
        response = self.ask("ledger_open", {"order_id": 55, "symbol": "DOGEUSDT", "entry_price": 0.08152,
                                            "take_profit": 0.0825, "stop_loss": 0.0805, "quantity": 184.0,
                                            "net_quantity": 183.816, "entry_quote": 15.0, "entry_fee_usdt": 0.015,
                                            "entry_fees": "0.184 DOGE", "signal_price": 0.0815,
                                            "client_order_id": "bot_b_1"})
        self.assertEqual(response, {"status": "logged"})
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        doge = {r["client_order_id"]: r for r in rows}["bot_b_1"]
        self.assertEqual((doge["status"], doge["order_id"], doge["entry_price"], doge["timestamp"]),
                         ("OPEN", "55", "0.08152", first["timestamp"]))
        self.assertEqual([t["order_id"] for t in self.ask("sync_positions", {})], [55])

        # No existe en Binance: CANCELLED (una sola vez)
        cancel = {"client_order_id": "bot_b_2", "symbol": "ETHUSDT", "reason": "NO LLEGÓ A BINANCE (no apareció en ~2 min de consultas)"}
        self.assertEqual(self.ask("ledger_cancel", cancel), {"status": "updated"})
        self.assertEqual(self.ask("ledger_cancel", cancel)["status"], "error")
        eth = {r["client_order_id"]: r for r in self.rows()}["bot_b_2"]
        self.assertEqual((eth["status"], eth["exit_reason"]), ("CANCELLED", "NO LLEGÓ A BINANCE (no apareció en ~2 min de consultas)"))
        self.assertEqual(self.ask("sync_pending", {}), [])

        # Sin fila PENDING (p. ej. compras anteriores a este cambio) ledger_open añade la fila como antes
        self.ask("ledger_open", {"order_id": 56, "symbol": "BTCUSDT", "entry_price": 65000.0, "take_profit": 66000.0,
                                 "stop_loss": 64000.0, "quantity": 0.00023, "client_order_id": "bot_b_sin_fila"})
        self.assertEqual(len(self.rows()), 3)


def squeeze_case(start=400, n=520):
    """Velas en las que la trampa de VolatilitySqueeze (n=20) depende de cuántas se precargan: calma hasta start-91,
    caída del 1 % por vela (start-90..start-71), oscilación de +-2 % y ruptura del +10 % en start+30. Con su precarga
    (max(20 + 20, 100) = 100 velas) no hay BUY; con 116 (la ventana mayor de otra moneda, n=96) la trampa queda armada
    desde la calma y compra en start+30."""
    closes, level = [], 100.0
    for i in range(n):
        if i <= start - 91:
            price = 100.0 * (1 + 0.0005 * math.sin(i))
        elif i <= start - 71:
            level *= 0.99
            price = level
        elif i < start + 30:
            price = level * (1.02 if i % 2 else 0.98)
        elif i == start + 30:
            price = level * 1.10
        else:
            price = level
        closes.append(price)
    c = np.array(closes)
    df = pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 100.0})
    df["open_time"] = 1_700_000_000_000 + np.arange(n) * KLINE_INTERVAL_MS
    return df


class PreseedTest(unittest.TestCase):
    """Precarga por moneda (max(su ventana + margen, minimo)) y mismo estado que el backtest (fast_backtest con first)."""
    START = 400

    def setUp(self):
        self.saved = (server.engine, server.fetch_closed_klines, ledger.SIGNALS_FILE)
        self.tmp = tempfile.TemporaryDirectory()
        ledger.SIGNALS_FILE = os.path.join(self.tmp.name, "signals.csv")   # nunca orders/signals.csv
        self.calls, self.data, self.available = [], {}, {}

        def fake_fetch(symbol, limit=None, start_time=None, end_time=None):
            self.calls.append({"symbol": symbol, "limit": limit, "end_time": end_time})
            df = self.data[symbol].iloc[:self.available[symbol]]
            if end_time is not None:
                df = df[df["open_time"] <= end_time]
            if limit is not None:
                df = df.iloc[-limit:]
            return [[int(r.open_time), r.open, r.high, r.low, r.close, r.volume, int(r.open_time) + KLINE_INTERVAL_MS - 1]
                    for r in df.itertuples()]
        server.fetch_closed_klines = fake_fetch

    def tearDown(self):
        server.engine, server.fetch_closed_klines, ledger.SIGNALS_FILE = self.saved
        self.tmp.cleanup()

    def make_engine(self, strategies):
        engine = StrategyEngine.__new__(StrategyEngine)   # sin leer ml_results.json ni filtros de entrada
        engine.init_state(min_risk=None, cosignal=None, momentum=None)
        engine.strategies = strategies
        server.engine = engine
        for symbol in strategies:
            self.data[symbol] = squeeze_case(self.START)
            self.available[symbol] = self.START
        return engine

    def live_buys(self, symbol, start, end):
        """Velas [start, end) por el WebSocket (handle_request 'evaluate'): índices con BUY."""
        buys = []
        for i in range(start, end):
            row = self.data[symbol].iloc[i]
            self.available[symbol] = i
            market_data = {"open_time": int(row.open_time), "open": float(row.open), "high": float(row.high),
                           "low": float(row.low), "close": float(row.close), "volume": float(row.volume)}
            with contextlib.redirect_stdout(io.StringIO()):
                signal = server.handle_request({"type": "evaluate", "payload": {"symbol": symbol, "market_data": market_data}})
            if signal and signal.get("action") == "BUY":
                buys.append(i)
        return buys

    def fast_buys(self, symbol, preseed, end):
        fs = FastSymbol(self.data[symbol])
        buys = fs.buy_indices("VolatilitySqueeze", 20, 2.0, first=self.START - preseed, end=end)
        return [int(i) for i in buys if i >= self.START]

    def test_cada_moneda_precarga_su_ventana_mas_margen(self):
        self.make_engine({"AAAUSDT": VolatilitySqueezeStrategy(window=20, std_dev_multiplier=2.0),
                          "BBBUSDT": MeanReversionStrategy(window=96, std_dev_multiplier=2.0)})
        with contextlib.redirect_stdout(io.StringIO()):
            server.pre_seed_engine(["AAAUSDT", "BBBUSDT", "CCCUSDT"])
        # limit + 1 (la última puede ser la vela en formación); sin estrategia (CCC) no se pide nada
        self.assertEqual([(c["symbol"], c["limit"]) for c in self.calls], [("AAAUSDT", 101), ("BBBUSDT", 117)])
        self.assertEqual(len(server.engine.strategies["AAAUSDT"].price_history["AAAUSDT"]), 20)
        for window in (8, 20, 80, 96, 150):
            server.engine.strategies["AAAUSDT"].window = window
            self.assertEqual(server.preseed_count("AAAUSDT"), walk_forward.preseed_candles(window))

    def test_volatility_squeeze_igual_que_el_backtest_con_first(self):
        # Otra moneda con ventana 96: con la precarga global (116 velas) la trampa quedaría armada y compraría
        self.make_engine({"AAAUSDT": VolatilitySqueezeStrategy(window=20, std_dev_multiplier=2.0),
                          "BBBUSDT": MeanReversionStrategy(window=96, std_dev_multiplier=2.0)})
        with contextlib.redirect_stdout(io.StringIO()):
            server.pre_seed_engine(["AAAUSDT", "BBBUSDT"])
        live = self.live_buys("AAAUSDT", self.START, self.START + 100)
        self.assertEqual(live, self.fast_buys("AAAUSDT", walk_forward.preseed_candles(20), self.START + 100))
        self.assertEqual(live, [])
        # La prueba distingue: con 116 velas de precarga el vivo y el backtest (first = inicio - 116) compran en +30
        self.make_engine({"AAAUSDT": VolatilitySqueezeStrategy(window=20, std_dev_multiplier=2.0)})
        with contextlib.redirect_stdout(io.StringIO()):
            server.pre_seed_engine(["AAAUSDT"], required_candles=116)
        self.assertEqual(self.live_buys("AAAUSDT", self.START, self.START + 100), [self.START + 30])
        self.assertEqual(self.fast_buys("AAAUSDT", 116, self.START + 100), [self.START + 30])

    def test_fill_gap_por_moneda_y_reinicio_tras_un_hueco_mayor_que_la_precarga(self):
        engine = self.make_engine({"AAAUSDT": VolatilitySqueezeStrategy(window=20, std_dev_multiplier=2.0),
                                   "BBBUSDT": MeanReversionStrategy(window=96, std_dev_multiplier=2.0)})
        with contextlib.redirect_stdout(io.StringIO()):
            server.pre_seed_engine(["AAAUSDT"])
        original = engine.strategies["AAAUSDT"]
        self.calls.clear()
        # Hueco de 10 velas (<= 100): se piden solo esas y la instancia sigue
        self.live_buys("AAAUSDT", self.START + 10, self.START + 11)
        self.assertEqual([(c["limit"], c["end_time"]) for c in self.calls],
                         [(10, int(self.data["AAAUSDT"].open_time.iloc[self.START + 10]) - 1)])
        self.assertIs(engine.strategies["AAAUSDT"], original)
        # Hueco de 104 velas (> 100): instancia nueva (trampa desarmada) precargada con sus 100 velas
        self.calls.clear()
        self.live_buys("AAAUSDT", self.START + 115, self.START + 116)
        fresh = engine.strategies["AAAUSDT"]
        self.assertIsNot(fresh, original)
        self.assertEqual((fresh.window, fresh.std_dev_multiplier, fresh.squeeze_threshold), (20, 2.0, 0.05))
        self.assertEqual([c["limit"] for c in self.calls], [100])
        self.assertEqual(engine.last_open_time["AAAUSDT"], int(self.data["AAAUSDT"].open_time.iloc[self.START + 115]))


if __name__ == "__main__":
    unittest.main()
