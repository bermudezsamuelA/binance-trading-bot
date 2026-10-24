"""v3_trader.py sin red: cola de senales S1H, niveles en porcentaje, barrera de tiempo desde el ledger y monedas de la testnet."""
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v3_trader as VT  # noqa: E402

T = 1_792_800_000_000 - 1_792_800_000_000 % VT.MS15


def row(sym, brazo="S1H", t=T, price=100.0, tp=103.0, sl=95.0):
    return {"symbol": sym, "brazo": brazo, "open_time_ms": t, "precio": price, "tp": tp, "sl": sl, "p": 0.8}


class TraderTest(unittest.TestCase):
    def make(self, rows, now=None):
        clock = {"t": (now or T + 2 * 60_000) / 1000}
        tr = VT.V3Trader(["AAAUSDT", "BBBUSDT"], lambda: rows, now=lambda: clock["t"])
        return tr, clock

    def test_solo_s1h_del_universo_con_niveles_en_fraccion(self):
        tr, _ = self.make([row("AAAUSDT"), row("AAAUSDT", brazo="S1"), row("ZZZUSDT"), row("BBBUSDT", price=200.0, tp=206.0, sl=190.0)])
        self.assertEqual(tr.tick(), 2)
        out = tr.poll([])
        self.assertEqual([s["symbol"] for s in out["signals"]], ["AAAUSDT", "BBBUSDT"])
        a = out["signals"][0]
        self.assertAlmostEqual(a["tp_pct"], 0.03)
        self.assertAlmostEqual(a["sl_pct"], 0.05)
        self.assertEqual(a["open_time"], T)

    def test_no_repite_ni_entrega_dos_veces(self):
        tr, _ = self.make([row("AAAUSDT")])
        tr.tick()
        tr.tick()                                   # la misma vela otra vez: no se duplica en la cola
        self.assertEqual(len(tr.poll([])["signals"]), 1)
        tr.tick()                                   # ya entregada: no vuelve
        self.assertEqual(tr.poll([])["signals"], [])

    def test_senal_vieja_no_se_entrega(self):
        tr, clock = self.make([row("AAAUSDT")])
        tr.tick()
        clock["t"] = (T + 4 * VT.MS15) / 1000
        self.assertEqual(tr.poll([])["signals"], [])

    def test_barrera_de_tiempo_desde_el_ledger(self):
        tr, clock = self.make([])
        entry = T
        trades = [{"symbol": "AAAUSDT", "timestamp": entry}, {"symbol": "BBBUSDT", "timestamp": entry + 10 * VT.MS15},
                  {"symbol": "CCCUSDT", "timestamp": None}]
        clock["t"] = (entry + VT.TIME_STOP_MS - 1) / 1000
        self.assertEqual(tr.poll(trades)["exits"], [])
        clock["t"] = (entry + VT.TIME_STOP_MS) / 1000
        self.assertEqual(tr.poll(trades)["exits"], ["AAAUSDT"])
        clock["t"] = (entry + 10 * VT.MS15 + VT.TIME_STOP_MS) / 1000
        self.assertEqual(tr.poll(trades)["exits"], ["AAAUSDT", "BBBUSDT"])

    def test_historia_una_vez_al_dia_y_error_no_detiene(self):
        calls = []
        tr = VT.V3Trader(["AAAUSDT"], lambda: [], now=lambda: T / 1000, history_update=lambda d: calls.append(d))
        tr.tick()
        tr.tick()
        self.assertEqual(len(calls), 1)
        bad = VT.V3Trader(["AAAUSDT"], lambda: [], now=lambda: T / 1000,
                          history_update=lambda d: (_ for _ in ()).throw(RuntimeError("sin red")))
        self.assertEqual(bad.tick(), 0)             # no lanza; reintenta en el siguiente ciclo
        self.assertIsNone(bad.last_history_day)

    def test_monedas_que_cotizan_en_la_testnet(self):
        info = {"symbols": [{"symbol": "AAAUSDT", "status": "TRADING", "quoteAsset": "USDT"},
                            {"symbol": "BBBUSDT", "status": "BREAK", "quoteAsset": "USDT"},
                            {"symbol": "CCCBTC", "status": "TRADING", "quoteAsset": "BTC"}]}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        got = VT.testnet_symbols("https://x", ["AAAUSDT", "BBBUSDT", "CCCUSDT"], opener=lambda url, timeout: Resp(json.dumps(info).encode()))
        self.assertEqual(got, ["AAAUSDT"])


if __name__ == "__main__":
    unittest.main()
