import unittest

import numpy as np

import common as C


def make_lib(seed=0, n=400, nc=2, d=5):
    r = np.random.default_rng(seed)
    X = r.normal(size=(n * nc, d)).astype(np.float32)
    coin = np.repeat(np.arange(nc), n)
    t = np.tile(np.arange(n), nc)
    return C.Library(X, coin, t), r


class KnnTest(unittest.TestCase):
    def test_no_future_and_exact(self):
        lib, r = make_lib()
        Q = r.normal(size=(50, 5)).astype(np.float32)
        qt = r.integers(30, 400, 50)
        I, D = C.knn(lib, Q, qt, k=5, lag=24, sep=1)
        for i in range(50):
            ok = I[i] >= 0
            self.assertTrue((lib.t[I[i][ok]] <= qt[i] - 24).all())
            allowed = np.flatnonzero(lib.t <= qt[i] - 24)
            d = np.sqrt(((lib.X[allowed] - Q[i]) ** 2).sum(1))
            np.testing.assert_allclose(np.sort(d)[:ok.sum()], D[i][ok], rtol=1e-3, atol=1e-3)

    def test_one_per_episode(self):
        lib, r = make_lib(1)
        Q = r.normal(size=(30, 5)).astype(np.float32)
        I, _ = C.knn(lib, Q, np.full(30, 399), k=10, sep=12)
        for row in I:
            keys = [(lib.coin[j], lib.t[j] // 12) for j in row if j >= 0]
            self.assertEqual(len(keys), len(set(keys)))

    def test_empty_library(self):
        lib, r = make_lib(2)
        I, D = C.knn(lib, r.normal(size=(3, 5)), np.array([5, 10, 20]), k=3)
        self.assertTrue((I == -1).all() and np.isinf(D).all())


class RuleTest(unittest.TestCase):
    def test_no_overlap_and_threshold(self):
        H = C.HOUR
        t = np.arange(0, 48) * H
        coin = np.zeros(48, int)
        yhat = np.full(48, 0.01); frac = np.full(48, 0.9); y = np.full(48, 0.02)
        yhat[5] = 0.001                                     # no paga el costo
        tt, cc, net = C.trades(t, coin, yhat, frac, y, h=24, q=0.6)
        self.assertEqual(list(tt // H), [0, 24])
        self.assertAlmostEqual(net[0], np.exp(0.02) - 1 - C.COST)

    def test_predict_weights(self):
        y = np.array([0.01, -0.02, 0.03])
        yhat, frac = C.predict(y, np.array([[0, 1, 2]]), np.array([[0.0, 1.0, 1.0]]), 3, weighted=False)
        self.assertAlmostEqual(yhat[0], np.mean(y)); self.assertAlmostEqual(frac[0], 2 / 3)
        yhat_w, _ = C.predict(y, np.array([[0, 1, 2]]), np.array([[0.0, 1.0, 1.0]]), 3, weighted=True)
        self.assertAlmostEqual(yhat_w[0], 0.01, places=4)


class DataTest(unittest.TestCase):
    def test_hourly_alignment(self):
        try:
            d = C.load_hourly(["BTCUSDT"], start=C.to_ms("2024-01-01"))
        except FileNotFoundError:
            self.skipTest("sin datos locales")
        self.assertTrue((np.diff(d["T"]) == C.HOUR).all())
        self.assertTrue(np.isfinite(d["close"]).all())


if __name__ == "__main__":
    unittest.main()
