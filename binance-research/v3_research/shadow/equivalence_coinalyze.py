"""Prueba de equivalencia de Coinalyze como fuente de los datos de futuros del dia en curso (seccion 7.6, salida 2).

Criterio fijado ANTES de correrla (2026-10-24): Coinalyze es equivalente si, con un hueco de 1 dia (lo que pasaria en
vivo: data.binance.vision llega hasta ayer y Coinalyze cubre hoy), el modelo congelado da las mismas velas con senal que
con los datos reales con Jaccard >= 0.8, y lo mismo para las de S1 (18 monedas, A18 >= 3), con al menos MIN_SIGNALS
velas con senal reales (con menos, el resultado es "no concluyente": dos conjuntos vacios coinciden siempre).
Coinalyze solo guarda ~7 dias a 5 min: cada corrida anade lo nuevo a cache/coinalyze/ (coinalyze.update_cache) y la
prueba usa toda la historia guardada, asi que se vuelve concluyente con el tiempo. Se informa tambien un hueco
de 2 dias y una prueba de estres (6 dias seguidos con Coinalyze), y la correlacion de p vela a vela.

Como en vivo: hasta el corte, los datos reales; desde el corte, los de Coinalyze (coinalyze.to_binance), con los ratios
de top traders arrastrados desde su ultimo valor real (Coinalyze no los tiene) y la prima reemplazada por la base
futuro/spot ("base") o por su ultimo valor real ("arrastre"). Las velas spot son siempre las reales (en vivo salen de la
API spot de Binance, que si funciona). El funding de octubre, que aun no publica Binance, es el reconstruido con la prima
(run_daily.ProxyFunding) hasta el corte y el de Coinalyze despues.

Uso (desde binance-research, con COINALYZE_API_KEY y los datos de las 18 monedas en v3_research/):
  python v3_research/shadow/equivalence_coinalyze.py
Salida: v3_research/output/prospectivo/equivalencia_coinalyze.json
"""
import datetime as dt
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import coinalyze as CZ  # noqa: E402
import run_daily as RD  # noqa: E402

C = RD.C
MIN_JACCARD = 0.8
MIN_SIGNALS = 5
NEAR_P = 0.6              # velas "cerca del umbral" (theta = 0.714) en las que se compara p con detalle
OUT = os.path.join(RD.OUT_DIR, "equivalencia_coinalyze.json")


class CoinalyzeFutures:
    """Mientras esta activo, nn_common.load_fut devuelve los datos reales hasta cut_ms y los de Coinalyze despues."""

    def __init__(self, raw: dict, offsets: dict, cut_ms: int, premium: str = "base", data_dir: str = RD.RESEARCH):
        self.raw, self.offsets, self.cut, self.premium, self.data_dir = raw, offsets, int(cut_ms), premium, data_dir

    def __enter__(self):
        self.original = C.load_fut
        original = self.original

        def load_fut(data_dir, sym):
            fu = {k: v.copy() for k, v in original(data_dir, sym).items()}
            sub = CZ.to_binance(self.raw[sym], self.offsets)
            cut = self.cut
            M = fu["metrics"][np.argsort(fu["metrics"][:, 0])]
            real, new = M[M[:, 0] < cut], sub["metrics"][sub["metrics"][:, 0] >= cut].copy()
            for col in (3, 4):                     # top traders: el ultimo valor real, arrastrado
                ok = np.isfinite(real[:, col])
                new[:, col] = real[ok, col][-1] if ok.any() else np.nan
            fu["metrics"] = np.vstack([real, new])
            K = fu["fut15m"]
            fu["fut15m"] = np.vstack([K[K[:, 0] < cut], sub["fut15m"][sub["fut15m"][:, 0] >= cut]])
            P = fu["premium15m"]
            keep = P[P[:, 0] < cut]
            if self.premium == "base":
                k = fu["fut15m"][fu["fut15m"][:, 0] >= cut]
                spot = C.load_spot(data_dir, sym)
                j = np.searchsorted(spot[:, 0], k[:, 0])
                ok = (j < len(spot)) & (spot[np.minimum(j, len(spot) - 1), 0] == k[:, 0])
                b = k[ok, 4] / spot[j[ok], 4] - 1
                rows = np.column_stack([k[ok, 0], b, b, b, b])
            else:
                last = keep[-1, 4]
                tt = np.arange(cut, int(P[:, 0].max()) + C.MS15, C.MS15, dtype=np.float64)
                rows = np.column_stack([tt, *([np.full(len(tt), last)] * 4)])
            fu["premium15m"] = np.vstack([keep, rows])
            F = fu["funding"]
            fu["funding"] = np.vstack([F[F[:, 0] < cut], sub["funding"][sub["funding"][:, 0] >= cut]])
            return fu
        C.load_fut = load_fut
        return self

    def __exit__(self, *exc):
        C.load_fut = self.original


