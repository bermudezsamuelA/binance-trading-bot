"""
Ledger de operaciones del bot (orders/trades.csv).

Se lee y escribe como texto con el módulo csv: las celdas existentes nunca se reinterpretan ni se
reformatean (pandas, al reescribir, convierte 184 en 184.0 si la columna tiene vacíos). Al actualizar
una operación solo cambian las celdas de esa fila.

Columnas:
- Originales (mismo orden): order_id, symbol, action, entry_price, take_profit, stop_loss, quantity,
  status, timestamp, exit_price, pnl, exit_reason, exit_timestamp.
  Desde las órdenes MARKET: entry_price/exit_price = precio medio REAL ejecutado, quantity = cantidad
  comprada ejecutada y pnl = PnL NETO en USDT (USDT recibidos + residuo − USDT pagados − comisiones;
  residuo = residual_quantity valorada a exit_price).
  pnl vacío en una fila CLOSED = cerrada sin venta (polvo o sin saldo; ver exit_reason).
  status: PENDING (compra registrada antes de enviarla, sin confirmar) -> OPEN (misma fila, con los fills reales)
  -> CLOSED; o PENDING -> CANCELLED si Binance no tiene la orden. PENDING y CANCELLED no son operaciones.
- Nuevas (al final): EXECUTION_COLUMNS. Las filas antiguas las tienen vacías.

Si el archivo tiene un encabezado sin las columnas nuevas, ensure_ledger() guarda una copia
(trades.backup-AAAAMMDD-HHMMSS.csv) y añade las columnas al final, vacías, sin tocar el resto.
"""
import csv
import math
import os
import shutil
import time
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER_DIR = os.path.join(BASE_DIR, "orders")
LEDGER_FILE = os.path.join(LEDGER_DIR, "trades.csv")
# Diario de senales: cada BUY de una estrategia, abierto o bloqueado por un filtro de entrada (strategy_engine.py),
# para medir despues si los filtros ayudan. El resultado de las bloqueadas se puede simular con las velas.
SIGNALS_FILE = os.path.join(LEDGER_DIR, "signals.csv")
SIGNALS_COLUMNS = [
    "logged_at", "symbol", "open_time", "strategy", "window", "multiplier", "entry_price", "take_profit", "stop_loss",
    "risk_pct", "decision", "reason", "momentum_on", "market",
]

LEGACY_COLUMNS = [
    "order_id", "symbol", "action", "entry_price", "take_profit", "stop_loss", "quantity", "status",
    "timestamp", "exit_price", "pnl", "exit_reason", "exit_timestamp",
]
EXECUTION_COLUMNS = [
    "signal_price",        # precio de la señal (cierre de la vela); entry_price / signal_price = deslizamiento
    "net_quantity",        # cantidad en cartera: quantity menos la comisión cobrada en la moneda base
    "entry_quote",         # USDT pagados en la compra (cummulativeQuoteQty)
    "entry_fee_usdt",      # comisiones de la compra valoradas en USDT
    "entry_fees",          # comisiones de la compra por activo, p. ej. "0.0184 DOGE"
    "exit_trigger_price",  # precio que disparó el TP/SL (exit_price es el precio medio ejecutado)
    "exit_quantity",       # cantidad vendida
    "exit_quote",          # USDT recibidos en la venta, antes de comisión (cummulativeQuoteQty)
    "exit_fee_usdt",       # comisiones de la venta valoradas en USDT
    "exit_fees",           # comisiones de la venta por activo
    "exit_order_id",       # orderId de la venta en Binance
    "residual_quantity",   # lo que quedó en la cuenta sin poder venderse (bajo el stepSize/mínimo); pnl lo valora
                           # a exit_price (con la comisión de compra en la moneda base siempre queda casi un paso)
    "client_order_id",     # newClientOrderId de la compra (lo genera Node): la fila PENDING se escribe ANTES de
                           # enviarla, así una compra ejecutada justo antes de que el proceso muera no queda huérfana
]

