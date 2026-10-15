"""
Resumen de las operaciones en vivo registradas en orders/trades.csv.
Uso: .venv\\Scripts\\python report.py
"""
import os
import pandas as pd

LEDGER_FILE = os.path.join(os.path.dirname(__file__), "orders", "trades.csv")


def main():
    df = pd.read_csv(LEDGER_FILE)
    if df.empty:
        print("No hay operaciones registradas.")
        return

    df["fecha"] = pd.to_datetime(df["timestamp"], unit="ms")
    print(f"Operaciones registradas: {len(df)} "
          f"({df['fecha'].min():%Y-%m-%d %H:%M} -> {df['fecha'].max():%Y-%m-%d %H:%M})")
    print(df.groupby(["symbol", "status"]).size().unstack(fill_value=0).to_string(), "\n")

    if "pnl" not in df.columns or df["pnl"].isna().all():
        print("Ninguna operación cerrada tiene PnL registrado todavía.")
        return

    closed = df[(df["status"] == "CLOSED") & df["pnl"].notna()]
    rows = []
    for symbol, g in list(closed.groupby("symbol")) + [("TOTAL", closed)]:
        wins = (g["pnl"] > 0).sum()
        gross_win = g.loc[g["pnl"] > 0, "pnl"].sum()
        gross_loss = -g.loc[g["pnl"] < 0, "pnl"].sum()
        rows.append({
            "symbol": symbol,
            "trades": len(g),
            "win_rate_%": round(100 * wins / len(g), 2),
            "pnl_total": round(g["pnl"].sum(), 4),
            "pnl_medio": round(g["pnl"].mean(), 4),
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        })
    print(pd.DataFrame(rows).to_string(index=False))

    if "exit_reason" in closed.columns:
        print("\nMotivo de cierre:")
        print(closed["exit_reason"].value_counts().to_string())


if __name__ == "__main__":
    main()
