"""E02 - UMBRAL CON GARANTIA (Learn-then-Test / Clopper-Pearson con n efectivo por dias / seleccion conforme de
Jin-Candes con BH) frente al umbral v2 (max E con WR_val >= 0.75). DISENO, ENS13, salida X5.

Pregunta: ¿un umbral elegido con garantia estadistica de precision (WR >= 0.75 u 0.80) entrega en el pliegue de
prueba un WR realizado >= objetivo con mas frecuencia que el umbral v2, y con cuantas operaciones?
Nota: las etiquetas de velas cercanas estan muy correlacionadas (una capitulacion = decenas de velas); por eso el
n efectivo se toma como el numero de DIAS distintos seleccionados (conservador).
"""
import os, sys, json, math
import numpy as np
from scipy.stats import beta as Beta, binom
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H

D = B.load_ens()
GRID = [0.90, 0.93, 0.95, 0.96, 0.97, 0.98, 0.985, 0.99, 0.993, 0.995, 0.997, 0.998]


def cp_lower(k, n, conf):
    return 0.0 if k == 0 else float(Beta.ppf(1 - conf, k, n - k + 1))


def ltt_threshold(V, target, delta=0.10, objective="n"):
    """LTT con Bonferroni sobre la rejilla: H0_theta: prec < target, p-valor binomial con n_eff = dias distintos
    y k_eff = round(WR * n_eff). Devuelve el theta valido con mayor numero de velas (o mayor E)."""
    p, net, day = V["p"], V["netX"], V["t"] // B.DAY
    best = None
    G = len(GRID)
    for q in GRID:
        th = float(np.quantile(p, q))
        s = p >= th
        if s.sum() < 20:
            continue
        nd = len(np.unique(day[s]))
        wr = float(np.mean(net[s] > 0))
        k = int(round(wr * nd))
        pval = float(binom.sf(k - 1, nd, target))     # P(X >= k | prec = target)
        if pval <= delta / G and np.mean(net[s]) > 0:
            key = s.sum() if objective == "n" else np.mean(net[s])
            if best is None or key > best[1]:
                best = (th, key, wr, nd, pval)
    return best


def conformal_bh(V, p_test, alpha):
    """Seleccion conforme (Jin y Candes 2023) con H0_j: la operacion j pierde. p_j = (1 + #{i cal: pierde y
    s_i >= s_j}) / (n_cal + 1); BH a nivel alpha sobre el pliegue de prueba (usa las puntuaciones -no los
    resultados- de todo el trimestre: no es causal en vivo, es la referencia teorica)."""
    s_cal, y_cal = V["p"], V["netX"] > 0
    lose = np.sort(s_cal[~y_cal])
    n = len(s_cal)
    cnt = len(lose) - np.searchsorted(lose, p_test, side="left")
    pv = (1 + cnt) / (n + 1)
    m = len(pv)
    o = np.argsort(pv)
    ok = pv[o] <= alpha * np.arange(1, m + 1) / m
    if not ok.any():
        return np.zeros(m, bool)
    kmax = np.max(np.flatnonzero(ok)) + 1
    sel = np.zeros(m, bool)
    sel[o[:kmax]] = True
    return sel


lines = ["# E02 umbral con garantia (diseno, ENS13, X5)\n"]
rules = {}
sig_v2 = D["p"] >= D["thr"]
rules["v2: max E con WR_val >= 0.75"] = sig_v2
per_fold = {}
for target in (0.75, 0.80):
    m = np.zeros(len(D["p"]), bool)
    info = []
    for k in range(6):
        V = D["vals"][k]
        b = ltt_threshold(V, target)
        fm = D["fold"] == k
        if b is not None:
            m |= fm & (D["p"] >= b[0])
        info.append(None if b is None else (round(b[0], 3), round(b[2], 3), b[3], f"{b[4]:.1e}"))
    rules[f"LTT Bonferroni, WR >= {target} (delta 0.10, n_ef = dias)"] = m
    per_fold[f"LTT {target}"] = info
