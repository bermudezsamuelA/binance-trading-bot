"""E07/E08 - ENTRADA MAKER bajo el cierre de la capitulacion y REDUCCION DE COSTOS (BNB, TP maker). DISENO.

Para cada senal v2 (p >= umbral del pliegue) en la vela i:
  * mercado (referencia): compra a c_i, costos taker 0.10 % + 0.02 % por lado.
  * maker k, J: orden limite L = c_i (1 - k sigma15_i) valida J velas. Llenado SOLO si low_j < L (1 - 1e-4)
    (cruce estricto, no basta tocar); si la vela abre por debajo de L se llena al open. En la vela de llenado se
    asume lo peor: si low_j <= SL sale por SL; el TP solo cuenta desde la vela siguiente. Si no se llena, se cancela
    y la moneda queda libre. Barreras: absolutas desde c_i (A) o re-ancladas al precio de llenado (B).
    Comision maker de entrada 0.10 % (o 0.075 % con BNB), sin deslizamiento.
  * costos BNB: mercado con 0.075 % + 0.02 % por lado y TP como limite (0.075 %, sin deslizamiento).
Siempre se reporta la E POR SENAL (las no llenadas cuentan 0) y la E de las senales no llenadas si se hubieran
comprado a mercado (rebotes perdidos). Azar: la misma regla aplicada a 1 de cada 7 velas (sin restriccion).
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H
C = B.C

D = B.load_ens()
A_, M_, HX = 0.7, 1.75, 288
COINS = {}
for ci_, s in enumerate(H.SYMBOLS):
    z = D["cache"][s]
    n = len(z["c"])
    a = np.load(C.find_file(C.RESEARCH, "klines", f"{s}_15m.npy"))[:n]
    COINS[ci_] = dict(o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], s15=z["s15"])
# fin de periodo por (moneda, pliegue)
PEND = {}
for k in range(6):
    for ci_ in range(4):
        m = (D["fold"] == k) & (D["ci"] == ci_)
        PEND[(ci_, k)] = int(D["ii"][m].max()) + 1


def one(ci_, i, j_end, rule):
    """Devuelve (lleno, j_entrada, j_salida, px_e, px_s, motivo, neto) o (False, ...) si no se llena."""
    X = COINS[ci_]
    o, h, l, c, s15 = X["o"], X["h"], X["l"], X["c"], X["s15"]
    sd = s15[i] * np.sqrt(96)
    if not np.isfinite(sd) or sd <= 0:
        return None
    kind = rule["kind"]
    fe, fx, sx = rule["fee_e"], rule["fee_x"], rule["slip_x"]
    se = rule.get("slip_e", 0.0)
    tpfee = rule.get("tp_fee", fx); tpslip = rule.get("tp_slip", sx)
    if kind == "market":
        e_px, je = c[i], i
        tp, sl = c[i] * (1 + A_ * sd), c[i] * (1 - M_ * sd)
        j0 = i + 1
        jx, px, why = H.resolve_exit(o, h, l, c, j0, j_end, e_px, tp, sl, None, HX)
    else:
        L = c[i] * (1 - rule["k"] * s15[i])
        je = None
        for j in range(i + 1, min(i + 1 + rule["J"], j_end)):
            if l[j] < L * (1 - 1e-4):
                je = j
                break
        if je is None:
            return (False, i + rule["J"], i + rule["J"], np.nan, np.nan, -1, 0.0)
        e_px = min(L, o[je])
        if rule["anchor"] == "A":
            tp, sl = c[i] * (1 + A_ * sd), c[i] * (1 - M_ * sd)
        else:
            tp, sl = e_px * (1 + A_ * sd), e_px * (1 - M_ * sd)
        if l[je] <= sl:
            jx, px, why = je, min(sl, e_px), 1
        else:
            jx, px, why = H.resolve_exit(o, h, l, c, je + 1, j_end, e_px, tp, sl, None, max(1, HX - (je - i)))
    g = px / e_px
    if why == 0:
        net = (g - 1) - (fe + se) - (tpfee + tpslip) * g
    else:
        net = (g - 1) - (fe + se) - (fx + sx) * g
    return (True, je, jx, e_px, px, why, net)


def run_rule(rule, mask):
    out = []          # por senal: (ci, i, lleno, neto, dia, mes)
    for ci_ in range(4):
        rows = np.flatnonzero(mask & (D["ci"] == ci_))
        rows = rows[np.argsort(D["ii"][rows])]
        free_at = -1
        for r in rows:
            i = int(D["ii"][r])
            if i <= free_at:
                continue
            res = one(ci_, i, PEND[(ci_, int(D["fold"][r]))], rule)
            if res is None:
                continue
            filled, je, jx, epx, xpx, why, net = res
            free_at = jx
            out.append((ci_, i, filled, net, int(D["day"][r]), int(D["month"][r]), why, r))
    return out


def rand_rule(rule, step=7):
    out = []
    for ci_ in range(4):
        rows = np.flatnonzero(D["ci"] == ci_)
        rows = rows[np.argsort(D["ii"][rows])][::step]
        for r in rows:
            if not np.isfinite(D["netX"][r]):
                continue
            res = one(ci_, int(D["ii"][r]), PEND[(ci_, int(D["fold"][r]))], rule)
            if res is None:
                continue
            out.append((float(res[0]), res[6]))
    a = np.array(out, float)
    f = a[:, 0] > 0
    return dict(fill=float(f.mean()), wr_filled=float(np.mean(a[f, 1] > 0)), E_filled=float(a[f, 1].mean() * 100),
                E_signal=float(np.where(f, a[:, 1], 0).mean() * 100))


TAKER = dict(fee_e=0.001, slip_e=0.0002, fee_x=0.001, slip_x=0.0002)
RULES = [("mercado, taker 0.24 % (referencia)", dict(kind="market", **TAKER)),
         ("mercado, BNB 0.075 % + TP limite", dict(kind="market", fee_e=0.00075, slip_e=0.0002, fee_x=0.00075,
                                                  slip_x=0.0002, tp_fee=0.00075, tp_slip=0.0))]
for k in (0.5, 1.0, 2.0):
    for J in (1, 4):
        RULES.append((f"maker k={k} σ15, J={J}, barreras A", dict(kind="maker", k=k, J=J, anchor="A", fee_e=0.001,
                                                                   fee_x=0.001, slip_x=0.0002)))
for k in (0.5, 1.0):
    RULES.append((f"maker k={k} σ15, J=4, barreras B (re-ancladas)", dict(kind="maker", k=k, J=4, anchor="B",
                                                                           fee_e=0.001, fee_x=0.001, slip_x=0.0002)))
RULES.append(("maker k=1 σ15, J=4, A, BNB + TP limite", dict(kind="maker", k=1.0, J=4, anchor="A", fee_e=0.00075,
                                                              fee_x=0.00075, slip_x=0.0002, tp_fee=0.00075, tp_slip=0.0)))
sig = D["p"] >= D["thr"]
# resultado de mercado por senal para medir rebotes perdidos
mk = {(o_[0], o_[1]): o_[3] for o_ in run_rule(RULES[0][1], sig)}
lines = ["# E07/E08 entrada maker y costos (diseno, ENS13, X5, senales v2)\n",
         "| Regla | señales | % llenadas | n op | WR llenadas % [Wilson] | E por op llenada % | E por SEÑAL % (no llenadas = 0) | t día (por señal) | E a mercado de las NO llenadas % | Azar con la misma regla: llenado / WR / E op / E señal |",
         "|---|---|---|---|---|---|---|---|---|---|"]
res = {}
for lab, rule in RULES:
    out = run_rule(rule, sig)
    a = np.array([(x[2], x[3], x[4]) for x in out], float)
    f = a[:, 0] > 0
    nf = int(f.sum())
    wr, lo, hi = B.wilson(int(np.sum(a[f, 1] > 0)), nf)
    e_op = a[f, 1].mean() * 100
    e_sig = a[:, 1].mean() * 100
    t_sig = B.cluster_t(a[:, 1], a[:, 2])
    miss = [mk.get((x[0], x[1]), np.nan) for x in out if not x[2]]
    miss = np.array([m for m in miss if np.isfinite(m)])
    rb = rand_rule(rule)
    lines.append(f"| {lab} | {len(out)} | {f.mean()*100:.0f} | {nf} | {wr*100:.1f} [{lo*100:.1f}, {hi*100:.1f}] | "
                 f"{e_op:+.2f} | {e_sig:+.2f} | {t_sig:.2f} | "
                 f"{(miss.mean()*100 if len(miss) else float('nan')):+.2f} (n={len(miss)}) | "
                 f"{rb['fill']*100:.0f} % / {rb['wr_filled']*100:.1f} % / {rb['E_filled']:+.2f} / {rb['E_signal']:+.2f} |")
    res[lab] = dict(signals=len(out), fill=float(f.mean()), n=nf, wr=wr, wr_lo=lo, wr_hi=hi, E_op=e_op, E_sig=e_sig,
                    t_sig=t_sig, E_missed=float(miss.mean() * 100) if len(miss) else None, rand=rb)
    print(lines[-1])
B.log_once("maker", len(RULES) - 1, "E07/E08 entrada maker k{0.5,1,2}xJ{1,4} A/B, BNB+TP limite (diseno)")
with open(os.path.join(B.OUT, "be_maker.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_maker.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
