"""
Filtros de entrada (config.py): el bot en vivo (strategy_engine.py) y el backtest (strategy_filters.py, que usa
walk_forward.py) dan las mismas señales con riesgo mínimo y co-señal, y el interruptor de momentum bloquea y queda en
el diario de señales. Sin red ni datos reales: dos monedas sintéticas con movimientos correlacionados.

    .venv\\Scripts\\python -m unittest test_filters -v     (o npm run test:python desde la raíz)
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
import server
import strategy_filters as SF
from config import KLINE_INTERVAL_MS
from fast_backtest import FastSymbol
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from strategy_engine import StrategyEngine

COINS = ["AAAUSDT", "BBBUSDT"]
RULES = {"AAAUSDT": (20, 1.0), "BBBUSDT": (32, 1.4)}


def correlated_coins(n=1500, seed=7):
    """Dos paseos aleatorios con un shock común (así hay co-señales y también señales aisladas)."""
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 0.003, n)
    out = {}
    for k, symbol in enumerate(COINS):
        c = 100 * (1 + k) * np.exp(np.cumsum(common + rng.normal(0, 0.002, n)))
        df = pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
                           "volume": rng.uniform(50, 150, n)})
        df["open_time"] = 1_700_000_000_000 + np.arange(n) * KLINE_INTERVAL_MS
        out[symbol] = df
    return out


def make_engine(min_risk=None, cosignal=None, momentum=None, roster=COINS, ignore_momentum=False):
    engine = StrategyEngine.__new__(StrategyEngine)   # sin leer ml_results.json
    engine.init_state(min_risk=min_risk, cosignal=cosignal, momentum=momentum, roster=roster,
                      ignore_momentum=ignore_momentum)
    engine.strategies = {s: MeanReversionStrategy(window=w, std_dev_multiplier=m) for s, (w, m) in RULES.items()
                         if s in roster}
    engine.build_shadows()
    return engine


def market_data(row):
    return {"open_time": int(row.open_time), "open": float(row.open), "high": float(row.high), "low": float(row.low),
            "close": float(row.close), "volume": float(row.volume)}


class LiveVsBacktestTest(unittest.TestCase):
    MIN_RISK, COSIGNAL, FIRST = 0.015, 48, 100

    def test_mismas_senales_con_riesgo_minimo_y_cosenal(self):
        data = correlated_coins()
        engine = make_engine(min_risk=self.MIN_RISK, cosignal=self.COSIGNAL)
        live = {s: [] for s in COINS}
        reasons = {"riesgo": 0, "cosenal": 0}
        n = len(data[COINS[0]])
        with contextlib.redirect_stdout(io.StringIO()):
            for i in range(self.FIRST, n):       # velas intercaladas: en cada instante, primero AAA y luego BBB
                for s in COINS:
                    signal = engine.get_signal(s, market_data(data[s].iloc[i]))
                    if signal and signal.get("action") == "BUY":
                        live[s].append(i)
                    elif signal and signal.get("bloqueada"):
                        reasons["riesgo"] += "riesgo" in signal["bloqueada"]
                        reasons["cosenal"] += "co-senal" in signal["bloqueada"]

        for s in COINS:
            fs = FastSymbol(data[s])
            others = [(FastSymbol(data[o]), data[o]["open_time"].to_numpy(np.int64)) for o in COINS if o != s]
            ffs = SF.FilteredFS(fs, data[s]["open_time"].to_numpy(np.int64), others, KLINE_INTERVAL_MS,
                                self.MIN_RISK, self.COSIGNAL)
            w, m = RULES[s]
            mask = ffs.cosignal_mask("MeanReversion", w, m, self.FIRST)
            expected = []
            for i in fs.buy_indices("MeanReversion", w, m, first=self.FIRST):
                entry, _, sl = fs.entry_levels("MeanReversion", w, int(i))
                if mask[i] and not entry - sl < entry * self.MIN_RISK:
                    expected.append(int(i))
            self.assertEqual(live[s], expected, s)
        # La prueba distingue: los dos filtros bloquean algo y aun así pasan señales
        self.assertGreater(sum(len(v) for v in live.values()), 5)
        self.assertGreater(reasons["riesgo"], 5)
        self.assertGreater(reasons["cosenal"], 5)

    def test_la_cosenal_no_cuenta_la_vela_actual_ni_la_de_hace_mas_de_w(self):
        t = 1_700_000_000_000 + np.arange(200) * KLINE_INTERVAL_MS
        other = type("Other", (), {"buy_indices": lambda self, *a: np.array([100])})()
        ffs = SF.FilteredFS(None, t, [(other, t)], KLINE_INTERVAL_MS, None, 48)
        mask = ffs.cosignal_mask("MeanReversion", 20, 1.0)
        self.assertEqual(np.flatnonzero(mask).tolist(), list(range(101, 149)))   # velas 101..148 (100 + 1 .. 100 + 48)


class MomentumTest(unittest.TestCase):
    def test_interruptor_por_pnl_en_sombra(self):
        rows = [{"prueba": f"2026-0{i + 1}", "pnl": p, "ops": 1} for i, p in enumerate([1.0, -3.0, 1.0, 1.0, 1.0])]
        self.assertEqual(SF.momentum_gate(rows, [], 2), [False, True, False, False, True])
        self.assertEqual(SF.momentum_gate(rows[:1], [-1.0, 2.0], 2), [True])
        t = np.array([pd.Timestamp(f"2026-0{i + 1}-10", tz="UTC").value // 10**6 for i in range(5)])
        gated, e, x, p = SF.gate_trades(rows, np.arange(5), np.arange(5), np.ones(5), t, [False, True, False, False, True])
        self.assertEqual(e.tolist(), [1, 4])
        self.assertEqual([(g["ops"], g["pnl"], g["pnl_sombra"]) for g in gated[:2]], [(0, 0.0, 1.0), (1, -3.0, -3.0)])

    def test_apagado_bloquea_el_buy_y_queda_en_el_diario(self):
        data = correlated_coins()["AAAUSDT"]
        saved = (server.engine, ledger.SIGNALS_FILE)
        with tempfile.TemporaryDirectory() as tmp:
            ledger.SIGNALS_FILE = os.path.join(tmp, "signals.csv")
            try:
                for switch in (False, True):
                    engine = make_engine(momentum=12, roster=["AAAUSDT"])
                    engine.momentum_on["AAAUSDT"] = switch
                    server.engine = engine
                    with contextlib.redirect_stdout(io.StringIO()):
                        for i in range(30):          # precarga directa (la primera vela por el server pediría al REST)
                            engine.get_signal("AAAUSDT", market_data(data.iloc[i]))
                        signals = [server.handle_request({"type": "evaluate", "payload": {
                            "symbol": "AAAUSDT", "market_data": market_data(data.iloc[i])}}) for i in range(30, 600)]
                    buys = [s for s in signals if s["action"] == "BUY"]
                    blocked = [s for s in signals if s.get("bloqueada")]
                    if switch:
                        self.assertTrue(buys)
                        self.assertFalse(blocked)
                    else:
                        self.assertFalse(buys)
                        self.assertTrue(blocked)
                        self.assertIn("momentum", blocked[0]["bloqueada"])
                with open(ledger.SIGNALS_FILE, encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(list(rows[0]), ledger.SIGNALS_COLUMNS)
                self.assertEqual({r["decision"] for r in rows}, {"bloqueada", "BUY"})
                self.assertTrue(all(r["strategy"] == "MeanReversion" and r["window"] == "20" for r in rows))
            finally:
                server.engine, ledger.SIGNALS_FILE = saved

    def test_ignorado_en_testnet_abre_y_lo_anota(self):
        data = correlated_coins()["AAAUSDT"]
        engine = make_engine(momentum=12, roster=["AAAUSDT"], ignore_momentum=True)
        engine.momentum_on["AAAUSDT"] = False
        buys = []
        with contextlib.redirect_stdout(io.StringIO()):
            for i in range(600):
                signal = engine.get_signal("AAAUSDT", market_data(data.iloc[i]))
                if signal and signal.get("action") == "BUY":
                    buys.append(engine.journal_entry)
        self.assertTrue(buys)
        self.assertTrue(all(j["decision"] == "BUY" and j["reason"] == "momentum apagado, ignorado en testnet"
                            and j["momentum_on"] is False for j in buys))


if __name__ == "__main__":
    unittest.main()
