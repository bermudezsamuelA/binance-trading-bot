"""Senales de la v3 EN VIVO (sin ordenes): cada 15 min, la vela recien cerrada de las 18 monedas.

Que hace con cada vela cerrada:
  * Historia: velas spot y futuros de data.binance.vision hasta ayer (feeds.py, una vez por dia).
  * Hoy: velas spot de la API publica de Binance mainnet (/api/v3/klines; el modelo se construyo con precios de mainnet,
    no de la testnet) y futuros de Coinalyze (coinalyze.py, con su cache), con los mismos reemplazos que mide
    equivalence_coinalyze.py: top traders arrastrados y prima reemplazada por la base futuro/spot.
  * Modelo congelado (hashes verificados) y reglas del pre-registro: P1 (anclas, A4 >= 1) y S1 (18 monedas, A18 >= 3), con
    su TP, SL y cierre por tiempo (X5, 384 velas).
  * Anota cada senal en output/vivo/senales_vivo.csv (una fila por moneda y vela, sin repetir).

NO compra ni vende. Mientras equivalence_coinalyze.py no de "equivalente", estas senales son de prueba: sirven para
comparar en el canal sombra que lo que saldria en vivo coincide con lo que se mide un dia despues.

Uso (desde binance-research, VPN apagada, con COINALYZE_API_KEY en el .env):
  .venv\\Scripts\\python v3_research\\shadow\\v3_live.py            # la ultima vela cerrada
  .venv\\Scripts\\python v3_research\\shadow\\v3_live.py --loop     # cada 15 min, hasta Ctrl+C
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import coinalyze as CZ  # noqa: E402
import equivalence_coinalyze as EQ  # noqa: E402
import run_daily as RD  # noqa: E402

C, H = RD.C, RD.H
SPOT_URL = "https://api.binance.com/api/v3/klines"
OUT_DIR = os.path.join(RD.RESEARCH, "output", "vivo")
OUT_FILE = os.path.join(OUT_DIR, "senales_vivo.csv")
COLUMNS = ["open_time_utc", "symbol", "brazo", "p", "A4", "A18", "precio", "tp", "sl", "cierre_por_tiempo_utc",
           "fuente_futuros", "anotado_utc"]


def fetch_spot_15m(symbol: str, start_ms: int, opener=urllib.request.urlopen) -> np.ndarray:
    """Velas spot de 15 min CERRADAS desde start_ms (formato de harness: t, o, h, l, c, v, taker_buy)."""
    rows, now = [], int(time.time() * 1000)
    while True:
        url = f"{SPOT_URL}?symbol={symbol}&interval=15m&startTime={int(start_ms)}&limit=1000"
        with opener(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        data = [k for k in data if int(k[6]) < now]
        rows += [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]), float(k[9])) for k in data]
        if len(data) < 1000:
            break
        start_ms = int(data[-1][0]) + C.MS15
    return np.array(rows, dtype=np.float64).reshape(-1, 7)


class LiveSpot:
    """Mientras esta activo, nn_common.load_spot devuelve la historia guardada mas las velas de hoy de la API."""

    def __init__(self, today: dict):
        self.today = today

    def __enter__(self):
        self.original = C.load_spot
        original, today = self.original, self.today

        def load_spot(data_dir, sym):
            a = original(data_dir, sym)
            b = today.get(sym)
            if b is None or not len(b):
                return a
            a = np.vstack([a, b[b[:, 0] > a[:, 0].max()]])
            return a
        C.load_spot = load_spot
        return self

    def __exit__(self, *exc):
        C.load_spot = self.original


def signals_for(ev: dict, open_time: int) -> list:
    """Senales de P1 y S1 en la vela open_time, con sus niveles de salida (X5 con 384 velas)."""
    a, m, hold = C.GEOMS["X5_384"]
    out = []
    for sym, d in ev["D"].items():
        t = d["S"]["t"].astype(np.int64)
        idx = np.flatnonzero(t == open_time)
        if not len(idx) or not d["sig"][idx[0]]:
            continue
        i = idx[0]
        c, sd = float(d["S"]["c"][i]), float(d["S"]["s15"][i] * np.sqrt(96))
        arms = []
        if sym in RD.ANCHORS and d["A"][i] >= 1:
            arms.append("P1")
        if d["A18"][i] >= RD.S1_MIN:
            arms.append("S1")
            if d["p"][i] >= RD.P_HIGH:
                arms.append("S1H")
        for arm in arms:
            out.append({"open_time_utc": RD.iso(open_time), "symbol": sym, "brazo": arm, "p": round(float(d["p"][i]), 4),
                        "A4": int(d["A"][i]), "A18": int(d["A18"][i]), "precio": c, "tp": round(c * (1 + a * sd), 8),
                        "sl": round(c * (1 - m * sd), 8),
                        "cierre_por_tiempo_utc": RD.iso(open_time + (hold + 1) * C.MS15)})
    return out


def append_signals(rows: list, source: str, path: str = OUT_FILE) -> int:
    """Anade las senales que no esten ya (misma vela, moneda y brazo). Devuelve cuantas se anadieron."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    seen = set()
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            seen = {(r["open_time_utc"], r["symbol"], r["brazo"]) for r in csv.DictReader(f)}
    new = [r for r in rows if (r["open_time_utc"], r["symbol"], r["brazo"]) not in seen]
    if not new:
        return 0
    write_header = not os.path.exists(path)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        if write_header:
            w.writeheader()
        for r in new:
            w.writerow({**r, "fuente_futuros": source, "anotado_utc": stamp})
    return len(new)


