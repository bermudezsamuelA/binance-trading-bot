"""
Reconstruye el resultado real de las operaciones a partir de las ejecuciones
(fills) registradas en Binance (/api/v3/myTrades) y calcula win rate,
esperanza matemática y PnL por símbolo.

Uso (con la VPN desactivada):
    .venv\\Scripts\\python report_binance.py              # todo el roster
    .venv\\Scripts\\python report_binance.py DOGEUSDT     # un símbolo
"""
import hashlib
import hmac
import os
import sys
import time
from urllib.parse import urlencode

import pandas as pd
import requests

from config import ACTIVE_ROSTER

with open(os.path.join(os.path.dirname(__file__), "..", ".env"), encoding="utf-8") as env_file:
    for line in env_file:
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.strip().split("=", 1)
            os.environ.setdefault(key, value.strip('"\''))
API_KEY = os.environ["BINANCE_API_KEY"]
API_SECRET = os.environ["BINANCE_API_SECRET"]
REST_URL = os.environ.get("BINANCE_REST_URL", "https://testnet.binance.vision/api")


def signed_get(path: str, params: dict):
    server_time = requests.get(f"{REST_URL}/v3/time").json()["serverTime"]
    params = {**params, "timestamp": server_time, "recvWindow": 10000}
    query = urlencode(params)
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    r = requests.get(f"{REST_URL}{path}?{query}&signature={sig}", headers={"X-MBX-APIKEY": API_KEY})
    r.raise_for_status()
    return r.json()


def fetch_fills(symbol: str) -> pd.DataFrame:
    fills, from_id = [], 0
    while True:
        batch = signed_get("/v3/myTrades", {"symbol": symbol, "fromId": from_id, "limit": 1000})
        fills += batch
        if len(batch) < 1000:
            break
        from_id = batch[-1]["id"] + 1
    df = pd.DataFrame(fills)
    if df.empty:
        return df
    for c in ("price", "qty", "quoteQty", "commission"):
        df[c] = df[c].astype(float)
    return df.sort_values("time")


def round_trips(fills: pd.DataFrame) -> pd.DataFrame:
    """Empareja compras y ventas (FIFO) y devuelve una fila por operación cerrada."""
    trades, inventory = [], []  # inventory: [qty_restante, precio, time]
    for f in fills.itertuples():
        if f.isBuyer:
            inventory.append([f.qty, f.price, f.time])
            continue
        qty_left = f.qty
        while qty_left > 1e-12 and inventory:
            lot = inventory[0]
            q = min(lot[0], qty_left)
            trades.append({
                "entrada": pd.to_datetime(lot[2], unit="ms"),
                "salida": pd.to_datetime(f.time, unit="ms"),
                "qty": q,
                "precio_entrada": lot[1],
                "precio_salida": f.price,
                "pnl": (f.price - lot[1]) * q,
            })
            lot[0] -= q
            qty_left -= q
            if lot[0] <= 1e-12:
                inventory.pop(0)
    return pd.DataFrame(trades)


def summarize(symbol: str, rt: pd.DataFrame, fees_quote: float) -> dict:
    wins = rt[rt["pnl"] > 0]["pnl"]
    losses = rt[rt["pnl"] <= 0]["pnl"]
    p = len(wins) / len(rt)
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = -losses.mean() if len(losses) else 0.0
    return {
        "symbol": symbol,
        "trades": len(rt),
        "win_rate_%": round(100 * p, 2),
        "ganancia_media": round(avg_win, 4),
        "perdida_media": round(avg_loss, 4),
        # E = p * G - (1 - p) * L  (USDT por operación, antes de comisiones)
        "esperanza": round(p * avg_win - (1 - p) * avg_loss, 4),
        "pnl_bruto": round(rt["pnl"].sum(), 4),
        "comisiones_usdt": round(fees_quote, 4),
        "pnl_neto": round(rt["pnl"].sum() - fees_quote, 4),
    }


def main():
    symbols = sys.argv[1:] or ACTIVE_ROSTER
    rows = []
    for symbol in symbols:
        fills = fetch_fills(symbol)
        if fills.empty:
            continue
        rt = round_trips(fills)
        if rt.empty:
            print(f"{symbol}: {len(fills)} ejecuciones, ninguna operación cerrada.")
            continue
        # Comisiones: las cobradas en USDT se suman; las cobradas en la moneda base se valoran al precio del fill
        base = symbol.replace("USDT", "")
        fees = fills.apply(
            lambda f: f.commission if f.commissionAsset == "USDT"
            else f.commission * f.price if f.commissionAsset == base else 0.0, axis=1).sum()
        rows.append(summarize(symbol, rt, fees))
        open_qty = fills.loc[fills.isBuyer, "qty"].sum() - fills.loc[~fills.isBuyer, "qty"].sum()
        if open_qty > 1e-12:
            print(f"{symbol}: quedan {open_qty:g} unidades compradas sin vender (no entran en el resumen).")

    if not rows:
        print("No hay operaciones cerradas en Binance para estos símbolos.")
        return
    print()
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nesperanza = win_rate × ganancia_media − (1 − win_rate) × perdida_media, en USDT por operación (sin comisiones).")


if __name__ == "__main__":
    main()
