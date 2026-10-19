"""
report.ledger_report sobre ledgers temporales: filas antiguas, cerradas con PnL neto y cerradas sin venta
(pnl vacío) no rompen las métricas. Sin red: solo se prueba la parte del ledger local.
"""
import contextlib
import io
import os
import re
import tempfile
import unittest

import ledger
import report

LEGACY_ROW = {"order_id": 1, "symbol": "DOGEUSDT", "action": "BUY", "entry_price": 0.08133, "take_profit": 0.08,
              "stop_loss": 0.08, "quantity": 184, "status": "CLOSED", "timestamp": 1792086603322}
SOLD_ROW = {"order_id": 2, "symbol": "DOGEUSDT", "action": "BUY", "entry_price": 0.0815, "take_profit": 0.0825,
            "stop_loss": 0.0805, "quantity": 184, "status": "CLOSED", "timestamp": 1792100000000, "signal_price": 0.0815,
            "net_quantity": 183.816, "entry_quote": 14.996, "entry_fee_usdt": 0.015, "entry_fees": "0.184 DOGE",
            "exit_price": 0.08249, "exit_quantity": 183, "exit_quote": 15.09567, "exit_fee_usdt": 0.0151,
            "exit_fees": "0.0151 USDT", "exit_trigger_price": 0.0826, "pnl": 0.0698, "exit_reason": "TAKE PROFIT ✅",
            "exit_timestamp": 1792100900000, "exit_order_id": 3}
NO_SALE_ROW = {"order_id": 4, "symbol": "BTCUSDT", "action": "BUY", "entry_price": 65000, "take_profit": 66000,
               "stop_loss": 64000, "quantity": 0.00023, "status": "CLOSED", "timestamp": 1792100000001,
               "signal_price": 64990, "net_quantity": 0.00022977, "entry_quote": 14.95, "entry_fee_usdt": 0.01495,
               "pnl": None, "exit_reason": "SIN SALDO al arrancar: libre 0 BTC", "exit_timestamp": 1792100000002}
