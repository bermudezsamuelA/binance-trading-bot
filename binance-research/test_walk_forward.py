"""
walk_forward.run_folds sin datos reales: una posición por moneda entre meses de prueba (como el bot), la validación
final hereda la operación abierta del desarrollo y las operaciones que salen en la reserva no cuentan en el desarrollo.

    .venv\\Scripts\\python -m unittest test_walk_forward -v     (o npm run test:python desde la raíz)
"""
import unittest

import numpy as np
import pandas as pd

import walk_forward as wf

MONTH = 100  # velas por "mes" en este ejemplo


class FakeFS:
    """FastSymbol mínimo: en cada mes hay una señal en a + 10 y la operación dura `hold` velas."""

    def __init__(self, hold):
        self.hold = hold
        self.calls = []

    def simulate(self, strategy, w, m, first=0, start=0, entry_end=None, stop=None):
        self.calls.append({"first": first, "start": start, "entry_end": entry_end})
        a = entry_end - MONTH
        entries = [i for i in (a + 10,) if start <= i < entry_end]
        exits = [i + self.hold for i in entries]
        return (np.asarray(entries, dtype=np.int64), np.asarray(exits, dtype=np.int64),
                np.ones(len(entries), dtype=np.float64))


class FakeEV:
    def __init__(self, hold):
        self.fs = FakeFS(hold)
        self.strategy = "TrendFollowing"

    @staticmethod
    def idx(ts):
        return int(ts)

    def select(self, train):
        return {"combo": (20, 2.0), "trades": 30, "wins": 15, "pnl": 1.0, "operar": True}

    test_trades = wf.PairEvaluator.test_trades


def folds(starts, limit, kind="dev"):
    return [{"name": str(a), "kind": kind, "train": (a - 6 * MONTH, a), "test": (a, a + MONTH), "limit": limit}
            for a in starts]


class RunFoldsTest(unittest.TestCase):
    def test_un_mes_no_abre_mientras_sigue_abierta_la_del_anterior(self):
        ev = FakeEV(hold=150)                     # la operación del mes 1000 (entra en 1010) sale en 1160
        rows, e, x, p, open_until = wf.run_folds(ev, folds([1000, 1100, 1200], limit=5000))
        # el mes 1100 no abre (su señal en 1110 llega con la anterior abierta); el 1200 sí (1210 > 1160)
        self.assertEqual(e.tolist(), [1010, 1210])
        self.assertEqual(x.tolist(), [1160, 1360])
        self.assertEqual([r["ops"] for r in rows], [1, 0, 1])
        self.assertEqual(ev.fs.calls[1]["start"], 1161)          # empieza en la vela siguiente a la salida
        self.assertEqual(ev.fs.calls[1]["first"], 1100 - wf.preseed_candles(20))   # precarga desde el mes
        self.assertEqual(open_until, 1360)
        self.assertTrue(np.all(e[1:] > x[:-1]))                  # nunca dos posiciones a la vez

    def test_la_reserva_hereda_la_operacion_abierta_y_no_cuenta_en_desarrollo(self):
        ev = FakeEV(hold=150)
        # el último mes de desarrollo (1100) abre en 1110 y sale en 1260, dentro de la reserva (limit = 1200)
        rows, e, x, p, open_until = wf.run_folds(ev, folds([1000, 1100], limit=1200)[1:])
        self.assertEqual(e.tolist(), [])                        # su salida cae en la reserva: no cuenta
        self.assertEqual(open_until, 1260)                      # pero bloquea la reserva
        hrows, he, hx, hp, _ = wf.run_folds(ev, folds([1200], limit=5000, kind="holdout"), open_until)
        self.assertEqual(he.tolist(), [])                       # la señal de 1210 llega con la posición abierta
        self.assertEqual(ev.fs.calls[-1]["start"], 1261)


if __name__ == "__main__":
    unittest.main()
