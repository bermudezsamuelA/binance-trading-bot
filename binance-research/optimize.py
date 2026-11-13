# optimize.py
import pandas as pd
import numpy as np
import sys
import os

from config import PAY_FEES_WITH_BNB

# Lo mismo que hace el bot en vivo (src/api/ws-client.ts): ~15 USDT por operacion, una posicion por moneda.
NOTIONAL_USDT = 15.0
INITIAL_CAPITAL = 1000.0
# Costos por lado: comision de Binance spot + deslizamiento (0.02 %), como harness.py. La comision es 0.10 %, o 0.075 %
# si se paga con BNB (config.PAY_FEES_WITH_BNB, en el .env).
FEE_PER_SIDE_STANDARD = 0.001
FEE_PER_SIDE_BNB = 0.00075
FEE_PER_SIDE = FEE_PER_SIDE_BNB if PAY_FEES_WITH_BNB else FEE_PER_SIDE_STANDARD
SLIPPAGE_PER_SIDE = 0.0002


def calculate_metrics(initial_capital, capital_curve, winning_trades, losing_trades, gross_profit, gross_loss):
    total_trades = winning_trades + losing_trades
    if total_trades == 0:
        return {"win_rate": 0, "max_drawdown_pct": 0, "profit_factor": 0, "expected_payoff": 0, "pnl": 0, "trades": 0}

    win_rate = (winning_trades / total_trades) * 100
    pnl = capital_curve[-1] - initial_capital

    # Max Drawdown
    peak = initial_capital
    max_dd = 0
    for cap in capital_curve:
        if cap > peak:
            peak = cap
        dd = (peak - cap) / peak
        if dd > max_dd:
            max_dd = dd

    # Profit Factor & Payoff
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else round(gross_profit, 2)
    expected_payoff = pnl / total_trades

    return {
        "trades": total_trades,
        "win_rate": round(win_rate, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "profit_factor": round(profit_factor, 2),
        "expected_payoff": round(expected_payoff, 4),
        "pnl": round(pnl, 4)
    }


def _simulate_custom_live(symbol: str, candles: pd.DataFrame, strategy, base_strat) -> list:
    """
    Simulador extendido para estrategias con `requires_full_candle = True` (ej. CustomFractalStrategy):
    - Envia la vela completa {'open_time', 'open', 'high', 'low', 'close', 'volume'}.
    - Respeta el dimensionamiento dinamico (`quote_usdt` de RiskManager) o usa NOTIONAL_USDT por defecto.
    - Simula cierres parciales (PARTIAL_CLOSE 50%/25%), ajustes de SL (UPDATE_SL a Break Even / Trailing EMA)
      y salidas completas (FULL_CLOSE por TP3 4H, Time-Stop o toque de SL/TP intravela).
    """
    cost = FEE_PER_SIDE + SLIPPAGE_PER_SIDE
    o = candles["open"].to_numpy(float)
    h = candles["high"].to_numpy(float)
    l = candles["low"].to_numpy(float)
    c = candles["close"].to_numpy(float)
    v = candles["volume"].to_numpy(float)
    if "open_time" in candles.columns:
        ot = candles["open_time"].to_numpy(np.int64)
    else:
        ot = np.arange(len(c), dtype=np.int64) * (15 * 60 * 1000) + 1704067200000

    pm = getattr(base_strat, "position_manager", None)
    sym_upper = symbol.upper()

    trades = []
    position = None

    for i in range(len(c)):
        exited_now = False

        # 1. Si hay posicion abierta, primero verificamos gaps de apertura o toque directo de SL/TP estatico
        if position is not None:
            sl = position["stop_loss"]
            tp = position["take_profit"]
            # Si la posicion no usa parciales (modo estatico), evaluamos TP completo igual que simulate_live
            if not position["has_partials"]:
                exit_price = reason = None
                if o[i] <= sl:
                    exit_price, reason = o[i], "SL"
                elif o[i] >= tp:
                    exit_price, reason = o[i], "TP"
                elif l[i] <= sl:
                    exit_price, reason = sl, "SL"
                elif h[i] >= tp:
                    exit_price, reason = tp, "TP"

                if exit_price is not None:
                    rem_qty = position["initial_qty"] * position["remaining_ratio"]
                    gross = rem_qty * (exit_price - position["entry_price"])
                    fees = rem_qty * (position["entry_price"] + exit_price) * cost
                    total_pnl = position["realized_pnl"] + (gross - fees)
                    total_exit_quote = position["realized_exit_quote"] + (rem_qty * exit_price)
                    avg_exit_px = total_exit_quote / position["initial_qty"] if position["initial_qty"] > 0 else exit_price
                    trades.append({
                        "entry_index": position["entry_index"],
                        "exit_index": i,
                        "entry_price": position["entry_price"],
                        "exit_price": avg_exit_px,
                        "reason": reason,
                        "pnl": total_pnl
                    })
                    if pm is not None:
                        pm.remove_position(sym_upper)
                    position = None
                    exited_now = True
            else:
                # Con parciales activos: si la apertura abre con gap debajo del SL, sale en o[i] (conservador)
                if o[i] <= sl:
                    exit_price = o[i]
                    rem_qty = position["initial_qty"] * position["remaining_ratio"]
                    gross = rem_qty * (exit_price - position["entry_price"])
                    fees = rem_qty * (position["entry_price"] + exit_price) * cost
                    total_pnl = position["realized_pnl"] + (gross - fees)
                    total_exit_quote = position["realized_exit_quote"] + (rem_qty * exit_price)
                    avg_exit_px = total_exit_quote / position["initial_qty"] if position["initial_qty"] > 0 else exit_price
                    trades.append({
                        "entry_index": position["entry_index"],
                        "exit_index": i,
                        "entry_price": position["entry_price"],
                        "exit_price": avg_exit_px,
                        "reason": "SL",
                        "pnl": total_pnl
                    })
                    if pm is not None:
                        pm.remove_position(sym_upper)
                    position = None
                    exited_now = True

        # 2. Evaluar la vela completa en la estrategia (actualiza ventanas MTF y PositionManager interno)
        candle_dict = {
            "open_time": int(ot[i]),
            "open": float(o[i]),
            "high": float(h[i]),
            "low": float(l[i]),
            "close": float(c[i]),
            "volume": float(v[i])
        }
        signal = strategy.evaluate(symbol, candle_dict) or {"action": "HOLD"}
        action = signal.get("action")

        # Si estamos fuera del rango de entradas permitido por _SignalWindow (ej. precarga en modo tramo),
        # y la estrategia internamente registro una posicion fantasma durante la precarga, la limpiamos.
        if position is None and pm is not None and sym_upper in pm.positions and action == "HOLD":
            pm.remove_position(sym_upper)

        # 3. Procesar senales de gestion sobre la posicion abierta
        if position is not None and not exited_now:
            if action == "UPDATE_SL" and signal.get("new_stop_loss") is not None:
                position["stop_loss"] = float(signal["new_stop_loss"])

            elif action == "PARTIAL_CLOSE":
                ratio_rem = float(signal.get("close_ratio_of_remaining", 0.5))
                exit_px = float(signal.get("exit_price", c[i]))
                sold_ratio_total = position["remaining_ratio"] * ratio_rem
                sold_qty = position["initial_qty"] * sold_ratio_total

                gross_part = sold_qty * (exit_px - position["entry_price"])
                fees_part = sold_qty * (position["entry_price"] + exit_px) * cost
                position["realized_pnl"] += (gross_part - fees_part)
                position["realized_exit_quote"] += (sold_qty * exit_px)
                position["remaining_ratio"] = max(0.0, position["remaining_ratio"] - sold_ratio_total)
                position["take_profit"] = float("inf")
                if signal.get("new_stop_loss") is not None:
                    position["stop_loss"] = float(signal["new_stop_loss"])

            elif action == "FULL_CLOSE":
                exit_px = float(signal.get("exit_price", c[i]))
                rem_qty = position["initial_qty"] * position["remaining_ratio"]
                gross_rem = rem_qty * (exit_px - position["entry_price"])
                fees_rem = rem_qty * (position["entry_price"] + exit_px) * cost
                total_pnl = position["realized_pnl"] + (gross_rem - fees_rem)
                total_exit_quote = position["realized_exit_quote"] + (rem_qty * exit_px)
                avg_exit_px = total_exit_quote / position["initial_qty"] if position["initial_qty"] > 0 else exit_px
                raw_reason = str(signal.get("reason", "EXIT"))
                short_reason = "SL" if "STOP LOSS" in raw_reason else ("TP" if "TP" in raw_reason or "TRAILING" in raw_reason else raw_reason)
                trades.append({
                    "entry_index": position["entry_index"],
                    "exit_index": i,
                    "entry_price": position["entry_price"],
                    "exit_price": avg_exit_px,
                    "reason": short_reason,
                    "pnl": total_pnl
                })
                if pm is not None:
                    pm.remove_position(sym_upper)
                position = None
                exited_now = True

            # Si _SignalWindow bloqueo la senal (devolvio HOLD despues de entry_end), pero la posicion sigue abierta,
            # verificamos el SL/TP directamente para que pueda cerrarse antes de `stop`
            elif action == "HOLD" and pm is not None and sym_upper not in pm.positions:
                # PositionManager ya la cerro internamente durante strategy.evaluate() (ocultado por _SignalWindow)
                if l[i] <= position["stop_loss"]:
                    exit_px, short_reason = position["stop_loss"], "SL"
                elif h[i] >= position["take_profit"]:
                    exit_px, short_reason = position["take_profit"], "TP"
                else:
                    exit_px, short_reason = c[i], "TP"
                rem_qty = position["initial_qty"] * position["remaining_ratio"]
                gross_rem = rem_qty * (exit_px - position["entry_price"])
                fees_rem = rem_qty * (position["entry_price"] + exit_px) * cost
                total_pnl = position["realized_pnl"] + (gross_rem - fees_rem)
                total_exit_quote = position["realized_exit_quote"] + (rem_qty * exit_px)
                avg_exit_px = total_exit_quote / position["initial_qty"] if position["initial_qty"] > 0 else exit_px
                trades.append({
                    "entry_index": position["entry_index"],
                    "exit_index": i,
                    "entry_price": position["entry_price"],
                    "exit_price": avg_exit_px,
                    "reason": short_reason,
                    "pnl": total_pnl
                })
                position = None
                exited_now = True

        # 4. Apertura de nueva posicion en BUY
        if action == "BUY" and position is None and not exited_now:
            entry_px = float(signal["entry_price"])
            tp_px = float(signal["take_profit"])
            sl_px = float(signal["stop_loss"])
            notional = float(signal.get("quote_usdt") or NOTIONAL_USDT)
            if not getattr(base_strat, "use_dynamic_notional_in_backtest", False):
                # Por defecto en Walk-Forward comparamos bajo la misma base NOTIONAL_USDT salvo que se active
                notional = NOTIONAL_USDT
            exit_plan = signal.get("exit_plan") or {}
            has_partials = exit_plan.get("mode") in ("SWING_PARCIALES", "SCALPING_EMA")
            position = {
                "entry_index": i,
                "entry_price": entry_px,
                "take_profit": tp_px,
                "stop_loss": sl_px,
                "notional_usdt": notional,
                "initial_qty": notional / entry_px,
                "remaining_ratio": 1.0,
                "realized_pnl": 0.0,
                "realized_exit_quote": 0.0,
                "has_partials": has_partials
            }

    return trades


def simulate_live(symbol: str, candles: pd.DataFrame, strategy) -> list:
    """
    Simula vela a vela lo mismo que hace el bot en vivo con velas de 15 min cerradas:
    - La estrategia recibe TODAS las velas cerradas (con volumen), tambien con posicion abierta:
      la ventana nunca se congele (server.py / strategy_engine.py).
    - Si la estrategia tiene `requires_full_candle = True` (ej. CustomFractalStrategy), delega en
      `_simulate_custom_live` pasando el diccionario OHLCV completo y gestionando tramos parciales.
    - Para las 5 estrategias clasicas, ejecuta el bucle original intacto garantizando paridad bit a bit.
    """
    base_strat = getattr(strategy, "strategy", strategy)
    if getattr(base_strat, "requires_full_candle", False):
        return _simulate_custom_live(symbol, candles, strategy, base_strat)

    cost = FEE_PER_SIDE + SLIPPAGE_PER_SIDE
    o = candles["open"].to_numpy(float)
    h = candles["high"].to_numpy(float)
    l = candles["low"].to_numpy(float)
    c = candles["close"].to_numpy(float)
    v = candles["volume"].to_numpy(float)

    trades = []
    position = None
    for i in range(len(c)):
        exited_now = False
        if position is not None:
            tp, sl = position["take_profit"], position["stop_loss"]
            exit_price = reason = None
            if o[i] <= sl:
                exit_price, reason = o[i], "SL"
            elif o[i] >= tp:
                exit_price, reason = o[i], "TP"
            elif l[i] <= sl:
                exit_price, reason = sl, "SL"
            elif h[i] >= tp:
                exit_price, reason = tp, "TP"
            if exit_price is not None:
                qty = NOTIONAL_USDT / position["entry_price"]
                gross = qty * (exit_price - position["entry_price"])
                fees = qty * (position["entry_price"] + exit_price) * cost
                trades.append({"entry_index": position["entry_index"], "exit_index": i,
                               "entry_price": position["entry_price"], "exit_price": exit_price,
                               "reason": reason, "pnl": gross - fees})
                position = None
                exited_now = True

        signal = strategy.evaluate(symbol, {"close": c[i], "volume": v[i]})
        if signal.get("action") == "BUY" and position is None and not exited_now:
            position = {"entry_index": i, "entry_price": float(signal["entry_price"]),
                        "take_profit": float(signal["take_profit"]), "stop_loss": float(signal["stop_loss"])}
    return trades


def trades_to_metrics(trades: list) -> dict:
    capital = INITIAL_CAPITAL
    capital_curve = [capital]
    winning_trades = losing_trades = 0
    gross_profit = gross_loss = 0.0
    for t in trades:
        capital += t["pnl"]
        capital_curve.append(capital)
        if t["pnl"] > 0:
            winning_trades += 1
            gross_profit += t["pnl"]
        else:
            losing_trades += 1
            gross_loss -= t["pnl"]
    return calculate_metrics(INITIAL_CAPITAL, capital_curve, winning_trades, losing_trades, gross_profit, gross_loss)


class QuantCalculator:
    """
    Herramienta matemática pura. Recibe las velas de 15 min, una estrategia y rangos de variables.
    Devuelve las métricas (netas de costos) de la mejor combinación e imprime el recorrido para depuración.
    """
    @staticmethod
    def evaluate_strategy(symbol: str, candles: pd.DataFrame, StrategyClass, windows: list, multipliers: list) -> dict:
        best_score = -999999
        best_result = {}
        strategy_name = StrategyClass.__name__

        print(f"\n[CALCULATOR] Iniciando evaluacion de {strategy_name} para {symbol}")
        print(f"[CALCULATOR] Total de velas a procesar: {len(candles)}")

        for w in windows:
            for m in multipliers:
                # Imprimir el inicio de cada combinación para saber exactamente dónde estamos
                print(f" -> Probando Ventana: {w} | Multiplicador: {m:.2f}...", end=" ")

                strategy = StrategyClass(window=int(w), std_dev_multiplier=float(m))
                metrics = trades_to_metrics(simulate_live(symbol, candles, strategy))
                score = metrics["pnl"] - (metrics["max_drawdown_pct"] * 10)

                print(f"Completado (Trades: {metrics['trades']})")

                if score > best_score and metrics["trades"] > 5:
                    best_score = score
                    best_result = {
                        "window": int(w),
                        "multiplier": round(float(m), 2),
                        **metrics
                    }
                    print(f"    *** NUEVO RECORD *** PnL: ${metrics['pnl']} | WinRate: {metrics['win_rate']}% | MaxDD: {metrics['max_drawdown_pct']}%")

        print(f"[CALCULATOR] Evaluacion finalizada para {strategy_name}. Mejor PnL: ${best_result.get('pnl', 0)}")
        return best_result