"""
strategy_engine.load_best_strategies sin red: qué estrategias se cargan con y sin ALLOW_UNVALIDATED_STRATEGIES,
en testnet y en mainnet, con el ml_results.json real y con uno sintético (una moneda validada y otra no).

    .venv\\Scripts\\python -m unittest test_strategy_engine -v     (o npm run test:python desde la raíz)
"""
import contextlib
import io
import json
import unittest

import strategy_engine
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from quantitative_strategies.rolling_volatility import RollingVolatilityStrategy
from quantitative_strategies.volatility_squeeze import VolatilitySqueezeStrategy
from quantitative_strategies.vwap_strategy import VWAPReversionStrategy
from quantitative_strategies.capitulation import CapitulationStrategy

CLASSES = {"MeanReversion": MeanReversionStrategy, "TrendFollowing": RollingVolatilityStrategy,
           "VWAP": VWAPReversionStrategy, "VolatilitySqueeze": VolatilitySqueezeStrategy,
           "Capitulation": CapitulationStrategy}


def entry(status, window, multiplier, oos_pnl, operar=True, hold_pnl=0.1):
    return {"window": window, "multiplier": multiplier, "status": status, "motivo": "x",
            "entrenamiento_vivo": {"operar": operar}, "oos": {"pnl": oos_pnl, "trades": 40},
            "validacion_final": {"pnl": hold_pnl, "trades": 3}}


SYNTHETIC = {
    "_protocolo": {"generado": "prueba", "criterios": {}},
    # BTC: una validada (VWAP) y otra con mejor PnL OOS pero rechazada -> en ambos modos, la validada
    "BTCUSDT": {"seleccionada": "VWAP", "motivo": "validada",
                "VWAP": entry("validada", 40, 2.0, 5.0),
                "MeanReversion": entry("rechazada", 20, 1.0, 9.0)},
    # ETH: ninguna validada; la de mejor PnL OOS no tiene parámetros rentables en vivo -> la siguiente
    "ETHUSDT": {"seleccionada": None, "motivo": "ninguna",
                "MeanReversion": entry("rechazada", 24, 2.2, 3.0, operar=False),
                "TrendFollowing": entry("rechazada", 56, 3.0, -1.0),
                "VWAP": entry("rechazada", 84, 2.6, -2.0)},
}


class StrategyEngineTest(unittest.TestCase):
    def setUp(self):
        self.saved = (strategy_engine.ALLOW_UNVALIDATED, strategy_engine.BINANCE_MARKET)

    def tearDown(self):
        strategy_engine.ALLOW_UNVALIDATED, strategy_engine.BINANCE_MARKET = self.saved
        if hasattr(strategy_engine, "open"):
            del strategy_engine.open

    def load(self, allow, market, results=None):
        strategy_engine.ALLOW_UNVALIDATED = allow
        strategy_engine.BINANCE_MARKET = market
        if results is not None:
            strategy_engine.open = lambda *a, **k: io.StringIO(json.dumps(results))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            engine = strategy_engine.StrategyEngine()
        return engine, out.getvalue()

    def test_sintetico_normal_solo_validadas(self):
        engine, _ = self.load(False, "testnet", SYNTHETIC)
        self.assertEqual(set(engine.strategies), {"BTCUSDT"})
        s = engine.strategies["BTCUSDT"]
        self.assertIsInstance(s, VWAPReversionStrategy)
        self.assertEqual((s.window, s.std_dev_multiplier), (40, 2.0))

    def test_sintetico_experimental_en_testnet(self):
        engine, text = self.load(True, "testnet", SYNTHETIC)
        self.assertIsInstance(engine.strategies["BTCUSDT"], VWAPReversionStrategy)   # la validada, no la de más PnL
        eth = engine.strategies["ETHUSDT"]
        self.assertIsInstance(eth, RollingVolatilityStrategy)   # MeanReversion no tiene parámetros rentables en vivo
        self.assertEqual((eth.window, eth.std_dev_multiplier), (56, 3.0))
        self.assertIn("NO VALIDADA", text)

    def test_sintetico_experimental_se_ignora_en_mainnet(self):
        engine, text = self.load(True, "mainnet", SYNTHETIC)
        self.assertEqual(set(engine.strategies), {"BTCUSDT"})
        self.assertIn("se ignora en mainnet", text)

    def test_ml_results_real(self):
        with open(strategy_engine.__file__.replace("strategy_engine.py", "machine_learning_strategies/ml_results.json"),
                  encoding="utf-8") as f:
            results = json.load(f)
        coins = {s: d for s, d in results.items() if not s.startswith("_")}
        validated = {s: d["seleccionada"] for s, d in coins.items() if d.get("seleccionada")}
        # Modo normal (y experimental en mainnet): solo las monedas con estrategia validada, con esa estrategia
        for engine in (self.load(False, "testnet")[0], self.load(True, "mainnet")[0]):
            self.assertEqual(set(engine.strategies), set(validated))
            for symbol, name in validated.items():
                self.assertIs(type(engine.strategies[symbol]), CLASSES[name])
        # Experimental en testnet: las validadas igual; el resto, la de mejor PnL OOS con parámetros en vivo
        engine, _ = self.load(True, "testnet")
        for symbol, data in coins.items():
            if symbol in validated:
                best = validated[symbol]
            else:
                names = [n for n in CLASSES
                         if isinstance(data.get(n), dict) and data[n].get("entrenamiento_vivo", {}).get("operar")
                         and data[n].get("window")]
                if not names:
                    self.assertNotIn(symbol, engine.strategies)
                    continue
                best = max(names, key=lambda n: data[n]["oos"]["pnl"])
            s = engine.strategies[symbol]
            self.assertIs(type(s), CLASSES[best])
            self.assertEqual((s.window, s.std_dev_multiplier), (data[best]["window"], float(data[best]["multiplier"])))


class CapitulationTest(unittest.TestCase):
    """Compra solo si la última hora cae más de k desviaciones Y la vela trae volumen climático."""

    def feed(self, crash_volume):
        s = CapitulationStrategy(window=20, std_dev_multiplier=2.0)
        prices = [100 + 0.1 * ((-1) ** i) for i in range(30)] + [99.5, 99.0, 98.0, 96.0]
        volumes = [10.0] * 33 + [crash_volume]
        signals = [s.evaluate("X", {"close": p, "volume": v}) for p, v in zip(prices, volumes)]
        return signals

    def test_caida_con_volumen_compra_con_geometria_x5(self):
        signals = self.feed(crash_volume=40.0)
        self.assertTrue(all(x["action"] == "HOLD" for x in signals[:-1]))
        last = signals[-1]
        self.assertEqual(last["action"], "BUY")
        self.assertEqual(last["entry_price"], 96.0)
        up, down = last["take_profit"] - 96.0, 96.0 - last["stop_loss"]
        self.assertAlmostEqual(down / up, 1.75 / 0.7, places=5)   # SL a 1.75 sd y TP a 0.7 sd

    def test_caida_sin_volumen_no_compra(self):
        self.assertTrue(all(x["action"] == "HOLD" for x in self.feed(crash_volume=10.0)))


if __name__ == "__main__":
    unittest.main()
