# quantitative_strategies/capitulation.py
import math

import pandas as pd

from config import KLINE_INTERVAL_MS

# Compra de capitulacion solo con velas spot (doc/agente-rl-y-esperanza-positiva.md, practica 5, y
# doc/estrategia-v3-hacia-el-80.md, seccion 2): caida brusca en las ultimas 4 velas con volumen climatico.
# Sale con la geometria X5 de la v3 (seccion 2.10): TP corto y SL ancho en multiplos de la volatilidad diaria.
DROP_CANDLES = 4          # caida medida en las ultimas 4 velas (1 hora con velas de 15 min)
VOLUME_SPIKE = 2.0        # volumen de la vela >= 2 x la media de la ventana
TP_SD = 0.7               # TP = entrada * (1 + 0.7 * sd)
SL_SD = 1.75              # SL = entrada * (1 - 1.75 * sd)
MIN_RISK_PCT = 0.005      # riesgo minimo 0.5 % del precio, como las demas estrategias
SQRT_DROP = math.sqrt(DROP_CANDLES)
DAY_MS = 86_400_000


def set_candle_ms(candle_ms: int):
    """Velas por dia para pasar la volatilidad de una vela a la diaria (sqrt(96) con velas de 15 min). En vivo sale de
    config.KLINE_INTERVAL_MS; el evaluador la cambia cuando prueba otra temporalidad (ml_evaluator.py --interval)."""
    global SQRT_DAY
    SQRT_DAY = math.sqrt(DAY_MS // candle_ms)


set_candle_ms(KLINE_INTERVAL_MS)


class CapitulationStrategy:
    def __init__(self, window=48, std_dev_multiplier=2.5):
        self.window = window
        self.std_dev_multiplier = std_dev_multiplier
        self.history = {}

    def evaluate(self, symbol: str, market_data) -> dict:
        if isinstance(market_data, dict):
            current_price = float(market_data.get("close", 0.0))
            current_volume = float(market_data.get("volume", 0.0))
        else:
            current_price = float(market_data)
            current_volume = 0.0

        if symbol not in self.history:
            self.history[symbol] = {"prices": [], "volumes": []}

        history = self.history[symbol]
        history["prices"].append(current_price)
        history["volumes"].append(current_volume)

        # window retornos necesitan window + 1 cierres
        if len(history["prices"]) > self.window + 1:
            history["prices"].pop(0)
        if len(history["volumes"]) > self.window:
            history["volumes"].pop(0)

        prices = history["prices"]
        if len(prices) < self.window + 1:
            return {"action": "HOLD"}

        returns = [prices[j] / prices[j - 1] - 1 for j in range(1, len(prices))]
        rolling_std = pd.Series(returns).std()
        mean_volume = pd.Series(history["volumes"]).mean()
        drop = current_price / prices[-1 - DROP_CANDLES] - 1

        # Capitulacion: las ultimas 4 velas caen mas de k desviaciones (de 4 velas) y la vela trae volumen climatico
        if drop < -(rolling_std * self.std_dev_multiplier * SQRT_DROP) and current_volume >= mean_volume * VOLUME_SPIKE:
            sd = rolling_std * SQRT_DAY
            tp = current_price * (1 + TP_SD * sd)
            sl = current_price * (1 - SL_SD * sd)
            risk = current_price - sl

            if risk < (current_price * MIN_RISK_PCT):
                return {"action": "HOLD"}

            return {
                "action": "BUY",
                "entry_price": current_price,
                "take_profit": round(tp, 8),
                "stop_loss": round(sl, 8),
                "weight": 0.8
            }

        return {"action": "HOLD"}
