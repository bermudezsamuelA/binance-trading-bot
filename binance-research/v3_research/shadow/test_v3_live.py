"""v3_live.py sin red: historia hasta ayer + velas spot de la API + futuros de Coinalyze, y las senales anotadas."""
import csv
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import coinalyze as CZ  # noqa: E402
import run_daily as RD  # noqa: E402
import v3_live as VL  # noqa: E402
from test_run_daily import write_synthetic  # noqa: E402

CUT = RD.to_ms("2026-10-19")          # data.binance.vision llega hasta aqui; despues, API spot y Coinalyze
NOW = RD.to_ms("2026-10-20") + 5 * 60_000


def raw_from(full: str, sym: str) -> dict:
    """Series 'de Coinalyze' sacadas de los datos completos (lo que daria Coinalyze si fuera exacto)."""
    fu = RD.C.load_fut(full, sym)
    M, K, F = fu["metrics"], fu["fut15m"], fu["funding"]
    r = M[:, 6]
    close = np.interp(M[:, 0], K[:, 0], K[:, 4])
    return {"oi": M[:, [0, 1]], "ls": M[:, [0, 5]],
            "k5": np.column_stack([M[:, 0], close, np.full(len(M), 2.0), 2.0 * r / (1 + r)]),
            "k15": K.copy(), "fr": np.column_stack([F[:, 0] - F[:, 0] % 3_600_000, F[:, 1] * 100])}


class LiveTest(unittest.TestCase):
    def test_ultima_vela_con_coinalyze_y_api_spot(self):
        syms = RD.UNIVERSE[:6]
        with tempfile.TemporaryDirectory() as full, tempfile.TemporaryDirectory() as hist:
            write_synthetic(full, symbols=syms)
            write_synthetic(hist, symbols=syms, t1=CUT)                  # misma semilla: mismos datos hasta CUT
            raw = {s: raw_from(full, s) for s in syms}
            spot = lambda s, start: (lambda a: a[a[:, 0] >= start])(RD.C.load_spot(full, s))
            last_open = NOW - NOW % RD.C.MS15 - RD.C.MS15
            original_cache, original_predict = CZ.update_cache, RD.V3.predict
            CZ.update_cache = lambda cz, symbols, now_ms, *a, **k: raw

            def fake_predict(members, X, ridx, Q):
                p = np.zeros(len(X))
                p[ridx[-1:]] = 0.99                                       # senal en la ultima vela evaluada
                return p
            RD.V3.predict = fake_predict
            try:
                out = os.path.join(hist, "vivo.csv")
                with redirect_stdout(io.StringIO()):
                    res = VL.run_once(hist, syms, cz=object(), spot_fetch=spot, now_ms=NOW, out_file=out)
                    again = VL.run_once(hist, syms, cz=object(), spot_fetch=spot, now_ms=NOW, out_file=out)
            finally:
                CZ.update_cache, RD.V3.predict = original_cache, original_predict
            self.assertEqual(res["vela"], RD.iso(last_open))
            self.assertTrue(res["fuente_futuros"].startswith("Coinalyze"))
            arms = {(r["symbol"], r["brazo"]) for r in res["senales"]}
            self.assertEqual({s for s, a in arms if a == "S1"}, set(syms))          # 5 otras con senal: A18 = 5 >= 3
            self.assertEqual({s for s, a in arms if a == "P1"}, set(RD.ANCHORS))
            self.assertEqual({s for s, a in arms if a == "S1H"}, set(syms))                # p = 0.99 >= 0.745
            r0 = res["senales"][0]
            self.assertLess(r0["sl"], r0["precio"])
            self.assertLess(r0["precio"], r0["tp"])
            self.assertEqual(again["nuevas"], 0)                                    # no repite filas
            with open(out, newline="", encoding="utf-8") as f:
                self.assertEqual(len(list(csv.DictReader(f))), len(res["senales"]))


if __name__ == "__main__":
    unittest.main()
