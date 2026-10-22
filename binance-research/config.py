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

# Filtros de entrada (doc/agente-rl-y-esperanza-positiva.md, sugerencias 3, 5 y 6). Los aplican igual el evaluador
# (walk_forward.py, al elegir los parametros y al probar) y el bot en vivo (strategy_engine.py), para que el bot opere
# lo mismo que se valido. None desactiva cada uno. Detalle en strategy_filters.py.
ENTRY_MIN_RISK_PCT = 0.015   # descarta el BUY si entrada - SL < 1.5 % del precio (con 0.5 % el costo es ~0.5 R)
COSIGNAL_CANDLES = 48        # el BUY necesita que la misma regla haya dado BUY en otra moneda del roster en las 48 velas
                             # anteriores (12 h con velas de 15 min), sin contar la actual
MOMENTUM_MONTHS = 12         # una moneda solo opera su estrategia si el PnL en sombra de sus ultimos 12 meses es > 0
