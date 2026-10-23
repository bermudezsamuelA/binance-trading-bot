"""riesgo_r3_final.py - Ronda 3 final: evaluacion del PAQUETE DE RIESGO (tamano + interruptores) sobre las operaciones
de C1 en HOLDOUT, regeneradas con el codigo congelado (C1_eval.py) porque el Validador no guardo las operaciones.
C1 ya esta RECHAZADO y el holdout gastado: esto NO ajusta ni cambia ninguna decision; la consulta queda registrada."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import harness as H
import analista_features as af
import C1_eval as C1

S0, S1 = H.ms(2025, 7, 1), H.ms(2026, 10, 1)
REASON = "Gestor de Riesgo R3: evaluar paquete de riesgo (tamano/interruptores) sobre operaciones de C1 ya RECHAZADO; sin reajuste"
bars, data = C1.load_until(S1, REASON, S0)
Fs = af.add_cross({s: af.build(data[s], 20) for s in C1.SYMS}, list(C1.SYMS))
ST = C1.signal_table(data, Fs)
take, _, _, _ = C1.scores(ST, S0, S1)
s = 0.0012
PARAM = {"T48": dict(geom="SECUNDARIA_T48", F=0.015, DD=0.10, DAY=0.06, L=11, Elcb=0.0032, sd=0.048),
         "G3H96": dict(geom="PRIMARIA_G3H96", F=0.03, DD=0.12, DAY=0.05, L=8, Elcb=0.0016, sd=0.0438)}
for name, p in PARAM.items():
    trs = C1.simulate_all(bars, data, ST, take, S0, S1, p["geom"])
    T = H.Trades.concat(trs)
    x = T.net_ret.astype(float); n = len(x)
    print(f"\n=== {name}: n={n} E={x.mean()*100:+.3f}% WR={np.mean(x>0)*100:.1f}% (Validador: G3 148/-0.498, T48 150/+0.056)")
    if name == "G3H96":
        lu = ((T.entry_px - T.sl) + s * (T.entry_px + T.sl)) / T.entry_px
    else:
        lu = np.full(n, 0.15)
    Q = np.maximum(lu + 0.02, 0.15) if name == "G3H96" else np.full(n, 0.15)
    for TC in ((0.06, 0.10) if name == "G3H96" else (0.06,)):
        w0 = np.minimum(0.10, p["F"] / lu)
        # eventos cronologicos: entradas y salidas; tamano = w * capital en la entrada
        ev = sorted([(T.entry_t[i], 1, i) for i in range(n)] + [(T.exit_t[i], 0, i) for i in range(n)])
        eq, peak, mdd = 1.0, 1.0, 0.0
        notional = np.zeros(n); wf = np.zeros(n); openset = set()
        trig = {}; closed = 0; cum = 0.0; streak = 0; day_pnl = {}
        curve = []
        for t, kind, i in ev:
            if kind == 1:
                not_left = 0.40 - sum(wf[j] for j in openset)
                tail_left = TC - sum(wf[j] * Q[j] for j in openset)
                wi = min(w0[i], not_left, tail_left / Q[i])
                if wi >= 0.01:
                    wf[i] = wi; notional[i] = wi * eq; openset.add(i)
            else:
                if i not in openset:
                    continue
                openset.discard(i)
                pnl = notional[i] * x[i]; eq += pnl
                peak = max(peak, eq); dd = 1 - eq / peak; mdd = max(mdd, dd)
                closed += 1; cum += x[i]; streak = streak + 1 if x[i] <= 0 else 0
                d = t // 86400000; day_pnl[d] = day_pnl.get(d, 0.0) + pnl / (eq - pnl)
                date = H.iso(t)[:10]
                if dd >= p["DD"] and "caida" not in trig: trig["caida"] = (closed, date, eq)
                if -day_pnl[d] >= p["DAY"] and "dia" not in trig: trig["dia"] = (closed, date, eq)
                if streak >= p["L"] and "racha" not in trig: trig["racha"] = (closed, date, eq)
                if closed >= 30 and cum < closed * p["Elcb"] - 2 * p["sd"] * np.sqrt(closed) and "cusum" not in trig:
                    trig["cusum"] = (closed, date, eq)
                curve.append((closed, date, eq, cum))
        worst_day = min(day_pnl.values())
        # minimo margen del CUSUM
        marg = [(c, d, cu - (c * p["Elcb"] - 2 * p["sd"] * np.sqrt(c))) for c, d, e, cu in curve if c >= 30]
        mm = min(marg, key=lambda z: z[2])
        print(f"  tope de cola {TC:.2f}: capital final {eq*100-100:+.2f}%  MDD {mdd*100:.2f}%  peor dia {worst_day*100:.2f}%  "
              f"racha max {max(1, max((sum(1 for _ in g) for k, g in __import__('itertools').groupby(x[np.argsort(T.exit_t)] <= 0) if k), default=0))}")
        print(f"  CUSUM margen minimo {mm[2]*100:+.1f} pp de nocional en la op {mm[0]} ({mm[1]}); disparos: " +
              (", ".join(f"{k}: op {v[0]} el {v[1]} con capital {v[2]*100-100:+.2f}%" for k, v in trig.items()) if trig else "ninguno"))
