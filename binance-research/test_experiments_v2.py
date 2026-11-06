# test_experiments_v2.py
"""Reglas pre-registradas de experiments_v2.py: TP con orden LIMIT (fast_backtest), tamano por E de 12 meses y p*.
Uso: python -m unittest test_experiments_v2"""
import unittest

import numpy as np
import pandas as pd

import experiments_v2 as X2
from fast_backtest import FastSymbol
from optimize import FEE_PER_SIDE, NOTIONAL_USDT, SLIPPAGE_PER_SIDE

COST = FEE_PER_SIDE + SLIPPAGE_PER_SIDE


def candles(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


class LevelsFS(FastSymbol):
    """FastSymbol con una sola senal en la vela 0, entrada 100, TP 102 y SL 98."""

    def buy_indices(self, strategy, w, m, first=0, end=None):
        return np.array([0], np.int64)

    def entry_levels(self, strategy, w, i):
        return 100.0, 102.0, 98.0


class TpLimitTest(unittest.TestCase):
    def test_touch_fills_market_but_not_limit(self):
        fs = LevelsFS(candles([[100, 100, 100, 100, 1], [100, 102, 99.5, 100, 1], [100, 103, 99.5, 101, 1]]))
        market = fs.simulate("X", 8, 1.0, detail=True)
        limit = fs.simulate("X", 8, 1.0, detail=True, tp_limit=True)
        self.assertEqual(market[0]["exit_index"], 1)
        self.assertEqual(limit[0]["exit_index"], 2)
        self.assertEqual(limit[0]["exit_price"], 102.0)

    def test_limit_tp_pays_only_fee_on_exit(self):
        fs = LevelsFS(candles([[100, 100, 100, 100, 1], [100, 103, 99.5, 101, 1]]))
        qty = NOTIONAL_USDT / 100.0
        market = fs.simulate("X", 8, 1.0, detail=True)[0]["pnl"]
        limit = fs.simulate("X", 8, 1.0, detail=True, tp_limit=True)[0]["pnl"]
        self.assertAlmostEqual(market, qty * 2.0 - qty * 202.0 * COST)
        self.assertAlmostEqual(limit, qty * 2.0 - qty * (100.0 * COST + 102.0 * FEE_PER_SIDE))

    def test_gap_above_tp_fills_at_tp(self):
        fs = LevelsFS(candles([[100, 100, 100, 100, 1], [103, 104, 102.5, 103, 1]]))
        self.assertEqual(fs.simulate("X", 8, 1.0, detail=True)[0]["exit_price"], 103.0)
        self.assertEqual(fs.simulate("X", 8, 1.0, detail=True, tp_limit=True)[0]["exit_price"], 102.0)

    def test_stop_loss_unchanged(self):
        fs = LevelsFS(candles([[100, 100, 100, 100, 1], [100, 101, 97, 98, 1]]))
        market = fs.simulate("X", 8, 1.0, detail=True)[0]
        limit = fs.simulate("X", 8, 1.0, detail=True, tp_limit=True)[0]
        self.assertEqual((limit["reason"], limit["exit_price"], limit["pnl"]),
                         (market["reason"], market["exit_price"], market["pnl"]))


class SizeTest(unittest.TestCase):
    def test_off_without_edge(self):
        for e12 in (0.0, -0.001, np.nan):
            self.assertEqual(X2.size_mult(e12), 0.0)

    def test_proportional_and_clipped(self):
        self.assertAlmostEqual(X2.size_mult(2 * COST), 1.0)             # E12 = costo de ida y vuelta -> 15 USDT
        self.assertAlmostEqual(X2.size_mult(COST), 0.5)
        self.assertAlmostEqual(X2.size_mult(1e-5), 5.0 / NOTIONAL_USDT)  # minimo de Binance
        self.assertAlmostEqual(X2.size_mult(0.05), 2.0)                 # tope 30 USDT

    def test_pair_edge_uses_previous_months_only(self):
        folds = [{"ops": 2, "pnl": 0.3}, {"ops": 0, "pnl": 0.0}, {"ops": 1, "pnl": -0.6}, {"ops": 4, "pnl": 9.0}]
        self.assertTrue(np.isnan(X2.pair_edge(folds, 0, 12)))
        self.assertAlmostEqual(X2.pair_edge(folds, 3, 12), (0.3 - 0.6) / 3 / NOTIONAL_USDT)
        self.assertAlmostEqual(X2.pair_edge(folds, 3, 1), -0.6 / NOTIONAL_USDT)


class PStarTest(unittest.TestCase):
    def test_breakeven_win_rate(self):
        x = pd.DataFrame({"c_r": [0.17, 0.0], "b": [2.0, 1.0]})
        np.testing.assert_allclose(X2.p_star(x), [1.17 / 3, 0.5])


if __name__ == "__main__":
    unittest.main()
