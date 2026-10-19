# config.py
import os

ACTIVE_ROSTER = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]

# Temporalidad de las velas que ve la estrategia. Debe ser la misma del backtest
# (download_data.py usa data_frequency="15m" y optimize.py evalua cierres de 15 min).
KLINE_INTERVAL = "15m"
KLINE_INTERVAL_MS = 15 * 60 * 1000

# Mercado de Binance: lo decide BINANCE_MARKET ("testnet" o "mainnet") en el .env de la raiz, el mismo
# que lee Node (src/config/env.ts) para las ordenes y el WebSocket. Asi la precarga de velas (server.py)
# y el resumen (report.py) siempre son del mismo mercado en el que opera el bot.
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")


def load_env():
    """Carga el .env de la raiz en os.environ (sin pisar variables ya definidas)."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, encoding="utf-8") as env_file:
        for line in env_file:
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.strip().split("=", 1)
                os.environ.setdefault(key, value.strip('"\''))


load_env()
_MARKET_REST_URLS = {
    "testnet": "https://testnet.binance.vision",
    "mainnet": "https://api.binance.com",
}
BINANCE_MARKET = os.environ.get("BINANCE_MARKET", "testnet").strip().lower()
if BINANCE_MARKET not in _MARKET_REST_URLS:
    raise ValueError(f'BINANCE_MARKET="{BINANCE_MARKET}" no es valido. Usa "testnet" o "mainnet" en el archivo .env')
MARKET_DATA_REST_URL = _MARKET_REST_URLS[BINANCE_MARKET]

# Precarga: max(ventana de las estrategias cargadas) + margen, con un minimo.
PRESEED_MARGIN = 20
PRESEED_MIN = 100
