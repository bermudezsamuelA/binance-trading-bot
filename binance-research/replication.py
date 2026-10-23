# replication.py
"""
Replicacion PRE-REGISTRADA en monedas nuevas (2026-10-23, antes de descargar sus datos y de ver resultados).

Por que: ninguna pareja de las 4 monedas del bot pasa la validacion estricta (p < 0.05 / 20 = 0.0025). Las mejores
(SOL TrendFollowing p = 0.113, DOGE TrendFollowing p = 0.207, SOL VolatilitySqueeze p = 0.174) pueden ser suerte: es
lo que se espera de la mejor de 20 sin ventaja. Si la ventaja es real, la MISMA estrategia con el MISMO procedimiento
del bot tiene que ganar tambien en monedas que nunca se usaron. Como son solo 2 hipotesis fijadas de antemano, el
umbral es 0.05 / 2 = 0.025, y la muestra combinada de 14 monedas da mucha mas potencia que una sola moneda.

Hipotesis (una por estrategia): TrendFollowing y VolatilitySqueeze, las dos familias con PnL OOS positivo en SOL/DOGE.
Universo (fijo): las 14 monedas del laboratorio que el bot nunca opero (UNIVERSE); BTC/ETH/SOL/DOGE quedan fuera.
Procedimiento: el del bot sin cambios (walk_forward.evaluate_pair): velas de config.KLINE_INTERVAL, 6 meses de
entrenamiento -> 1 de prueba, rejilla y seleccion suavizada, filtros de config.py (riesgo minimo, co-senal entre las
monedas del universo e interruptor de momentum), una posicion por moneda, 15 USDT por operacion y la comision de
optimize.FEE_PER_SIDE (con BNB si PAY_FEES_WITH_BNB). Cada moneda elige SUS parametros; no se reoptimiza nada aqui.

Cartera: las 14 monedas operan a la vez, cada una con su posicion de 15 USDT (como el bot con varias monedas). El PnL
combinado es la suma; se mide por dia de salida.
Una hipotesis PASA si, en el OOS de desarrollo:
  1. PnL combinado > 0 y prueba t de una cola sobre el PnL combinado por dia con p < 0.025;
  2. la mayoria de las monedas con operaciones gana (>= MAJORITY_PCT % con PnL OOS > 0);
  3. >= 50 % de los meses combinados en positivo;
  4. y la validacion final (meses reservados) no pierde en conjunto (PnL combinado >= 0).
Aparte se informa cada moneda con la validacion estricta del bot (decide con 14 x 2 = 28 pruebas): sirve para ver cuales
cargaria el bot por si solas, no para decidir la hipotesis.

Uso (desde binance-research; --download necesita la VPN apagada):
  .venv\\Scripts\\python replication.py --download
Resultado: machine_learning_strategies/replication_results.json y las tablas por consola.
"""
import argparse
import datetime
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import walk_forward as wf
from config import COSIGNAL_CANDLES, ENTRY_MIN_RISK_PCT, KLINE_INTERVAL, MOMENTUM_MONTHS, PAY_FEES_WITH_BNB
from optimize import FEE_PER_SIDE, NOTIONAL_USDT, SLIPPAGE_PER_SIDE

UNIVERSE = ["ADAUSDT", "ATOMUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOTUSDT", "ETCUSDT", "FILUSDT", "LINKUSDT",
            "LTCUSDT", "NEARUSDT", "TRXUSDT", "UNIUSDT", "XRPUSDT"]
HYPOTHESES = ["TrendFollowing", "VolatilitySqueeze"]
ALPHA = 0.05 / len(HYPOTHESES)
MAJORITY_PCT = 50.0          # "la mayoria": mas de la mitad de las monedas con operaciones
MIN_POSITIVE_MONTHS_PCT = 50.0
RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "machine_learning_strategies",
                            "replication_results.json")
DAY_MS = 86_400_000


def daily_t(exit_ms, pnl) -> tuple:
    """(dias, t, p) de la prueba t de una cola sobre el PnL sumado por dia de salida (dias con operaciones)."""
    pnl = np.asarray(pnl, float)
    if not len(pnl):
        return 0, 0.0, 1.0
    _, inv = np.unique(np.asarray(exit_ms, np.int64) // DAY_MS, return_inverse=True)
    daily = np.bincount(inv, weights=pnl)
    if len(daily) < 2 or daily.std(ddof=1) == 0:
        return len(daily), 0.0, 1.0
    t = daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily)))
    return len(daily), float(t), float(sp_stats.t.sf(t, len(daily) - 1))


