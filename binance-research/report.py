"""
Resumen de resultados del bot: win rate, esperanza matemática y PnL por símbolo.

1. Ledger local (orders/trades.csv): operaciones cerradas con datos de ejecución real (órdenes MARKET:
   precio medio, cantidad y comisiones de Binance) y PnL neto de comisiones. Las filas antiguas (órdenes
   LIMIT que quizá no se llenaron) no entran en el resumen.
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

from config import ACTIVE_ROSTER, MARKET_DATA_REST_URL, load_env
from ledger import LEDGER_FILE

TIMEOUT = 10


def summarize(symbol: str, pnl: pd.Series, fees: float = 0.0, net: bool = False) -> dict:
    """Métricas de una serie de PnL por operación (USDT). net=True: pnl ya descuenta las comisiones
    (win rate y esperanza sobre el PnL neto); net=False: pnl bruto y las comisiones se restan al final."""
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
        # E = p * G - (1 - p) * L  (USDT por operación; neta de comisiones si net=True)
        "esperanza": round(float(p * avg_win - (1 - p) * avg_loss), 4),
        "profit_factor": round(float(wins.sum() / gross_loss), 2) if gross_loss > 0 else None,
        "pnl_bruto": round(float(pnl.sum() + fees if net else pnl.sum()), 4),
        "comisiones": round(float(fees), 4),
        "pnl_neto": round(float(pnl.sum() if net else pnl.sum() - fees), 4),
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

    # PENDING (compra sin confirmar) y CANCELLED (Binance no la tenía) no son operaciones: fuera de las métricas
    pending = df[df["status"] == "PENDING"]
    cancelled = df[df["status"] == "CANCELLED"]
    if len(pending):
        print(f"\n{len(pending)} compra(s) PENDIENTE(S) de confirmar en Binance: el bot las resuelve al arrancar.")
    if len(cancelled):
        print(f"{len(cancelled)} compra(s) CANCELADA(S) (no llegaron a Binance o fueron rechazadas): fuera del resumen.")
    df = df[~df["status"].isin(["PENDING", "CANCELLED"])]

    # Solo cuentan las filas con datos de ejecución real (entry_quote = USDT pagados según Binance)
    real = df[df["entry_quote"].notna()] if "entry_quote" in df.columns else df.iloc[0:0]
    legacy = df[~df.index.isin(real.index)]
    if len(legacy):
        print(f"\n{len(legacy)} operaciones antiguas sin datos de ejecución real (órdenes LIMIT): fuera del resumen.")

    closed = real[real["status"] == "CLOSED"]
    sold = closed[closed["pnl"].notna()]
    no_sale = closed[closed["pnl"].isna()]
    if sold.empty:
        print("Ninguna operación con ejecución real se ha cerrado con venta todavía.")
    else:
        fees = lambda g: float(g["entry_fee_usdt"].fillna(0).sum() + g["exit_fee_usdt"].fillna(0).sum())
        print()
        print_table([summarize(s, g["pnl"], fees(g), net=True) for s, g in sold.groupby("symbol")])
        # Deslizamiento real frente al precio de la señal (entrada) y al nivel TP/SL (salida); el backtest asume 0.02 %
        entry_slip = (sold["entry_price"] / sold["signal_price"] - 1).dropna() * 100
        exit_slip = (sold["exit_price"] / sold["exit_trigger_price"] - 1).dropna() * 100
        if len(entry_slip) and len(exit_slip):
            print(f"\nDeslizamiento medio: entrada {entry_slip.mean():+.4f} % (vs señal), "
                  f"salida {exit_slip.mean():+.4f} % (vs nivel TP/SL)")
        # Residuo bajo el stepSize que quedó en la cuenta: el PnL lo valora al precio de salida (no es pérdida)
        if "residual_quantity" in sold.columns:
            residual = (sold["residual_quantity"].fillna(0) * sold["exit_price"]).groupby(sold["symbol"]).sum()
            residual = residual[residual > 0]
            if len(residual):
                detalle = ", ".join(f"{s} {v:.4f}" for s, v in residual.items())
                print(f"\nResiduo sin vender (bajo el paso de Binance), valorado a la salida e incluido en el PnL: "
                      f"{residual.sum():.4f} USDT ({detalle})")
        print("\nMotivo de cierre:")
        print(sold["exit_reason"].value_counts().to_string())
    if len(no_sale):
        print(f"\n{len(no_sale)} cerradas sin venta (sin PnL):")
        print(no_sale["exit_reason"].value_counts().to_string())


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
    return df.sort_values(["time", "id"], kind="stable")


def lot_filters(rest_url: str, symbol: str) -> tuple:
    """(stepSize, minNotional) del par (público): por debajo de eso un resto no se puede vender (residuo)."""
    info = requests.get(f"{rest_url}/v3/exchangeInfo", params={"symbol": symbol}, timeout=TIMEOUT).json()
    filters = {f["filterType"]: f for f in info["symbols"][0]["filters"]}
    step = float(filters.get("LOT_SIZE", {}).get("stepSize", 0) or 0)
    notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
    return step, float(notional.get("minNotional", 0) or 0)


def round_trips(fills: pd.DataFrame, base_asset: str, step: float = 0.0, min_notional: float = 0.0,
                bnb_price: float = None) -> pd.DataFrame:
    """Una fila por COMPRA cerrada (como el ledger: una posición = una orden de compra y sus ventas).

    - Se agrupa por orden (una MARKET suele llenarse en varios fills: cada fill no es una operación).
    - La comisión de compra cobrada en la moneda base reduce lo que se puede vender (cantidad neta).
    - Las ventas se emparejan FIFO con las compras. Cuando lo que queda de una compra está por debajo del stepSize
      o del mínimo nocional ya no se puede vender (residuo): la compra se da por cerrada y el residuo se valora al
      precio de la venta, igual que el PnL del ledger.
    - Comisiones en USDT tal cual, en la moneda base a su precio y en BNB con bnb_price (sin precio cuentan 0).
    pnl = PnL neto en USDT; fees = todas las comisiones valoradas en USDT."""
    if fills.empty:
        return pd.DataFrame(columns=["qty", "pnl", "fees", "open"])
    f = fills.copy()
    f["quote"] = f["quoteQty"].astype(float) if "quoteQty" in f.columns else f["price"] * f["qty"]
    f["fee_base"] = f["commission"].where(f["commissionAsset"] == base_asset, 0.0)
    f["fee_usdt"] = f["commission"].where(f["commissionAsset"] == "USDT", 0.0)
    if bnb_price:
        f["fee_usdt"] += f["commission"].where(f["commissionAsset"] == "BNB", 0.0) * bnb_price
    orders = (f.groupby("orderId", sort=False)
               .agg(time=("time", "min"), isBuyer=("isBuyer", "first"), qty=("qty", "sum"), quote=("quote", "sum"),
                    fee_base=("fee_base", "sum"), fee_usdt=("fee_usdt", "sum"))
               .sort_values("time", kind="stable"))

    def unsellable(qty: float, price: float) -> bool:
        return qty <= 1e-12 or (step > 0 and qty < step - 1e-12) or (min_notional > 0 and qty * price < min_notional)

    trades, lots = [], []
    for o in orders.itertuples():
        price = o.quote / o.qty if o.qty > 0 else 0.0
        if o.isBuyer:
            net = o.qty - o.fee_base
            lots.append({"net": net, "left": net, "cost": o.quote + o.fee_usdt, "proceeds": 0.0,
                         "fees": o.fee_usdt + o.fee_base * price})
            continue
        qty_left = o.qty
        sell_fee = o.fee_usdt + o.fee_base * price
        while qty_left > 1e-12 and lots:
            lot = lots[0]
            m = min(lot["left"], qty_left)
            share = m / o.qty
            lot["proceeds"] += m * price - sell_fee * share
            lot["fees"] += sell_fee * share
            lot["left"] -= m
            qty_left -= m
            if unsellable(lot["left"], price):
                residual = max(lot["left"], 0.0) * price
                trades.append({"qty": lot["net"] - lot["left"], "pnl": lot["proceeds"] + residual - lot["cost"],
                               "fees": lot["fees"], "open": False})
                lots.pop(0)
    for lot in lots:
        trades.append({"qty": lot["left"], "pnl": None, "fees": lot["fees"], "open": True})
    return pd.DataFrame(trades, columns=["qty", "pnl", "fees", "open"])


def binance_report(symbols: list):
    print("\n--- 2. Binance (compras y ventas ejecutadas) ---")
    load_env()
    rest_url = f"{MARKET_DATA_REST_URL}/api"  # mismo mercado que el bot (BINANCE_MARKET)
    rows = []
    try:
        bnb_price = None
        for symbol in symbols:
            fills = fetch_fills(rest_url, symbol)
            if fills.empty:
                continue
            if bnb_price is None and (fills["commissionAsset"] == "BNB").any():
                try:
                    bnb_price = float(requests.get(f"{rest_url}/v3/ticker/price", params={"symbol": "BNBUSDT"},
                                                   timeout=TIMEOUT).json()["price"])
                    print(f"Comisiones en BNB valoradas al precio actual de BNB ({bnb_price:g} USDT).")
                except Exception:
                    bnb_price = 0.0
                    print("No se pudo leer el precio de BNB: las comisiones en BNB cuentan 0.")
            step, min_notional = lot_filters(rest_url, symbol)
            base = fills["symbol"].iloc[0][:-4] if "symbol" in fills.columns else symbol.replace("USDT", "")
            rt = round_trips(fills, base, step, min_notional, bnb_price)
            still_open = rt[rt["open"]]
            if len(still_open):
                print(f"{symbol}: {len(still_open)} compra(s) sin vender ({still_open['qty'].sum():g} {base}); "
                      f"no entran en el resumen.")
            closed = rt[~rt["open"]]
            if closed.empty:
                continue
            rows.append(summarize(symbol, closed["pnl"].astype(float), float(closed["fees"].sum()), net=True))
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