def offsets_from(raw: dict, data_dir: str, sym: str = "BTCUSDT") -> dict:
    """Desfases de cada serie de Coinalyze respecto de Binance (con BTC, en los dias que estan las dos)."""
    fu, r = C.load_fut(data_dir, sym), raw[sym]
    M, K = fu["metrics"], fu["fut15m"]
    taker = r["k5"][:, 3] / (r["k5"][:, 2] - r["k5"][:, 3])
    return {"oi": CZ.align_offset(M[:, 0], M[:, 1], r["oi"][:, 0], r["oi"][:, 1], 300_000, log_diff=False)[0],
            "ls": CZ.align_offset(M[:, 0], M[:, 5], r["ls"][:, 0], r["ls"][:, 1], 300_000, log_diff=False)[0],
            "k5": CZ.align_offset(M[:, 0], np.log(M[:, 6]), r["k5"][:, 0], np.log(taker), 300_000, log_diff=False)[0],
            "k15": CZ.align_offset(K[:, 0], K[:, 4], r["k15"][:, 0], r["k15"][:, 4], 900_000)[0],
            "fr": 0}


def candles(ev: dict, t0: int, t1: int) -> dict:
    """{(moneda, open_time): (p, senal, S1, P1)} de las velas evaluadas en [t0, t1)."""
    out = {}
    for sym, d in ev["D"].items():
        t = d["S"]["t"].astype(np.int64)
        for i in d["ridx"]:
            if t0 <= t[i] < t1:
                out[(sym, int(t[i]))] = (float(d["p"][i]), bool(d["sig"][i]), bool(d["sig"][i] and d["A18"][i] >= RD.S1_MIN),
                                          bool(sym in RD.ANCHORS and d["sig"][i] and d["A"][i] >= 1))
    return out


def compare(real: dict, sub: dict) -> dict:
    keys = sorted(set(real) & set(sub))
    if not keys:
        return {"velas": 0}
    pr, ps = np.array([real[k][0] for k in keys]), np.array([sub[k][0] for k in keys])
    sets = lambda src, j: {k for k in keys if src[k][j]}
    out = {"velas": len(keys), "corr_p": round(float(np.corrcoef(pr, ps)[0, 1]), 4),
           "dif_media_p": round(float(np.mean(np.abs(pr - ps))), 5)}
    near = np.maximum(pr, ps) >= NEAR_P
    out["cerca_del_umbral"] = {"velas": int(near.sum()), "max_p_real": round(float(pr.max()), 4),
                               "dif_media_p": round(float(np.mean(np.abs(pr - ps)[near])), 5) if near.any() else None,
                               "corr_p": round(float(np.corrcoef(pr[near], ps[near])[0, 1]), 4) if near.sum() > 2 else None}
    for name, j in (("senales", 1), ("S1", 2), ("P1", 3)):
        a, b = sets(real, j), sets(sub, j)
        out[name] = {"real": len(a), "coinalyze": len(b), "comunes": len(a & b), "jaccard": round(RD.jaccard(a, b), 4)}
    return out