# Estados de una fila. PENDING: compra enviada (o a punto) sin confirmar; pasa a OPEN con los fills reales o a
# CANCELLED si Binance no la tiene. Ni PENDING ni CANCELLED entran en las métricas (report.py).
PENDING, OPEN, CLOSED, CANCELLED = "PENDING", "OPEN", "CLOSED", "CANCELLED"
LEDGER_COLUMNS = LEGACY_COLUMNS + EXECUTION_COLUMNS

NUMERIC_COLUMNS = {
    "entry_price", "take_profit", "stop_loss", "quantity", "exit_price", "pnl", "signal_price", "net_quantity",
    "entry_quote", "entry_fee_usdt", "exit_trigger_price", "exit_quantity", "exit_quote", "exit_fee_usdt",
    "residual_quantity",
}


def format_value(value) -> str:
    """Valor -> celda. Números sin notación científica (1e-07 -> 0.0000001); None/NaN -> vacío."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return format(Decimal(repr(value)), "f")
    return str(value)


def _read(path: str):
    """Encabezado y filas como listas de texto."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        rows = [row for row in reader if row]
    return header, rows


def _write(path: str, header: list, rows: list):
    """Reescritura atómica: archivo temporal y os.replace (un corte a mitad no deja el ledger roto)."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    os.replace(tmp, path)


def ensure_ledger(path: str = None) -> list:
    """Crea el ledger si no existe y migra el encabezado si le faltan columnas. Devuelve el encabezado."""
    path = path or LEDGER_FILE
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
        print(f"[SISTEMA] Directorio '{directory}' creado.")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        _write(path, LEDGER_COLUMNS, [])
        print("[SISTEMA] Ledger trades.csv inicializado en blanco.")
        return list(LEDGER_COLUMNS)

    header, rows = _read(path)
    missing = [c for c in LEDGER_COLUMNS if c not in header]
    if not missing:
        return header

    too_long = [i + 2 for i, row in enumerate(rows) if len(row) > len(header)]
    if too_long:
        raise ValueError(f"Ledger con filas de más campos que el encabezado (líneas {too_long[:5]}): "
                         "no se migra para no desalinear columnas.")
    backup = os.path.join(os.path.dirname(path), f"trades.backup-{time.strftime('%Y%m%d-%H%M%S')}.csv")
    shutil.copy2(path, backup)
    new_header = header + missing
    new_rows = [row + [""] * (len(new_header) - len(row)) for row in rows]
    _write(path, new_header, new_rows)
    print(f"[LEDGER] Encabezado migrado (+{len(missing)} columnas, {len(rows)} filas intactas). Copia: {backup}")
    return new_header


def append_trade(trade: dict, path: str = None):
    """Añade una operación. Las columnas que no vengan en trade quedan vacías."""
    path = path or LEDGER_FILE
    header = ensure_ledger(path)
    needs_newline = not _ends_with_newline(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        csv.writer(f, lineterminator="\n").writerow([format_value(trade.get(c)) for c in header])


def append_signal(signal: dict, path: str = None):
    """Añade una fila al diario de señales (orders/signals.csv); lo crea con su encabezado si no existe."""
    path = path or SIGNALS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        if new:
            writer.writerow(SIGNALS_COLUMNS)
        writer.writerow([format_value(signal.get(c)) for c in SIGNALS_COLUMNS])


def _ends_with_newline(path: str) -> bool:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            return True
        f.seek(-1, os.SEEK_END)
        return f.read(1) == b"\n"


def _same_id(cell: str, order_id) -> bool:
    if str(cell).strip() == str(order_id).strip():
        return True
    try:
        return int(float(cell)) == int(float(order_id))
    except (TypeError, ValueError):
        return False


def update_trade(order_id, values: dict, path: str = None, symbol: str = None, only_open: bool = False) -> int:
    """Actualiza solo las celdas indicadas de la(s) fila(s) con ese order_id. Devuelve cuántas cambió.

    Binance numera las órdenes POR SÍMBOLO (y la testnet se reinicia cada mes): el mismo orderId puede estar
    en otra moneda o en una fila antigua ya cerrada. Para cerrar una posición se pasa symbol y only_open=True,
    así solo cambia la fila OPEN de esa moneda."""
    path = path or LEDGER_FILE
    ensure_ledger(path)
    header, rows = _read(path)
    unknown = [k for k in values if k not in header]
    if unknown:
        raise KeyError(f"Columnas desconocidas en el ledger: {unknown}")
    id_col = header.index("order_id")
    symbol_col = header.index("symbol")
    status_col = header.index("status")

    def cell(row, col):
        return row[col] if len(row) > col else ""

    updated = 0
    for row in rows:
        if symbol is not None and cell(row, symbol_col).strip().upper() != str(symbol).strip().upper():
            continue
        if only_open and cell(row, status_col) != "OPEN":
            continue
        if len(row) > id_col and _same_id(row[id_col], order_id):
            row.extend([""] * (len(header) - len(row)))
            for key, value in values.items():
                row[header.index(key)] = format_value(value)
            updated += 1
    if updated:
        _write(path, header, rows)
    return updated


def _parse_cell(column: str, cell: str):
    if cell is None or cell == "":
        return None
    if column in NUMERIC_COLUMNS:
        try:
            value = float(cell)
            return value if math.isfinite(value) else None
        except ValueError:
            return None
    if column in ("order_id", "timestamp", "exit_timestamp", "exit_order_id"):
        try:
            return int(float(cell))
        except ValueError:
            return cell
    return cell


def update_by_client_order_id(client_order_id: str, values: dict, path: str = None, symbol: str = None,
                              statuses=(PENDING,)) -> int:
    """Actualiza las celdas indicadas de la fila con ese client_order_id (y estado en statuses). Devuelve cuántas
    cambió. Así la compra confirmada reutiliza su fila PENDING en vez de añadir otra."""
    path = path or LEDGER_FILE
    ensure_ledger(path)
    header, rows = _read(path)
    unknown = [k for k in values if k not in header]
    if unknown:
        raise KeyError(f"Columnas desconocidas en el ledger: {unknown}")
    cid_col, symbol_col, status_col = header.index("client_order_id"), header.index("symbol"), header.index("status")

    def cell(row, col):
        return row[col] if len(row) > col else ""

    updated = 0
    for row in rows:
        if not client_order_id or cell(row, cid_col) != str(client_order_id):
            continue
        if symbol is not None and cell(row, symbol_col).strip().upper() != str(symbol).strip().upper():
            continue
        if statuses is not None and cell(row, status_col) not in statuses:
            continue
        row.extend([""] * (len(header) - len(row)))
        for key, value in values.items():
            row[header.index(key)] = format_value(value)
        updated += 1
    if updated:
        _write(path, header, rows)
    return updated


def trades_with_status(status: str, path: str = None) -> list:
    """Filas con ese estado, con tipos de JSON válidos (vacío -> None, nunca NaN)."""
    path = path or LEDGER_FILE
    if not os.path.exists(path):
        return []
    header, rows = _read(path)
    trades = []
    for row in rows:
        record = dict(zip(header, row))
        if record.get("status") == status:
            trades.append({column: _parse_cell(column, record.get(column, "")) for column in header})
    return trades


def open_trades(path: str = None) -> list:
    """Operaciones OPEN con tipos de JSON válidos (vacío -> None, nunca NaN)."""
    return trades_with_status(OPEN, path)


def pending_trades(path: str = None) -> list:
    """Compras PENDING (sin confirmar): al arrancar se consultan en Binance por client_order_id."""
    return trades_with_status(PENDING, path)


def open_symbols(path: str = None) -> list:
    """Monedas con posición abierta o compra pendiente: el WebSocket también tiene que vigilarlas."""
    return sorted({t["symbol"] for t in open_trades(path) + pending_trades(path) if t.get("symbol")})
