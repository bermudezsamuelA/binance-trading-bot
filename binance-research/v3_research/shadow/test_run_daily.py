"""Pruebas del canal sombra v3 sin red: datos sinteticos con el formato de nn_download_futures.py y harness.py.

  python -m unittest discover -s v3_research/shadow -p "test_*.py"     (desde binance-research)
"""
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import feeds  # noqa: E402
import run_daily as RD  # noqa: E402

MS15 = 900_000
T0 = RD.to_ms("2026-08-10")
T1 = RD.to_ms("2026-10-20")


def write_synthetic(data_dir, seed=0, t0=T0, t1=T1, funding_until=None, symbols=None):
    """Velas spot y series de futuros de las 4 anclas con una caida comun (un 'panico') a mitad de octubre. El funding
    sale de la prima con la formula de Binance mas ruido (como el real); funding_until lo corta antes (mes sin archivo)."""
    rng = np.random.default_rng(seed)
    t = np.arange(t0, t1, MS15, dtype=np.int64)
    n = len(t)
    common = rng.normal(0, 0.003, n)
    crash = (t >= RD.to_ms("2026-10-08")) & (t < RD.to_ms("2026-10-08") + 8 * MS15)
    common[crash] -= 0.02
    os.makedirs(os.path.join(data_dir, "klines"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "futures"), exist_ok=True)
    for k, sym in enumerate(symbols or RD.ANCHORS):
        lr = common + rng.normal(0, 0.003, n)
        c = 100.0 * (k + 1) * np.exp(np.cumsum(lr))
        o = np.r_[c[0], c[:-1]]
        h, l = np.maximum(o, c) * (1 + rng.uniform(0, 0.002, n)), np.minimum(o, c) * (1 - rng.uniform(0, 0.002, n))
        v = rng.uniform(100, 200, n) * (1 + 3 * crash)
        np.save(os.path.join(data_dir, "klines", f"{sym}_15m.npy"),
                np.column_stack([t, o, h, l, c, v, v * rng.uniform(0.3, 0.7, n)]).astype(np.float64))
        tm = np.arange(t0, t1, 300_000, dtype=np.int64)
        m = len(tm)
        oi = 1e6 * np.exp(np.cumsum(rng.normal(0, 0.001, m)))
        metrics = np.column_stack([tm, oi, oi * 100, rng.uniform(1, 3, m), rng.uniform(1, 3, m), rng.uniform(1, 3, m),
                                   rng.uniform(0.7, 1.3, m)])
        # prima que a ratos sale de la banda de +-0.05 % (dentro de ella el funding es justo 0.01 %, como en Binance)
        prem = np.convolve(rng.normal(0, 2e-3, n), np.ones(8) / 8, mode="same") + 8e-4 * np.sin(np.arange(n) / 300)
        premium = np.column_stack([t, prem, prem + 1e-4, prem - 1e-4, prem])
        funding = RD.funding_proxy(premium, t0, t1)
        funding[:, 0] += 5                                  # la marca real trae milisegundos
        funding[:, 1] += rng.normal(0, 2e-6, len(funding))
        if funding_until is not None:
            funding = funding[funding[:, 0] < funding_until]
        fc = c * (1 + rng.normal(0, 3e-4, n))
        fv = v * 5
        fut = np.column_stack([t, o, h, l, fc, fv, fv * rng.uniform(0.3, 0.7, n)])
        for name, arr in (("metrics", metrics), ("funding", funding), ("premium15m", premium), ("fut15m", fut)):
            np.save(os.path.join(data_dir, "futures", f"{sym}_{name}.npy"), arr.astype(np.float64))


