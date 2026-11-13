# custom_strategies/trade_filters.py
from typing import Optional
import numpy as np
import pandas as pd


class TradeFilters:
    @staticmethod
    def validate_fibonacci_pullback(
        retracement_level: float,
        min_allowed: float = 0.382,
        max_allowed: float = 0.750
    ) -> bool:
        """
        Filtro de Zona de Valor e Invalidación Estricta por Fibonacci (Módulo 2):
        - El retroceso en 1H debe haber corregido al menos hasta la zona mínima (0.382 / 0.50).
        - Si el retroceso supera el nivel 0.75 (75%), se invalida y cancela el setup.
        """
        if retracement_level is None or np.isnan(retracement_level):
            return False
        return float(min_allowed) <= float(retracement_level) <= float(max_allowed)

    @staticmethod
    def validate_pullback_depth(
        pullback_extreme: float,
        ema_15m: Optional[float] = None,
        sma_200_1h: Optional[float] = None,
        ema_50_4h: Optional[float] = None,
        fibo_50_1h: Optional[float] = None,
        is_long: bool = True,
        tolerance_pct: float = 0.0025
    ) -> bool:
        """
        Filtro de Profundidad de Pullback en Cripto (Módulo 3 - Casos DOT e ICP):
        Descarta pullbacks superficiales que solo tocan la EMA 50 de 5M y quedan en el aire.
        Exige que el extremo del retroceso haya alcanzado (con una tolerancia de 0.25%) al menos uno de:
        - EMA 50 de 15M (en scalping/intradía)
        - SMA 200 de 1H o EMA 50 de 4H (en sobreextensión/day trading)
        - Nivel 0.50 de Fibonacci del impulso de 1H
        """
        if pullback_extreme is None or pullback_extreme <= 0:
            return False

        ext = float(pullback_extreme)
        valid_targets = [
            float(x) for x in (ema_15m, sma_200_1h, ema_50_4h, fibo_50_1h)
            if x is not None and not np.isnan(x) and float(x) > 0
        ]
        if not valid_targets:
            return True

        if is_long:
            # En Long, el mínimo del pullback debe haber bajado hasta tocar o perforar alguno de los soportes
            return any(ext <= target * (1.0 + tolerance_pct) for target in valid_targets)
        else:
            # En Short, el máximo del pullback debe haber subido hasta tocar o superar alguna de las resistencias
            return any(ext >= target * (1.0 - tolerance_pct) for target in valid_targets)

    @staticmethod
    def check_sma200_5m_fakeout(
        current_price: float,
        sma_200_5m: Optional[float],
        candle_closed_beyond_sma: bool = False,
        is_long: bool = True,
        obstacle_threshold_pct: float = 0.50
    ) -> bool:
        """
        Filtro Anti-Fakeout por SMA 200 en 5M (Módulo 3 - Casos BCH y BTC):
        - En LONG:
            * Si el precio ya está por encima de la SMA 200 (5M) y cerró confirmando -> APROBADO (True).
            * Si la SMA 200 (5M) está por encima del precio actual a una distancia < `obstacle_threshold_pct` (0.5%),
              actúa como un techo inminente -> BLOQUEADO (False) hasta que la rompa y cierre por encima.
            * Si la SMA 200 (5M) está muy lejos por encima (>= `obstacle_threshold_pct`), hay espacio operativo -> APROBADO (True).
        - En SHORT: Simétrico.
        """
        if sma_200_5m is None or np.isnan(sma_200_5m) or sma_200_5m <= 0 or current_price <= 0:
            return True

        px = float(current_price)
        sma = float(sma_200_5m)
        dist_pct = abs(px - sma) / px * 100.0

        if is_long:
            if px >= sma:
                # Si acaba de cruzarla y está pegado (< 0.15%), exigimos que la vela haya cerrado encima
                if dist_pct < 0.15 and not candle_closed_beyond_sma:
                    return False
                return True
            else:
                # El precio está por debajo de la SMA 200 (5M): si está a menos de 0.5%, bloquea por riesgo de rechazo
                if dist_pct < obstacle_threshold_pct:
                    return False
                return True
        else:
            if px <= sma:
                if dist_pct < 0.15 and not candle_closed_beyond_sma:
                    return False
                return True
            else:
                # En Short, el precio está por encima de la SMA 200 (5M): si está a menos de 0.5% abajo, bloquea
                if dist_pct < obstacle_threshold_pct:
                    return False
                return True

    @staticmethod
    def validate_deceleration(df_window: pd.DataFrame, lookback: int = 5, ratio_threshold: float = 0.85) -> bool:
        """
        Validador de Compresión y Desaceleración en el Pullback (Módulos 2 y 3):
        Verifica que el retroceso no sea una caída/subida vertical acelerada, sino que las últimas
        `lookback` velas muestren contracción en el tamaño de sus cuerpos o mechas de rechazo.
        """
        if df_window is None or len(df_window) < lookback + 5:
            return True

        opens = df_window["open"].to_numpy(float)
        closes = df_window["close"].to_numpy(float)
        body_sizes = np.abs(closes - opens)

        avg_prior = float(np.mean(body_sizes[-(lookback + 8):-lookback]))
        avg_recent = float(np.mean(body_sizes[-lookback:]))

        if avg_prior <= 0:
            return True

        return avg_recent <= (avg_prior * ratio_threshold)