def merge(parts: list) -> dict:
    """Junta las velas de varias corridas (una por dia de prueba)."""
    out = {}
    for p in parts:
        out.update(p)
    return out


def trimmed_copy(src: str, dst: str, since_ms: int) -> str:
    """Copia de klines/ y futures/ desde since_ms (basta con el calentamiento del modelo): la prueba corre muchas veces el
    modelo sobre pocos dias y asi no recalcula las variables de todo el historial."""
    for sub in ("klines", "futures"):
        os.makedirs(os.path.join(dst, sub), exist_ok=True)
        for name in os.listdir(os.path.join(src, sub)):
            a = np.load(os.path.join(src, sub, name))
            np.save(os.path.join(dst, sub, name), a[a[:, 0] >= since_ms])
    return dst


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    symbols = RD.UNIVERSE
    now = int(time.time() * 1000)
    raw = CZ.update_cache(CZ.Coinalyze(), symbols, now)
    data_dir = trimmed_copy(RD.RESEARCH, os.path.join(RD.RESEARCH, "tmp", "equiv_data"), now - 80 * RD.DAY_MS)
    offsets = offsets_from(raw, data_dir)
    with RD.ProxyFunding():
        real_end, _ = RD.data_end_ms(data_dir, symbols)          # ultimo dia con datos reales (sin Coinalyze)
    first = max(int(min(r["oi"][0, 0] for r in raw.values())), int(min(r["ls"][0, 0] for r in raw.values())))
    day0 = (first // RD.DAY_MS + 2) * RD.DAY_MS                    # primer dia entero con Coinalyze y uno de margen
    days = list(range(day0, real_end, RD.DAY_MS))
    iso = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
    print(f"[EQUIV] Desfases {offsets}; dias de prueba {iso(days[0])} a {iso(days[-1])} (datos reales hasta {RD.iso(real_end)}).")

    def run(cut, t0, t1, premium=None):
        with RD.ProxyFunding():
            if premium is None:
                ev = RD.evaluate(data_dir, iso(t0), t1, symbols=symbols)
            else:
                with CoinalyzeFutures(raw, offsets, cut, premium, data_dir):
                    ev = RD.evaluate(data_dir, iso(t0), t1, symbols=symbols)
        return candles(ev, t0, t1)

    real = run(None, days[0], real_end)
    res = {"criterio": f"hueco de 1 dia: Jaccard de senales y de S1 >= {MIN_JACCARD}", "desfases_ms": offsets,
           "dias": [iso(days[0]), iso(days[-1])], "generado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    for premium in ("base", "arrastre"):
        for gap in (1, 2):
            parts = [run(d - (gap - 1) * RD.DAY_MS, d, d + RD.DAY_MS, premium) for d in days]
            res[f"hueco_{gap}d_prima_{premium}"] = compare(real, merge(parts))
            print(f"[EQUIV] hueco {gap} d, prima {premium}: {res[f'hueco_{gap}d_prima_{premium}']}", flush=True)
        res[f"estres_{len(days)}d_prima_{premium}"] = compare(real, run(days[0], days[0], real_end, premium))
        print(f"[EQUIV] estres {len(days)} d, prima {premium}: {res[f'estres_{len(days)}d_prima_{premium}']}", flush=True)
    def verdict(r):
        if r.get("senales", {}).get("real", 0) < MIN_SIGNALS:
            return f"no concluyente ({r.get('senales', {}).get('real', 0)} velas con senal reales < {MIN_SIGNALS})"
        ok = r["senales"]["jaccard"] >= MIN_JACCARD and r["S1"]["jaccard"] >= MIN_JACCARD
        return "equivalente" if ok else "NO equivalente"
    res["veredicto"] = {p: verdict(res[f"hueco_1d_prima_{p}"]) for p in ("base", "arrastre")}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"[EQUIV] Veredicto (hueco de 1 dia): {res['veredicto']}. Salida: {OUT}")
    return res


if __name__ == "__main__":
    main()
