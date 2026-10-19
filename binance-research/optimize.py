#optimize.py
import pandas as pd
import numpy as np
import sys
import os

# Lo mismo que hace el bot en vivo (src/api/ws-client.ts): ~15 USDT por operacion, una posicion por moneda.
NOTIONAL_USDT = 15.0
INITIAL_CAPITAL = 1000.0
# Costos por lado: comision de Binance spot (0.10 %) + deslizamiento (0.02 %), como harness.py.
FEE_PER_SIDE = 0.001
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

def simulate_live(symbol: str, candles: pd.DataFrame, strategy) -> list:
    """
    Simula vela a vela lo mismo que hace el bot en vivo con velas de 15 min cerradas:
    - La estrategia recibe TODAS las velas cerradas (con volumen), tambien con posicion abierta:
      la ventana nunca se congela (server.py / strategy_engine.py).
    - Entrada al cierre de la vela de senal (entry_price de la estrategia).
    - TP y SL desde la vela siguiente, con el maximo y el minimo de cada vela. Si la vela abre mas alla
      de una barrera, sale a la apertura; si toca las dos, cuenta el SL (supuesto conservador).
    - En la vela en la que se cierra una posicion no se abre otra (canOpenPosition en ws-client.ts).
    Devuelve una lista de operaciones con PnL neto de costos en USDT.
    """
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
