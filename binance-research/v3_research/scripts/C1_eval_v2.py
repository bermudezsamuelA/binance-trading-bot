"""C1_eval_v2.py - prueba única pre-registrada de C1 con el procedimiento de HOLM (ronda 3, propuesta P1).

No cambia la estrategia: reutiliza SIN MODIFICAR las funciones de C1_eval.py (señal, variables, ridge, umbral,
simulación con harness.simulate). Solo cambia la REGLA DE DECISIÓN y lo que se informa. Sin parámetros libres.

Uso (desde research/scripts):
    python -I C1_eval_v2.py --start 2023-10-01 --end 2025-07-01        # comprobación previa en DISEÑO (obligatoria)
    python -I C1_eval_v2.py --start 2025-07-01 --end 2026-10-01 --reason "C1 prueba unica preregistrada (ronda 3)"

Regla de decisión (C1_spec_v2.json):
  H1: E>0 en G3H96 (TP=SMA20, SL=C-3(SMA20-C), 96 velas);  H2: E>0 en T48 (solo tiempo, 48 velas).
  p_k = P(T_{G-1} >= t_día_k): t con errores agrupados por día UTC (CR1), G = número de días con operaciones.
  Holm (FWER 0.05): ordenar p ascendente; la menor se compara con 0.025; si la rechaza, la otra con 0.05;
  si la menor no rechaza, ninguna rechaza.
  APRUEBA_k = Holm rechaza H0_k  Y  p iid_k < nivel Holm_k  Y  E_k > 0 con costos de 0.30 % ida y vuelta.
  INDICIO_k = no APRUEBA, E_k > 0 y t_día_k > 0.84.   RECHAZA_k = el resto.
  Terciaria (solo si APRUEBA G3H96): se afirma WR >= 70 % si el límite inferior de Wilson al 95 % >= 0.70.
  Implementación: G3H96 si APRUEBA; si no y T48 APRUEBA -> T48 (y se declara que el WR 70-80 % no se logró);
  si ninguna aprueba -> no se implementa (con INDICIO solo prueba prospectiva en testnet).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from scipy import stats
import harness as H
import analista_features as af
import C1_eval as C1          # funciones congeladas (su SHA-256 se verifica abajo)

SPEC_V2 = os.path.abspath(os.path.join(HERE, "..", "output", "analista", "C1_spec_v2.json"))
FROZEN = ("analista_features.py", "analista_common.py", "C1_eval.py", "C1_eval_v2.py", "harness.py")
HYP = {"G3H96": "PRIMARIA_G3H96", "T48": "SECUNDARIA_T48"}
DESIGN_CHECK = {"G3H96": dict(n=467, E_pct=0.5408, wr=0.7238), "T48": dict(n=459, E_pct=0.7280)}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_frozen():
    if not os.path.exists(SPEC_V2):
        print("AVISO: no existe C1_spec_v2.json (solo válido antes del congelamiento)")
        return
    spec = json.load(open(SPEC_V2, encoding="utf-8"))
    for fn, h in spec["sha256"].items():
        cur = sha(os.path.join(HERE, fn))
        if cur != h:
            raise SystemExit(f"ARCHIVO MODIFICADO tras el pre-registro: {fn} ({cur[:12]} != {h[:12]}). No se ejecuta.")


def p_cluster_day(trs):
    T = H.Trades.concat(trs)
    t_day, G = C1.clustered_t(T, "day")
    return t_day, G, float(stats.t.sf(t_day, max(1, G - 1))) if np.isfinite(t_day) else float("nan")


def holm(pvals, alpha=0.05):
    keys = sorted(pvals, key=lambda k: pvals[k])
    level, rej, stop = {}, {}, False
    for j, k in enumerate(keys):
        level[k] = alpha / (len(keys) - j)
        rej[k] = (not stop) and pvals[k] <= level[k]
        if not rej[k]:
            stop = True
    return rej, level


def run(start_ms, end_ms, reason=None):
    bars, data = C1.load_until(end_ms, reason, start_ms)
    Fs = af.add_cross({s: af.build(data[s], 20) for s in C1.SYMS}, list(C1.SYMS))
    ST = C1.signal_table(data, Fs)
    take, _, _, log = C1.scores(ST, start_ms, end_ms)
    yrs = (end_ms - start_ms) / (365.25 * 86400e3)
    out = {"start": H.iso(start_ms), "end": H.iso(end_ms), "refits": len(log),
           "purge_ok": all(r[4] is None or r[4] <= r[0] for r in log), "n_taken_signals": int(take.sum()), "hyp": {}}
    pv = {}
    for k, g in HYP.items():
        trs = C1.simulate_all(bars, data, ST, take, start_ms, end_ms, g)
        m = C1.summarize(trs, g, yrs)
        m030 = C1.summarize(C1.simulate_all(bars, data, ST, take, start_ms, end_ms, g, slip=0.0005), g, yrs)
        mno = C1.summarize(C1.simulate_all(bars, data, ST, take, start_ms, end_ms, g, entry_mode="next_open"), g, yrs)
        t_day, G, p_day = p_cluster_day(trs)
        pv[k] = p_day
        out["hyp"][k] = {"metrics": m, "E_pct_costos_0.30": m030["E_pct"], "E_pct_next_open": mno["E_pct"],
                         "t_dia": t_day, "dias": G, "p_dia": p_day, "p_iid": m["p_value"]}
    rej, level = holm(pv)
    for k, h in out["hyp"].items():
        m = h["metrics"]
        ok = bool(rej[k] and h["p_iid"] < level[k] and h["E_pct_costos_0.30"] > 0)
        h["nivel_holm"] = level[k]
        h["holm_rechaza_H0"] = bool(rej[k])
        h["VEREDICTO"] = "APRUEBA" if ok else ("INDICIO" if (m["E_pct"] > 0 and h["t_dia"] > 0.84) else "RECHAZA")
    g3 = out["hyp"]["G3H96"]
    g3["WR_70_AFIRMADO"] = bool(g3["VEREDICTO"] == "APRUEBA" and g3["metrics"]["wr_lo"] >= 0.70) if g3["VEREDICTO"] == "APRUEBA" else None
    if g3["VEREDICTO"] == "APRUEBA":
        out["IMPLEMENTAR"] = "G3H96"
    elif out["hyp"]["T48"]["VEREDICTO"] == "APRUEBA":
        out["IMPLEMENTAR"] = "T48 (se declara que el WR 70-80 % no se logró)"
    elif any(h["VEREDICTO"] == "INDICIO" for h in out["hyp"].values()):
        out["IMPLEMENTAR"] = "ninguna; solo prueba prospectiva en testnet (INDICIO)"
    else:
        out["IMPLEMENTAR"] = "ninguna (RECHAZA)"
    return out


def report(out):
    for k, h in out["hyp"].items():
        m = h["metrics"]
        print(f"{k:6s} N={m['n']:4d} WR={m['wr']*100:5.2f}% [{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}] b={m['b_eff']:.2f} "
              f"E={m['E_pct']:+.4f}% | t_día={h['t_dia']:+.2f} ({h['dias']} días) p_día={h['p_dia']:.4f} p_iid={h['p_iid']:.4f} "
              f"nivel Holm={h['nivel_holm']:.3f} | E(0.30%)={h['E_pct_costos_0.30']:+.3f}% E(next_open)={h['E_pct_next_open']:+.3f}% "
              f"=> {h['VEREDICTO']}")
        print("        por moneda: " + "  ".join(f"{s[:4]} n={v['n']} WR={v['wr']*100:.0f}% E={v['E_pct']:+.2f}%"
                                          for s, v in m["per_coin"].items()))
    print("WR >= 70 % afirmado (terciaria):", out["hyp"]["G3H96"]["WR_70_AFIRMADO"])
    print("IMPLEMENTAR:", out["IMPLEMENTAR"], "| reajustes:", out["refits"], "purga_ok:", out["purge_ok"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--reason", default=None)
    a = ap.parse_args()
    check_frozen()
    s = int(dt.datetime.strptime(a.start, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    e = int(dt.datetime.strptime(a.end, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    out = run(s, e, a.reason)
    report(out)
    if (a.start, a.end) == ("2023-10-01", "2025-07-01"):
        ok = True
        for k, ref in DESIGN_CHECK.items():
            m = out["hyp"][k]["metrics"]
            ok &= m["n"] == ref["n"] and abs(m["E_pct"] - ref["E_pct"]) < 5e-4
            if "wr" in ref:
                ok &= abs(m["wr"] - ref["wr"]) < 5e-5
        print("COMPROBACIÓN DE DISEÑO (n=467/E=+0.5408 % G3H96; n=459/E=+0.728 % T48):", "OK" if ok else "FALLA -> NO EJECUTAR EL HOLDOUT")
    fn = os.path.join(HERE, "..", "output", "analista", f"C1_eval_v2_{a.start}_{a.end}.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
    print("guardado:", os.path.abspath(fn))


if __name__ == "__main__":
    main()