# variante: calibracion AGRANDADA = validacion del pliegue + pliegues de prueba anteriores (puntuaciones OOS de
# modelos previos; mas dias independientes) y objetivo 0.70
for target in (0.70, 0.75):
    m = np.zeros(len(D["p"]), bool)
    info = []
    for k in range(6):
        V = dict(D["vals"][k])
        if k > 0:
            prev = (D["fold"] < k) & np.isfinite(D["netX"]) & (D["t"] < D["t"][D["fold"] == k].min() - 289 * B.C.MS15)
            V = dict(p=np.concatenate([V["p"], D["p"][prev]]), netX=np.concatenate([V["netX"], D["netX"][prev]]),
                     t=np.concatenate([V["t"], D["t"][prev]]))
        b = ltt_threshold(V, target)
        fm = D["fold"] == k
        if b is not None:
            m |= fm & (D["p"] >= b[0])
        info.append(None if b is None else (round(b[0], 3), round(b[2], 3), b[3], f"{b[4]:.1e}"))
    rules[f"LTT calibracion agrandada, WR >= {target}"] = m
    per_fold[f"LTT agrandada {target}"] = info
for alpha in (0.25, 0.20):
    m = np.zeros(len(D["p"]), bool)
    info = []
    for k in range(6):
        V = D["vals"][k]
        fm = np.flatnonzero(D["fold"] == k)
        sel = conformal_bh(V, D["p"][fm], alpha)
        m[fm[sel]] = True
        info.append(int(sel.sum()))
    rules[f"Conforme Jin-Candes + BH, FDR {alpha} (no causal)"] = m
    per_fold[f"BH {alpha}"] = info
lines += list(B.MD_HEAD)
res = {}
okx = np.isfinite(D["netX"])
fold_tab = ["\n## WR realizado por pliegue (velas seleccionadas, por vela) y operaciones simuladas\n",
            "| Regla | " + " | ".join(f"P{k}" for k in range(6)) + " | pliegues bajo objetivo |",
            "|---|" + "---|" * 7]
for lab, m in rules.items():
    T, s = B.simulate_entries(D, m)
    r = B.summarize_trades(T, s, D, label=lab)
    lines.append(B.md_row(r)); print(B.fmt(r)); res[lab] = r
    cells, below = [], 0
    if "FDR" in lab:
        target = 1 - float(lab.split("FDR ")[1].split(" ")[0])
    elif ">=" in lab:
        target = float(lab.split(">= ")[1].split(" ")[0].rstrip(","))
    else:
        target = 0.75
    for k in range(6):
        fk = (D["fold"] == k) & m & okx
        if T is not None:
            tk = (T.entry_t >= H.ms(*B.TESTS[k][0], 1)) & (T.entry_t < H.ms(*B.TESTS[k][1], 1))
            ntr = int(tk.sum()); wtr = float(np.mean(T.net_ret[tk] > 0)) if ntr else float("nan")
        else:
            ntr, wtr = 0, float("nan")
        wv = float(np.mean(D["netX"][fk] > 0)) if fk.any() else float("nan")
        if ntr and wtr < target:
            below += 1
        cells.append(f"{fk.sum()} v / {wv*100:.0f} % · {ntr} op / {wtr*100:.0f} %" if fk.any() else "0")
    fold_tab.append(f"| {lab} | " + " | ".join(cells) + f" | {below} de 6 (objetivo {target:.2f}) |")
lines += fold_tab
lines.append("\nUmbrales por pliegue: " + json.dumps(per_fold, default=str))
B.log_once("conformal_extra", 2, "E02 LTT con calibracion agrandada (val + tests previos), WR>={0.70,0.75}")
B.log_once("conformal", 4, "E02 umbral con garantia: LTT-Bonferroni {0.75,0.80}, conforme+BH {0.25,0.20}")
with open(os.path.join(B.OUT, "be_conformal.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_conformal.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
print("\n".join(lines))