def max_drawdown(exit_ms, pnl) -> float:
    """Caida maxima (USDT) de la curva de PnL combinado acumulado, en orden de salida."""
    if not len(pnl):
        return 0.0
    order = np.argsort(np.asarray(exit_ms, np.int64), kind="stable")
    curve = np.concatenate(([0.0], np.cumsum(np.asarray(pnl, float)[order])))
    return float(np.max(np.maximum.accumulate(curve) - curve))


def coin_row(res: dict) -> dict:
    """PnL individual de una moneda y su estado con la validacion estricta del bot (28 pruebas)."""
    oos, hold = res.get("oos") or {}, res.get("validacion_final") or {}
    status, why, _ = wf.decide(res, len(UNIVERSE) * len(HYPOTHESES))
    return {"symbol": res["symbol"], "ops": oos.get("trades", 0), "win_rate": oos.get("win_rate", 0),
            "pnl": round(float(oos.get("pnl", 0.0)), 4), "meses_positivos_pct": oos.get("pliegues_positivos_pct", 0.0),
            "p_valor": oos.get("p_valor", 1.0), "pnl_validacion": round(float(hold.get("pnl", 0.0)), 4),
            "momentum_encendido": (res.get("momentum") or {}).get("encendido"), "estricta": status, "motivo": why}


def combine(results: list, strategy: str) -> dict:
    """Cartera de las monedas del universo con una estrategia: PnL por moneda y combinado, y la decision."""
    rs = [r for r in results if r["strategy"] == strategy]
    coins = [coin_row(r) for r in rs]
    cat = lambda part, key: np.concatenate([np.asarray(r["operaciones"][part][key], float) for r in rs]) if rs else np.zeros(0)
    ex, pnl = cat("oos", "salida_ms").astype(np.int64), cat("oos", "pnl")
    hx, hp = cat("validacion", "salida_ms").astype(np.int64), cat("validacion", "pnl")
    days, t, p = daily_t(ex, pnl)
    months = pd.to_datetime(ex, unit="ms", utc=True).strftime("%Y-%m") if len(ex) else pd.Index([])
    by_month = pd.Series(pnl).groupby(np.asarray(months)).sum() if len(ex) else pd.Series(dtype=float)
    traded = [c for c in coins if c["ops"] > 0]
    winners = sum(1 for c in traded if c["pnl"] > 0)
    sign_p = float(sp_stats.binomtest(winners, len(traded), 0.5, alternative="greater").pvalue) if traded else 1.0
    combined = {"monedas": len(coins), "monedas_con_operaciones": len(traded), "monedas_ganadoras": winners,
                "monedas_ganadoras_pct": round(100.0 * winners / len(traded), 1) if traded else 0.0,
                "p_signo": round(sign_p, 4), "ops": int(len(pnl)), "pnl": round(float(pnl.sum()), 4),
                "pnl_por_100_usdt": round(100 * float(pnl.mean()) / NOTIONAL_USDT, 4) if len(pnl) else 0.0,
                "win_rate": round(100 * float(np.mean(pnl > 0)), 1) if len(pnl) else 0.0,
                "meses": int(len(by_month)), "meses_positivos_pct": round(100.0 * float((by_month > 0).mean()), 1) if len(by_month) else 0.0,
                "mdd_usdt": round(max_drawdown(ex, pnl), 4), "dias": days, "t_dia": round(t, 3), "p_valor": float(f"{p:.3g}"),
                "validacion_ops": int(len(hp)), "validacion_pnl": round(float(hp.sum()), 4),
                "monedas_estricta": [c["symbol"] for c in coins if c["estricta"] == "validada"]}
    fails = []
    if combined["pnl"] <= 0:
        fails.append(f"PnL combinado {combined['pnl']:+.2f} USDT <= 0")
    if combined["p_valor"] >= ALPHA:
        fails.append(f"p = {combined['p_valor']:.3g} >= {ALPHA:g}")
    if combined["monedas_ganadoras_pct"] <= MAJORITY_PCT:
        fails.append(f"solo {winners} de {len(traded)} monedas ganan")
    if combined["meses_positivos_pct"] < MIN_POSITIVE_MONTHS_PCT:
        fails.append(f"solo {combined['meses_positivos_pct']} % de meses positivos")
    if combined["validacion_pnl"] < 0:
        fails.append(f"pierde en la validacion final ({combined['validacion_pnl']:+.2f} USDT)")
    combined["pasa"] = not fails
    combined["motivo"] = "; ".join(fails) if fails else (
        f"{winners}/{len(traded)} monedas ganan, PnL combinado {combined['pnl']:+.2f} USDT, p = {combined['p_valor']:.3g} < {ALPHA:g}")
    return {"combinado": combined, "por_moneda": sorted(coins, key=lambda c: -c["pnl"])}


