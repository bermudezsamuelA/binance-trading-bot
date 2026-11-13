"""Pruebas: utilidades de velas y que la simulación no mire el futuro.

Uso: python -m unittest test_estrategia
"""
import dataclasses
import os
import unittest

import numpy as np

import backtest as B
import estrategia as E


def walk(n, seed=0, step=5 * E.MIN):
    r = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(r.normal(0, 0.002, n)))
    o = np.r_[100, c[:-1]]
    h = np.maximum(o, c) * (1 + abs(r.normal(0, 0.001, n)))
    l = np.minimum(o, c) * (1 - abs(r.normal(0, 0.001, n)))
    T = (np.arange(n) * step + 1_600_000_000_000 // E.DAY * E.DAY).astype(np.int64)
    return {"T": T, "O": o, "H": h, "L": l, "C": c}


class Utils(unittest.TestCase):
    def test_resample(self):
        b = walk(12 * 30)
        h = E.resample(b, E.HOUR, 12)
        self.assertEqual(len(h["T"]), 30)
        self.assertAlmostEqual(h["O"][3], b["O"][36])
        self.assertAlmostEqual(h["C"][3], b["C"][47])
        self.assertAlmostEqual(h["H"][3], b["H"][36:48].max())
        self.assertAlmostEqual(h["L"][3], b["L"][36:48].min())
        h2 = E.resample({k: v[:-5] for k, v in b.items()}, E.HOUR, 12)     # última hora incompleta: fuera
        self.assertEqual(len(h2["T"]), 29)

    def test_pivots_and_confirmation(self):
        x = np.array([5, 4, 3, 4, 5, 6, 5, 4, 5, 6.0])
        self.assertEqual(list(E.pivots(x, 2, high=False)), [2, 7])
        self.assertEqual(list(E.pivots(x, 2, high=True)), [5])
        lc = E.last_confirmed(E.pivots(x, 2, high=False), 2, len(x))
        self.assertEqual(list(lc), [-1, -1, -1, -1, 2, 2, 2, 2, 2, 7])     # el pivote 2 se conoce recién en 4

    def test_ema(self):
        x = np.arange(1, 50.0)
        e = E.ema(x, 9)
        ref, a = [x[0]], 2 / 10
        for v in x[1:]:
            ref.append(a * v + (1 - a) * ref[-1])
        np.testing.assert_allclose(e, ref)


class NoLookahead(unittest.TestCase):
    """Cortar los datos en un instante no cambia ninguna decisión tomada antes de ese instante."""

    def check(self, base, bms, p):
        full = E.Coin("X", base, bms)
        tr, _ = E.run_coin(full, p)
        self.assertGreater(len(tr), 0, "la prueba necesita alguna operación")
        for t in tr[: min(5, len(tr))]:
            cut = t.t_entrada
            k = np.searchsorted(base["T"], cut)                    # velas que cierran a más tardar en `cut`
            part = E.Coin("X", {kk: v[:k] for kk, v in base.items()}, bms)
            tr2, _ = E.run_coin(part, dataclasses.replace(p, max_dias=0))
            ent = {(x.dia_senal, x.t_entrada, round(x.entrada, 8)) for x in tr2}
            self.assertIn((t.dia_senal, t.t_entrada, round(t.entrada, 8)), ent)

    def test_real_data(self):
        b = B.load("BTCUSDT", "15m", B.DIRS["15m"])
        if b is None:
            self.skipTest("sin datos de 15 min")
        p = dataclasses.replace(B.VIDEO, theta=1.5, usar_c3=False, c_conf=2.0, gatillo="ema")
        self.check(b, 15 * E.MIN, p)


if __name__ == "__main__":
    unittest.main()