class StatsTest(unittest.TestCase):
    def test_episodios_separados_por_mas_de_dos_dias(self):
        day = RD.DAY_MS
        et = np.array([0, day, 3 * day, 7 * day, 7 * day + 1]) + T0
        self.assertEqual(RD.episodes(et, [1, -0.5, 1, -1, -1]), [1.5, -2.0])

    def test_e_proceso_crece_con_wr_alto_y_no_con_wr_bajo(self):
        rng = np.random.default_rng(0)
        high = RD.e_process(rng.random(400) < 0.85)
        low = RD.e_process(rng.random(400) < 0.60)
        self.assertGreater(high[-1], RD.E_STOP)
        self.assertLess(low[-1], 1.0)
        self.assertTrue(all(m > 0 for m in high + low))

    def test_bootstrap_por_dias(self):
        a, b = np.full(30, 0.01), np.full(30, -0.01)
        d = np.arange(30)
        self.assertEqual(RD.boot_diff_days(a, d, b, d, B=500), 0.0)
        self.assertEqual(RD.boot_diff_days(b, d, a, d, B=500), 1.0)
        self.assertTrue(np.isnan(RD.boot_diff_days(a[:1], d[:1], b, d)))

    def test_dvol_z30_y_hora_cerrada(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dvol.json")
            hours = [[T0 + h * 3_600_000, 50, 50, 50, 50.0 + (h % 7)] for h in range(800)]
            with open(path, "w") as fh:
                json.dump(hours, fh)
            ser = RD.dvol_z30(path)
            self.assertTrue(np.isnan(ser[1][718]) and np.isfinite(ser[1][719]))
            # la vela que abre justo al cerrar la hora h usa el z de h; la que abre 1 ms antes, el de h - 1
            t_close = int(ser[0][750])
            z = RD.z_at_open(ser, [t_close, t_close - 1, t_close + 3 * 3_600_000 + RD.DAY_MS * 400])
            self.assertEqual(z[0], ser[1][750])
            self.assertEqual(z[1], ser[1][749])
            self.assertTrue(np.isnan(z[2]))          # DVOL de hace mas de 2 h: no veta
            self.assertTrue(np.isnan(RD.z_at_open(None, [t_close])[0]))


class DataEndTest(unittest.TestCase):
    def test_corte_por_la_serie_mas_atrasada(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_synthetic(tmp, t1=RD.to_ms("2026-08-20"))
            end, limits = RD.data_end_ms(tmp)
            self.assertEqual(end % MS15, 0)
            self.assertEqual(end, min(limits.values()) - min(limits.values()) % MS15)
            # el funding (cada 8 h) es la serie que manda
            self.assertTrue(min(limits, key=limits.get).endswith("funding")
                            or min(limits.values()) == RD.to_ms("2026-08-20"))


class FeedsTest(unittest.TestCase):
    def test_meses_completos_y_dias_del_mes_en_curso(self):
        months, days = feeds.split_months(dt.date(2026, 8, 30), dt.date(2026, 10, 2), today=dt.date(2026, 10, 3))
        self.assertEqual(months, [(2026, 8), (2026, 9)])
        self.assertEqual(days, [dt.date(2026, 10, 1), dt.date(2026, 10, 2)])

    def test_spot_en_microsegundos(self):
        txt = "1767225600000000,1,2,0.5,1.5,10,1767226499999999,15,3,4,6,0\nopen_time,x\n"
        self.assertEqual(feeds.parse_spot(txt), [(1767225600000, 1.0, 2.0, 0.5, 1.5, 10.0, 4.0)])

    def test_dvol_pagina_y_fusiona(self):
        pages = [{"result": {"data": [[3_600_000 * 5, 1, 1, 1, 50], [3_600_000 * 6, 1, 1, 1, 51]], "continuation": 3_600_000 * 4}},
                 {"result": {"data": [[3_600_000 * 3, 1, 1, 1, 49]], "continuation": None}}]

        class Resp:
            def __init__(self, body):
                self.body = body

            def read(self):
                return json.dumps(self.body).encode()
        calls = []

        def opener(url, timeout=60):
            calls.append(url)
            return Resp(pages[len(calls) - 1])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dvol_BTC_1h.json")
            with open(path, "w") as fh:
                json.dump([[3_600_000 * 2, 1, 1, 1, 48], [3_600_000 * 3, 1, 1, 1, 0]], fh)
            rep = feeds.update_dvol(("BTC",), tmp, now_ms=3_600_000 * 7, opener=opener)
            with open(path) as fh:
                rows = json.load(fh)
        self.assertEqual(rep, {"BTC": 2})
        self.assertEqual([r[0] // 3_600_000 for r in rows], [2, 3, 5, 6])
        self.assertEqual(rows[1][4], 49)             # la hora repetida se actualiza con la descarga nueva
        self.assertIn("start_timestamp=10800000", calls[0])   # desde la ultima hora guardada


class FundingProxyTest(unittest.TestCase):
    def premium(self, values, t0=RD.to_ms("2026-10-01")):
        t = t0 + np.arange(len(values)) * MS15
        return np.column_stack([t, values, values, values, values]).astype(float)

    def test_formula_de_binance(self):
        for p, expected in ((0.0, 1e-4), (0.001, 0.0005), (-0.002, -0.0015), (2e-4, 1e-4)):
            rows = RD.funding_proxy(self.premium(np.full(32, p)), RD.to_ms("2026-10-01"), RD.to_ms("2026-10-01 08:00"))
            self.assertEqual(rows[:, 0].tolist(), [RD.to_ms("2026-10-01 08:00")])
            self.assertAlmostEqual(rows[0, 1], expected)

    def test_media_ponderada_y_huecos(self):
        x = np.linspace(0, 0.0031, 32)
        rows = RD.funding_proxy(self.premium(x), RD.to_ms("2026-10-01"), RD.to_ms("2026-10-01 08:00"))
        P = np.sum(np.arange(1, 33) * x) / np.sum(np.arange(1, 33))
        self.assertAlmostEqual(rows[0, 1], P + np.clip(1e-4 - P, -5e-4, 5e-4))
        holed = np.delete(self.premium(np.zeros(32)), 5, axis=0)       # falta una vela: no se reconstruye
        self.assertEqual(len(RD.funding_proxy(holed, RD.to_ms("2026-10-01"), RD.to_ms("2026-10-01 08:00"))), 0)

    def test_reemplaza_solo_despues_del_corte_y_restaura(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_synthetic(tmp, t1=RD.to_ms("2026-09-05"), funding_until=RD.to_ms("2026-09-01"))
            real = RD.C.load_fut(tmp, "BTCUSDT")["funding"]
            original = RD.C.load_fut
            with RD.ProxyFunding():
                fu = RD.C.load_fut(tmp, "BTCUSDT")["funding"]
            self.assertIs(RD.C.load_fut, original)
            self.assertEqual(fu[:len(real)].tolist(), real.tolist())
            self.assertGreater(len(fu), len(real))
            self.assertTrue(np.all(fu[len(real):, 0] > real[:, 0].max()))
            self.assertTrue(np.all(np.diff(fu[:, 0]) > 0))


class PipelineTest(unittest.TestCase):
    """De punta a punta con los 13 modelos congelados (hashes verificados) sobre datos sinteticos."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        write_synthetic(cls.tmp.name)
        cls.out = os.path.join(cls.tmp.name, "out")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_main(self, *extra):
        with redirect_stdout(io.StringIO()) as buf:
            res = RD.main(["--data-dir", self.tmp.name, "--out", self.out, "--solo-anclas", *extra])
        return res, buf.getvalue()

    def test_modelos_reales_y_salidas(self):
        res, text = self.run_main()
        self.assertIsNotNone(res)
        for name in ("resumen.md", "resumen.json", "senales.csv", "operaciones_P1.csv", "operaciones_C0.csv"):
            self.assertTrue(os.path.exists(os.path.join(self.out, name)), name)
        self.assertEqual(res["periodo"][0], "2026-10-01")
        self.assertIn("P1 c=0.24 %", res["brazos"])
        self.assertIn("Canal sombra v3", text)
        json.dumps(res, default=float)

    def test_brazos_con_senales_forzadas(self):
        """Con p forzada (umbral facil), P1 = C0 con A4 >= 1, S3 excluye las vetadas y el azar se calcula."""
        original = RD.V3.predict

        def fake_predict(members, X, ridx, Q):
            p = np.zeros(len(X))
            p[ridx] = (np.arange(len(ridx)) % 97 == 0) * 0.99
            return p
        RD.V3.predict = fake_predict
        try:
            end, _ = RD.data_end_ms(self.tmp.name)
            ev = RD.evaluate(self.tmp.name, "2026-10-01", end)
            sim = RD.simulate_arms(ev)
        finally:
            RD.V3.predict = original
        n = lambda arm: sum(len(t) for _, t in sim["trades"][(arm, RD.MAIN_COST)])
        self.assertGreater(n("C0"), 0)
        self.assertLessEqual(n("P1"), n("C0"))
        self.assertLessEqual(n("S3"), n("P1"))
        for sym, tr in sim["trades"][("P1", RD.MAIN_COST)]:
            d = ev["D"][sym]
            self.assertTrue(np.all(d["A"][tr.sig_idx] >= 1))
            self.assertTrue(np.all(tr.entry_t >= RD.to_ms("2026-10-01")))
        crit = RD.criteria(sim)
        self.assertIn("n", crit)
        # cada costo mas alto da un PnL menor en las mismas operaciones
        e = {c: sum(float(t.net_ret.sum()) for _, t in sim["trades"][("C0", c)]) for c in RD.COSTS}
        self.assertGreater(e["0.19 % (BNB)"], e["0.24 %"])
        self.assertGreater(e["0.24 %"], e["0.30 %"])
        # con el TP como orden limite, las salidas por TP no pagan deslizamiento (y el resto queda igual)
        self.assertGreater(e["0.17 % (BNB + TP límite)"], e["0.19 % (BNB)"])
        for (_, a), (_, b) in zip(sim["trades"][("C0", "0.19 % (BNB)")], sim["trades"][("C0", "0.17 % (BNB + TP límite)")]):
            tp = a.reason == RD.H.TP
            np.testing.assert_allclose(b.net_ret[~tp], a.net_ret[~tp])
            np.testing.assert_allclose(b.net_ret[tp] - a.net_ret[tp], RD.H.SLIP * a.exit_px[tp] / a.entry_px[tp])


if __name__ == "__main__":
    unittest.main()


class ProvisionalPipelineTest(unittest.TestCase):
    """Sin el archivo de funding del mes en curso: se reconstruye, se mide la equivalencia (y se guarda) y el resumen
    queda marcado como provisional. La equivalencia abre la reserva con motivo: aqui no se escribe holdout_log.csv."""

    def test_funding_del_mes_en_curso_reconstruido(self):
        logged = []
        original_log = RD.H.log_holdout
        RD.H.log_holdout = lambda reason, who="", detail="": logged.append(reason)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                write_synthetic(tmp, t0=RD.to_ms("2026-07-20"), funding_until=RD.to_ms("2026-10-01"))
                out = os.path.join(tmp, "out")
                with redirect_stdout(io.StringIO()):
                    self.assertIsNone(RD.main(["--data-dir", tmp, "--out", out, "--solo-anclas", "--solo-definitivo"]))
                    res = RD.main(["--data-dir", tmp, "--out", out, "--solo-anclas"])
                prov = res["provisional"]
                self.assertIsNotNone(prov)
                self.assertTrue(prov["funding_reconstruido_desde"].startswith("2026-10-01"))
                eq = prov["equivalencia"]
                self.assertEqual(eq["ventana"][0], "2026-09-01")
                self.assertGreater(eq["funding"]["BTCUSDT"]["corr"], 0.99)
                self.assertLess(eq["funding"]["BTCUSDT"]["error_medio_pb"], 0.1)
                self.assertTrue(eq["equivalente"], eq)
                self.assertGreater(res["periodo"][1], "2026-10-19")
                with open(os.path.join(out, "resumen.md"), encoding="utf-8") as f:
                    self.assertIn("PROVISIONAL", f.read())
                n_logs = len(logged)
                self.assertGreater(n_logs, 0)
                with redirect_stdout(io.StringIO()):
                    RD.main(["--data-dir", tmp, "--out", out, "--solo-anclas"])   # la equivalencia ya esta guardada
                self.assertEqual(len(logged), n_logs)
        finally:
            RD.H.log_holdout = original_log


class UniverseTest(unittest.TestCase):
    """Con 18 monedas: S1 (A18 >= 3) en todas, P1/C0/S3 solo en las anclas y PnL por moneda con la fila combinada."""

    def test_s1_en_las_18_monedas(self):
        original = RD.V3.predict

        def fake_predict(members, X, ridx, Q):
            p = np.zeros(len(X))
            p[ridx] = (np.arange(len(ridx)) % 41 < 3) * 0.99
            return p
        RD.V3.predict = fake_predict
        try:
            with tempfile.TemporaryDirectory() as tmp:
                write_synthetic(tmp, symbols=RD.UNIVERSE)
                out = os.path.join(tmp, "out")
                with redirect_stdout(io.StringIO()):
                    res = RD.main(["--data-dir", tmp, "--out", out])
                self.assertEqual(res["monedas"], RD.UNIVERSE)
                self.assertIn("S1 c=0.24 %", res["brazos"])
                rows = res["por_moneda"]["S1"]
                self.assertEqual(rows[-1]["symbol"], "COMBINADO")
                self.assertEqual(rows[-1]["n"], sum(r["n"] for r in rows[:-1]))
                self.assertEqual({r["symbol"] for r in res["por_moneda"]["P1"][:-1]} - set(RD.ANCHORS), set())
                self.assertTrue(os.path.exists(os.path.join(out, "operaciones_S1.csv")))
                with open(os.path.join(out, "resumen.md"), encoding="utf-8") as f:
                    self.assertIn("PnL por moneda: S1", f.read())
        finally:
            RD.V3.predict = original

    def test_a18_cuenta_las_otras_monedas(self):
        original = RD.V3.predict

        def fake_predict(members, X, ridx, Q):
            p = np.zeros(len(X))
            p[ridx[:1]] = 0.99           # una sola vela con senal por moneda (la primera de la prueba)
            return p
        RD.V3.predict = fake_predict
        try:
            with tempfile.TemporaryDirectory() as tmp:
                syms = RD.UNIVERSE[:6]
                write_synthetic(tmp, symbols=syms)
                end, _ = RD.data_end_ms(tmp, syms)
                ev = RD.evaluate(tmp, "2026-10-01", end, symbols=syms)
        finally:
            RD.V3.predict = original
        for s in syms:
            d = ev["D"][s]
            i = d["ridx"][0]
            self.assertEqual(d["A18"][i], 5)                     # las otras 5 dieron senal en la misma vela
            self.assertEqual(d["A"][i], 3 if s in RD.ANCHORS else 4)
