# custom_strategies/position_manager.py
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class ManagedPositionState:
    """
    Estado interno de una posición gestionada por tramos y trailing dinámico.
    """
    symbol: str
    is_long: bool
    entry_price: float
    initial_stop_loss: float
    current_stop_loss: float
    tp1_price: float
    opened_at_ms: int
    initial_quantity: float = 1.0
    remaining_ratio: float = 1.0  # 1.0 = 100%, 0.50 tras TP1, 0.25 tras TP2, 0.0 cerrado
    tp1_hit: bool = False
    tp2_hit: bool = False
    moved_to_be: bool = False
    highest_watermark: float = field(default=0.0)
    lowest_watermark: float = field(default=0.0)
    mode: str = "SWING_PARCIALES"  # "SWING_PARCIALES" | "SCALPING_EMA" | "STATIC_FAST"

    def __post_init__(self):
        self.highest_watermark = max(self.entry_price, self.highest_watermark)
        self.lowest_watermark = min(self.entry_price, self.lowest_watermark) if self.lowest_watermark > 0 else self.entry_price


class PositionManager:
    def __init__(
        self,
        time_stop_hours: float = 4.5,
        be_fee_buffer_pct: float = 0.0020,
        scalping_ema_buffer_pct: float = 0.0005,
        fibo_trailing_level: float = 0.618
    ):
        """
        Gestor Dinámico de Salidas, Parciales, Trailing EMA/Fibo y Time-Stop (Módulos 1, 2 y 3).

        Args:
            time_stop_hours (float): Horas máximas permitidas en estancamiento antes de aplicar Time-Stop (4 a 5h).
            be_fee_buffer_pct (float): Margen extra sobre el precio de entrada al mover a Break Even (0.20% cubre fees).
            scalping_ema_buffer_pct (float): Holgura detrás de la EMA 50 en 2M/5M para el Trailing Stop.
            fibo_trailing_level (float): Nivel de retroceso (0.618 o 0.75) para el Trailing de Fibonacci progresivo.
        """
        self.time_stop_ms = int(float(time_stop_hours) * 3600 * 1000)
        self.be_fee_buffer_pct = float(be_fee_buffer_pct)
        self.scalping_ema_buffer_pct = float(scalping_ema_buffer_pct)
        self.fibo_trailing_level = float(fibo_trailing_level)
        self.positions: Dict[str, ManagedPositionState] = {}

    def register_position(
        self,
        symbol: str,
        is_long: bool,
        entry_price: float,
        stop_loss: float,
        tp1_price: Optional[float] = None,
        opened_at_ms: int = 0,
        quantity: float = 1.0,
        mode: str = "SWING_PARCIALES"
    ) -> ManagedPositionState:
        """
        Registra una nueva posición abierta para su seguimiento activo.
        Si no se especifica `tp1_price`, se calcula automáticamente a ratio 1:1 respecto al Stop Loss inicial.
        """
        risk = abs(entry_price - stop_loss)
        if tp1_price is None or tp1_price <= 0:
            tp1_price = (entry_price + risk) if is_long else (entry_price - risk)

        state = ManagedPositionState(
            symbol=symbol.upper(),
            is_long=bool(is_long),
            entry_price=float(entry_price),
            initial_stop_loss=float(stop_loss),
            current_stop_loss=float(stop_loss),
            tp1_price=float(tp1_price),
            opened_at_ms=int(opened_at_ms),
            initial_quantity=float(quantity),
            remaining_ratio=1.0,
            mode=mode
        )
        self.positions[symbol.upper()] = state
        return state

    def remove_position(self, symbol: str):
        """Elimina una posición cerrada del registro activo."""
        self.positions.pop(symbol.upper(), None)

    def get_break_even_price(self, state: ManagedPositionState) -> float:
        """Calcula el precio de Break Even sumando un pequeño colchón para cubrir comisiones de ida y vuelta."""
        if state.is_long:
            return round(state.entry_price * (1.0 + self.be_fee_buffer_pct), 8)
        return round(state.entry_price * (1.0 - self.be_fee_buffer_pct), 8)

    @staticmethod
    def calculate_progressive_fibonacci_sl(
        impulse_start: float,
        impulse_extreme: float,
        current_sl: float,
        is_long: bool = True,
        fibo_level: float = 0.618,
        buffer_pct: float = 0.0010
    ) -> float:
        """
        Método 1 de Trailing Stop (Módulo 3): Fibonacci Progresivo.
        Cuando el precio rompe un nuevo extremo a favor, traza Fibonacci sobre el nuevo impulso
        y sube el Stop Loss detrás del nivel `fibo_level` (0.618 o 0.75), nunca retrocediéndolo.
        """
        rng = abs(impulse_extreme - impulse_start)
        if rng <= 0:
            return current_sl

        if is_long:
            if impulse_extreme <= impulse_start:
                return current_sl
            fibo_price = impulse_extreme - (rng * fibo_level)
            candidate_sl = fibo_price * (1.0 - buffer_pct)
            return round(max(current_sl, candidate_sl), 8)
        else:
            if impulse_extreme >= impulse_start:
                return current_sl
            fibo_price = impulse_extreme + (rng * fibo_level)
            candidate_sl = fibo_price * (1.0 + buffer_pct)
            return round(min(current_sl, candidate_sl), 8)

    def check_time_stop(self, state: ManagedPositionState, current_price: float, current_time_ms: int) -> Dict[str, Any]:
        """
        Evalúa el Filtro de Límite de Tiempo / Estancamiento (Módulo 3 - Caso BCH):
        Si pasan 4 a 5 horas (`self.time_stop_ms`) sin que se haya tocado el TP1 y el precio
        sigue estancado sin lograr al menos 0.5R de recorrido:
        - Si está con ganancia suficiente para cubrir comisiones, mueve SL a Break Even.
        - Si sigue en zona muerta o leve pérdida al borde del patrón, ordena cierre por Time-Stop.
        """
        if state.opened_at_ms <= 0 or current_time_ms <= state.opened_at_ms:
            return {"triggered": False}

        elapsed_ms = current_time_ms - state.opened_at_ms
        if elapsed_ms < self.time_stop_ms or state.tp1_hit:
            return {"triggered": False}

        initial_risk = abs(state.entry_price - state.initial_stop_loss)
        if initial_risk <= 0:
            return {"triggered": False}

        unrealized_r = (
            (current_price - state.entry_price) / initial_risk
            if state.is_long
            else (state.entry_price - current_price) / initial_risk
        )

        # Si ya lleva buen recorrido (> 0.6R), solo aseguramos Break Even si no estaba ya en BE
        be_price = self.get_break_even_price(state)
        if unrealized_r >= 0.25:
            if not state.moved_to_be:
                if (state.is_long and current_price > be_price) or (not state.is_long and current_price < be_price):
                    state.current_stop_loss = max(state.current_stop_loss, be_price) if state.is_long else min(state.current_stop_loss, be_price)
                    state.moved_to_be = True
                    return {
                        "triggered": True,
                        "action": "UPDATE_SL",
                        "new_stop_loss": state.current_stop_loss,
                        "reason": f"TIME_STOP_BE: {elapsed_ms / 3600000:.1f}h transcurridas, SL protegido en Break Even"
                    }
            return {"triggered": False}

        # Estancamiento puro (< 0.25R tras 4.5 horas): salir del mercado para no dormir con riesgo abierto
        return {
            "triggered": True,
            "action": "FULL_CLOSE",
            "close_ratio_of_remaining": 1.0,
            "reason": f"TIME_STOP_EXIT: Estancamiento tras {elapsed_ms / 3600000:.1f}h sin impulso ({unrealized_r:+.2f}R)"
        }

    def evaluate_position(
        self,
        symbol: str,
        current_price: float,
        current_time_ms: int = 0,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
        close_1h: Optional[float] = None,
        ema50_1h: Optional[float] = None,
        close_4h: Optional[float] = None,
        ema50_4h: Optional[float] = None,
        close_micro: Optional[float] = None,
        ema50_micro: Optional[float] = None,
        impulse_start_fibo: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Evalúa en cada tick o cierre de vela el estado de la posición abierta y devuelve la instrucción exacta
        para el motor de ejecución (Node.js / simulate_live):
        - "HOLD": Sin cambios.
        - "UPDATE_SL": Actualizar Stop Loss (Break Even, Trailing EMA o Trailing Fibonacci).
        - "PARTIAL_CLOSE": Vender un porcentaje de la posición actual (ej. 50% en TP1, o 50% del resto en TP2).
        - "FULL_CLOSE": Cerrar el 100% de la posición remanente (Stop Loss, TP3 en 4H, Time-Stop o modo estático).

        Nota sobre proporciones para Node.js (`sellRemaining`):
        - Al tocar TP1 (50% del total), `close_ratio_of_remaining` = 0.50 (queda 50% vivo).
        - Al tocar TP2 (25% del total), como queda el 50% vivo, se vende la mitad de lo que queda:
          `close_ratio_of_remaining` = 0.50 (queda 25% vivo).
        - Al tocar TP3 o SL, se vende todo lo que queda: `close_ratio_of_remaining` = 1.0.
        """
        sym = symbol.upper()
        state = self.positions.get(sym)
        if state is None or state.remaining_ratio <= 0:
            return {"action": "HOLD", "symbol": sym, "reason": "Sin posición activa"}

        hi = float(high_price) if high_price is not None else float(current_price)
        lo = float(low_price) if low_price is not None else float(current_price)
        px = float(current_price)

        state.highest_watermark = max(state.highest_watermark, hi)
        state.lowest_watermark = min(state.lowest_watermark, lo)

        # -------------------------------------------------------------------------
        # 1. VERIFICACIÓN PRIORITARIA DE STOP LOSS (Protección de Capital)
        # -------------------------------------------------------------------------
        sl_hit = (lo <= state.current_stop_loss) if state.is_long else (hi >= state.current_stop_loss)
        if sl_hit:
            exit_px = state.current_stop_loss
            reason = "BREAK EVEN 🛡️" if state.moved_to_be and not state.tp1_hit else (
                "TRAILING STOP ✅" if state.tp1_hit else "STOP LOSS ⚠️"
            )
            self.remove_position(sym)
            return {
                "action": "FULL_CLOSE",
                "symbol": sym,
                "exit_price": exit_px,
                "close_ratio_of_total": state.remaining_ratio,
                "close_ratio_of_remaining": 1.0,
                "remaining_ratio_after": 0.0,
                "reason": reason
            }

        # -------------------------------------------------------------------------
        # 2. MODO SALIDA RÁPIDA ESTÁTICA (Ej. Trade PENGU en Módulo 3)
        # -------------------------------------------------------------------------
        tp1_reached = (hi >= state.tp1_price) if state.is_long else (lo <= state.tp1_price)
        if state.mode == "STATIC_FAST" and tp1_reached:
            self.remove_position(sym)
            return {
                "action": "FULL_CLOSE",
                "symbol": sym,
                "exit_price": state.tp1_price,
                "close_ratio_of_total": 1.0,
                "close_ratio_of_remaining": 1.0,
                "remaining_ratio_after": 0.0,
                "reason": "TAKE PROFIT ESTÁTICO (100%) ✅"
            }

        # -------------------------------------------------------------------------
        # 3. TRAMO 1: CIERRE PARCIAL DEL 50% EN TP1 (Mínimo/Máximo anterior o 1:1)
        # -------------------------------------------------------------------------
        if not state.tp1_hit and tp1_reached:
            state.tp1_hit = True
            state.remaining_ratio = 0.50
            # Al asegurar el primer 50%, protegemos el resto moviendo el Stop Loss a Break Even
            be_px = self.get_break_even_price(state)
            if state.is_long and be_px > state.current_stop_loss:
                state.current_stop_loss = be_px
                state.moved_to_be = True
            elif not state.is_long and be_px < state.current_stop_loss:
                state.current_stop_loss = be_px
                state.moved_to_be = True

            return {
                "action": "PARTIAL_CLOSE",
                "stage": "TP1_50_PCT",
                "symbol": sym,
                "exit_price": state.tp1_price,
                "close_ratio_of_total": 0.50,
                "close_ratio_of_remaining": 0.50,
                "remaining_ratio_after": 0.50,
                "new_stop_loss": state.current_stop_loss,
                "reason": "TP1 PARCIAL (50%) ASEGURADO + SL A BREAK EVEN ✅"
            }

        # -------------------------------------------------------------------------
        # 4. MODO SCALPING / INTRADÍA: TRAILING STOP CON EMA 50 EN 2M / 5M (Caso BTC)
        # -------------------------------------------------------------------------
        if state.mode == "SCALPING_EMA" and close_micro is not None and ema50_micro is not None and ema50_micro > 0:
            c_micro = float(close_micro)
            e_micro = float(ema50_micro)
            # Si ya estamos en ganancia (o tras TP1), cerramos si la vela micro cierra cruzando en contra la EMA 50
            in_profit = (c_micro > state.entry_price) if state.is_long else (c_micro < state.entry_price)
            if state.tp1_hit or in_profit:
                micro_broken = (c_micro < e_micro) if state.is_long else (c_micro > e_micro)
                if micro_broken:
                    rem = state.remaining_ratio
                    self.remove_position(sym)
                    return {
                        "action": "FULL_CLOSE",
                        "symbol": sym,
                        "exit_price": c_micro,
                        "close_ratio_of_total": rem,
                        "close_ratio_of_remaining": 1.0,
                        "remaining_ratio_after": 0.0,
                        "reason": "TRAILING EMA 50 MICRO ROTA (2M/5M) ✅"
                    }
                # Actualizar el Stop Loss pegado detrás de la EMA 50 micro
                candidate_sl = e_micro * (1.0 - self.scalping_ema_buffer_pct) if state.is_long else e_micro * (1.0 + self.scalping_ema_buffer_pct)
                if (state.is_long and candidate_sl > state.current_stop_loss) or (not state.is_long and candidate_sl < state.current_stop_loss):
                    state.current_stop_loss = round(candidate_sl, 8)
                    return {
                        "action": "UPDATE_SL",
                        "symbol": sym,
                        "new_stop_loss": state.current_stop_loss,
                        "reason": "TRAILING SL AJUSTADO A EMA 50 MICRO (2M/5M)"
                    }

        # -------------------------------------------------------------------------
        # 5. TRAMO 2 (25% TOTAL) Y TRAMO 3 (25% FINAL): GESTIÓN CON EMA 50 EN 1H Y 4H
        # -------------------------------------------------------------------------
        if state.tp1_hit:
            # Evaluación de TP3 primero (si 4H rompe en contra, cierra toda la posición restante de golpe)
            if close_4h is not None and ema50_4h is not None and ema50_4h > 0:
                c_4h, e_4h = float(close_4h), float(ema50_4h)
                broken_4h = (c_4h < e_4h) if state.is_long else (c_4h > e_4h)
                if broken_4h:
                    rem = state.remaining_ratio
                    self.remove_position(sym)
                    return {
                        "action": "FULL_CLOSE",
                        "stage": "TP3_FINAL_4H",
                        "symbol": sym,
                        "exit_price": c_4h,
                        "close_ratio_of_total": rem,
                        "close_ratio_of_remaining": 1.0,
                        "remaining_ratio_after": 0.0,
                        "reason": "TP3 FINAL: CIERRE DE VELA 4H CONTRA EMA 50 ✅"
                    }

            # Evaluación de TP2 (cierra el 25% del total = 50% del 50% restante cuando 1H cierra contra EMA 50)
            if not state.tp2_hit and close_1h is not None and ema50_1h is not None and ema50_1h > 0:
                c_1h, e_1h = float(close_1h), float(ema50_1h)
                broken_1h = (c_1h < e_1h) if state.is_long else (c_1h > e_1h)
                if broken_1h:
                    state.tp2_hit = True
                    state.remaining_ratio = 0.25
                    return {
                        "action": "PARTIAL_CLOSE",
                        "stage": "TP2_25_PCT_1H",
                        "symbol": sym,
                        "exit_price": c_1h,
                        "close_ratio_of_total": 0.25,
                        "close_ratio_of_remaining": 0.50,  # Vende la mitad del 50% que quedaba
                        "remaining_ratio_after": 0.25,
                        "new_stop_loss": state.current_stop_loss,
                        "reason": "TP2 PARCIAL (25%): CIERRE DE VELA 1H CONTRA EMA 50 ✅"
                    }

        # -------------------------------------------------------------------------
        # 6. TRAILING DE FIBONACCI PROGRESIVO (Si se provee el inicio del nuevo impulso)
        # -------------------------------------------------------------------------
        if impulse_start_fibo is not None and impulse_start_fibo > 0 and state.tp1_hit:
            extreme = state.highest_watermark if state.is_long else state.lowest_watermark
            new_sl = self.calculate_progressive_fibonacci_sl(
                impulse_start=float(impulse_start_fibo),
                impulse_extreme=extreme,
                current_sl=state.current_stop_loss,
                is_long=state.is_long,
                fibo_level=self.fibo_trailing_level
            )
            if (state.is_long and new_sl > state.current_stop_loss) or (not state.is_long and new_sl < state.current_stop_loss):
                state.current_stop_loss = new_sl
                return {
                    "action": "UPDATE_SL",
                    "symbol": sym,
                    "new_stop_loss": state.current_stop_loss,
                    "reason": f"TRAILING FIBONACCI PROGRESIVO ({self.fibo_trailing_level})"
                }

        # -------------------------------------------------------------------------
        # 7. FILTRO DE ESTANCAMIENTO (TIME-STOP 4 A 5 HORAS)
        # -------------------------------------------------------------------------
        if current_time_ms > 0:
            ts_check = self.check_time_stop(state, px, current_time_ms)
            if ts_check.get("triggered"):
                if ts_check["action"] == "FULL_CLOSE":
                    rem = state.remaining_ratio
                    self.remove_position(sym)
                    return {
                        "action": "FULL_CLOSE",
                        "symbol": sym,
                        "exit_price": px,
                        "close_ratio_of_total": rem,
                        "close_ratio_of_remaining": 1.0,
                        "remaining_ratio_after": 0.0,
                        "reason": ts_check["reason"]
                    }
                return {
                    "action": "UPDATE_SL",
                    "symbol": sym,
                    "new_stop_loss": ts_check["new_stop_loss"],
                    "reason": ts_check["reason"]
                }

        return {
            "action": "HOLD",
            "symbol": sym,
            "current_stop_loss": state.current_stop_loss,
            "remaining_ratio": state.remaining_ratio
        }