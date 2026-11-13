"""coinalyze.py sin red: formato de Binance de las series, desfases, reintento con 429 y clave obligatoria."""
import io
import json
import os
import sys
import unittest
import urllib.error

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coinalyze as CZ  # noqa: E402

T0 = 1_792_800_000_000 - 1_792_800_000_000 % (8 * 3_600_000)


def raw(n=300):
    t5 = T0 + np.arange(n) * 300_000
    t15 = T0 + np.arange(n // 3) * 900_000
    th = T0 + np.arange(n // 12) * 3_600_000
    return {"oi": np.column_stack([t5, 1000 + np.arange(n)]).astype(float),
            "ls": np.column_stack([t5, np.full(n, 2.0)]).astype(float),
            "k5": np.column_stack([t5, np.full(n, 50.0), np.full(n, 10.0), np.full(n, 4.0)]).astype(float),
            "k15": np.column_stack([t15, *([np.full(len(t15), 50.0)] * 4), np.full(len(t15), 30.0),
                                    np.full(len(t15), 12.0)]).astype(float),
            "fr": np.column_stack([th, np.full(len(th), 0.01)]).astype(float)}


class ToBinanceTest(unittest.TestCase):
    def test_formato_de_nn_download_futures(self):
        out = CZ.to_binance(raw(), {"oi": 0, "ls": -300_000, "k5": 0, "k15": 0, "fr": 0})
        M = out["metrics"]
        self.assertEqual(M.shape[1], 7)
        self.assertTrue(np.all(np.isnan(M[:, 3])) and np.all(np.isnan(M[:, 4])))   # sin top traders
        np.testing.assert_allclose(M[:, 2], M[:, 1] * 50.0)                         # OI x precio
        np.testing.assert_allclose(M[:, 6], 4.0 / 6.0)                              # bv / (v - bv)
        self.assertTrue(np.isnan(M[-1, 5]))                                          # ls corrido 5 min: la ultima no tiene par
        self.assertEqual(out["fut15m"].shape[1], 7)
        F = out["funding"]
        self.assertTrue(np.all(F[:, 0].astype(np.int64) % (8 * 3_600_000) == 0))     # solo horas de liquidacion
        np.testing.assert_allclose(F[:, 1], 0.0001)                                 # Coinalyze da el funding en %

    def test_desfase_que_mejor_alinea(self):
        t = T0 + np.arange(400) * 300_000
        x = 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, 400))
        off, corr = CZ.align_offset(t, x, t - 300_000, x, 300_000, log_diff=False)
        self.assertEqual(off, 300_000)
        self.assertGreater(corr, 0.999)


class CacheTest(unittest.TestCase):
    def test_la_historia_crece_entre_corridas(self):
        import tempfile
        calls = []

        def fake_raw(cz, symbols, t0, t1):
            calls.append((t0, t1))
            k = len(calls)
            rows = np.column_stack([T0 + np.arange(k, k + 3) * 300_000, np.arange(3.0) + 10 * k])
            return {s: {"oi": rows, "ls": rows, "k5": np.zeros((0, 4)), "k15": np.zeros((0, 7)), "fr": rows} for s in symbols}
        original = CZ.raw_series
        CZ.raw_series = fake_raw
        try:
            with tempfile.TemporaryDirectory() as tmp:
                CZ.update_cache(None, ["BTCUSDT"], T0, tmp)
                out = CZ.update_cache(None, ["BTCUSDT"], T0, tmp)
        finally:
            CZ.raw_series = original
        oi = out["BTCUSDT"]["oi"]
        self.assertEqual(((oi[:, 0] - T0) // 300_000).tolist(), [1, 2, 3, 4])   # union sin repetidas
        self.assertEqual(oi[0, 1], 10.0)                                         # la primera guardada se conserva
        self.assertEqual(len(out["BTCUSDT"]["k5"]), 0)


class ClientTest(unittest.TestCase):
    def test_reintenta_con_429_y_manda_la_clave_en_la_cabecera(self):
        calls = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout=60):
            calls.append(req)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {"Retry-After": "0"}, None)
            return Resp(json.dumps([{"symbol": "BTCUSDT_PERP.A", "history": [{"t": 1, "c": 2}]}]).encode())
        cz = CZ.Coinalyze("clave-de-prueba", opener=opener, sleep=lambda s: None)
        out = cz.history("open-interest-history", ["BTCUSDT"], "5min", 0, 10)
        self.assertEqual(out, {"BTCUSDT": [{"t": 1, "c": 2}]})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1].get_header("Api_key"), "clave-de-prueba")
        self.assertIn("symbols=BTCUSDT_PERP.A", calls[-1].full_url)

    def test_sin_clave_no_arranca_y_la_lee_del_env(self):
        import tempfile
        saved, saved_file = os.environ.pop("COINALYZE_API_KEY", None), CZ.ENV_FILE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                CZ.ENV_FILE = os.path.join(tmp, ".env")
                with self.assertRaises(RuntimeError):
                    CZ.Coinalyze()
                with open(CZ.ENV_FILE, "w", encoding="utf-8") as f:
                    f.write('BINANCE_MARKET="testnet"\nCOINALYZE_API_KEY="abc-123"\n')
                self.assertEqual(CZ.env_file_value("COINALYZE_API_KEY", CZ.ENV_FILE), "abc-123")
                self.assertEqual(CZ.Coinalyze().api_key, "abc-123")
        finally:
            CZ.ENV_FILE = saved_file
            if saved is not None:
                os.environ["COINALYZE_API_KEY"] = saved


if __name__ == "__main__":
    unittest.main()
