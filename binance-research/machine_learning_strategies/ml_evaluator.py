import os
import sys
import glob
import json
import re
import time
import datetime
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import ACTIVE_ROSTER, COSIGNAL_CANDLES, ENTRY_MIN_RISK_PCT, KLINE_INTERVAL, MOMENTUM_MONTHS
from fast_backtest import INTERVAL_MS, STRATEGY_CLASSES, check_parity, check_stats_bitwise, load_history, set_interval
import walk_forward as wf

# Modelos ML
from machine_learning_strategies.xgboost_classifier import XGBoostClassifier

RESULTS_FILE = os.path.join(os.path.dirname(__file__), "ml_results.json")
FOLD_COLUMNS = ["prueba", "n", "k", "ops_ent", "pnl_ent", "ops", "pnl", "ops_sombra", "pnl_sombra", "encendido"]


def results_file(interval: str) -> str:
    """ml_results.json es el de la temporalidad del bot (config.KLINE_INTERVAL), el unico que lee strategy_engine.py;
    las otras son estudios aparte (p. ej. ml_results_15m.json, ml_results_4h.json) que no cambian lo que carga el bot."""
    return RESULTS_FILE if interval == KLINE_INTERVAL else RESULTS_FILE.replace(".json", f"_{interval}.json")


def parity_smoke_test(symbol: str, interval: str = "15m") -> bool:
    """FASE 0: la version rapida solo se usa si da EXACTAMENTE las mismas operaciones que simulate_live con las
    clases reales (en este equipo y con estas versiones de pandas/numpy). Prueba completa: python fast_backtest.py"""
    hist = load_history(symbol, interval=interval)
    t = pd.to_datetime(hist["open_time"], unit="ms", utc=True)
    last_month = t.iloc[-1].normalize().replace(day=1) - pd.DateOffset(months=1)
    month = hist[(t >= last_month) & (t < last_month + pd.DateOffset(months=1))].reset_index(drop=True)
    if check_stats_bitwise(month, [8, 20, 52, 96], samples=40) > 0:
        print("[FASE 0] ❌ La media/desviacion rapida no coincide bit a bit con pandas.")
        return False
    cases = [(symbol, month, s, w, m) for s in STRATEGY_CLASSES for w, m in [(8, 0.8), (48, 2.0), (96, 3.2)]]
    # Modo tramo (mes de prueba del walk-forward): instancia nueva precargada, entradas durante el penultimo mes
    # completo y salidas seguidas hasta un mes despues. Tambien con el inicio retrasado: si la operacion del mes
    # anterior sigue abierta, el mes no abre hasta la vela siguiente a su salida (una posicion por moneda).
    start = int(np.searchsorted(hist["open_time"].to_numpy(), (last_month - pd.DateOffset(months=1)).value // 10**6))
    end = int(np.searchsorted(hist["open_time"].to_numpy(), last_month.value // 10**6))
    for s, (w, m) in zip(STRATEGY_CLASSES, [(20, 1.4), (56, 2.2), (32, 1.8), (88, 2.6), (12, 1.0)]):
        for delay in (0, 500):
            cases.append((symbol, hist, s, w, m, (start - wf.preseed_candles(w), start + delay, end,
                                                  min(len(hist), 2 * end - start))))
    return check_parity(cases, verbose=True)


def _compact_json(obj) -> str:
    """JSON con sangria, pero cada lista de valores simples en una sola linea (los pliegues ocupan una linea)."""
    text = json.dumps(obj, indent=4)
    return re.sub(r"\[\s*([^\[\]\{\}]*?)\s*\]",
                  lambda m: "[" + " ".join(x.strip() for x in m.group(1).splitlines()) + "]", text)


def _strategy_entry(res: dict, status: str, motivo: str, passed_wf: bool) -> dict:
    """Entrada de ml_results.json para una estrategia. window/multiplier/pnl/... son los parametros que se cargan
    en vivo y sus metricas en la ventana de entrenamiento mas reciente (mismo esquema que antes)."""
    entry = {}
    if res["vivo"] is not None:
        entry.update({k: v for k, v in res["vivo"].items() if k not in ("operar", "score_suavizado")})
    else:
        entry.update({"window": None, "multiplier": None, "trades": 0, "pnl": 0.0})
    entry["status"] = status
    entry["motivo"] = motivo
    entry["pasa_walk_forward"] = passed_wf
    entry["entrenamiento_vivo"] = {"operar": bool(res["vivo"] and res["vivo"]["operar"]),
                                   "score_suavizado": res["vivo"]["score_suavizado"] if res["vivo"] else None,
                                   "motivo": res["vivo_motivo"]}
    entry["momentum"] = res.get("momentum")
    entry["entrenamiento_pliegues"] = res["entrenamiento_pliegues"]
    entry["oos"] = res["oos"]
    entry["validacion_final"] = res["validacion_final"]
    rows = lambda rs: [[r["prueba"], r["n"], r["k"], r["ops_ent"], round(r["pnl_ent"], 4), r["ops"], round(r["pnl"], 4),
                        r.get("ops_sombra", r["ops"]), round(r.get("pnl_sombra", r["pnl"]), 4), int(r.get("encendido", True))]
                       for r in rs]
    entry["pliegues"] = rows(res["pliegues"])
    entry["pliegues_validacion"] = rows(res["pliegues_validacion"])
    return entry


def _print_summary(analysis: dict, roster: list):
    print("\n" + "=" * 132)
    print(f"{'Moneda':<9}{'Estrategia':<18}| {'Entrenamiento (en muestra)':<27}| {'OOS walk-forward (desarrollo)':<46}"
          f"| {'Validacion final':<21}| Estado")
    print(f"{'':<27}| {'ops/mes  WR %    PnL/op':<27}| {'ops   WR %    PnL     PnL/op  meses+  t/dia  p':<46}| {'ops  WR %    PnL':<21}|")
    print("-" * 132)
    for symbol in roster:
        for name in STRATEGY_CLASSES:
            e = analysis[symbol][name]
            tr, oos, hold = e["entrenamiento_pliegues"], e["oos"], e["validacion_final"]
            print(f"{symbol:<9}{name:<18}| {tr['ops_por_mes']:>6.1f} {tr['win_rate']:>5.1f} {tr['expected_payoff']:>+9.4f}{'':<5}"
                  f"| {oos['trades']:>4} {oos['win_rate']:>5.1f} {oos['pnl']:>+8.2f} {oos['expected_payoff']:>+8.4f}"
                  f" {oos['pliegues_positivos_pct']:>5.0f}% {oos['t_dia']:>+6.2f} {oos['p_valor']:<7.3g}"
                  f"| {hold['trades']:>3} {hold['win_rate']:>5.1f} {hold['pnl']:>+7.2f}   | {e['status']}"
                  + (f" · momentum {'ON' if e['momentum']['encendido'] else 'OFF'}" if e.get("momentum") else ""))
        sel = analysis[symbol]["seleccionada"]
        print(f"{'':<9}-> {'opera con ' + sel if sel else 'NO OPERA'}: {analysis[symbol]['motivo']}")
    print("=" * 132)


def run_ml_evaluation(roster: list, interval: str = KLINE_INTERVAL):
    out_file = results_file(interval)
    print(f"[ML EVALUATOR] Iniciando evaluación maestra para {len(roster)} activos en velas de {interval}...")
    if interval != KLINE_INTERVAL:
        print(f"[ML EVALUATOR] Estudio de temporalidad: se guarda en {os.path.basename(out_file)}; el bot sigue "
              f"leyendo ml_results.json (velas de {KLINE_INTERVAL}, config.py).")
    t_start = time.perf_counter()
    set_interval(interval)

    # --- FASE 0: PARIDAD DE LA VERSION RAPIDA ---
    print("\n[FASE 0] Verificando paridad exacta de la simulacion rapida con optimize.simulate_live...")
    if not parity_smoke_test(roster[0], interval):
        print(f"[FASE 0] ❌ Sin paridad exacta: no se usa la version rapida y no se actualiza {os.path.basename(out_file)}.")
        sys.exit(1)
    print("[FASE 0] ✅ Paridad exacta (mismas operaciones, mismos precios, mismo PnL).")

    # --- FASE 1: SELECCION CON WALK-FORWARD ---
    candles = load_history(roster[0], interval=interval)
    periods = wf.build_periods(candles["open_time"].to_numpy(np.int64), candle_ms=INTERVAL_MS[interval])
    dev, hold = periods["dev"], periods["holdout"]
    print(f"\n[FASE 1] Walk-forward: {wf.TRAIN_MONTHS} meses de entrenamiento -> 1 mes de prueba, "
          f"{len(dev)} pliegues ({dev[0]['name']} a {dev[-1]['name']}).")
    print(f"[FASE 1] Validacion final reservada: {periods['holdout_start']:%Y-%m-%d} a "
          f"{periods['end'] - pd.Timedelta(days=1):%Y-%m-%d} (no elige nada; solo veta si pierde dinero).")
    print(f"[FASE 1] Rejilla: {len(wf.WINDOWS)} ventanas x {len(wf.MULTIPLIERS)} multiplicadores por estrategia.")
    results = wf.run_walk_forward(roster, interval=interval)
    n_tests = len(results)

    ml_analysis = {"_protocolo": {
        "version": "walk-forward-v1",
        "generado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "datos": {"desde": f"{periods['start']:%Y-%m-%d}", "hasta": f"{periods['end'] - pd.Timedelta(days=1):%Y-%m-%d}",
                  "vela": interval},
        "entrenamiento_meses": wf.TRAIN_MONTHS,
        "desarrollo": {"pliegues": len(dev), "primer_mes_prueba": dev[0]["name"], "ultimo_mes_prueba": dev[-1]["name"]},
        "validacion_final": {"desde": f"{periods['holdout_start']:%Y-%m-%d}",
                             "hasta": f"{periods['end'] - pd.Timedelta(days=1):%Y-%m-%d}",
                             "uso": "no elige parametros ni estrategia; veta: si una estrategia que pasa el walk-forward "
                                    "pierde dinero (PnL < 0) en este periodo, queda rechazada y no se carga en modo normal"},
        "entrenamiento_vivo": {"desde": f"{periods['live']['train'][0]:%Y-%m-%d}",
                               "hasta": f"{periods['end'] - pd.Timedelta(days=1):%Y-%m-%d}"},
        "rejilla": {"windows": wf.WINDOWS, "multipliers": wf.MULTIPLIERS},
        "seleccion": (f"max del score (PnL - {wf.DD_PENALTY:g} * MDD %) promediado con sus vecinos 3x3 de la rejilla, "
                      f"entre combinaciones con >= {wf.MIN_TRADES_TRAIN} operaciones; si su PnL de entrenamiento <= 0, no opera"),
        "mes_de_prueba": ("instancia nueva precargada con max(n + 20, 100) velas (como pre_seed_engine); entradas solo "
                          "durante el mes; una posicion por moneda, como el bot: si la operacion de un mes anterior sigue "
                          "abierta, no abre hasta la vela siguiente a su salida (la validacion final hereda la del "
                          "desarrollo); cada operacion se sigue hasta su salida real, salvo las que saldrian dentro de "
                          "la validacion final"),
        "criterios": {"min_operaciones_oos": wf.MIN_TRADES_OOS, "pnl_oos": "> 0",
                      "min_meses_positivos_pct": 100 * wf.MIN_POSITIVE_FOLDS,
                      "prueba": "t de una cola sobre el PnL por dia (dias con operaciones cerradas)",
                      "pares_probados": n_tests, "alfa": wf.ALPHA, "alfa_bonferroni": round(wf.ALPHA / n_tests, 6),
                      "veto_validacion_final": "PnL < 0 en la validacion final -> rechazada"},
        "filtros": {"riesgo_minimo_pct": ENTRY_MIN_RISK_PCT, "cosenal_velas": COSIGNAL_CANDLES,
                    "momentum_meses": MOMENTUM_MONTHS,
                    "detalle": "strategy_filters.py; los aplica igual strategy_engine.py en vivo. ops/pnl de cada pliegue "
                               "= lo operado con el interruptor de momentum; ops_sombra/pnl_sombra = lo que habria dado "
                               "sin el; encendido = si ese mes se opero"},
        "costos": "0.12 % por lado (0.10 % comision + 0.02 % deslizamiento), 15 USDT por operacion",
        "pliegues_columnas": FOLD_COLUMNS,
    }}

    for symbol in roster:
        ml_analysis[symbol] = {}
        for res in (r for r in results if r["symbol"] == symbol):
            status, motivo, passed_wf = wf.decide(res, n_tests)
            ml_analysis[symbol][res["strategy"]] = _strategy_entry(res, status, motivo, passed_wf)
        validated = [n for n, e in ml_analysis[symbol].items() if e["status"] == "validada"]
        if validated:
            best = max(validated, key=lambda n: ml_analysis[symbol][n]["oos"]["t_dia"])
            ml_analysis[symbol]["seleccionada"] = best
            ml_analysis[symbol]["motivo"] = f"mayor t por dia entre {len(validated)} validada(s)"
        else:
            best = max(STRATEGY_CLASSES, key=lambda n: ml_analysis[symbol][n]["oos"]["pnl"])
            oos = ml_analysis[symbol][best]["oos"]
            ml_analysis[symbol]["seleccionada"] = None
            ml_analysis[symbol]["motivo"] = (f"ninguna estrategia validada (mejor OOS: {best}, {oos['trades']} ops, "
                                             f"PnL {oos['pnl']:+.2f} USDT, p = {oos['p_valor']:.3g})")

    # --- FASE 2: ENTRENAMIENTO DE MACHINE LEARNING (XGBOOST) ---
    # Igual que antes: el ultimo mes completo, etiquetas a 12 velas. No se usa en vivo ni en la seleccion.
    # Solo con velas de 15 min (lee los CSV de 15 min); en los estudios de otra temporalidad se omite.
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    for symbol in (roster if interval == "15m" else []):
        files = glob.glob(f"{data_path}/**/*{symbol}*.csv", recursive=True)
        m15_files = sorted(f for f in files if '15m' in f and 'monthly' in f)
        if not m15_files:
            print(f"[ML EVALUATOR] ⚠️ No se encontraron datos 15m para {symbol}")
            continue
        print(f"\n[FASE 2] Entrenando filtro táctico XGBoost para {symbol} ({os.path.basename(m15_files[-1])})...")
        df = pd.read_csv(m15_files[-1])
        # Mapeo de seguridad por si el CSV no tiene cabeceras
        if 'close' not in df.columns:
            df.columns = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]

        # Etiquetado (Labeling): Le enseñamos a la IA qué es un buen trade.
        # Regla: "Es un buen trade (1) si el precio sube más de un 1% en las próximas 12 velas (3 horas)"
        df['future_return'] = df['close'].shift(-12) / df['close'] - 1
        target_labels = (df['future_return'] > 0.01).astype(int)

        # Instanciamos y entrenamos el cerebro táctico
        xgb_model = XGBoostClassifier()
        xgb_model.train(df, target_labels)

        # Marcamos en el JSON que el modelo está entrenado y listo
        ml_analysis[symbol]["XGBoost_Status"] = "Trained"

    with open(out_file, 'w', encoding='utf-8', newline='\n') as f:
        f.write(_compact_json(ml_analysis) + "\n")

    _print_summary(ml_analysis, roster)
    print(f"\n[ML EVALUATOR] ✅ Ciclo completado en {time.perf_counter() - t_start:.0f} s. Archivo actualizado: {out_file}")
    return ml_analysis


if __name__ == "__main__":
    import argparse
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Seleccion walk-forward de estrategias por moneda.")
    parser.add_argument("--interval", choices=list(INTERVAL_MS), default=KLINE_INTERVAL,
                        help=f"temporalidad de las velas (1h y 4h se arman con las de 15 min; por defecto la del bot, "
                             f"{KLINE_INTERVAL}, que escribe ml_results.json)")
    run_ml_evaluation(ACTIVE_ROSTER, parser.parse_args().interval)
