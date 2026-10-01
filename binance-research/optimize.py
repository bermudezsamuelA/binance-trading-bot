#optimize.py
import pandas as pd
import numpy as np
import sys
import os

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
        "expected_payoff": round(expected_payoff, 2),
        "pnl": round(pnl, 2)
    }

class QuantCalculator:
    """
    Herramienta matemática pura. Recibe un arreglo de precios, una estrategia y rangos de variables.
    Devuelve las métricas de rendimiento crudas e imprime el recorrido para depuración.
    """
    @staticmethod
    def evaluate_strategy(symbol: str, prices: np.ndarray, StrategyClass, windows: list, multipliers: list) -> dict:
        best_score = -999999
        best_result = {}
        strategy_name = StrategyClass.__name__

        print(f"\n[CALCULATOR] Iniciando evaluacion de {strategy_name} para {symbol}")
        print(f"[CALCULATOR] Total de precios a procesar: {len(prices)}")

        for w in windows:
            for m in multipliers:
                # Imprimir el inicio de cada combinación para saber exactamente dónde estamos
                print(f" -> Probando Ventana: {w} | Multiplicador: {m:.2f}...", end=" ")
                
                strategy = StrategyClass(window=int(w), std_dev_multiplier=float(m))
                
                capital = 1000.0
                capital_curve = [capital]
                position = None
                winning_trades = 0
                losing_trades = 0
                gross_profit = 0.0
                gross_loss = 0.0

                for price in prices:
                    if position:
                        if price >= position['take_profit']:
                            profit = position['risk_amount'] * 2.0
                            capital += profit
                            gross_profit += profit
                            winning_trades += 1
                            capital_curve.append(capital)
                            position = None
                        elif price <= position['stop_loss']:
                            loss = position['risk_amount']
                            capital -= loss
                            gross_loss += loss
                            losing_trades += 1
                            capital_curve.append(capital)
                            position = None
                        continue

                    # Se elimina el silenciador os.devnull para permitir la detección de errores reales
                    signal = strategy.evaluate(symbol, price)
                    
                    if signal["action"] == "BUY":
                        position = {
                            'take_profit': signal['take_profit'],
                            'stop_loss': signal['stop_loss'],
                            'risk_amount': 15.0
                        }

                metrics = calculate_metrics(1000.0, capital_curve, winning_trades, losing_trades, gross_profit, gross_loss)
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