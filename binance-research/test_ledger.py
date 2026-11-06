"""
Pruebas del ledger (ledger.py) sobre archivos temporales: nunca tocan orders/trades.csv.

    .venv\\Scripts\\python -m unittest test_ledger -v     (o npm run test:python desde la raíz)
"""
import glob
import json
import os
import tempfile
import unittest

import ledger

# Ledger con el formato antiguo: 13 columnas, filas añadidas con header=False (9 campos) y una fila
# reescrita por pandas (exit_timestamp como float, emoji en el motivo, PnL con muchos decimales).
LEGACY = (
    "order_id,symbol,action,entry_price,take_profit,stop_loss,quantity,status,timestamp,exit_price,pnl,exit_reason,exit_timestamp\n"
    "375301,DOGEUSDT,BUY,0.08133,0.08,0.08,184,CLOSED,1792086603322,,,,\n"
    "377357,DOGEUSDT,BUY,0.08159,0.08,0.08,183,CLOSED,1792091121234,0.08142,-0.031109999999998,TAKE PROFIT ✅,1792093081550.0\n"
    "377400,BTCUSDT,BUY,65000.5,66000,64000,0.00023,OPEN,1792091200000\n"
)


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "trades.csv")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def read(self):
        with open(self.path, encoding="utf-8", newline="") as f:
            return f.read()

    def backups(self):
        return glob.glob(os.path.join(self.tmp.name, "trades.backup-*.csv"))

    def test_crea_ledger_nuevo_con_todas_las_columnas(self):
        header = ledger.ensure_ledger(self.path)
        self.assertEqual(header, ledger.LEDGER_COLUMNS)
        self.assertEqual(self.read(), ",".join(ledger.LEDGER_COLUMNS) + "\n")
        self.assertEqual(self.backups(), [])

    def test_migracion_conserva_filas_y_guarda_copia(self):
        self.write(LEGACY)
        ledger.ensure_ledger(self.path)
        old_lines = LEGACY.splitlines()
        new_lines = self.read().splitlines()
        self.assertEqual(new_lines[0], old_lines[0] + "," + ",".join(ledger.EXECUTION_COLUMNS))
        self.assertEqual(len(new_lines), len(old_lines))
        n = len(ledger.LEDGER_COLUMNS)
        for old, new in zip(old_lines[1:], new_lines[1:]):
            # cada fila antigua queda igual, solo con las celdas vacías que le faltaban al final
            self.assertTrue(new.startswith(old), (old, new))
            self.assertEqual(set(new[len(old):]), {","})
            self.assertEqual(new.count(","), n - 1)
        # copia previa idéntica al original y migración idempotente
        [backup] = self.backups()
        with open(backup, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), LEGACY)
        before = self.read()
        ledger.ensure_ledger(self.path)
        self.assertEqual(self.read(), before)
        self.assertEqual(len(self.backups()), 1)

    def test_no_migra_si_hay_filas_desalineadas(self):
        self.write(LEGACY + "1,DOGEUSDT,BUY,1,1,1,1,OPEN,1,1,1,x,1,EXTRA\n")
        with self.assertRaises(ValueError):
            ledger.ensure_ledger(self.path)
        self.assertEqual(self.read(), LEGACY + "1,DOGEUSDT,BUY,1,1,1,1,OPEN,1,1,1,x,1,EXTRA\n")

    def test_abrir_y_cerrar_operacion_solo_toca_su_fila(self):
        self.write(LEGACY)
        ledger.ensure_ledger(self.path)
        migrated = self.read()
        ledger.append_trade({
            "order_id": 500, "symbol": "DOGEUSDT", "action": "BUY", "entry_price": 0.08152174, "take_profit": 0.0825,
            "stop_loss": 0.0805, "quantity": 184.0, "status": "OPEN", "timestamp": 1792100000000,
            "signal_price": 0.0815, "net_quantity": 183.816, "entry_quote": 15.0, "entry_fee_usdt": 0.015,
            "entry_fees": "0.184 DOGE",
        }, self.path)
        self.assertTrue(self.read().startswith(migrated))
        self.assertEqual(ledger.update_trade(500, {
            "status": "CLOSED", "exit_price": 0.08249, "pnl": 0.0791, "exit_reason": "TAKE PROFIT ✅",
            "exit_timestamp": 1792100900000, "exit_trigger_price": 0.0826, "exit_quantity": 183.0, "exit_quote": 15.09567,
            "exit_fee_usdt": 0.01509567, "exit_fees": "0.01509567 USDT", "exit_order_id": 501,
        }, self.path), 1)
        lines = self.read().splitlines()
        self.assertEqual(lines[:4], migrated.splitlines()[:4])   # filas antiguas intactas
        row = dict(zip(lines[0].split(","), lines[4].split(",")))
        self.assertEqual(row["status"], "CLOSED")
        self.assertEqual(row["entry_price"], "0.08152174")
        self.assertEqual(row["exit_fee_usdt"], "0.01509567")
        self.assertEqual(row["exit_order_id"], "501")
        self.assertEqual(row["pnl"], "0.0791")
        self.assertEqual(ledger.update_trade(999, {"status": "CLOSED"}, self.path), 0)

    def test_cierre_por_simbolo_solo_toca_la_fila_open_de_esa_moneda(self):
        # Binance numera las órdenes por símbolo (y la testnet se reinicia cada mes): el mismo orderId aparece en
        # una fila antigua cerrada (DOGE), en otra posición abierta (DOGE) y en la que se cierra (SOL).
        self.write(LEGACY)
        ledger.ensure_ledger(self.path)
        base = {"action": "BUY", "entry_price": 1.0, "take_profit": 2.0, "stop_loss": 0.5, "quantity": 10.0,
                "status": "OPEN", "timestamp": 1792100000000, "entry_quote": 10.0}
        ledger.append_trade({**base, "order_id": 375301, "symbol": "SOLUSDT"}, self.path)
        ledger.append_trade({**base, "order_id": 375301, "symbol": "BTCUSDT"}, self.path)
        before = self.read().splitlines()
        self.assertEqual(ledger.update_trade(375301, {"status": "CLOSED", "pnl": 0.5, "residual_quantity": 0.001},
                                             self.path, symbol="SOLUSDT", only_open=True), 1)
        after = self.read().splitlines()
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(changed), 1)
        row = dict(zip(after[0].split(","), after[changed[0]].split(",")))
        self.assertEqual((row["symbol"], row["status"], row["pnl"], row["residual_quantity"]),
                         ("SOLUSDT", "CLOSED", "0.5", "0.001"))
        # la misma orden ya cerrada no se vuelve a tocar, ni la de otra moneda sin symbol coincidente
        self.assertEqual(ledger.update_trade(375301, {"pnl": 9}, self.path, symbol="SOLUSDT", only_open=True), 0)
        self.assertEqual(ledger.update_trade(375301, {"pnl": 9}, self.path, symbol="ETHUSDT", only_open=True), 0)
        self.assertEqual(self.read().splitlines(), after)

    def test_numeros_sin_notacion_cientifica_y_vacios(self):
        self.assertEqual(ledger.format_value(1.5e-07), "0.00000015")
        self.assertEqual(ledger.format_value(15.0), "15.0")
        self.assertEqual(ledger.format_value(None), "")
        self.assertEqual(ledger.format_value(float("nan")), "")
        self.assertEqual(ledger.format_value(1792100000000), "1792100000000")

    def test_cierre_sin_venta_deja_pnl_vacio(self):
        self.write(LEGACY)
        self.assertEqual(ledger.update_trade(377400, {"status": "CLOSED", "pnl": None,
                                                      "exit_reason": "SIN SALDO al arrancar: libre 0 BTC"}, self.path), 1)
        row = [r for r in self.read().splitlines() if r.startswith("377400,")][0].split(",")
        header = self.read().splitlines()[0].split(",")
        self.assertEqual(row[header.index("pnl")], "")
        self.assertEqual(row[header.index("status")], "CLOSED")

    def test_open_trades_json_valido(self):
        self.write(LEGACY)
        trades = ledger.open_trades(self.path)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t["order_id"], 377400)
        self.assertEqual(t["symbol"], "BTCUSDT")
        self.assertEqual(t["entry_price"], 65000.5)
        self.assertEqual(t["quantity"], 0.00023)
        self.assertIsNone(t["exit_price"])
        json.dumps(trades, allow_nan=False)   # sin NaN: Node lo puede leer
        self.assertEqual(ledger.open_symbols(self.path), ["BTCUSDT"])

    def test_ledger_inexistente(self):
        self.assertEqual(ledger.open_trades(self.path), [])

    def test_migracion_anade_client_order_id_a_un_ledger_con_las_columnas_de_ejecucion_previas(self):
        # Ledger ya migrado una vez (sin client_order_id): solo se añade esa columna, las filas no cambian
        previous = [c for c in ledger.LEDGER_COLUMNS if c != "client_order_id"]
        row = ["900", "DOGEUSDT", "BUY", "0.0815", "0.0825", "0.0805", "184", "OPEN", "1792100000000"] + \
              [""] * (len(previous) - 9)
        self.write(",".join(previous) + "\n" + ",".join(row) + "\n")
        header = ledger.ensure_ledger(self.path)
        self.assertEqual(header[-1], "client_order_id")
        self.assertEqual(self.read().splitlines()[1], ",".join(row) + ",")
        self.assertEqual(len(self.backups()), 1)

    def test_pending_pasa_a_open_en_la_misma_fila_o_a_cancelled(self):
        self.write(LEGACY)
        for cid, symbol in (("bot_b_1", "DOGEUSDT"), ("bot_b_2", "ETHUSDT")):
            ledger.append_trade({"symbol": symbol, "action": "BUY", "status": ledger.PENDING, "timestamp": 1,
                                 "signal_price": 0.0815, "take_profit": 0.0825, "stop_loss": 0.0805,
                                 "client_order_id": cid}, self.path)
        self.assertEqual([t["client_order_id"] for t in ledger.pending_trades(self.path)], ["bot_b_1", "bot_b_2"])
        # las monedas con compra pendiente también se vigilan (roster)
        self.assertEqual(ledger.open_symbols(self.path), ["BTCUSDT", "DOGEUSDT", "ETHUSDT"])
        rows_before = len(self.read().splitlines())
        n = ledger.update_by_client_order_id("bot_b_1", {"status": ledger.OPEN, "order_id": 777, "entry_price": 0.08152,
                                                         "quantity": 184.0}, self.path, symbol="DOGEUSDT")
        self.assertEqual(n, 1)
        self.assertEqual(len(self.read().splitlines()), rows_before)   # la misma fila, no una nueva
        opened = [t for t in ledger.open_trades(self.path) if t["symbol"] == "DOGEUSDT"][0]
        self.assertEqual((opened["order_id"], opened["client_order_id"], opened["signal_price"]), (777, "bot_b_1", 0.0815))
        # otra moneda o un estado distinto de PENDING no se toca
        self.assertEqual(ledger.update_by_client_order_id("bot_b_2", {"status": ledger.CANCELLED}, self.path,
                                                          symbol="DOGEUSDT"), 0)
        self.assertEqual(ledger.update_by_client_order_id("bot_b_1", {"status": ledger.CANCELLED}, self.path), 0)
        self.assertEqual(ledger.update_by_client_order_id("bot_b_2", {"status": ledger.CANCELLED,
                                                                      "exit_reason": "NO LLEGÓ A BINANCE"}, self.path), 1)
        self.assertEqual(ledger.pending_trades(self.path), [])
        self.assertEqual(ledger.update_by_client_order_id("", {"status": ledger.CANCELLED}, self.path), 0)
        json.dumps(ledger.trades_with_status(ledger.CANCELLED, self.path), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
