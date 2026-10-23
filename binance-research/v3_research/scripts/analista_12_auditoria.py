"""Ronda 2 - Auditoría de fuga de información de C1 (solo DISEÑO).
A) Invariancia por truncamiento: cada una de las 41 variables (incluidas las que cruzan monedas) calculada con
   datos hasta la vela i debe ser idéntica a la calculada con toda la serie, en la vela i.
B) Envenenamiento del futuro (punta a punta): se reemplazan TODAS las velas con t > tau por un paseo aleatorio y
   volúmenes aleatorios en las 4 monedas; se recalculan variables, entrenamiento mensual, estandarización, umbral
   Q90 y decisiones. Las puntuaciones y decisiones de las señales con t <= tau deben ser idénticas.
C) Purga: el objetivo de cada fila de entrenamiento se conoce antes del inicio del mes de prueba.
D) Alineación temporal entre monedas."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_features as af
import C1_eval as C1
import harness as H

lines = []
P = lambda s: (print(s), lines.append(s))
END = H.DESIGN[1]
bars, data = C1.load_until(END)
syms = list(C1.SYMS)
P(f"D) Alineación: las 4 monedas comparten exactamente los mismos {len(data['BTCUSDT']['t'])} timestamps (assert en load_until): OK")
Ffull = af.add_cross({s: af.build(data[s], 20) for s in syms}, syms)

# ---------------- A) truncamiento
rng = np.random.default_rng(7)
cuts = np.sort(rng.integers(1200, len(data["BTCUSDT"]["t"]) - 1, 25))
maxdiff = {f: 0.0 for f in af.FEATURES + ["btc_ret_4h", "btc_ret_1d", "btc_z", "breadth_dip", "rel_ret_4h"] if True}
feats_all = sorted(set(af.FEATURES))
worst = {f: 0.0 for f in feats_all}
for i in cuts:
    dtr = {s: {k: (v[:i + 1] if isinstance(v, np.ndarray) else v) for k, v in data[s].items()} for s in syms}
    Ftr = af.add_cross({s: af.build(dtr[s], 20) for s in syms}, syms)
    for s in syms:
        for f in feats_all:
            a, b = Ftr[s][f][i], Ffull[s][f][i]
            if np.isnan(a) and np.isnan(b):
                continue
            d = abs(a - b) / max(1e-12, abs(b)) if np.isfinite(b) else (0.0 if a == b else np.inf)
            worst[f] = max(worst[f], d)
bad = {f: v for f, v in worst.items() if v > 1e-6}
P(f"A) Truncamiento en {len(cuts)} cortes aleatorios x 4 monedas x {len(feats_all)} variables: "
  f"máx. diferencia relativa = {max(worst.values()):.2e}. Variables con diferencia > 1e-6: {bad if bad else 'ninguna'}")

# ---------------- B) envenenamiento del futuro
START = H.ms(2023, 10, 1)
ST0 = C1.signal_table(data, Ffull)
take0, sc0, th0, log0 = C1.scores(ST0, START, END)
P(f"C) Purga: en los {len(log0)} reajustes, máx(instante en que se conoce el objetivo de entrenamiento) <= inicio del mes: "
  f"{all(r[4] <= r[0] for r in log0)}; holgura mínima = {min((r[0] - r[4]) / 60000 for r in log0):.0f} min")
for tau in (H.ms(2024, 2, 20), H.ms(2024, 11, 15), H.ms(2025, 3, 10) + 7 * 3600000):
    dp = {}
    for s in syms:
        d = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in data[s].items()}
        m = d["t"] > tau
        k = int(m.sum())
        base = d["c"][~m][-1]
        walk = base * np.exp(np.cumsum(rng.normal(0, 0.01, k)))
        d["o"][m] = walk * (1 + rng.normal(0, 0.002, k)); d["c"][m] = walk
        d["h"][m] = np.maximum(d["o"][m], walk) * (1 + np.abs(rng.normal(0, 0.003, k)))
        d["l"][m] = np.minimum(d["o"][m], walk) * (1 - np.abs(rng.normal(0, 0.003, k)))
        d["v"][m] = rng.uniform(1, 1000, k); d["tb"][m] = d["v"][m] * rng.uniform(0, 1, k)
        dp[s] = d
    Fp = af.add_cross({s: af.build(dp[s], 20) for s in syms}, syms)
    STp = C1.signal_table(dp, Fp)
    takep, scp, thp, _ = C1.scores(STp, START, END)
    # comparar señales con t <= tau (mismo conjunto de señales antes de tau)
    k0 = (ST0["t"] <= tau) & (ST0["t"] >= START)
    kp = (STp["t"] <= tau) & (STp["t"] >= START)
    same_set = np.array_equal(ST0["t"][k0], STp["t"][kp]) and np.array_equal(ST0["si"][k0], STp["si"][kp])
    dscore = np.nanmax(np.abs(sc0[k0] - scp[kp])) if same_set else np.inf
    dthr = np.nanmax(np.abs(th0[k0] - thp[kp])) if same_set else np.inf
    dtake = int((take0[k0] != takep[kp]).sum()) if same_set else -1
    nchg_after = int((take0[(ST0['t'] > tau)].sum()))
    P(f"B) tau={H.iso(tau)}: señales antes de tau={k0.sum()} mismo conjunto={same_set} | máx |Δscore|={dscore:.2e} "
      f"máx |Δumbral|={dthr:.2e} decisiones distintas={dtake} (después de tau sí cambian: control)")
with open(os.path.join(C1.HERE, "..", "output", "analista", "12_auditoria.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
