"""Ejecutor del Validador (custodio) para la prueba unica de C1 (preregistro_v2.md / C1_spec_v2.json).

v2 (ronda 3): la regla de decision se alinea EXACTAMENTE con C1_eval_v2.py congelado:
  p_k = P(T_{G-1} >= t_dia_k) (t de Student, G = dias con operaciones), Holm sobre p_dia (0.025 / 0.05),
  APRUEBA_k = Holm rechaza H0_k Y p iid_k < nivel Holm_k Y E_k(costos 0.30 %) > 0;
  INDICIO_k = no APRUEBA, E_k > 0 y t_dia_k > 0.84; RECHAZA_k = el resto. Terciaria Wilson >= 0.70 si G3H96 aprueba.
  (La v1 de este archivo usaba la normal para p y detenia Holm si fallaban las condiciones extra; se corrigio
   para coincidir con la especificacion congelada, antes de abrir el holdout.)
Ademas: llama a C1_eval_v2.run() (congelado) en el mismo proceso y exige cifras y decisiones identicas.
Modos:
  python -I holdout_C1_run.py design
  python -I holdout_C1_run.py holdout --go "<motivo>"     # UNA vez, por orden del coordinador
Salida: output/validador/C1_<modo>.json
"""
import hashlib
import json
import os
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402
import C1_eval as C  # noqa: E402
import C1_eval_v2 as C2  # noqa: E402

GEO = {"G3H96": "PRIMARIA_G3H96", "T48": "SECUNDARIA_T48"}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def verify_hashes():
    spec = json.load(open(C2.SPEC_V2, encoding="utf-8"))
    res = {fn: sha(os.path.join(HERE, fn)) == h for fn, h in spec["sha256"].items()}
    need = {"analista_features.py", "analista_common.py", "C1_eval.py", "C1_eval_v2.py", "harness.py"}
    res["completo"] = need <= set(spec["sha256"])
    return res


def t_day(T):
    x = np.asarray(T.net_ret, float)
    key = T.entry_t // 86_400_000
    u, inv = np.unique(key, return_inverse=True)
    r = np.bincount(inv, weights=x - x.mean())
    G = len(u)
    se = np.sqrt((r ** 2).sum()) / len(x) * np.sqrt(G / (G - 1))
    t = x.mean() / se
    return float(t), G, float(stats.t.sf(t, G - 1))


def decide(stats_):
    keys = sorted(stats_, key=lambda k: stats_[k]["p_dia"])
    stop = False
    for j, k in enumerate(keys):
        lvl = 0.05 / (len(keys) - j)
        rej = (not stop) and stats_[k]["p_dia"] <= lvl
        stop = stop or not rej
        s = stats_[k]
        ok = rej and s["p_iid"] < lvl and s["E030"] > 0
        s.update(nivel_holm=lvl, holm_rechaza=rej,
                 veredicto="APRUEBA" if ok else ("INDICIO" if (s["E"] > 0 and s["t_dia"] > 0.84) else "RECHAZA"))
    g = stats_["G3H96"]
    wr70 = (g["wr_lo"] >= 0.70) if g["veredicto"] == "APRUEBA" else None
    impl = ("G3H96" if g["veredicto"] == "APRUEBA" else
            "T48 (se declara que el WR 70-80 % no se logro)" if stats_["T48"]["veredicto"] == "APRUEBA" else
            "ninguna; solo prueba prospectiva en testnet (INDICIO)" if any(v["veredicto"] == "INDICIO" for v in stats_.values())
            else "ninguna (RECHAZA)")
    return wr70, impl


