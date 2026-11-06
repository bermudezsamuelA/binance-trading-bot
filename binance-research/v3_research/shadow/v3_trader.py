"""Senales de la v3 para el bot en la TESTNET (modo V3_TESTNET de server.py).

Un hilo calcula, 45 s despues del cierre de cada vela de 15 min, las senales S1H de las monedas del universo (v3_live.run_once:
historia de data.binance.vision, velas spot de hoy de la API de mainnet y futuros de Coinalyze) y las guarda en una cola.
Node las consulta con 'v3_poll' (nunca espera al calculo) y recibe:
  * signals: las senales nuevas, con TP y SL como FRACCION del precio de entrada (la testnet tiene otros precios que mainnet:
    Node los aplica al precio actual de la testnet);
  * exits: las monedas con posicion abierta en el ledger que cumplieron la barrera de tiempo (384 velas + 1 desde la entrada).
La historia se actualiza una vez al dia. Nada de esto envia ordenes: las ordena Node con su ejecucion de siempre.
"""
import datetime as dt
import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MS15 = 900_000
HOLD_CANDLES = 384
TIME_STOP_MS = (HOLD_CANDLES + 1) * MS15
COMPUTE_DELAY_S = 45
MAX_AGE_MS = 2 * MS15            # una senal mas vieja que esto ya no se entrega (entrada tardia)
ARM = "S1H"


def testnet_symbols(rest_url: str, universe: list, opener=urllib.request.urlopen) -> list:
    """Monedas del universo que existen y cotizan (TRADING) en la testnet."""
    with opener(f"{rest_url}/api/v3/exchangeInfo", timeout=30) as resp:
        info = json.loads(resp.read().decode())
    ok = {s["symbol"] for s in info.get("symbols", []) if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT"}
    return [s for s in universe if s in ok]


def signal_levels(row: dict) -> dict:
    """Fila de v3_live.signals_for -> senal para Node con TP y SL en fraccion del precio."""
    price = float(row["precio"])
    return {"symbol": row["symbol"], "open_time": row["open_time_ms"], "brazo": row["brazo"], "p": row["p"],
            "tp_pct": float(row["tp"]) / price - 1.0, "sl_pct": 1.0 - float(row["sl"]) / price}


class V3Trader:
    def __init__(self, symbols: list, compute, now=time.time, history_update=None):
        """compute(): lista de filas de v3_live (con 'open_time_ms'); history_update(): descarga diaria de la historia."""
        self.symbols, self.compute, self.now, self.history_update = list(symbols), compute, now, history_update
        self.queue, self.delivered, self.lock = [], set(), threading.Lock()
        self.last_history_day, self.thread, self.stopped = None, None, False

    # ---- calculo (hilo)
    def tick(self) -> int:
        """Un ciclo: actualiza la historia si es un dia nuevo y encola las senales S1H nuevas. Devuelve cuantas encolo."""
        today = dt.datetime.fromtimestamp(self.now(), dt.timezone.utc).date()
        if self.history_update and today != self.last_history_day:
            try:
                self.history_update(today)
                self.last_history_day = today
            except Exception as e:
                print(f"[V3] No se pudo actualizar la historia: {e}")
        added = 0
        for row in self.compute():
            if row.get("brazo") != ARM or row["symbol"] not in self.symbols:
                continue
            key = (row["symbol"], row["open_time_ms"])
            with self.lock:
                if key in self.delivered or any((q["symbol"], q["open_time"]) == key for q in self.queue):
                    continue
                self.queue.append(signal_levels(row))
                added += 1
        return added

    def run_forever(self):
        while not self.stopped:
            now = self.now()
            time.sleep(max(1.0, MS15 / 1000 - now % (MS15 / 1000) + COMPUTE_DELAY_S))
            try:
                n = self.tick()
                print(f"[V3] Ciclo listo: {n} senal(es) nueva(s) en cola.", flush=True)
            except Exception as e:  # una vela con error no detiene el hilo
                print(f"[V3] ⚠️ Error calculando las senales: {e}", flush=True)

    def start(self):
        self.thread = threading.Thread(target=self.run_forever, daemon=True)
        self.thread.start()

    # ---- consulta (ZMQ)
    def poll(self, open_trades: list) -> dict:
        now_ms = int(self.now() * 1000)
        with self.lock:
            fresh = [q for q in self.queue if now_ms - q["open_time"] <= MAX_AGE_MS + MS15]
            self.queue = []
            for q in fresh:
                self.delivered.add((q["symbol"], q["open_time"]))
        exits = sorted({t["symbol"] for t in open_trades
                        if t.get("symbol") and t.get("timestamp") and now_ms - int(t["timestamp"]) >= TIME_STOP_MS})
        return {"signals": fresh, "exits": exits}


def build(universe=None, rest_url=None):
    """V3Trader real: calculo con v3_live y descarga diaria de la historia."""
    import feeds
    import run_daily as RD
    import v3_live as VL
    universe = universe or RD.UNIVERSE

    def compute():
        res = VL.run_once(symbols=universe)
        return res["senales"]

    def history(today):
        since = today - dt.timedelta(days=RD.WARMUP_DAYS)
        feeds.update_spot(RD.RESEARCH, universe, since, today - dt.timedelta(days=1))
        feeds.update_futures(RD.RESEARCH, universe, since, today - dt.timedelta(days=1))

    symbols = testnet_symbols(rest_url, universe) if rest_url else list(universe)
    return V3Trader(symbols, compute, history_update=history)
