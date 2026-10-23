"""Re-evaluacion honesta de la configuracion actual del bot (ml_results.json) con el arnes.

Variantes (todas con costos 0.24 % i/v, high/low, regla conservadora, b real de cada estrategia):
  A  "fiel"        ventana congelada con posicion abierta + TP/SL redondeados a 2 decimales (como el bot);
                   niveles invalidos cierran al instante (pierden solo costos). Entrada al cierre.
  A0 "fiel s/redondeo"  igual que A sin redondeo.
  B  "limpia"      ventana continua, sin redondeo, entrada al cierre de la vela de senal.
  C  "limpia+open" como B pero entrando a la apertura siguiente con niveles re-anclados.
Periodos: DISENO (2023-01..2025-06), HOLDOUT limpio (2025-07..2026-08), SEP-2026 (mes en que el bot
optimizo: in-sample del bot, dentro del holdout del equipo).
Salida: output/validador/reeval_bot.md y reeval_bot.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import bot_replica as BR  # noqa: E402

ML = os.path.abspath(os.path.join(H.RESEARCH_DIR, "..", "..", "machine_learning_strategies", "ml_results.json"))
ref = json.load(open(ML, encoding="utf-8"))
LIVE = {"BTCUSDT": "MeanReversion", "ETHUSDT": "MeanReversion", "SOLUSDT": "MeanReversion", "DOGEUSDT": "TrendFollowing"}
REASON = "Ronda 1: evaluar config. vigente del bot (ml_results.json, no ajustada con estos datos)"

PERIODS = {
    "DISENO": ("design", None),
    "HOLDOUT 2025-07..2026-08": ((H.HOLDOUT[0], H.ms(2026, 9, 1)), REASON),
    "SEP-2026 (IS del bot)": ((H.ms(2026, 9, 1), H.ms(2026, 10, 1)), REASON),
}


def run_variant(bars, code, w, m, i0, i1, var, cache):
    if var == "A":
        return BR.run_frozen(bars, code, w, m, (i0, i1), rounding=True)
    if var == "A0":
        return BR.run_frozen(bars, code, w, m, (i0, i1), rounding=False)
    sig, tp, sl = BR.signals(bars, code, w, m, rounding=False, cache=cache)
    if var == "B":
        return H.simulate(bars, sig, tp, sl, period=(i0, i1), entry_mode="close")
    if var == "C":
        return H.simulate(bars, sig, tp, sl, period=(i0, i1), entry_mode="next_open", levels="relative")
    raise ValueError(var)


results = {}
lines = ["# Re-evaluacion honesta de la configuracion vigente del bot", "",
         "Costos 0.24 % ida y vuelta; TP/SL con high/low; TP y SL en la misma vela = SL; WR = P(neto > 0).", ""]
live_trades = {p: {"A": [], "B": []} for p in PERIODS}
for sym in H.SYMBOLS:
    bars = H.load(sym)
    cache = {}
    for name in ("MeanReversion", "TrendFollowing", "VolatilitySqueeze"):  # VWAP = MeanReversion en el bot
        cfg = ref[sym][name]
        code, w, m = BR.NAME2CODE[name], int(cfg["window"]), float(cfg["multiplier"])
        is_live = LIVE[sym] == name
        lines.append(f"## {sym} {name} (n={w}, k={m}){'  <- CARGADA EN VIVO' if is_live else ''}")
        lines.append(f"ml_results.json (sep-2026, optimizador original): {cfg['trades']} op., WR {cfg['win_rate']} %, "
                     f"PF {cfg['profit_factor']}, PnL {cfg['pnl']} USD; b real de la estrategia = {BR.B_REAL[code]}")
        lines.append("")
        lines.append(H.md_header("Periodo / variante"))
        for pname, (part, reason) in PERIODS.items():
            i0, i1 = H.bounds(bars, part, reason=reason, who="validador")
            variants = ("A", "A0", "B", "C") if pname == "DISENO" else ("A", "B")
            for var in variants:
                tr = run_variant(bars, code, w, m, i0, i1, var, cache)
                met = H.metrics(tr, n_configs=4 if is_live else 12, boot=2000)
                met["n_invalid"] = int(np.sum(tr.reason == H.INVALID))
                results.setdefault(sym, {}).setdefault(name, {}).setdefault(pname, {})[var] = met
                lines.append(H.md_row(f"{pname} / {var}", met))
                if is_live and var in ("A", "B"):
                    live_trades[pname][var].append(tr)
                print(H.fmt(met, f"{sym[:4]} {code} {pname[:8]} {var}"), f"inv={met['n_invalid']}")
        lines.append("")

lines.append("## Cartera de las 4 configuraciones cargadas en vivo (operaciones juntas)")
lines.append("")
lines.append(H.md_header("Periodo / variante"))
for pname in PERIODS:
    for var in ("A", "B"):
        tr = H.Trades.concat(live_trades[pname][var])
        met = H.metrics(tr, n_configs=4, boot=2000, frac=0.25)
        results.setdefault("CARTERA_VIVO", {}).setdefault(pname, {})[var] = met
        lines.append(H.md_row(f"{pname} / {var}", met))
        print(H.fmt(met, f"CARTERA {pname[:8]} {var}"))
lines.append("")
lines.append("MDD de la cartera calculado con 25 % del capital por operacion (4 monedas).")

open(os.path.join(H.VALIDADOR_DIR, "reeval_bot.md"), "w", encoding="utf-8").write("\n".join(lines))
json.dump(results, open(os.path.join(H.VALIDADOR_DIR, "reeval_bot.json"), "w"), indent=1, default=float)