def breakdown(T):
    mon = T.entry_t.astype("datetime64[ms]").astype("datetime64[M]")
    um = np.unique(mon)
    msum = [float(T.net_ret[mon == u].sum()) for u in um]
    q = T.entry_t.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)
    qk = (1970 + q // 12) * 10 + (q % 12) // 3 + 1
    quarters = {}
    for k in np.unique(qk):
        s = T.subset(qk == k)
        quarters[f"{k // 10}-T{k % 10}"] = {"n": len(s), "wr": float((s.net_ret > 0).mean()), "E_pct": float(s.net_ret.mean() * 100)}
    return {"meses_positivos": f"{sum(1 for x in msum if x > 0)}/{len(msum)}", "trimestres": quarters}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "design"
    hv = verify_hashes()
    if not all(hv.values()):
        raise SystemExit(f"HASHES NO COINCIDEN o spec incompleta: {hv}. NO SE EJECUTA.")
    C2.check_frozen()
    if mode == "design":
        s, e, reason = H.ms(2023, 10, 1), H.DESIGN[1], None
    elif mode == "holdout":
        if "--go" not in sys.argv:
            raise SystemExit("El holdout solo se ejecuta con --go \"<motivo>\" por orden del coordinador.")
        reason = sys.argv[sys.argv.index("--go") + 1]
        s, e = H.HOLDOUT
    else:
        raise SystemExit(mode)
    # --- implementacion propia (custodio)
    bars, data = C.load_until(e, reason, s)
    Fs = C.af.add_cross({x: C.af.build(data[x], 20) for x in C.SYMS}, list(C.SYMS))
    ST = C.signal_table(data, Fs)
    take, _, _, log = C.scores(ST, s, e)
    yrs = (e - s) / (365.25 * 86400e3)
    st, rep = {}, {}
    for k, g in GEO.items():
        trs = C.simulate_all(bars, data, ST, take, s, e, g)
        T = H.Trades.concat(trs)
        m = H.metrics(T, years=yrs)
        m030 = H.metrics(H.Trades.concat(C.simulate_all(bars, data, ST, take, s, e, g, slip=0.0005)))
        td, G, pd = t_day(T)
        st[k] = dict(n=m["n"], E=m["E_pct"], E030=m030["E_pct"], t_dia=td, dias=G, p_dia=pd, p_iid=m["p_value"],
                     wr=m["wr"], wr_lo=m["wr_lo"], wr_hi=m["wr_hi"])
        rep[k] = {kk: m[kk] for kk in ("n", "wr", "wr_lo", "wr_hi", "b_eff", "E_pct", "E_R", "t", "p_value", "pf",
                                       "mdd_pct", "mdd_R", "max_loss_streak", "avg_win_pct", "avg_loss_pct",
                                       "tp_rate", "sl_rate", "time_rate", "risk_med_pct", "trades_per_year")}
        rep[k]["E_030_pct"] = m030["E_pct"]
        rep[k]["por_moneda"] = {sym: {kk: H.metrics(t)[kk] for kk in ("n", "wr", "E_pct", "pf")} for sym, t in zip(C.SYMS, trs)}
        rep[k].update(breakdown(T))
    wr70, impl = decide(st)
    # --- implementacion congelada C1_eval_v2 (misma corrida, misma razon)
    o2 = C2.run(s, e, reason)
    same = {}
    for k in GEO:
        h = o2["hyp"][k]
        same[k] = (h["metrics"]["n"] == st[k]["n"] and abs(h["metrics"]["E_pct"] - st[k]["E"]) < 1e-9
                   and abs(h["t_dia"] - st[k]["t_dia"]) < 1e-9 and abs(h["p_dia"] - st[k]["p_dia"]) < 1e-12
                   and abs(h["E_pct_costos_0.30"] - st[k]["E030"]) < 1e-9 and h["VEREDICTO"] == st[k]["veredicto"])
    same["WR70"] = o2["hyp"]["G3H96"]["WR_70_AFIRMADO"] == wr70
    same["IMPLEMENTAR"] = o2["IMPLEMENTAR"].split(" ")[0] == impl.split(" ")[0]
    out = {"modo": mode, "rango": [H.iso(s), H.iso(e)], "hashes": hv, "reajustes": len(log),
           "purga_ok": all(r[4] is None or r[4] <= r[0] for r in log), "senales_tomadas": int(take.sum()),
           "decision": st, "WR70_afirmado": wr70, "implementar": impl, "coincide_con_C1_eval_v2": same,
           "C1_eval_v2": {"veredictos": {k: o2["hyp"][k]["VEREDICTO"] for k in GEO}, "IMPLEMENTAR": o2["IMPLEMENTAR"],
                          "WR_70_AFIRMADO": o2["hyp"]["G3H96"]["WR_70_AFIRMADO"]},
           "reporte": rep}
    json.dump(out, open(os.path.join(H.VALIDADOR_DIR, f"C1_{mode}.json"), "w", encoding="utf-8"), indent=1, default=float)
    for k in GEO:
        d, r = st[k], rep[k]
        print(f"{k:6s} n={r['n']} WR={r['wr']*100:.1f}% [{r['wr_lo']*100:.1f},{r['wr_hi']*100:.1f}] b={r['b_eff']:.2f} "
              f"E={r['E_pct']:+.3f}% (0.30%: {r['E_030_pct']:+.3f}%) t_dia={d['t_dia']:+.2f} ({d['dias']} dias) "
              f"p_dia={d['p_dia']:.4f} p_iid={d['p_iid']:.4f} nivel={d['nivel_holm']:.3f} PF={r['pf']:.2f} "
              f"MDD={r['mdd_pct']:.1f}% ({r['mdd_R']:.1f}R) racha={r['max_loss_streak']} meses+={r['meses_positivos']} => {d['veredicto']}")
        print("      monedas: " + "  ".join(f"{a[:4]} n={v['n']} WR={v['wr']*100:.0f}% E={v['E_pct']:+.2f}%" for a, v in r["por_moneda"].items()))
        print("      trimestres: " + "  ".join(f"{q} n={v['n']} E={v['E_pct']:+.2f}%" for q, v in r["trimestres"].items()))
    print("WR>=70 % afirmado:", wr70, "| IMPLEMENTAR:", impl)
    print("coincide con C1_eval_v2:", same, "| reajustes:", out["reajustes"], "purga_ok:", out["purga_ok"])


if __name__ == "__main__":
    main()
