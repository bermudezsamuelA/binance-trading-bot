"""E06 - ENTRADA CONFIRMADA por absorcion (DISENO, ENS13, senales v2, salida X5 re-anclada a la entrada).
Tras la senal en la vela i se espera hasta M velas; se compra al cierre de la primera vela j que cumpla:
  (a) low_j >= low_i (no hace un minimo nuevo) y (b) taker comprador spot de la vela j >= 50 % del volumen
  [variante (b'): ademas cierre_j > apertura_j]. Si no se cumple en M velas, se cancela.
Se reporta la E POR SENAL (canceladas = 0), la E de las canceladas si se hubieran comprado a mercado y el azar con
la misma regla (1 de cada 9 velas de test).
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
    COINS[ci_] = dict(o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], v=a[:, 5], tbv=a[:, 6], s15=z["s15"])
PEND = {}
for k in range(6):
    for ci_ in range(4):
        m = (D["fold"] == k) & (D["ci"] == ci_)
        PEND[(ci_, k)] = int(D["ii"][m].max()) + 1


def one(ci_, i, j_end, M, body, market=False):
    X = COINS[ci_]
    o, h, l, c, v, tbv, s15 = X["o"], X["h"], X["l"], X["c"], X["v"], X["tbv"], X["s15"]
    sd = s15[i] * np.sqrt(96)
    if not np.isfinite(sd) or sd <= 0:
        return None
    je = i if market else None
    if not market:
        for j in range(i + 1, min(i + 1 + M, j_end - 1)):
            ok = (l[j] >= l[i]) and (v[j] > 0 and tbv[j] / v[j] >= 0.5)
            if body:
                ok = ok and c[j] > o[j]
            if ok:
                je = j
                break
    if je is None:
        return (False, i + M, 0.0)
    e = c[je]
    tp, sl = e * (1 + A_ * sd), e * (1 - M_ * sd)
    jx, px, why = H.resolve_exit(o, h, l, c, je + 1, j_end, e, tp, sl, None, HX)
    return (True, jx, float(H.net_return(e, px)))


def run(M, body, market=False):
    sig = D["p"] >= D["thr"]
    out = []
    for ci_ in range(4):
        rows = np.flatnonzero(sig & (D["ci"] == ci_))
        rows = rows[np.argsort(D["ii"][rows])]
        free = -1
        for r in rows:
            i = int(D["ii"][r])
            if i <= free:
                continue
            res = one(ci_, i, PEND[(ci_, int(D["fold"][r]))], M, body, market)
            if res is None:
                continue
            free = res[1]
            out.append((ci_, i, res[0], res[2], int(D["day"][r])))
    return out


def rand(M, body, step=9):
    out = []
    for ci_ in range(4):
        rows = np.flatnonzero((D["ci"] == ci_) & np.isfinite(D["netX"]))
        rows = rows[np.argsort(D["ii"][rows])][::step]
        for r in rows:
            res = one(ci_, int(D["ii"][r]), PEND[(ci_, int(D["fold"][r]))], M, body)
            if res is not None:
                out.append((res[0], res[2]))
    a = np.array(out, float); f = a[:, 0] > 0
    return f.mean(), np.mean(a[f, 1] > 0), a[f, 1].mean() * 100, a[:, 1].mean() * 100


mk = {(x[0], x[1]): x[3] for x in run(0, False, market=True)}
lines = ["# E06 entrada confirmada por absorcion (diseno, ENS13, senales v2, X5 re-anclada)\n",
         "| Regla | señales | % ejecutadas | n op | WR % [Wilson] | E por op % | E por SEÑAL % | t día | E a mercado de las canceladas % | Azar misma regla: ejec. / WR / E op / E señal |",
         "|---|---|---|---|---|---|---|---|---|---|"]
res = {}
cfgs = [("mercado (referencia)", 0, False, True)] + [(f"confirmada M={M}{' + cuerpo alcista' if b else ''}", M, b, False)
                                                    for M in (1, 4) for b in (False, True)]
for lab, M, b, mkt in cfgs:
    out = run(M, b, market=mkt)
    a = np.array([(x[2], x[3], x[4]) for x in out], float)
    f = a[:, 0] > 0
    wr, lo, hi = B.wilson(int(np.sum(a[f, 1] > 0)), int(f.sum()))
    miss = np.array([mk[(x[0], x[1])] for x in out if not x[2] and (x[0], x[1]) in mk])
    rb = rand(M, b) if not mkt else (1.0, float("nan"), float("nan"), float("nan"))
    lines.append(f"| {lab} | {len(out)} | {f.mean()*100:.0f} | {int(f.sum())} | {wr*100:.1f} [{lo*100:.1f}, {hi*100:.1f}] | "
                 f"{a[f,1].mean()*100:+.2f} | {a[:,1].mean()*100:+.2f} | {B.cluster_t(a[:,1], a[:,2]):.2f} | "
                 f"{(miss.mean()*100 if len(miss) else float('nan')):+.2f} (n={len(miss)}) | "
                 f"{rb[0]*100:.0f} % / {rb[1]*100:.1f} % / {rb[2]:+.2f} / {rb[3]:+.2f} |")
    res[lab] = dict(n=int(f.sum()), wr=wr, E_op=float(a[f, 1].mean() * 100), E_sig=float(a[:, 1].mean() * 100))
    print(lines[-1])
B.log_once("confirm", 4, "E06 entrada confirmada M{1,4} x cuerpo{no,si} (diseno)")
with open(os.path.join(B.OUT, "be_confirm.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_confirm.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
