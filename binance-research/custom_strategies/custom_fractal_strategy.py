# custom_strategies/custom_fractal_strategy.py
import os
import sys
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from custom_strategies.risk_manager import RiskManager
from custom_strategies.trade_filters import TradeFilters
from custom_strategies.entry_trigger import EntryTrigger
from custom_strategies.position_manager import PositionManager


class _TimeframeBucketAggregator:
    """
    Construye velas cerradas de temporalidades superiores (15m, 1h, 4h, 1d) en tiempo real
    a partir del flujo de velas base (ej. 5m o 15m), alineadas a UTC como Binance.
    Solo publica una vela en `closed_candles` cuando empieza un nuevo bloque horario,
    garantizando CERO look-ahead bias tanto en backtest como en vivo.
    """
    def __init__(self, interval_ms: int, max_len: int = 260):
        self.interval_ms = int(interval_ms)
        self.max_len = int(max_len)
        self.current_bucket_time: Optional[int] = None
        self.current_candle: Optional[Dict[str, float]] = None
        self.closed_candles: List[Dict[str, float]] = []

    def update(self, candle: Dict[str, float], base_interval_ms: int) -> bool:
        """
        Actualiza el agregador con una vela base cerrada.
        Devuelve True si en este paso se completó y cerró una nueva vela de esta temporalidad.
        """
        open_time = int(candle["open_time"])
        bucket_time = (open_time // self.interval_ms) * self.interval_ms
        o, h, l, c, v = (
            float(candle["open"]),
            float(candle["high"]),
            float(candle["low"]),
            float(candle["close"]),
            float(candle["volume"]),
        )

        just_closed = False
        if self.current_bucket_time is None:
            self.current_bucket_time = bucket_time
            self.current_candle = {
                "open_time": bucket_time,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            }
        elif bucket_time > self.current_bucket_time:
            # El bloque anterior terminó; lo guardamos como vela cerrada si no venía ya del mismo bloque
            if self.current_candle is not None:
                self.closed_candles.append(self.current_candle)
                if len(self.closed_candles) > self.max_len:
                    self.closed_candles.pop(0)
                just_closed = True

            self.current_bucket_time = bucket_time
            self.current_candle = {
                "open_time": bucket_time,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            }
        else:
            # Mismo bloque horario: actualizamos máximo, mínimo, cierre y volumen acumulado
            self.current_candle["high"] = max(self.current_candle["high"], h)
            self.current_candle["low"] = min(self.current_candle["low"], l)
            self.current_candle["close"] = c
            self.current_candle["volume"] += v

        # Si la vela base ya tiene el mismo tamaño que el bucket (ej. base=1h y bucket=1h), cierra en el acto
        if base_interval_ms >= self.interval_ms and self.current_candle is not None:
            self.closed_candles.append(self.current_candle)
            if len(self.closed_candles) > self.max_len:
                self.closed_candles.pop(0)
            self.current_bucket_time = None
            self.current_candle = None
            just_closed = True

        return just_closed

    def to_dataframe(self, include_forming: bool = False) -> pd.DataFrame:
        rows = list(self.closed_candles)
        if include_forming and self.current_candle is not None:
            rows.append(self.current_candle)
        if not rows:
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
        return pd.DataFrame(rows)


class CustomFractalStrategy:
    """
    Estrategia Multitemporal de Continuación Fractal + Filtro SMA 200 + Gestión por Tramos (Módulos 1, 2 y 3).
    Compatible con `StrategyEngine`, `rule_copy()`, `optimize.simulate_live()` y `fast_backtest.py`.
    """
    requires_full_candle = True
    supports_custom_sizing = True

    def __init__(
        self,
        window: int = 200,
        std_dev_multiplier: float = 0.60,
        risk_percentage: float = 0.05,
        initial_capital: float = 5000.0,
        leverage: int = 10,
        allow_short: bool = False,
        exit_mode: str = "SWING_PARCIALES"
    ):
        """
        Args:
            window (int): Ventana de calentamiento en velas base (mínimo 200 para SMA 200).
            std_dev_multiplier (float): En esta estrategia actúa como el Multiplicador de Drawdown (M=0.60 o 0.30)
                                        o umbral de sensibilidad para mantener compatibilidad con Walk-Forward (n, k).
            risk_percentage (float): Riesgo por operación sobre el balance (ej. 0.05 = 5% o 0.01 = 1%).
            initial_capital (float): Capital inicial de referencia en USDT.
            leverage (int): Apalancamiento en modo ISOLATED (10x o 20x).
            allow_short (bool): False para Spot (solo BUY), True para Futuros (BUY y SELL).
            exit_mode (str): "SWING_PARCIALES" (50%/25%/25%), "SCALPING_EMA" o "STATIC_FAST".
        """
        self.window = int(max(window, 60))
        self.std_dev_multiplier = float(std_dev_multiplier)
        self.risk_percentage = float(risk_percentage)
        self.initial_capital = float(initial_capital)
        self.leverage = int(leverage)
        self.allow_short = bool(allow_short)
        self.exit_mode = str(exit_mode)

        # Instanciar submódulos
        self.risk_manager = RiskManager(
            initial_capital=self.initial_capital,
            risk_percentage=self.risk_percentage,
            max_concurrent_trades=4,
            leverage=self.leverage,
            dd_multiplier=self.std_dev_multiplier if 0.1 <= self.std_dev_multiplier <= 1.0 else 0.60
        )
        self.filters = TradeFilters()
        self.trigger = EntryTrigger(pivot_left=3, pivot_right=3, double_pattern_tol_pct=0.35)
        self.position_manager = PositionManager(time_stop_hours=4.5)

        # Estado multitemporal por símbolo
        self.symbol_state: Dict[str, Dict[str, Any]] = {}

    def _init_symbol(self, symbol: str):
        self.symbol_state[symbol] = {
            "base_candles": [],
            "base_interval_ms": None,
            "agg_15m": _TimeframeBucketAggregator(15 * 60 * 1000, max_len=250),
            "agg_1h": _TimeframeBucketAggregator(60 * 60 * 1000, max_len=250),
            "agg_4h": _TimeframeBucketAggregator(4 * 60 * 60 * 1000, max_len=200),
            "agg_1d": _TimeframeBucketAggregator(24 * 60 * 60 * 1000, max_len=120),
            "synthetic_time_ms": 1704067200000,  # Fallback si en un test unitario no envían open_time
            "ready": False
        }

    def _normalize_candle(self, state: Dict[str, Any], market_data: Any) -> Dict[str, float]:
        """
        Garantiza que siempre tengamos un diccionario OHLCV válido con `open_time` en ms,
        incluso si una prueba antigua pasa solo un float o un dict con {'close', 'volume'}.
        """
        if isinstance(market_data, dict):
            c = float(market_data.get("close", 0.0))
            o = float(market_data.get("open", c))
            h = float(market_data.get("high", max(o, c)))
            l = float(market_data.get("low", min(o, c)))
            v = float(market_data.get("volume", 0.0))
            ot = market_data.get("open_time")
        else:
            c = float(market_data)
            o = h = l = c
            v = 0.0
            ot = None

        if ot is None:
            ot = state["synthetic_time_ms"]
            state["synthetic_time_ms"] += 15 * 60 * 1000  # Asume pasos de 15m si no viene timestamp
        else:
            ot = int(ot)

        return {"open_time": ot, "open": o, "high": h, "low": l, "close": c, "volume": v}

    @staticmethod
    def _compute_ema(series: np.ndarray, span: int = 50) -> np.ndarray:
        if len(series) == 0:
            return np.array([])
        return pd.Series(series).ewm(span=span, adjust=False).mean().to_numpy(float)

    @staticmethod
    def _compute_sma(series: np.ndarray, window: int = 200) -> np.ndarray:
        if len(series) < window:
            return np.full(len(series), np.nan)
        return pd.Series(series).rolling(window=window).mean().to_numpy(float)

    def _extract_1h_impulse(self, df_1h: pd.DataFrame, is_long: bool = True) -> Dict[str, Any]:
        """
        Identifica el último impulso relevante en 1H (Swing Low -> Swing High para Long,
        o Swing High -> Swing Low para Short) y el extremo del pullback posterior.
        """
        if len(df_1h) < 30:
            return {"valid": False}

        highs = df_1h["high"].to_numpy(float)
        lows = df_1h["low"].to_numpy(float)
        closes = df_1h["close"].to_numpy(float)

        sh, sl = self.trigger.find_pivots(highs, lows, left=2, right=2)
        lookback = min(len(df_1h), 60)
        recent_h = highs[-lookback:]
        recent_l = lows[-lookback:]

        if is_long:
            # Buscamos el mínimo relevante y el máximo posterior dentro de la ventana de 1H
            max_rel_idx = int(np.argmax(recent_h[:-2])) if len(recent_h) > 4 else int(np.argmax(recent_h))
            if max_rel_idx < 3:
                return {"valid": False}
            impulse_high = float(recent_h[max_rel_idx])
            impulse_low = float(np.min(recent_l[:max_rel_idx + 1]))
            if impulse_high <= impulse_low:
                return {"valid": False}

            # El pullback es todo lo ocurrido desde que se marcó el máximo del impulso hasta ahora
            pullback_slice_l = recent_l[max_rel_idx + 1:]
            if len(pullback_slice_l) == 0:
                return {"valid": False}
            pullback_extreme = float(np.min(pullback_slice_l))
            rng = impulse_high - impulse_low
            retracement = (impulse_high - pullback_extreme) / rng
            fibo_50 = impulse_high - (rng * 0.50)

            return {
                "valid": True,
                "impulse_low": impulse_low,
                "impulse_high": impulse_high,
                "pullback_extreme": pullback_extreme,
                "retracement": retracement,
                "fibo_50": fibo_50,
                "current_close_1h": float(closes[-1])
            }
        else:
            min_rel_idx = int(np.argmin(recent_l[:-2])) if len(recent_l) > 4 else int(np.argmin(recent_l))
            if min_rel_idx < 3:
                return {"valid": False}
            impulse_low = float(recent_l[min_rel_idx])
            impulse_high = float(np.max(recent_h[:min_rel_idx + 1]))
            if impulse_high <= impulse_low:
                return {"valid": False}

            pullback_slice_h = recent_h[min_rel_idx + 1:]
            if len(pullback_slice_h) == 0:
                return {"valid": False}
            pullback_extreme = float(np.max(pullback_slice_h))
            rng = impulse_high - impulse_low
            retracement = (pullback_extreme - impulse_low) / rng
            fibo_50 = impulse_low + (rng * 0.50)

            return {
                "valid": True,
                "impulse_low": impulse_low,
                "impulse_high": impulse_high,
                "pullback_extreme": pullback_extreme,
                "retracement": retracement,
                "fibo_50": fibo_50,
                "current_close_1h": float(closes[-1])
            }

    def evaluate(self, symbol: str, market_data: Any) -> Dict[str, Any]:
        """
        Evalúa una nueva vela cerrada y devuelve la señal operativa.
        """
        sym = symbol.upper()
        if sym not in self.symbol_state:
            self._init_symbol(sym)

        state = self.symbol_state[sym]
        candle = self._normalize_candle(state, market_data)

        # Inferir el intervalo base (5m, 15m, 1h) a partir de las dos primeras velas
        if state["base_candles"]:
            prev_ot = state["base_candles"][-1]["open_time"]
            diff = candle["open_time"] - prev_ot
            if diff > 0 and state["base_interval_ms"] is None:
                state["base_interval_ms"] = diff

        base_ms = state["base_interval_ms"] or (15 * 60 * 1000)

        state["base_candles"].append(candle)
        max_base_keep = max(self.window + 50, 300)
        if len(state["base_candles"]) > max_base_keep:
            state["base_candles"].pop(0)

        # Actualizar agregadores multitemporales
        state["agg_15m"].update(candle, base_ms)
        state["agg_1h"].update(candle, base_ms)
        state["agg_4h"].update(candle, base_ms)
        state["agg_1d"].update(candle, base_ms)

        df_base = pd.DataFrame(state["base_candles"])
        df_15m = state["agg_15m"].to_dataframe(include_forming=True)
        df_1h = state["agg_1h"].to_dataframe(include_forming=True)
        df_4h = state["agg_4h"].to_dataframe(include_forming=True)

        # Indicadores clave para gestión de posiciones abiertas y entradas
        closes_base = df_base["close"].to_numpy(float)
        ema50_base = self._compute_ema(closes_base, 50)
        sma200_base = self._compute_sma(closes_base, 200)

        closes_1h = df_1h["close"].to_numpy(float) if len(df_1h) > 0 else closes_base
        ema50_1h = self._compute_ema(closes_1h, 50)
        sma200_1h = self._compute_sma(closes_1h, 200)

        closes_4h = df_4h["close"].to_numpy(float) if len(df_4h) > 0 else closes_1h
        ema50_4h = self._compute_ema(closes_4h, 50)

        closes_15m = df_15m["close"].to_numpy(float) if len(df_15m) > 0 else closes_base
        ema50_15m = self._compute_ema(closes_15m, 50)

        curr_price = float(candle["close"])
        curr_ema50_base = float(ema50_base[-1]) if len(ema50_base) > 0 else curr_price
        curr_sma200_base = float(sma200_base[-1]) if len(sma200_base) > 0 and not np.isnan(sma200_base[-1]) else -1.0
        curr_ema50_15m = float(ema50_15m[-1]) if len(ema50_15m) > 0 else curr_price
        curr_ema50_1h = float(ema50_1h[-1]) if len(ema50_1h) > 0 else curr_price
        curr_sma200_1h = float(sma200_1h[-1]) if len(sma200_1h) > 0 and not np.isnan(sma200_1h[-1]) else -1.0
        curr_ema50_4h = float(ema50_4h[-1]) if len(ema50_4h) > 0 else curr_price

        # -------------------------------------------------------------------------
        # 1. SI HAY POSICIÓN ABIERTA EN EL GESTOR: EVALUAR SALIDAS PARCIALES / TRAILING
        # -------------------------------------------------------------------------
        active_pos_Action = None
        if sym in self.position_manager.positions:
            pos_eval = self.position_manager.evaluate_position(
                symbol=sym,
                current_price=curr_price,
                current_time_ms=int(candle["open_time"]),
                high_price=float(candle["high"]),
                low_price=float(candle["low"]),
                close_1h=float(closes_1h[-1]) if len(closes_1h) > 0 else None,
                ema50_1h=curr_ema50_1h,
                close_4h=float(closes_4h[-1]) if len(closes_4h) > 0 else None,
                ema50_4h=curr_ema50_4h,
                close_micro=curr_price,
                ema50_micro=curr_ema50_base
            )
            if pos_eval.get("action") in ("PARTIAL_CLOSE", "FULL_CLOSE", "UPDATE_SL"):
                active_pos_Action = pos_eval

        # -------------------------------------------------------------------------
        # 2. FASE DE CALENTAMIENTO DE LA VENTANA
        # -------------------------------------------------------------------------
        if len(df_base) < self.window:
            return active_pos_Action or {"action": "HOLD"}

        if not state["ready"]:
            state["ready"] = True

        # Si ya tiene una posición abierta o acaba de emitir orden de gestión sobre la actual, no abre otra
        if sym in self.position_manager.positions or active_pos_Action is not None:
            return active_pos_Action or {"action": "HOLD"}

        if not self.risk_manager.validate_concurrent_trades(len(self.position_manager.positions)):
            return {"action": "HOLD", "reason": "Límite de 4 posiciones simultáneas alcanzado"}

        # -------------------------------------------------------------------------
        # 3. EVALUACIÓN DE ENTRADA MULTITEMPORAL (LONG Y OPCIONALMENTE SHORT)
        # -------------------------------------------------------------------------
        directions = [True] if not self.allow_short else [True, False]

        for is_long in directions:
            # Paso A: Alineación de Tendencia en 4H / 1H (o Sobreextensión en SMA 200 1H)
            if is_long:
                trend_aligned = (curr_price >= curr_ema50_4h * 0.995) or (
                    curr_sma200_1h > 0 and abs(curr_price - curr_sma200_1h) / curr_price <= 0.015
                )
            else:
                trend_aligned = (curr_price <= curr_ema50_4h * 1.005) or (
                    curr_sma200_1h > 0 and abs(curr_price - curr_sma200_1h) / curr_price <= 0.015
                )

            if not trend_aligned:
                continue

            # Paso B: Extraer impulso de referencia (en 1H si hay suficientes velas 1H, o en base reescalada)
            df_struct = df_1h if len(df_1h) >= 35 else df_base
            impulse = self._extract_1h_impulse(df_struct, is_long=is_long)
            if not impulse.get("valid"):
                continue

            # Paso C: Aplicar las 4 Barreras de `TradeFilters` (Módulos 2 y 3)
            # 1) Fibonacci entre 0.382 y 0.75 (cancela si > 0.75)
            if not self.filters.validate_fibonacci_pullback(
                impulse["retracement"], min_allowed=0.382, max_allowed=0.750
            ):
                continue

            # 2) Profundidad mínima del pullback (evitar pullbacks en el aire tipo DOT/ICP)
            if not self.filters.validate_pullback_depth(
                pullback_extreme=impulse["pullback_extreme"],
                ema_15m=curr_ema50_15m,
                sma_200_1h=curr_sma200_1h if curr_sma200_1h > 0 else None,
                ema_50_4h=curr_ema50_4h,
                fibo_50_1h=impulse["fibo_50"],
                is_long=is_long
            ):
                continue

            # 3) Desaceleración/compresión en el retroceso
            if not self.filters.validate_deceleration(df_struct.iloc[-15:], lookback=4, ratio_threshold=0.95):
                continue

            # 4) Filtro Anti-Fakeout de SMA 200 en temporalidad de disparo (5M / base)
            closed_beyond_sma = (
                (curr_price > curr_sma200_base) if is_long else (curr_price < curr_sma200_base)
            ) if curr_sma200_base > 0 else True

            if not self.filters.check_sma200_5m_fakeout(
                current_price=curr_price,
                sma_200_5m=curr_sma200_base if curr_sma200_base > 0 else None,
                candle_closed_beyond_sma=closed_beyond_sma,
                is_long=is_long,
                obstacle_threshold_pct=0.50
            ):
                continue

            # Paso D: Evaluar Gatillo Plan A (5M/Base) y, si no dispara, Plan B (Consolidación Horizontal)
            trigger_res = self.trigger.evaluate_plan_a_5m(
                df_5m=df_base,
                impulse_low_1h=impulse["impulse_low"],
                impulse_high_1h=impulse["impulse_high"],
                is_long=is_long
            )

            if not trigger_res.get("triggered"):
                target_1h = impulse["impulse_high"] if is_long else impulse["impulse_low"]
                trigger_res = self.trigger.evaluate_plan_b_2m(
                    df_2m=df_base,
                    impulse_target_1h=target_1h,
                    is_long=is_long
                )

            if not trigger_res.get("triggered"):
                continue

            # Paso E: Normalización de Precios y Dimensionamiento de Posición (Módulo 1)
            raw_entry = float(trigger_res["entry_price"])
            raw_sl = float(trigger_res["stop_loss"])
            raw_tp = float(trigger_res["take_profit"])

            # Determinar tick_size estimado según la magnitud del precio
            tick_size = 0.01 if raw_entry >= 10.0 else (0.001 if raw_entry >= 0.1 else 0.00001)
            entry_px = self.risk_manager.normalize_price(raw_entry, tick_size=tick_size, flat_ending=False)
            sl_px = self.risk_manager.normalize_price(raw_sl, tick_size=tick_size, flat_ending=True)
            tp_px = self.risk_manager.normalize_price(raw_tp, tick_size=tick_size, flat_ending=True)

            # Garantizar que el redondeo no invierta la geometría del Stop Loss
            if is_long and sl_px >= entry_px:
                sl_px = raw_sl
            elif not is_long and sl_px <= entry_px:
                sl_px = raw_sl

            try:
                sizing = self.risk_manager.calculate_position_size(
                    entry_price=entry_px,
                    stop_loss_price=sl_px,
                    current_balance=self.initial_capital,
                    use_scaling_table=True
                )
            except ValueError:
                continue

            # Registrar posición en el PositionManager interno para seguimiento de parciales/trailing
            self.position_manager.register_position(
                symbol=sym,
                is_long=is_long,
                entry_price=entry_px,
                stop_loss=sl_px,
                tp1_price=tp_px,
                opened_at_ms=int(candle["open_time"]),
                quantity=sizing["estimated_base_qty"],
                mode=self.exit_mode
            )

            return {
                "action": trigger_res["action"],  # "BUY" (o "SELL" si allow_short=True)
                "symbol": sym,
                "entry_price": round(entry_px, 8),
                "take_profit": round(tp_px, 8),
                "stop_loss": round(sl_px, 8),
                "quote_usdt": sizing["position_notional_usdt"],
                "risk_usd": sizing["risk_usd"],
                "distance_sl_pct": sizing["distance_sl_pct"],
                "leverage": sizing["leverage"],
                "plan": trigger_res.get("plan"),
                "fibo_retracement": round(impulse["retracement"], 4),
                "exit_plan": {
                    "mode": self.exit_mode,
                    "tp1_ratio": 0.50,
                    "tp2_ratio": 0.25,
                    "tp3_ratio": 0.25,
                    "time_stop_hours": 4.5
                },
                "reason": trigger_res.get("reason", "Confluencia MTF completada")
            }

        return {"action": "HOLD"}