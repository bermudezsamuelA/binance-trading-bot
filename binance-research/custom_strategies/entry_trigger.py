# custom_strategies/entry_trigger.py
import numpy as np
import pandas as pd


class EntryTrigger:
    def __init__(self, pivot_left: int = 3, pivot_right: int = 3, double_pattern_tol_pct: float = 0.35):
        """
        Motor de Disparo Dual (Módulo 2 y Módulo 3): Plan A (5M) y Plan B (2M).

        Args:
            pivot_left (int): Velas a la izquierda para confirmar un Swing High/Low.
            pivot_right (int): Velas a la derecha para confirmar un Swing High/Low (sin look-ahead bias).
            double_pattern_tol_pct (float): Tolerancia porcentual máxima entre dos suelos/techos (ej. 0.35%).
        """
        self.pivot_left = int(pivot_left)
        self.pivot_right = int(pivot_right)
        self.double_pattern_tol_pct = float(double_pattern_tol_pct)

    @staticmethod
    def find_pivots(highs: np.ndarray, lows: np.ndarray, left: int = 3, right: int = 3) -> tuple:
        """
        Detecta índices y precios de Swing Highs y Swing Lows confirmados.
        No evalúa las últimas `right` velas para evitar look-ahead bias en backtesting y vivo.

        Returns:
            (swing_highs, swing_lows): Listas de tuplas (indice, precio).
        """
        n = len(highs)
        swing_highs = []
        swing_lows = []
        if n < left + right + 1:
            return swing_highs, swing_lows

        for i in range(left, n - right):
            window_h = highs[i - left : i + right + 1]
            if highs[i] == np.max(window_h) and np.sum(window_h == highs[i]) == 1:
                swing_highs.append((i, float(highs[i])))

            window_l = lows[i - left : i + right + 1]
            if lows[i] == np.min(window_l) and np.sum(window_l == lows[i]) == 1:
                swing_lows.append((i, float(lows[i])))

        return swing_highs, swing_lows

    @staticmethod
    def is_engulfing(opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, is_long: bool = True, lookback: int = 3) -> bool:
        """
        Verifica si en las últimas `lookback` velas se formó un patrón de Vela Envolvente
        (Bullish Engulfing para Long, Bearish Engulfing para Short) o vela de rechazo fuerte.
        """
        if len(closes) < lookback + 1:
            return False

        for k in range(1, lookback + 1):
            idx = -k
            prev_idx = idx - 1
            o_curr, c_curr = opens[idx], closes[idx]
            o_prev, c_prev = opens[prev_idx], closes[prev_idx]
            body_curr = abs(c_curr - o_curr)
            body_prev = abs(c_prev - o_prev)

            if is_long:
                # Vela previa bajista (o doji) y vela actual alcista cuyo cuerpo envuelve o supera el máximo previo
                if c_curr > o_curr and (c_prev <= o_prev) and c_curr >= o_prev and body_curr >= body_prev * 0.9:
                    return True
            else:
                # Vela previa alcista y vela actual bajista cuyo cuerpo envuelve a la baja
                if c_curr < o_curr and (c_prev >= o_prev) and c_curr <= o_prev and body_curr >= body_prev * 0.9:
                    return True
        return False

    def detect_double_or_triple_level(self, pivots: list, is_long: bool = True) -> dict:
        """
        Detecta formación de Doble Suelo / Triple Suelo (en Long) o Doble/Triple Techo (en Short)
        evaluando los últimos pivotes confirmados (Módulo 3 - Setup BTC y BCH).
        """
        if len(pivots) < 2:
            return {"detected": False, "touches": 0, "extreme_price": None}

        recent = pivots[-3:] if len(pivots) >= 3 else pivots[-2:]
        last_idx, last_price = recent[-1]
        prev_idx, prev_price = recent[-2]

        if last_price <= 0:
            return {"detected": False, "touches": 0, "extreme_price": None}

        diff_pct = abs(last_price - prev_price) / last_price * 100.0
        if diff_pct <= self.double_pattern_tol_pct:
            touches = 2
            extreme = min(last_price, prev_price) if is_long else max(last_price, prev_price)
            if len(recent) == 3:
                first_price = recent[0][1]
                if abs(last_price - first_price) / last_price * 100.0 <= self.double_pattern_tol_pct:
                    touches = 3
                    extreme = min(extreme, first_price) if is_long else max(extreme, first_price)
            return {"detected": True, "touches": touches, "extreme_price": float(extreme)}

        return {"detected": False, "touches": 1, "extreme_price": float(last_price)}

    @staticmethod
    def check_diagonal_breakout(pivots: list, current_index: int, current_close: float, prev_close: float, is_long: bool = True) -> dict:
        """
        Traza la línea de tendencia diagonal (cuña/triángulo) usando los dos últimos pivotes
        relevantes del pullback y verifica si la vela actual rompe y cierra fuera de la diagonal.
        """
        if len(pivots) < 2:
            return {"broken": False, "projected_line": None}

        (x1, y1), (x2, y2) = pivots[-2], pivots[-1]
        if x2 <= x1:
            return {"broken": False, "projected_line": None}

        # En un pullback alcista (Long), la diagonal superior une máximos decrecientes (pendiente <= 0)
        # En un pullback bajista (Short), la diagonal inferior une mínimos crecientes (pendiente >= 0)
        slope = (y2 - y1) / float(x2 - x1)
        if is_long and slope > 0:
            # Si los máximos ya son crecientes, usamos el último máximo como nivel horizontal de BOS
            projected_now = y2
            projected_prev = y2
        elif not is_long and slope < 0:
            projected_now = y2
            projected_prev = y2
        else:
            projected_now = y2 + slope * (current_index - x2)
            projected_prev = y2 + slope * ((current_index - 1) - x2)

        if is_long:
            broken = current_close > projected_now and prev_close <= projected_prev * 1.001
        else:
            broken = current_close < projected_now and prev_close >= projected_prev * 0.999

        return {"broken": bool(broken), "projected_line": float(projected_now)}

    @staticmethod
    def select_fibonacci_stop_loss(impulse_low: float, impulse_high: float, pullback_extreme: float, is_long: bool = True, buffer_pct: float = 0.0015) -> dict:
        """
        Regla de colocación de Stop Loss según el Paso 6 del Módulo 2:
        El SL se coloca inmediatamente por detrás del siguiente nivel de Fibonacci válido en 1H
        (0.618 o 0.75) que NO haya sido perforado por el pullback.
        """
        rng = abs(impulse_high - impulse_low)
        if rng <= 0:
            return {"valid": False, "stop_loss": None, "fibo_level_used": None, "retracement": 0.0}

        if is_long:
            retracement = (impulse_high - pullback_extreme) / rng
            fibo_618 = impulse_high - rng * 0.618
            fibo_750 = impulse_high - rng * 0.750

            if retracement > 0.750:
                return {"valid": False, "stop_loss": None, "fibo_level_used": "INVALID_OVER_0.75", "retracement": retracement}
            elif retracement <= 0.600:
                # Rebotó entre 0.50 y 0.60 -> SL protege detrás del 0.618
                sl = min(fibo_618, pullback_extreme) * (1.0 - buffer_pct)
                level_tag = "0.618"
            else:
                # Llegó cerca o debajo del 0.618 hasta 0.75 -> SL protege detrás del 0.75
                sl = min(fibo_750, pullback_extreme) * (1.0 - buffer_pct)
                level_tag = "0.750"
        else:
            retracement = (pullback_extreme - impulse_low) / rng
            fibo_618 = impulse_low + rng * 0.618
            fibo_750 = impulse_low + rng * 0.750

            if retracement > 0.750:
                return {"valid": False, "stop_loss": None, "fibo_level_used": "INVALID_OVER_0.75", "retracement": retracement}
            elif retracement <= 0.600:
                sl = max(fibo_618, pullback_extreme) * (1.0 + buffer_pct)
                level_tag = "0.618"
            else:
                sl = max(fibo_750, pullback_extreme) * (1.0 + buffer_pct)
                level_tag = "0.750"

        return {
            "valid": True,
            "stop_loss": float(sl),
            "fibo_level_used": level_tag,
            "retracement": round(float(retracement), 4)
        }

    def evaluate_plan_a_5m(
        self,
        df_5m: pd.DataFrame,
        impulse_low_1h: float,
        impulse_high_1h: float,
        is_long: bool = True
    ) -> dict:
        """
        Evalúa el Gatillo Principal (Plan A en 5M):
        1. Cambio de estructura en 5M (BOS sobre último Swing High/Low o ruptura de diagonal).
        2. Cierre de vela confirmado por encima de EMA 50 (5M) y superando SMA 200 (5M).
        3. Presencia opcional/recomendada de Doble Suelo/Techo + Vela Envolvente.
        4. Cálculo automático de Stop Loss (tras nivel Fibo 1H o mínimo local) y Take Profit 1 (extremo previo).
        """
        if df_5m is None or len(df_5m) < 55:
            return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Datos insuficientes en 5M"}

        opens = df_5m["open"].to_numpy(float)
        highs = df_5m["high"].to_numpy(float)
        lows = df_5m["low"].to_numpy(float)
        closes = df_5m["close"].to_numpy(float)
        n = len(closes)

        ema_50 = pd.Series(closes).ewm(span=50, adjust=False).mean().to_numpy()
        sma_200 = pd.Series(closes).rolling(window=200).mean().to_numpy() if n >= 200 else np.full(n, np.nan)

        curr_close = float(closes[-1])
        prev_close = float(closes[-2])
        curr_ema50 = float(ema_50[-1])
        curr_sma200 = float(sma_200[-1]) if not np.isnan(sma_200[-1]) else -1.0

        swing_highs, swing_lows = self.find_pivots(highs, lows, self.pivot_left, self.pivot_right)
        if not swing_highs or not swing_lows:
            return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Sin pivotes confirmados en 5M"}

        if is_long:
            # 1. Validar que el precio cierre sobre EMA 50 y no esté bloqueado por SMA 200
            if curr_close <= curr_ema50:
                return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Cierre 5M debajo de EMA 50"}
            if curr_sma200 > 0 and curr_close < curr_sma200:
                return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Cierre 5M debajo de SMA 200 (Filtro Fakeout)"}

            # 2. Verificar ruptura de diagonal o BOS (ruptura del último Swing High en 5M)
            diag = self.check_diagonal_breakout(swing_highs, n - 1, curr_close, prev_close, is_long=True)
            last_sh_price = swing_highs[-1][1]
            bos_confirmed = curr_close > last_sh_price and prev_close <= last_sh_price

            # Verificar si acaba de cruzar EMA 50 o SMA 200 como gatillo directo (caso BTC en Módulo 3)
            ema_cross = curr_close > curr_ema50 and prev_close <= float(ema_50[-2])
            sma_cross = curr_sma200 > 0 and curr_close > curr_sma200 and prev_close <= float(sma_200[-2])

            double_bottom = self.detect_double_or_triple_level(swing_lows, is_long=True)
            engulfing = self.is_engulfing(opens, highs, lows, closes, is_long=True)

            # Condición de disparo: (BOS o Ruptura Diagonal) O (Doble Suelo + Envolvente + Cruce de Media)
            structural_trigger = diag["broken"] or bos_confirmed or (double_bottom["detected"] and (ema_cross or sma_cross))
            if not structural_trigger:
                return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Esperando ruptura de estructura/diagonal en 5M"}

            # 3. Calcular Stop Loss (Fibo 1H vs Mínimo de estructura 5M)
            pullback_low = float(np.min(lows[-30:]))
            fibo_sl = self.select_fibonacci_stop_loss(impulse_low_1h, impulse_high_1h, pullback_low, is_long=True)
            if not fibo_sl["valid"]:
                return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Pullback perforó el 0.75 de Fibonacci en 1H"}

            local_sl = pullback_low * 0.9985
            stop_loss = min(fibo_sl["stop_loss"], local_sl)
            take_profit_1 = max(float(impulse_high_1h), curr_close + (curr_close - stop_loss))

            return {
                "triggered": True,
                "plan": "PLAN_A_5M",
                "action": "BUY",
                "entry_price": curr_close,
                "stop_loss": round(stop_loss, 8),
                "take_profit": round(take_profit_1, 8),
                "fibo_level_protected": fibo_sl["fibo_level_used"],
                "double_bottom": double_bottom["detected"],
                "engulfing": engulfing,
                "reason": "Ruptura 5M confirmada sobre EMA50/SMA200"
            }

        else:
            # Lógica simétrica para SHORT
            if curr_close >= curr_ema50:
                return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Cierre 5M encima de EMA 50"}
            if curr_sma200 > 0 and curr_close > curr_sma200:
                return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Cierre 5M encima de SMA 200"}

            diag = self.check_diagonal_breakout(swing_lows, n - 1, curr_close, prev_close, is_long=False)
            last_sl_price = swing_lows[-1][1]
            bos_confirmed = curr_close < last_sl_price and prev_close >= last_sl_price

            ema_cross = curr_close < curr_ema50 and prev_close >= float(ema_50[-2])
            sma_cross = curr_sma200 > 0 and curr_close < curr_sma200 and prev_close >= float(sma_200[-2])

            double_top = self.detect_double_or_triple_level(swing_highs, is_long=False)
            engulfing = self.is_engulfing(opens, highs, lows, closes, is_long=False)

            structural_trigger = diag["broken"] or bos_confirmed or (double_top["detected"] and (ema_cross or sma_cross))
            if not structural_trigger:
                return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Esperando ruptura bajista en 5M"}

            pullback_high = float(np.max(highs[-30:]))
            fibo_sl = self.select_fibonacci_stop_loss(impulse_low_1h, impulse_high_1h, pullback_high, is_long=False)
            if not fibo_sl["valid"]:
                return {"triggered": False, "plan": "PLAN_A_5M", "reason": "Pullback perforó el 0.75 de Fibonacci en 1H"}

            local_sl = pullback_high * 1.0015
            stop_loss = max(fibo_sl["stop_loss"], local_sl)
            take_profit_1 = min(float(impulse_low_1h), curr_close - (stop_loss - curr_close))

            return {
                "triggered": True,
                "plan": "PLAN_A_5M",
                "action": "SELL",
                "entry_price": curr_close,
                "stop_loss": round(stop_loss, 8),
                "take_profit": round(take_profit_1, 8),
                "fibo_level_protected": fibo_sl["fibo_level_used"],
                "double_top": double_top["detected"],
                "engulfing": engulfing,
                "reason": "Ruptura bajista 5M confirmada bajo EMA50/SMA200"
            }

    def evaluate_plan_b_2m(
        self,
        df_2m: pd.DataFrame,
        impulse_target_1h: float,
        is_long: bool = True,
        consolidation_candles: int = 6,
        max_box_height_pct: float = 0.8
    ) -> dict:
        """
        Evalúa el Gatillo Secundario (Plan B en 2M - Caso HBAR en Módulo 3):
        Cuando la ruptura en 5M se escapa rápido sin dar entrada limpia:
        1. Verifica que el precio ya esté operando a favor de la EMA 50 en 2M.
        2. Detecta una micro-consolidación horizontal de `consolidation_candles` velas (rango estrecho).
        3. Dispara cuando la vela actual rompe el techo (Long) o suelo (Short) de esa consolidación.
        4. Ajusta el Stop Loss de forma agresiva justo debajo del mínimo local de esa consolidación en 2M.
        """
        if df_2m is None or len(df_2m) < 55:
            return {"triggered": False, "plan": "PLAN_B_2M", "reason": "Datos insuficientes en 2M"}

        highs = df_2m["high"].to_numpy(float)
        lows = df_2m["low"].to_numpy(float)
        closes = df_2m["close"].to_numpy(float)

        ema_50 = pd.Series(closes).ewm(span=50, adjust=False).mean().to_numpy()
        curr_close = float(closes[-1])
        curr_ema50 = float(ema_50[-1])

        # Caja de consolidación inmediatamente previa a la vela de ruptura actual
        box_highs = highs[-(consolidation_candles + 1) : -1]
        box_lows = lows[-(consolidation_candles + 1) : -1]
        box_top = float(np.max(box_highs))
        box_bottom = float(np.min(box_lows))

        if box_bottom <= 0:
            return {"triggered": False, "plan": "PLAN_B_2M", "reason": "Precios inválidos en caja 2M"}

        box_height_pct = ((box_top - box_bottom) / box_bottom) * 100.0
        if box_height_pct > max_box_height_pct:
            return {"triggered": False, "plan": "PLAN_B_2M", "reason": f"Sin consolidación estrecha en 2M ({box_height_pct:.2f}% > {max_box_height_pct}%)"}

        if is_long:
            if curr_close <= curr_ema50:
                return {"triggered": False, "plan": "PLAN_B_2M", "reason": "Precio 2M debajo de EMA 50"}
            if curr_close <= box_top:
                return {"triggered": False, "plan": "PLAN_B_2M", "reason": "Aún dentro del rango horizontal en 2M"}

            # SL ajustado debajo del último mínimo local de 2M (o EMA 50 2M)
            stop_loss = min(box_bottom, curr_ema50) * 0.9985
            risk = curr_close - stop_loss
            take_profit = max(float(impulse_target_1h), curr_close + risk * 1.5)

            return {
                "triggered": True,
                "plan": "PLAN_B_2M",
                "action": "BUY",
                "entry_price": curr_close,
                "stop_loss": round(stop_loss, 8),
                "take_profit": round(take_profit, 8),
                "box_top": box_top,
                "box_bottom": box_bottom,
                "reason": "Breakout de resistencia horizontal en 2M sobre EMA 50 (Plan B)"
            }
        else:
            if curr_close >= curr_ema50:
                return {"triggered": False, "plan": "PLAN_B_2M", "reason": "Precio 2M encima de EMA 50"}
            if curr_close >= box_bottom:
                return {"triggered": False, "plan": "PLAN_B_2M", "reason": "Aún dentro del rango horizontal en 2M"}

            stop_loss = max(box_top, curr_ema50) * 1.0015
            risk = stop_loss - curr_close
            take_profit = min(float(impulse_target_1h), curr_close - risk * 1.5)

            return {
                "triggered": True,
                "plan": "PLAN_B_2M",
                "action": "SELL",
                "entry_price": curr_close,
                "stop_loss": round(stop_loss, 8),
                "take_profit": round(take_profit, 8),
                "box_top": box_top,
                "box_bottom": box_bottom,
                "reason": "Breakout bajista de soporte horizontal en 2M bajo EMA 50 (Plan B)"
            }