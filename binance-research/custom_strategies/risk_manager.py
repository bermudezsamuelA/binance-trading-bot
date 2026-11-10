# custom_strategies/risk_manager.py
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from typing import Optional, Dict, Any


class RiskManager:
    def __init__(
        self,
        initial_capital: float = 5000.0,
        risk_percentage: float = 0.05,
        max_concurrent_trades: int = 4,
        leverage: int = 10,
        max_historical_dd_pct: float = 70.0,
        dd_multiplier: float = 0.60,
        max_risk_level: int = 4
    ):
        """
        Gestor de Riesgo, Dimensionamiento Nocional (P_USDT) y Escalado por Niveles (Módulo 1).

        Args:
            initial_capital (float): Capital base de la cuenta en USDT.
            risk_percentage (float): Riesgo base por operación (ej. 0.01 = 1%, 0.05 = 5%, 0.10 = 10%).
            max_concurrent_trades (int): Máximo de posiciones simultáneas permitidas (por defecto 4).
            leverage (int): Apalancamiento en modo ISOLATED (10x o 20x).
            max_historical_dd_pct (float): Drawdown máximo histórico en % (ej. 70.0 para 7 pérdidas al 10%).
            dd_multiplier (float): Multiplicador de condición de avance (0.60 conservador, 0.30 agresivo).
            max_risk_level (int): Nivel máximo de escalado en la tabla de interés compuesto (1 a 4).
        """
        if initial_capital <= 0:
            raise ValueError("initial_capital debe ser mayor que 0.")
        if not (0 < risk_percentage <= 1.0):
            raise ValueError("risk_percentage debe estar entre 0 y 1 (ej. 0.05 para 5%).")
        if leverage < 1:
            raise ValueError("leverage debe ser >= 1.")

        self.initial_capital = float(initial_capital)
        self.risk_percentage = float(risk_percentage)
        self.max_concurrent_trades = int(max_concurrent_trades)
        self.leverage = int(leverage)
        self.max_historical_dd_pct = float(max_historical_dd_pct)
        self.dd_multiplier = float(dd_multiplier)
        self.max_risk_level = int(max_risk_level)

    @staticmethod
    def normalize_price(price: float, tick_size: float = 0.01, flat_ending: bool = True) -> float:
        """
        Normaliza precios de Entrada, TP y SL respetando el tick_size de Binance y,
        si `flat_ending=True`, redondea el último dígito al escalón plano (.00 o .50 / múltiplo de 5 ticks)
        como se aplica en el Módulo 1 (ej. 106205.60 -> 106205.50).
        """
        if price <= 0 or tick_size <= 0:
            return float(price)

        d_price = Decimal(str(price))
        d_tick = Decimal(str(tick_size))

        if flat_ending:
            # Si el precio es grande (>= 100), aplanamos a múltiplos de 5 ticks (terminaciones en 0 o 5)
            step = d_tick * Decimal("5") if price >= 10.0 else d_tick
            normalized = (d_price / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
            # Asegurar alineación exacta al tick_size
            normalized = (normalized / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_tick
        else:
            normalized = (d_price / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_tick

        return float(normalized)

    def evaluate_drawdown_scaling(
        self,
        current_capital: float,
        base_capital: Optional[float] = None,
        max_historical_dd_pct: Optional[float] = None,
        multiplier: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calcula el Nivel de Riesgo actual (1 a `max_risk_level`) según la tabla del Módulo 1:
        - Condición de avance (%) = DD_max * Multiplicador (ej. 70% * 0.60 = 42%).
        - Cada vez que el capital supera un escalón de `required_gain_pct`, sube de nivel
          duplicando el riesgo base en USD (Nivel 1: 1x, Nivel 2: 2x, Nivel 3: 4x, Nivel 4: 8x).
        """
        base = float(base_capital) if base_capital is not None else self.initial_capital
        dd_max = float(max_historical_dd_pct) if max_historical_dd_pct is not None else self.max_historical_dd_pct
        mult = float(multiplier) if multiplier is not None else self.dd_multiplier

        if base <= 0:
            return {
                "level": 1,
                "risk_multiplier": 1.0,
                "can_scale": False,
                "current_gain_pct": 0.0,
                "required_gain_pct": 0.0,
                "risk_usd_per_setup": 0.0,
                "max_total_risk_usd": 0.0
            }

        current_gain_pct = ((float(current_capital) - base) / base) * 100.0
        step_gain_pct = dd_max * mult  # Ej. 42.0%

        if step_gain_pct <= 0 or current_gain_pct < step_gain_pct:
            level = 1
        else:
            # Cada escalón completado sube un nivel hasta max_risk_level
            steps_achieved = int(current_gain_pct // step_gain_pct)
            level = min(1 + steps_achieved, self.max_risk_level)

        risk_mult = float(2 ** (level - 1))  # Nivel 1=1x, Nivel 2=2x, Nivel 3=4x, Nivel 4=8x
        base_risk_usd = base * self.risk_percentage
        risk_usd_per_setup = base_risk_usd * risk_mult

        return {
            "level": level,
            "risk_multiplier": risk_mult,
            "can_scale": level > 1,
            "current_gain_pct": round(current_gain_pct, 2),
            "required_gain_pct": round(step_gain_pct, 2),
            "multiplier": mult,
            "risk_usd_per_setup": round(risk_usd_per_setup, 4),
            "max_total_risk_usd": round(risk_usd_per_setup * self.max_concurrent_trades, 4)
        }

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        current_balance: Optional[float] = None,
        use_scaling_table: bool = False,
        custom_risk_usd: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calcula la distancia al SL (D_SL), el riesgo monetario (R_USD), el tamaño de posición nocional (P_USDT)
        y el margen colateral aislado requerido (M_USDT).

        Fórmulas (Módulo 1):
            1. R_USD = Balance * % Riesgo (o según Nivel de la tabla de escalado)
            2. D_SL (%) = (|Entrada - SL| / Entrada) * 100
            3. P_USDT = (R_USD / D_SL) * 100
            4. M_USDT = P_USDT / Apalancamiento
        """
        balance = float(current_balance) if current_balance is not None else self.initial_capital
        entry = float(entry_price)
        sl = float(stop_loss_price)

        if entry <= 0 or sl <= 0:
            raise ValueError(f"Precios inválidos para cálculo de riesgo: Entrada={entry}, SL={sl}")

        d_sl = (abs(entry - sl) / entry) * 100.0
        if d_sl <= 0:
            raise ValueError(f"La distancia al Stop Loss no puede ser cero (Entrada={entry}, SL={sl})")

        # 1. Determinar Riesgo Monetario en USD (R_USD)
        scaling_info = self.evaluate_drawdown_scaling(current_capital=balance)
        if custom_risk_usd is not None and custom_risk_usd > 0:
            r_usd = float(custom_risk_usd)
        elif use_scaling_table:
            r_usd = scaling_info["risk_usd_per_setup"]
        else:
            r_usd = balance * self.risk_percentage

        # 2. Tamaño de la Posición Nocional (P_USDT)
        p_usdt = (r_usd / d_sl) * 100.0

        # 3. Margen Aislado requerido en Binance (M_USDT)
        m_usdt = p_usdt / float(self.leverage)

        # 4. Cantidad en moneda base aproximada
        base_qty = p_usdt / entry

        return {
            "balance_used": round(balance, 4),
            "risk_level": scaling_info["level"] if use_scaling_table else 1,
            "risk_usd": round(r_usd, 4),
            "distance_sl_pct": round(d_sl, 4),
            "position_notional_usdt": round(p_usdt, 4),
            "isolated_margin_usdt": round(m_usdt, 4),
            "estimated_base_qty": round(base_qty, 8),
            "leverage": self.leverage,
            "margin_exceeds_balance": m_usdt > balance
        }

    def validate_concurrent_trades(self, active_trades_count: int) -> bool:
        """
        Verifica que no se supere el límite de setups simultáneos (máximo 4).
        """
        return int(active_trades_count) < self.max_concurrent_trades