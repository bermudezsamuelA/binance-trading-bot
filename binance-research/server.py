import zmq
import json
import pandas as pd
import os
import time
import requests

from strategy_engine import StrategyEngine
from download_data import sync_historical_data
from config import ACTIVE_ROSTER

engine = StrategyEngine()

LEDGER_DIR = "./orders"
LEDGER_FILE = f"{LEDGER_DIR}/trades.csv"

def init_ledger():
    if not os.path.exists(LEDGER_DIR):
        os.makedirs(LEDGER_DIR)
        print("[SISTEMA] Directorio 'orders' creado.")
        
    if not os.path.exists(LEDGER_FILE):
        df = pd.DataFrame(columns=[
            "order_id", "symbol", "action", "entry_price", 
            "take_profit", "stop_loss", "quantity", "status", "timestamp"
        ])
        df.to_csv(LEDGER_FILE, index=False)
        print("[SISTEMA] Ledger trades.csv inicializado en blanco.")

def pre_seed_engine(roster: list, required_candles: int = 100):
    print("[PRE-SEED] Obteniendo contexto historico inmediato via REST...")
    for symbol in roster:
        try:
            # Cambiamos a 1m para que coincida con el WebSocket
            url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit={required_candles}"
            response = requests.get(url)
            klines = response.json()
            
            for kline in klines:
                market_data = {
                    "open": float(kline[1]),
                    "high": float(kline[2]),
                    "low": float(kline[3]),
                    "close": float(kline[4]),
                    "volume": float(kline[5])
                }
                engine.get_signal(symbol, market_data)
                
            print(f"[PRE-SEED] Buffer de memoria lleno para {symbol}.")
        except Exception as e:
            print(f"[PRE-SEED] Error cargando contexto para {symbol}: {e}")

def handle_request(message: dict):
    req_type = message.get("type")
    
    if req_type == "roster":
        try:
            df = pd.read_csv(LEDGER_FILE)
            if not df.empty and 'status' in df.columns:
                open_trades = df[df['status'] == 'OPEN']['symbol'].tolist()
                return list(set(ACTIVE_ROSTER + open_trades))
        except:
            pass
        return ACTIVE_ROSTER
    
    elif req_type == "sync_positions":
        try:
            df = pd.read_csv(LEDGER_FILE)
            if not df.empty and 'status' in df.columns:
                open_trades = df[df['status'] == 'OPEN'].to_dict(orient='records')
                return open_trades
        except:
            pass
        return []
        
    elif req_type == "evaluate":
        payload = message.get("payload", {})
        symbol = payload.get("symbol")
        # Recibimos el diccionario completo
        market_data = payload.get("market_data", {})
        
        signal = engine.get_signal(symbol, market_data)
        return signal
        
    elif req_type == "ledger_open":
        trade = message.get("payload", {})
        new_row = pd.DataFrame([{
            "order_id": trade["order_id"],
            "symbol": trade["symbol"].upper(),
            "action": trade["action"],
            "entry_price": trade["entry_price"],
            "take_profit": trade["take_profit"],
            "stop_loss": trade["stop_loss"],
            "quantity": trade["quantity"],
            "status": "OPEN",
            "timestamp": int(time.time() * 1000)
        }])
        new_row.to_csv(LEDGER_FILE, mode='a', header=False, index=False)
        print(f"[LEDGER] Trade ABIERTO para {trade['symbol']} (ID: {trade['order_id']})")
        return {"status": "logged"}
        
    elif req_type == "ledger_close":
        trade = message.get("payload", {})
        order_id = trade.get("order_id")
        try:
            df = pd.read_csv(LEDGER_FILE)
            if not df.empty and 'order_id' in df.columns:
                df.loc[df['order_id'] == order_id, 'status'] = 'CLOSED'
                df.to_csv(LEDGER_FILE, index=False)
                print(f"[LEDGER] Trade ID {order_id} marcado como CERRADO.")
            return {"status": "updated"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"error": "Tipo de solicitud desconocida"}

if __name__ == "__main__":
    init_ledger()
    
    # 1. Sincronizar datos
    sync_historical_data(ACTIVE_ROSTER)
    
    # 2. Precargar buffer con el historial inmediato
    pre_seed_engine(ACTIVE_ROSTER, required_candles=100)
    
    # 3. Iniciar ZMQ
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind("tcp://127.0.0.1:5555")
    
    print("[SISTEMA] Motor de Estrategia ZMQ activo en tcp://127.0.0.1:5555")
    
    while True:
        raw_msg = socket.recv_string()
        try:
            message = json.loads(raw_msg)
            response = handle_request(message)
            socket.send_string(json.dumps(response))
        except Exception as e:
            print(f"[ERROR] Procesando mensaje: {e}")
            socket.send_string(json.dumps({"error": str(e)}))