"""
replication.py sin datos descargados: la cartera combina las operaciones de todas las monedas por dia, la decision
exige PnL combinado > 0, p < 0.025, mayoria de monedas ganadoras, meses positivos y no perder en la validacion final,
y walk_forward.evaluate_pair devuelve las operaciones con las que se combina (las mismas de su OOS).

    .venv\\Scripts\\python -m unittest test_replication -v
"""
import unittest

import numpy as np
import pandas as pd

import replication as RP
import walk_forward as wf
from config import KLINE_INTERVAL
from fast_backtest import INTERVAL_MS

DAY = 86_400_000
T0 = 1_700_000_000_000


def fake_result(symbol, strategy, pnls, days, hold_pnl=(0.1,), p=0.5):
    pnls = np.asarray(pnls, float)
    exits = [T0 + d * DAY for d in days]
    months = pd.to_datetime(exits, unit="ms", utc=True).strftime("%Y-%m")
    by_month = pd.Series(pnls).groupby(np.asarray(months)).sum()
    return {"symbol": symbol, "strategy": strategy, "momentum": {"encendido": True},
            "oos": {"trades": len(pnls), "pnl": float(pnls.sum()), "win_rate": 100 * float(np.mean(pnls > 0)),
                    "pliegues_positivos_pct": 100 * float((by_month > 0).mean()), "p_valor": p, "t_dia": 0.0},
            "validacion_final": {"pnl": float(sum(hold_pnl))},
            "vivo": {"operar": True}, "vivo_motivo": None,
            "operaciones": {"oos": {"salida_ms": exits, "pnl": pnls.tolist()},
                            "validacion": {"salida_ms": [T0 + 900 * DAY] * len(hold_pnl), "pnl": list(hold_pnl)}}}


class CombineTest(unittest.TestCase):
    def test_cartera_que_gana_en_la_mayoria_pasa(self):
        rng = np.random.default_rng(0)
        results = [fake_result(f"C{k}USDT", "TrendFollowing", rng.normal(0.08, 0.3, 120), np.arange(0, 600, 5))
                   for k in range(10)]
        out = RP.combine(results, "TrendFollowing")
        c = out["combinado"]
        self.assertEqual(c["ops"], 1200)
        self.assertAlmostEqual(c["pnl"], round(sum(r["oos"]["pnl"] for r in results), 4), places=3)
        self.assertGreater(c["monedas_ganadoras"], 5)
        self.assertLess(c["p_valor"], RP.ALPHA)
        self.assertTrue(c["pasa"], c["motivo"])
        # el PnL por moneda queda ordenado de mayor a menor y cada una trae su estado estricto
        pnls = [r["pnl"] for r in out["por_moneda"]]
        self.assertEqual(pnls, sorted(pnls, reverse=True))
        self.assertTrue(all(r["estricta"] in ("validada", "rechazada") for r in out["por_moneda"]))

    def test_pnl_combinado_positivo_por_una_sola_moneda_no_pasa(self):
        results = [fake_result("AUSDT", "TrendFollowing", [5.0] * 40, range(0, 400, 10))]
        results += [fake_result(f"L{k}USDT", "TrendFollowing", [-0.05] * 40, range(1, 401, 10)) for k in range(5)]
        c = RP.combine(results, "TrendFollowing")["combinado"]
        self.assertGreater(c["pnl"], 0)
        self.assertEqual((c["monedas_ganadoras"], c["monedas_con_operaciones"]), (1, 6))
        self.assertFalse(c["pasa"])
        self.assertIn("1 de 6 monedas ganan", c["motivo"])

    def test_pierde_en_la_validacion_final_no_pasa(self):
        rng = np.random.default_rng(1)
        results = [fake_result(f"C{k}USDT", "VolatilitySqueeze", rng.normal(0.1, 0.2, 100), range(0, 500, 5),
                               hold_pnl=(-1.0,)) for k in range(6)]
        c = RP.combine(results, "VolatilitySqueeze")["combinado"]
        self.assertFalse(c["pasa"])
        self.assertIn("validacion final", c["motivo"])

    def test_solo_cuenta_la_estrategia_pedida(self):
        results = [fake_result("AUSDT", "TrendFollowing", [1.0], [0]), fake_result("AUSDT", "VolatilitySqueeze", [-1.0], [0])]
        self.assertEqual(RP.combine(results, "VolatilitySqueeze")["combinado"]["pnl"], -1.0)

    def test_t_por_dia_suma_las_monedas_del_mismo_dia(self):
        days, t, p = RP.daily_t([T0, T0 + 1, T0 + DAY, T0 + 2 * DAY], [1.0, 1.0, 1.0, 3.0])
        self.assertEqual(days, 3)                       # las dos primeras salen el mismo dia: un solo dato (2.0)
        self.assertAlmostEqual(t, 2.0 / (np.std([2.0, 1.0, 3.0], ddof=1) / np.sqrt(3)))
        self.assertEqual(RP.daily_t([], []), (0, 0.0, 1.0))
        self.assertEqual(RP.max_drawdown([T0, T0 + 1, T0 + 2], [1.0, -3.0, 1.0]), 3.0)


class EvaluatePairOperationsTest(unittest.TestCase):
    """evaluate_pair con velas sinteticas: las operaciones devueltas son exactamente las de su OOS y su validacion."""

    def test_operaciones_cuadran_con_el_oos(self):
        candle = INTERVAL_MS[KLINE_INTERVAL]
        n = int(15 * 30 * DAY / candle)                 # ~15 meses

        def fake_history(symbol, interval="15m", **kw):
            r = np.random.default_rng(sum(map(ord, symbol)))
            c = 100 * np.exp(np.cumsum(r.normal(0, 0.006, n)))
            o = np.r_[c[0], c[:-1]]
            return pd.DataFrame({"open_time": T0 - T0 % (30 * DAY) + np.arange(n) * candle, "open": o,
                                 "high": np.maximum(o, c) * 1.003, "low": np.minimum(o, c) * 0.997, "close": c,
                                 "volume": r.uniform(50, 150, n), "taker_buy": r.uniform(20, 70, n)})
        original = wf.load_history
        wf.load_history = fake_history
        try:
            res = wf.evaluate_pair(("AAAUSDT", "TrendFollowing", wf.TRAIN_MONTHS, None, KLINE_INTERVAL,
                                    ("AAAUSDT", "BBBUSDT")))
        finally:
            wf.load_history = original
        ops = res["operaciones"]
        self.assertGreater(res["oos"]["trades"], 0)
        self.assertEqual(len(ops["oos"]["pnl"]), res["oos"]["trades"])
        self.assertAlmostEqual(sum(ops["oos"]["pnl"]), res["oos"]["pnl"], places=3)
        self.assertEqual(len(ops["validacion"]["pnl"]), res["validacion_final"]["trades"])
        self.assertEqual(len(ops["oos"]["salida_ms"]), len(ops["oos"]["pnl"]))


if __name__ == "__main__":
    unittest.main()
