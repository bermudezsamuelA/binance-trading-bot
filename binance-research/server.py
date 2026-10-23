import inspect
import sys
import zmq
import json
import pandas as pd
import os
import time
import requests

import ledger
# Tamano por operacion del backtest: unica fuente. Node lo recibe en el handshake 'market' y lo usa.
from optimize import NOTIONAL_USDT
from strategy_engine import StrategyEngine
from download_data import sync_historical_data
from config import (ACTIVE_ROSTER, BINANCE_MARKET, KLINE_INTERVAL, KLINE_INTERVAL_MS, MARKET_DATA_REST_URL,
                    PRESEED_MARGIN, PRESEED_MIN)

sys.stdout.reconfigure(encoding='utf-8')

# Se declara vacía. Así los subprocesos de Windows no cargan la IA en RAM.
engine = None 

def init_ledger():
    # Crea orders/trades.csv o, si le faltan las columnas de ejecucion real, las anade al final
    # (con copia de seguridad previa y sin tocar las filas existentes). Ver ledger.py.
    ledger.ensure_ledger()

def fetch_closed_klines(symbol: str, limit: int = None, start_time: int = None, end_time: int = None) -> list:
    """Velas CERRADAS de KLINE_INTERVAL del mismo mercado que el WebSocket (MARKET_DATA_REST_URL).
    Binance devuelve tambien la vela en formacion: se descarta toda vela cuyo close_time no haya pasado."""
    params = {"symbol": symbol, "interval": KLINE_INTERVAL}
    if limit is not None:
        params["limit"] = min(int(limit), 1000)
    if start_time is not None:
        params["startTime"] = int(start_time)
    if end_time is not None:
        params["endTime"] = int(end_time)
    response = requests.get(f"{MARKET_DATA_REST_URL}/api/v3/klines", params=params, timeout=10)
    response.raise_for_status()
    now_ms = server_time_ms()
    return [k for k in response.json() if int(k[6]) < now_ms]

def server_time_ms() -> int:
    """Hora del servidor de Binance: con el reloj local adelantado, la vela en formacion pasaria por cerrada."""
    try:
        response = requests.get(f"{MARKET_DATA_REST_URL}/api/v3/time", timeout=10)
        response.raise_for_status()
        return int(response.json()["serverTime"])
    except Exception:
        return int(time.time() * 1000)

def kline_to_market_data(kline: list) -> dict:
    return {
        "open_time": int(kline[0]),
        "open": float(kline[1]),
        "high": float(kline[2]),
        "low": float(kline[3]),
        "close": float(kline[4]),
        "volume": float(kline[5])
    }

def preseed_count(symbol: str) -> int:
    """Velas de precarga de una moneda: max(SU ventana + PRESEED_MARGIN, PRESEED_MIN). Es lo que simula el
    backtest (walk_forward.preseed_candles(n) y fast_backtest con first = inicio - precarga): con la ventana
    mas grande de todas las monedas, una VolatilitySqueeze de ventana corta veria velas de mas y su trampa
    podria quedar armada (o disparada) distinto que en el backtest."""
    strategy = engine.strategies.get(symbol)
    window = int(getattr(strategy, "window", 0) or 0)
    return max(window + PRESEED_MARGIN, PRESEED_MIN)

def reset_strategy(symbol: str):
    """Instancia NUEVA de la estrategia de la moneda, con los mismos parametros, y sin historial de velas. Igual
    que al arrancar: ventana vacia y la trampa de VolatilitySqueeze desarmada (fast_backtest con `first`)."""
    old = engine.strategies[symbol]
    params = {name: getattr(old, name) for name in inspect.signature(type(old).__init__).parameters
              if name != "self" and hasattr(old, name)}
    engine.strategies[symbol] = type(old)(**params)
    engine.last_open_time.pop(symbol, None)

