"""Reproduce ml_results.json con la replica literal de optimize.py sobre el ultimo mes (sep-2026)
y explica el 94.74 % de DOGE. Escribe output/validador/reproduce_ml_results.json."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import bot_replica as BR  # noqa: E402

ML = os.path.abspath(os.path.join(H.RESEARCH_DIR, "..", "..", "machine_learning_strategies", "ml_results.json"))
ref = json.load(open(ML, encoding="utf-8"))
windows = np.arange(8, 100, 4)
mults = np.arange(0.8, 3.2, 0.2)
out = {}
for sym in H.SYMBOLS:
    bars = H.load(sym)
    i0, i1 = H.bounds(bars, (H.ms(2026, 9, 1), H.ms(2026, 10, 1)),
                      reason="reproducir ml_results.json (mes de optimizacion del bot; sin ajuste del equipo)")
    closes = bars.c[i0:i1]
    out[sym] = {}
    for name, code in BR.NAME2CODE.items():
        best, best_score = None, -1e18
        for w in windows:
            for m in mults:
                r = BR.original_optimizer(closes, code, int(w), float(m))
                if r["trades"] == 0:
                    continue
                score = r["pnl"] - r["max_drawdown_pct"] * 10
                if score > best_score and r["trades"] > 5:
                    best_score, best = score, {"window": int(w), "multiplier": round(float(m), 2), **r}
        rf = ref[sym][name]
        same = best is not None and all(best[k] == rf[k] for k in ("window", "multiplier", "trades", "win_rate", "pnl"))
        det = best.pop("detail") if best else []
        # Diagnostico del redondeo: operaciones cuyo TP redondeado quedo <= precio de entrada
        tp_le = sum(1 for d in det if d["tp"] <= d["entry"])
        sl_ge = sum(1 for d in det if d["sl"] >= d["entry"])
        wins_tp_le = sum(1 for d in det if d["tp"] <= d["entry"] and d["win"])
        hold = [d["exit_i"] - d["entry_i"] for d in det]
        out[sym][name] = {"replica": best, "ml_results": rf, "coincide": same, "tp_redondeado_<=_entrada": tp_le,
                          "ganadas_con_tp_<=_entrada": wins_tp_le, "sl_redondeado_>=_entrada": sl_ge,
                          "duracion_mediana_velas": float(np.median(hold)) if hold else None}
        print(f"{sym:9s} {name:18s} replica={best and (best['window'], best['multiplier'], best['trades'], best['win_rate'], best['pnl'])}"
              f"  json={(rf['window'], rf['multiplier'], rf['trades'], rf['win_rate'], rf['pnl'])}  coincide={same}"
              f"  TP<=entrada={tp_le} (ganadas {wins_tp_le})  SL>=entrada={sl_ge}  dur.med={out[sym][name]['duracion_mediana_velas']}")
json.dump(out, open(os.path.join(H.VALIDADOR_DIR, "reproduce_ml_results.json"), "w"), indent=1)