OPEN_ROW = {"order_id": 5, "symbol": "DOGEUSDT", "action": "BUY", "entry_price": 0.08, "take_profit": 0.09,
            "stop_loss": 0.07, "quantity": 187, "status": "OPEN", "timestamp": 1792100000003, "entry_quote": 14.96}


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "trades.csv")
        self.original = report.LEDGER_FILE
        report.LEDGER_FILE = self.path

    def tearDown(self):
        report.LEDGER_FILE = self.original
        self.tmp.cleanup()

    def run_report(self, rows):
        with contextlib.redirect_stdout(io.StringIO()):
            ledger.ensure_ledger(self.path)
        for row in rows:
            ledger.append_trade(row, self.path)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            report.ledger_report(["DOGEUSDT", "BTCUSDT"])
        return out.getvalue()

    def test_pending_y_cancelled_fuera_de_metricas_y_no_cuentan_como_antiguas(self):
        pending = {"symbol": "DOGEUSDT", "action": "BUY", "status": "PENDING", "timestamp": 1792100000004,
                   "signal_price": 0.0815, "take_profit": 0.0825, "stop_loss": 0.0805, "client_order_id": "bot_b_p"}
        cancelled = {**pending, "status": "CANCELLED", "client_order_id": "bot_b_c", "exit_reason": "NO LLEGÓ A BINANCE"}
        text = self.run_report([SOLD_ROW, pending, cancelled])
        self.assertIn("1 compra(s) PENDIENTE(S)", text)
        self.assertIn("1 compra(s) CANCELADA(S)", text)
        self.assertNotIn("operaciones antiguas", text)
        table = [line.split() for line in text.splitlines() if len(line.split()) == 10 and line.split()[0] == "DOGEUSDT"]
        self.assertEqual(table[0][1], "1")                        # solo la vendida
        self.assertNotIn("cerradas sin venta", text)

    def test_mezcla_antiguas_vendidas_sin_venta_y_abiertas(self):
        text = self.run_report([LEGACY_ROW, SOLD_ROW, NO_SALE_ROW, OPEN_ROW])
        self.assertIn("1 operaciones antiguas sin datos de ejecución real", text)
        self.assertIn("1 cerradas sin venta (sin PnL)", text)
        self.assertIn("SIN SALDO al arrancar: libre 0 BTC", text)
        self.assertIn("Deslizamiento medio", text)
        # una sola operación en métricas: la vendida, con su PnL neto
        table = [line.split() for line in text.splitlines() if len(line.split()) == 10 and line.split()[0] == "DOGEUSDT"]
        self.assertEqual(len(table), 1)
        self.assertEqual(table[0][1], "1")          # trades
        self.assertEqual(table[0][-1], "0.0698")    # pnl_neto = pnl del ledger
        self.assertEqual(table[0][-2], "0.0301")    # comisiones = entrada + salida
        self.assertIsNone(re.search(r"\bnan\b", text, re.IGNORECASE))   # ningún NaN en métricas

    def test_residuo_bajo_el_paso_se_informa(self):
        row = {**SOLD_ROW, "residual_quantity": 0.816}
        text = self.run_report([row])
        self.assertIn("Residuo sin vender (bajo el paso de Binance), valorado a la salida e incluido en el PnL: "
                      "0.0673 USDT (DOGEUSDT 0.0673)", text)   # 0.816 × 0.08249

    def test_solo_cierres_sin_venta(self):
        text = self.run_report([LEGACY_ROW, NO_SALE_ROW])
        self.assertIn("Ninguna operación con ejecución real se ha cerrado con venta todavía.", text)
        self.assertIn("1 cerradas sin venta (sin PnL)", text)

    def test_round_trips_binance_por_orden_con_comision_en_base_y_residuo(self):
        import pandas as pd

        def fill(i, order, buyer, qty, price, fee, asset):
            return {"id": i, "orderId": order, "isBuyer": buyer, "qty": qty, "price": price, "quoteQty": qty * price,
                    "commission": fee, "commissionAsset": asset, "time": i, "symbol": "BTCUSDT"}
        fills = pd.DataFrame([
            # compra 1 en dos fills (comisión en BTC) y venta de lo vendible: quedan 0.00000984 BTC (< paso)
            fill(1, 10, True, 0.0001, 88000.0, 0.0000001, "BTC"), fill(2, 10, True, 0.00006, 88010.0, 0.00000006, "BTC"),
            fill(3, 11, False, 0.00015, 89000.0, 0.01335, "USDT"),
            # compra 2 (comisión en BNB) vendida en dos órdenes
            fill(4, 12, True, 0.00017, 87000.0, 0.00002, "BNB"),
            fill(5, 13, False, 0.0001, 86000.0, 0.0086, "USDT"), fill(6, 14, False, 0.00007, 86500.0, 0.006055, "USDT"),
            # compra 3 aún abierta
            fill(7, 15, True, 0.00016, 90000.0, 0.00000016, "BTC"),
        ])
        rt = report.round_trips(fills, "BTC", step=0.00001, min_notional=5.0, bnb_price=600.0)
        closed = rt[~rt["open"]]
        self.assertEqual(len(closed), 2)                  # 2 operaciones, no una por fill ni por residuo
        self.assertEqual(int(rt["open"].sum()), 1)
        buy1 = 0.0001 * 88000 + 0.00006 * 88010
        residual = 0.00016 - 0.00000016 - 0.00015
        self.assertAlmostEqual(closed["pnl"].iloc[0], 0.00015 * 89000 - 0.01335 + residual * 89000 - buy1, places=9)
        sells2 = 0.0001 * 86000 + 0.00007 * 86500
        self.assertAlmostEqual(closed["pnl"].iloc[1], sells2 - 0.0086 - 0.006055 - 0.00017 * 87000 - 0.00002 * 600,
                               places=9)
        self.assertAlmostEqual(closed["fees"].iloc[1], 0.0086 + 0.006055 + 0.012, places=9)

    def test_summarize_neto(self):
        import pandas as pd
        row = report.summarize("DOGEUSDT", pd.Series([0.5, -0.25, 0.25]), fees=0.1, net=True)
        self.assertEqual(row["trades"], 3)
        self.assertAlmostEqual(row["pnl_neto"], 0.5)
        self.assertAlmostEqual(row["pnl_bruto"], 0.6)
        self.assertAlmostEqual(row["win_rate_%"], 66.67)


if __name__ == "__main__":
    unittest.main()
