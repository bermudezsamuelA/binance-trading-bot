import zmq
import json
import pandas as pd
import os
import time

LEDGER_DIR = "./orders"
LEDGER_FILE = f"{LEDGER_DIR}/trades.csv"

def init_ledger():
    if not os.path.exists(LEDGER_DIR):
        os.makedirs(LEDGER_DIR)
        print("Created 'orders' directory.")
        
    if not os.path.exists(LEDGER_FILE):
        df = pd.DataFrame(columns=[
            "order_id", "symbol", "action", "entry_price", 
            "take_profit", "stop_loss", "quantity", "status", "timestamp"
        ])
        df.to_csv(LEDGER_FILE, index=False)
        print("Initialized empty trades.csv ledger.")

def handle_request(message: dict):
    req_type = message.get("type")
    
    if req_type == "roster":
        base_roster = ["BTCUSDT", "ETHUSDT"]
        try:
            df = pd.read_csv(LEDGER_FILE)
            if not df.empty and 'status' in df.columns:
                open_trades = df[df['status'] == 'OPEN']['symbol'].tolist()
                return list(set(base_roster + open_trades))
        except:
            pass
        return base_roster
    
    elif req_type == "sync_positions":
        try:
            df = pd.read_csv(LEDGER_FILE)
            if not df.empty and 'status' in df.columns:
                # Convert the rows where status is OPEN into a list of dictionaries
                open_trades = df[df['status'] == 'OPEN'].to_dict(orient='records')
                return open_trades
        except:
            pass
        return []
        
    elif req_type == "evaluate":
        payload = message.get("payload", {})
        symbol = payload.get("symbol")
        current_price = payload.get("current_price")
        
        # Hardcoded strategy logic (To be updated later)
        entry = current_price * 0.999
        tp = entry * 1.02
        sl = entry * 0.99
        
        return {
            "symbol": symbol.upper(),
            "action": "BUY", 
            "entry_price": round(entry, 2),
            "take_profit": round(tp, 2),
            "stop_loss": round(sl, 2)
        }
        
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
        print(f"Logged OPEN trade for {trade['symbol']} (ID: {trade['order_id']})")
        return {"status": "logged"}
        
    elif req_type == "ledger_close":
        trade = message.get("payload", {})
        order_id = trade.get("order_id")
        try:
            df = pd.read_csv(LEDGER_FILE)
            if not df.empty and 'order_id' in df.columns:
                df.loc[df['order_id'] == order_id, 'status'] = 'CLOSED'
                df.to_csv(LEDGER_FILE, index=False)
                print(f"Marked trade ID {order_id} as CLOSED in ledger.")
            return {"status": "updated"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"error": "Unknown request type"}

if __name__ == "__main__":
    init_ledger()
    
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind("tcp://127.0.0.1:5555")
    
    print("ZeroMQ Strategy Engine running on tcp://127.0.0.1:5555")
    
    while True:
        raw_msg = socket.recv_string()
        try:
            message = json.loads(raw_msg)
            response = handle_request(message)
            socket.send_string(json.dumps(response))
        except Exception as e:
            print(f"Error processing message: {e}")
            socket.send_string(json.dumps({"error": str(e)}))