def run_once(data_dir: str = RD.RESEARCH, symbols=None, cz=None, spot_fetch=fetch_spot_15m, now_ms: int = None,
             premium: str = "base", out_file: str = OUT_FILE) -> dict:
    """Evalua la ultima vela cerrada de todas las monedas y anota sus senales."""
    symbols = symbols or RD.UNIVERSE
    now_ms = now_ms or int(time.time() * 1000)
    last_open = now_ms - now_ms % C.MS15 - C.MS15                       # ultima vela de 15 min ya cerrada
    with RD.ProxyFunding():
        hist_end, _ = RD.data_end_ms(data_dir, symbols)                  # datos de data.binance.vision completos
    spot_last = min(int(C.load_spot(data_dir, s)[:, 0].max()) for s in symbols)
    today = {s: spot_fetch(s, spot_last + C.MS15) for s in symbols}
    source = "data.binance.vision"
    with RD.ProxyFunding():
        if last_open >= hist_end:
            raw = CZ.update_cache(cz or CZ.Coinalyze(), symbols, now_ms)
            offsets = EQ.offsets_from(raw, data_dir)
            source = f"Coinalyze desde {RD.iso(hist_end)}"
            with LiveSpot(today), EQ.CoinalyzeFutures(raw, offsets, hist_end, premium, data_dir):
                ev = RD.evaluate(data_dir, RD.iso(last_open - 2 * RD.DAY_MS)[:10], last_open + C.MS15, symbols=symbols)
        else:
            with LiveSpot(today):
                ev = RD.evaluate(data_dir, RD.iso(last_open - 2 * RD.DAY_MS)[:10], last_open + C.MS15, symbols=symbols)
    rows = signals_for(ev, last_open)
    added = append_signals(rows, source, out_file)
    return {"vela": RD.iso(last_open), "fuente_futuros": source, "senales": rows, "nuevas": added}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--loop", action="store_true", help="repite cada 15 min (1 min despues del cierre de cada vela)")
    ap.add_argument("--no-download", action="store_true", help="no actualiza la historia de data.binance.vision")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    last_day = None
    while True:
        today = dt.datetime.now(dt.timezone.utc).date()
        if not a.no_download and today != last_day:
            import feeds
            since = today - dt.timedelta(days=RD.WARMUP_DAYS)
            feeds.update_spot(RD.RESEARCH, RD.UNIVERSE, since, today - dt.timedelta(days=1))
            feeds.update_futures(RD.RESEARCH, RD.UNIVERSE, since, today - dt.timedelta(days=1))
            last_day = today
        try:
            res = run_once()
            print(f"[V3 VIVO] Vela {res['vela']} UTC ({res['fuente_futuros']}): "
                  + (", ".join(f"{r['brazo']} {r['symbol']} p={r['p']} TP {r['tp']} SL {r['sl']}" for r in res["senales"])
                     or "sin senales") + f". Nuevas anotadas: {res['nuevas']}.", flush=True)
        except Exception as e:  # una vela con error no detiene el ciclo
            print(f"[V3 VIVO] ⚠️ Error en esta vela: {e}", flush=True)
        if not a.loop:
            return
        now = time.time()
        time.sleep(900 - now % 900 + 60)


if __name__ == "__main__":
    main()
