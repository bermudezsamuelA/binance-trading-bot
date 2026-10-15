"""
Resumen de resultados del bot: win rate, esperanza matemática y PnL por símbolo.

1. Ledger local (orders/trades.csv): operaciones cerradas con PnL registrado.
2. Binance (/api/v3/myTrades): reconstruye todas las operaciones a partir de las
   compras y ventas ejecutadas, incluidas las que el ledger no tiene. Requiere
   conexión con Binance (VPN desactivada); si falla, se omite.

Se imprime solo al detener server.py con Ctrl+C, o a mano:
    .venv\\Scripts\\python report.py              # todo el roster
    .venv\\Scripts\\python report.py DOGEUSDT     # un símbolo
"""
import hashlib
import hmac
import os
import sys
from urllib.parse import urlencode

import pandas as pd
import requests

from config import ACTIVE_ROSTER

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER_FILE = os.path.join(BASE_DIR, "orders", "trades.csv")
TIMEOUT = 10


def load_env():
    env_path = os.path.join(BASE_DIR, "..", ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as env_file:
        for line in env_file:
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.strip().split("=", 1)
                os.environ.setdefault(key, value.strip('"\''))


def summarize(symbol: str, pnl: pd.Series, fees: float = 0.0) -> dict:
    """Métricas de una serie de PnL por operación (USDT)."""
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    p = len(wins) / len(pnl)
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = -losses.mean() if len(losses) else 0.0
    gross_loss = -losses.sum()
    return {
        "symbol": symbol,
        "trades": len(pnl),
        "win_rate_%": round(100 * p, 2),
        "ganancia_media": round(float(avg_win), 4),
        "perdida_media": round(float(avg_loss), 4),
        # E = p * G - (1 - p) * L  (USDT por operación, antes de comisiones)
        "esperanza": round(float(p * avg_win - (1 - p) * avg_loss), 4),
        "profit_factor": round(float(wins.sum() / gross_loss), 2) if gross_loss > 0 else None,
        "pnl_bruto": round(float(pnl.sum()), 4),
        "comisiones": round(float(fees), 4),
        "pnl_neto": round(float(pnl.sum() - fees), 4),
    }


def print_table(rows: list):
    df = pd.DataFrame(rows)
    if len(rows) > 1:
        total = df[["trades", "pnl_bruto", "comisiones", "pnl_neto"]].sum()
        print(df.to_string(index=False))
        print(f"\nTOTAL: {int(total['trades'])} operaciones | PnL bruto {total['pnl_bruto']:.4f} "
              f"| comisiones {total['comisiones']:.4f} | PnL neto {total['pnl_neto']:.4f} USDT")
    else:
        print(df.to_string(index=False))


# ---------------------------------------------------------------- 1. Ledger local

def ledger_report(symbols: list):
    print("\n--- 1. Ledger local (orders/trades.csv) ---")
    if not os.path.exists(LEDGER_FILE):
        print("No existe el ledger todavía.")
        return
    df = pd.read_csv(LEDGER_FILE)
    df = df[df["symbol"].isin(symbols)]
    if df.empty:
        print("No hay operaciones registradas.")
        return

    fechas = pd.to_datetime(df["timestamp"], unit="ms")
    print(f"Operaciones registradas: {len(df)} ({fechas.min():%Y-%m-%d %H:%M} -> {fechas.max():%Y-%m-%d %H:%M})")
    print(df.groupby(["symbol", "status"]).size().unstack(fill_value=0).to_string())

    if "pnl" not in df.columns or df["pnl"].isna().all():
        print("Ninguna operación cerrada tiene PnL registrado todavía.")
        return
    closed = df[(df["status"] == "CLOSED") & df["pnl"].notna()]
    print()
    print_table([summarize(s, g["pnl"]) for s, g in closed.groupby("symbol")])
    if "exit_reason" in closed.columns:
        print("\nMotivo de cierre:")
        print(closed["exit_reason"].value_counts().to_string())


# ---------------------------------------------------------------- 2. Binance

def signed_get(rest_url: str, path: str, params: dict):
    server_time = requests.get(f"{rest_url}/v3/time", timeout=TIMEOUT).json()["serverTime"]
    params = {**params, "timestamp": server_time, "recvWindow": 10000}
    query = urlencode(params)
    sig = hmac.new(os.environ["BINANCE_API_SECRET"].encode(), query.encode(), hashlib.sha256).hexdigest()
    r = requests.get(f"{rest_url}{path}?{query}&signature={sig}",
                     headers={"X-MBX-APIKEY": os.environ["BINANCE_API_KEY"]}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_fills(rest_url: str, symbol: str) -> pd.DataFrame:
    fills, from_id = [], 0
    while True:
        batch = signed_get(rest_url, "/v3/myTrades", {"symbol": symbol, "fromId": from_id, "limit": 1000})
        fills += batch
        if len(batch) < 1000:
            break
        from_id = batch[-1]["id"] + 1
    df = pd.DataFrame(fills)
    if df.empty:
        return df
    for c in ("price", "qty", "commission"):
        df[c] = df[c].astype(float)
    return df.sort_values("time")


def round_trips(fills: pd.DataFrame) -> pd.DataFrame:
    """Empareja compras y ventas (FIFO) y devuelve una fila por operación cerrada."""
    trades, inventory = [], []  # inventory: [qty_restante, precio]
    for f in fills.itertuples():
        if f.isBuyer:
            inventory.append([f.qty, f.price])
            continue
        qty_left = f.qty
        while qty_left > 1e-12 and inventory:
            lot = inventory[0]
            q = min(lot[0], qty_left)
            trades.append({"qty": q, "pnl": (f.price - lot[1]) * q})
            lot[0] -= q
            qty_left -= q
            if lot[0] <= 1e-12:
                inventory.pop(0)
    return pd.DataFrame(trades)


def binance_report(symbols: list):
    print("\n--- 2. Binance (compras y ventas ejecutadas) ---")
    load_env()
    rest_url = os.environ.get("BINANCE_REST_URL", "https://testnet.binance.vision/api")
    rows = []
    try:
        for symbol in symbols:
            fills = fetch_fills(rest_url, symbol)
            if fills.empty:
                continue
            rt = round_trips(fills)
            open_qty = fills.loc[fills.isBuyer, "qty"].sum() - fills.loc[~fills.isBuyer, "qty"].sum()
            if open_qty > 1e-12:
                print(f"{symbol}: quedan {open_qty:g} unidades compradas sin vender (no entran en el resumen).")
            if rt.empty:
                continue
            # Comisiones en USDT, o en la moneda base valoradas al precio del fill
            base = symbol.replace("USDT", "")
            fees = sum(f.commission if f.commissionAsset == "USDT"
                       else f.commission * f.price if f.commissionAsset == base else 0.0
                       for f in fills.itertuples())
            rows.append(summarize(symbol, rt["pnl"], fees))
    except Exception as e:
        print(f"No se pudo consultar Binance ({type(e).__name__}: {e}). ¿VPN activa?")
        return

    if not rows:
        print("No hay operaciones cerradas en Binance.")
        return
    print_table(rows)


def main(symbols: list = None):
    symbols = symbols or ACTIVE_ROSTER
    print("\n=========================== RESUMEN ===========================")
    ledger_report(symbols)
    binance_report(symbols)
    print("\nesperanza = win_rate × ganancia_media − (1 − win_rate) × perdida_media, en USDT por operación.")
    print("===============================================================")


if __name__ == "__main__":
    main(sys.argv[1:])