def pre_seed_engine(roster: list, required_candles: int = None):
    """Calienta cada estrategia con sus velas cerradas mas recientes (sus senales se ignoran), como el backtest
    antes del primer dia en que puede abrir. required_candles fuerza la misma cantidad para todas (pruebas).
    Co-senal: la regla de X en sombra sobre la moneda Y recibe las ultimas preseed_count(X) velas de Y, para empezar a
    la vez que la de X (strategy_filters.FilteredFS hace lo mismo en el backtest)."""
    global engine
    print(f"[PRE-SEED] Precarga de velas cerradas de {KLINE_INTERVAL} vía REST ({MARKET_DATA_REST_URL}), "
          f"max(ventana + {PRESEED_MARGIN}, {PRESEED_MIN}) por moneda...")
    for symbol in roster:
        own = symbol in engine.strategies
        shadow_counts = {x: required_candles or preseed_count(x) for x in engine.watchers(symbol)}
        if not own and not shadow_counts:
            continue  # sin estrategia cargada ni regla en sombra no hay nada que calentar
        own_count = (required_candles or preseed_count(symbol)) if own else 0
        count = max([own_count] + list(shadow_counts.values()))
        try:
            # limit + 1 porque la ultima suele ser la vela en formacion, que se descarta
            klines = fetch_closed_klines(symbol, limit=count + 1)[-count:]

            for k, kline in enumerate(klines):
                left = len(klines) - k  # velas que quedan, incluida esta
                engine.get_signal(symbol, kline_to_market_data(kline), own=left <= own_count,
                                  shadow_for={x for x, c in shadow_counts.items() if left <= c})

            print(f"[PRE-SEED] Buffer de memoria lleno para {symbol} ({len(klines)} velas"
                  + (f"; co-senal de {', '.join(shadow_counts)}" if shadow_counts else "") + ").")
        except Exception as e:
            print(f"[PRE-SEED] Error cargando contexto para {symbol}: {e}")

def fill_gap(symbol: str, open_time: int):
    """Si entre la ultima vela procesada y la que llega faltan velas (reconexion, arranque entre la
    precarga y el WebSocket), se piden al REST para que la ventana no tenga huecos."""
    own = symbol in engine.strategies
    watchers = engine.watchers(symbol)
    if not own and not watchers:
        return
    expected = engine.expected_next_open_time(symbol)
    if expected is not None and open_time <= expected:
        return
    needed = max([preseed_count(symbol) if own else 0] + [preseed_count(x) for x in watchers])
    missing = needed if expected is None else (open_time - expected) // KLINE_INTERVAL_MS
    if missing > needed and own:
        # Hueco mayor que la precarga (bot o red caidos mucho tiempo): se empieza como al arrancar, con una
        # instancia nueva precargada con sus `needed` velas; continuar la vieja dejaria su estado (la trampa de
        # VolatilitySqueeze) distinto del que tendria el backtest.
        print(f"[DATA] {symbol}: faltan {missing} velas (> {needed}); la estrategia se reinicia y se precarga de nuevo.")
        reset_strategy(symbol)
    try:
        for kline in fetch_closed_klines(symbol, limit=min(missing, needed), end_time=open_time - 1):
            engine.get_signal(symbol, kline_to_market_data(kline))
    except Exception as e:
        print(f"[DATA] No se pudieron recuperar velas faltantes de {symbol}: {e}")