def print_report(out: dict):
    for strategy in HYPOTHESES:
        e = out[strategy]
        c = e["combinado"]
        print("\n" + "=" * 112)
        print(f"{strategy}: {'✅ PASA' if c['pasa'] else '❌ no pasa'} ({c['motivo']})")
        print(f"{'Moneda':<10}{'ops':>5}{'WR %':>7}{'PnL OOS':>10}{'meses+':>8}{'p':>9}{'Val. final':>12}  Estricta (sola)")
        print("-" * 112)
        for r in e["por_moneda"]:
            print(f"{r['symbol']:<10}{r['ops']:>5}{r['win_rate']:>7.1f}{r['pnl']:>+10.2f}{r['meses_positivos_pct']:>7.0f}%"
                  f"{r['p_valor']:>9.3g}{r['pnl_validacion']:>+12.2f}  {r['estricta']}")
        print("-" * 112)
        print(f"{'COMBINADO':<10}{c['ops']:>5}{c['win_rate']:>7.1f}{c['pnl']:>+10.2f}{c['meses_positivos_pct']:>7.0f}%"
              f"{c['p_valor']:>9.3g}{c['validacion_pnl']:>+12.2f}  {c['monedas_ganadoras']}/{c['monedas_con_operaciones']} "
              f"monedas ganan (p signo {c['p_signo']}); caida max {c['mdd_usdt']:.2f} USDT; t/dia {c['t_dia']}")
    print("=" * 112)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="descarga antes las velas de las 14 monedas (VPN apagada)")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.download:
        from download_data import sync_historical_data
        sync_historical_data(UNIVERSE, force=True)
    t0 = time.perf_counter()
    tasks = [(s, st, wf.TRAIN_MONTHS, None, KLINE_INTERVAL, tuple(UNIVERSE)) for st in HYPOTHESES for s in UNIVERSE]
    workers = a.workers or max(1, (os.cpu_count() or 3) - 2)
    print(f"[REPLICACION] {len(tasks)} walk-forwards ({len(UNIVERSE)} monedas x {len(HYPOTHESES)} estrategias), velas de "
          f"{KLINE_INTERVAL}, comision {100 * FEE_PER_SIDE:.3f} % por lado, {workers} procesos.")
    from multiprocessing import Pool
    results = []
    with Pool(processes=min(workers, len(tasks))) as pool:
        for k, res in enumerate(pool.imap_unordered(wf.evaluate_pair, tasks), 1):
            o = res["oos"] or {}
            print(f"  [{k}/{len(tasks)}] {res['symbol']:<9} {res['strategy']:<17} {res['segundos']} s "
                  f"(OOS {o.get('trades', 0)} ops, PnL {o.get('pnl', 0):+.2f})", flush=True)
            results.append(res)
    out = {"_protocolo": {
        "preregistro": "2026-10-23, antes de descargar los datos de estas monedas (ver docstring de replication.py)",
        "generado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universo": UNIVERSE, "hipotesis": HYPOTHESES, "alfa": ALPHA, "mayoria_pct": MAJORITY_PCT,
        "vela": KLINE_INTERVAL, "comision_por_lado": FEE_PER_SIDE, "deslizamiento_por_lado": SLIPPAGE_PER_SIDE,
        "con_bnb": PAY_FEES_WITH_BNB, "nocional_usdt": NOTIONAL_USDT,
        "filtros": {"riesgo_minimo_pct": ENTRY_MIN_RISK_PCT, "cosenal_velas": COSIGNAL_CANDLES,
                    "momentum_meses": MOMENTUM_MONTHS},
        "segundos": round(time.perf_counter() - t0, 1)}}
    for strategy in HYPOTHESES:
        out[strategy] = combine(results, strategy)
    with open(RESULTS_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print_report(out)
    print(f"\n[REPLICACION] ✅ {out['_protocolo']['segundos']:.0f} s. Resultado: {RESULTS_FILE}")
    return out


if __name__ == "__main__":
    main()