def handle_request(message: dict):
    global engine
    req_type = message.get("type")
    
    if req_type == "roster":
        try:
            return list(set(ACTIVE_ROSTER + ledger.open_symbols()))
        except Exception as e:
            print(f"[LEDGER] No se pudo leer el ledger para el roster: {e}")
        return ACTIVE_ROSTER

    elif req_type == "market":
        # Node compara el mercado con el suyo antes de conectarse al WebSocket, compra notional_usdt por operacion
        # (el mismo NOTIONAL_USDT que simula el backtest en optimize.py) y se suscribe a las velas de kline_interval
        return {"market": BINANCE_MARKET, "notional_usdt": float(NOTIONAL_USDT), "kline_interval": KLINE_INTERVAL}

    elif req_type == "sync_positions":
        # Vacios como null (pandas devolvia NaN, que no es JSON valido para Node)
        try:
            return ledger.open_trades()
        except Exception as e:
            print(f"[LEDGER] No se pudo leer el ledger: {e}")
        return []
        
    elif req_type == "evaluate":
        payload = message.get("payload", {})
        symbol = payload.get("symbol")
        market_data = payload.get("market_data", {})
        if market_data.get("open_time") is not None:
            fill_gap(symbol, int(market_data["open_time"]))
        
        signal = engine.get_signal(symbol, market_data)
        # Diario de senales: cada BUY de la estrategia en una vela del WebSocket, abierto o bloqueado por un filtro
        # (las de la precarga y del relleno de huecos no pasan por aqui)
        if engine.journal_entry:
            try:
                ledger.append_signal(engine.journal_entry)
            except Exception as e:
                print(f"[LEDGER] No se pudo escribir el diario de senales: {e}")
            if signal and signal.get("bloqueada"):
                print(f"[SIGNAL] {symbol}: BUY bloqueado por los filtros de entrada ({signal['bloqueada']}).")
        return signal
        
    elif req_type == "sync_pending":
        # Compras PENDING (registradas antes de enviarlas y sin confirmar): Node las consulta por client_order_id
        try:
            return ledger.pending_trades()
        except Exception as e:
            print(f"[LEDGER] No se pudo leer el ledger: {e}")
        return []

    elif req_type == "ledger_pending":
        # Antes de enviar la compra: si el proceso muere entre la ejecucion y el registro, esta fila permite
        # encontrarla en Binance por client_order_id al arrancar
        trade = message.get("payload", {})
        try:
            ledger.append_trade({
                "symbol": trade["symbol"].upper(),
                "action": "BUY",
                "take_profit": trade.get("take_profit"),
                "stop_loss": trade.get("stop_loss"),
                "status": ledger.PENDING,
                "timestamp": int(time.time() * 1000),
                "signal_price": trade.get("signal_price"),
                "client_order_id": trade["client_order_id"],
            })
        except Exception as e:
            print(f"[LEDGER] Error registrando la compra pendiente {trade.get('client_order_id')}: {e}")
            return {"status": "error", "message": str(e)}
        print(f"[LEDGER] Compra PENDIENTE para {trade['symbol']} ({trade['client_order_id']})")
        return {"status": "logged"}

    elif req_type == "ledger_open":
        # Datos REALES de la compra MARKET (precio medio, cantidad y comisiones de la respuesta FULL). Con
        # client_order_id, la fila PENDING de esa compra pasa a OPEN (la misma fila, no una nueva).
        trade = message.get("payload", {})
        values = {
            "order_id": trade["order_id"],
            "symbol": trade["symbol"].upper(),
            "action": trade.get("action", "BUY"),
            "entry_price": trade["entry_price"],
            "take_profit": trade["take_profit"],
            "stop_loss": trade["stop_loss"],
            "quantity": trade["quantity"],
            "status": ledger.OPEN,
            "signal_price": trade.get("signal_price"),
            "net_quantity": trade.get("net_quantity"),
            "entry_quote": trade.get("entry_quote"),
            "entry_fee_usdt": trade.get("entry_fee_usdt"),
            "entry_fees": trade.get("entry_fees"),
            "client_order_id": trade.get("client_order_id"),
        }
        try:
            updated = 0
            if trade.get("client_order_id"):
                updated = ledger.update_by_client_order_id(trade["client_order_id"], values, symbol=values["symbol"])
            if not updated:
                ledger.append_trade({**values, "timestamp": int(time.time() * 1000)})
        except Exception as e:
            print(f"[LEDGER] Error registrando la compra {trade.get('order_id')}: {e}")
            return {"status": "error", "message": str(e)}
        print(f"[LEDGER] Trade ABIERTO para {trade['symbol']} (ID: {trade['order_id']})")
        return {"status": "logged"}

    elif req_type == "ledger_cancel":
        # La compra PENDING no existe en Binance (o fue rechazada): CANCELLED, fuera de las metricas
        trade = message.get("payload", {})
        try:
            updated = ledger.update_by_client_order_id(trade.get("client_order_id"), {
                "status": ledger.CANCELLED,
                "exit_reason": trade.get("reason"),
                "exit_timestamp": int(time.time() * 1000),
            }, symbol=trade.get("symbol"))
        except Exception as e:
            print(f"[LEDGER] Error cancelando la compra {trade.get('client_order_id')}: {e}")
            return {"status": "error", "message": str(e)}
        if not updated:
            return {"status": "error", "message": f"compra pendiente {trade.get('client_order_id')} no encontrada"}
        print(f"[LEDGER] Compra {trade.get('client_order_id')} CANCELADA: {trade.get('reason')}")
        return {"status": "updated"}
        
    elif req_type == "ledger_close":
        # pnl = PnL neto en USDT; null si se cerro sin venta (polvo o sin saldo, ver reason)
        trade = message.get("payload", {})
        order_id = trade.get("order_id")
        # Los orderId de Binance son por simbolo: solo se cierra la fila OPEN de esa moneda
        symbol = trade.get("symbol")
        if not symbol:
            print(f"[LEDGER] ledger_close sin symbol para la orden {order_id}: se busca solo entre las OPEN.")
        try:
            updated = ledger.update_trade(order_id, symbol=symbol, only_open=True, values={
                "status": "CLOSED",
                "exit_price": trade.get("exit_price"),
                "pnl": trade.get("pnl"),
                "exit_reason": trade.get("reason"),
                "exit_timestamp": int(time.time() * 1000),
                "exit_trigger_price": trade.get("exit_trigger_price"),
                "exit_quantity": trade.get("exit_quantity"),
                "exit_quote": trade.get("exit_quote"),
                "exit_fee_usdt": trade.get("exit_fee_usdt"),
                "exit_fees": trade.get("exit_fees"),
                "exit_order_id": trade.get("exit_order_id"),
                "residual_quantity": trade.get("residual_quantity"),
            })
        except Exception as e:
            print(f"[LEDGER] Error cerrando la orden {order_id}: {e}")
            return {"status": "error", "message": str(e)}
        if not updated:
            print(f"[LEDGER] Orden {order_id} ({symbol}) no encontrada entre las OPEN del ledger.")
            return {"status": "error", "message": f"order_id {order_id} ({symbol}) no encontrado entre las OPEN"}
        print(f"[LEDGER] Trade ID {order_id} marcado como CERRADO.")
        return {"status": "updated"}

    return {"error": "Tipo de solicitud desconocida"}

if __name__ == "__main__":
    print(f"[SISTEMA] Mercado: {BINANCE_MARKET} ({MARKET_DATA_REST_URL})")
    init_ledger()
    
    # 1. Sincronizar datos históricos (Solo el proceso maestro lo hace)
    sync_historical_data(ACTIVE_ROSTER)
    
    # 2. Instanciar el motor de estrategia pesada solo después de descargar
    engine = StrategyEngine()
    
    # 3. Precargar buffer con el historial inmediato
    pre_seed_engine(ACTIVE_ROSTER)
    
    # 4. Iniciar ZMQ
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    # BRAIN_ZMQ_BIND (opcional, .env): p. ej. tcp://0.0.0.0:5555 si Node corre en un contenedor Docker
    bind_address = os.environ.get("BRAIN_ZMQ_BIND", "tcp://127.0.0.1:5555")
    socket.bind(bind_address)
    
    print(f"[SISTEMA] Motor de Estrategia ZMQ activo en {bind_address}")
    
    # En Windows, recv bloqueante no deja que Ctrl+C interrumpa el proceso:
    # se espera con timeout para que KeyboardInterrupt llegue y se libere el puerto.
    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    try:
        while True:
            if not poller.poll(500):
                continue
            raw_msg = socket.recv_string()
            try:
                message = json.loads(raw_msg)
                response = handle_request(message)
                socket.send_string(json.dumps(response))
            except Exception as e:
                print(f"[ERROR] Procesando mensaje: {e}")
                socket.send_string(json.dumps({"error": str(e)}))
    except KeyboardInterrupt:
        print("[SISTEMA] Deteniendo motor...")
    finally:
        socket.close(linger=0)
        context.term()

    try:
        import report
        report.main(ACTIVE_ROSTER)
    except Exception as e:
        print(f"[SISTEMA] No se pudo generar el resumen: {e}")