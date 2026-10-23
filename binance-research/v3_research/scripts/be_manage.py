"""E12/E30 - GESTION DE LA OPERACION sobre las senales v2 (DISENO, ENS13, salida base X5 = 0.7/1.75/288).

Reglas (todas comparadas con el AZAR con la MISMA regla: 1 de cada 9 velas de test, sin restriccion de posicion):
  base      : X5.
  BE        : al tocar entrada + 0.35 sd (mitad del TP), el SL pasa a entrada x (1 + 0.24 %) (punto de equilibrio).
  PARCIAL   : al tocar entrada + 0.35 sd vende el 50 % ahi y el resto sigue con SL en punto de equilibrio.
  TIEMPO24  : si a las 96 velas (24 h) el cierre esta bajo la entrada, sale al cierre.
  SL_ANCHO  : SL = 2.5 sd (geometria: b ~ 0.28, "WR fabricado").
  TESIS_ROTA: desde la vela 16 tras la entrada, sale al cierre si oi_chg_16 > 0, ret_16 < 0 y taker_imb_16 < 0
              (llegan cortos nuevos con el precio cayendo y flujo vendedor: la capitulacion no termino).
Se reporta el WR CONTABLE (neto > 0) y la E; la diferencia contra el azar con la misma regla es lo que importa.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H
C = B.C

D = B.load_ens()
A_, M_, HX = 0.7, 1.75, 288
COST = 0.0024
FEE, SLIP = H.FEE, H.SLIP
names = list(D["cache"]["BTCUSDT"]["names"])
COINS = {}
for ci_, s in enumerate(H.SYMBOLS):
    z = D["cache"][s]
    n = len(z["c"])
    a = np.load(C.find_file(C.RESEARCH, "klines", f"{s}_15m.npy"))[:n]
    Xf = z["X"]
    brk = (Xf[:, names.index("oi_chg_16")] > 0) & (Xf[:, names.index("ret_16")] < 0) & \
          (Xf[:, names.index("taker_imb_16")] < 0)
    COINS[ci_] = dict(o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], s15=z["s15"], brk=brk)
PEND = {}
for k in range(6):
    for ci_ in range(4):
        m = (D["fold"] == k) & (D["ci"] == ci_)
        PEND[(ci_, k)] = int(D["ii"][m].max()) + 1


def net(e, x):
    g = x / e
    return (g - 1) - (FEE + SLIP) * (1 + g)


def first(mask):
    k = np.flatnonzero(mask)
    return int(k[0]) if len(k) else 10 ** 9


def trade(ci_, i, j_end, rule):
    X = COINS[ci_]
    o, h, l, c, s15 = X["o"], X["h"], X["l"], X["c"], X["s15"]
    sd = s15[i] * np.sqrt(96)
    if not np.isfinite(sd) or sd <= 0:
        return None
    e = c[i]
    m_ = 2.5 if rule == "SL_ANCHO" else M_
    tp, sl = e * (1 + A_ * sd), e * (1 - m_ * sd)
    j1 = min(i + 1 + HX, j_end)
    if j1 <= i + 1:
        return None
    hh, ll, oo, cc = h[i + 1:j1], l[i + 1:j1], o[i + 1:j1], c[i + 1:j1]
    n = len(hh)
    isl, itp = first(ll <= sl), first(hh >= tp)
    risk = (e - e * (1 - M_ * sd)) / e

    def base_exit():
        if isl <= itp and isl < n:
            return isl, min(sl, oo[isl])
        if itp < n:
            return itp, tp
        return n - 1, cc[n - 1]
    if rule in ("base", "SL_ANCHO"):
        k, px = base_exit()
        return net(e, px), risk
    if rule == "TIEMPO24":
        k, px = base_exit()
        if k > 95 and n > 96 and cc[95] < e:
            return net(e, cc[95]), risk
        return net(e, px), risk
    if rule == "TESIS_ROTA":
        k, px = base_exit()
        bj = X["brk"][i + 1:j1].copy()
        bj[:15] = False
        ib = first(bj)
        if ib < k:
            return net(e, cc[ib]), risk
        return net(e, px), risk
    # BE / PARCIAL
    tg = e * (1 + 0.5 * A_ * sd)
    itg = first(hh >= tg)
    if isl <= min(itp, itg) and isl < n:
        return net(e, min(sl, oo[isl])), risk
    if itg >= n:
        return net(e, cc[n - 1]), risk
    if itp == itg:   # TP en la misma vela del disparo
        return net(e, tp), risk
    be = e * (1 + COST)
    rest_h, rest_l, rest_o, rest_c = hh[itg + 1:], ll[itg + 1:], oo[itg + 1:], cc[itg + 1:]
    if len(rest_h) == 0:
        px2 = cc[n - 1]
    else:
        isl2, itp2 = first(rest_l <= be), first(rest_h >= tp)
        if isl2 <= itp2 and isl2 < len(rest_h):
            px2 = min(be, rest_o[isl2])
        elif itp2 < len(rest_h):
            px2 = tp
        else:
            px2 = rest_c[-1]
    if rule == "BE":
        return net(e, px2), risk
    return 0.5 * net(e, tg) + 0.5 * net(e, px2), risk   # PARCIAL


def run_signals(rule):
    sig = D["p"] >= D["thr"]
    out = []
    for ci_ in range(4):
        rows = np.flatnonzero(sig & (D["ci"] == ci_))
        rows = rows[np.argsort(D["ii"][rows])]
        busy_until = -1
        for r in rows:
            i = int(D["ii"][r])
            if (ci_, i) not in BUSY:
                continue
            res = trade(ci_, i, PEND[(ci_, int(D["fold"][r]))], rule)
            if res is None:
                continue
            # ocupacion: usar la salida de la regla base para mantener el mismo conjunto de entradas en todas
            busy_until = BUSY.get((ci_, i), i)
            out.append((res[0], res[1], int(D["day"][r])))
    return np.array(out, float)


def run_random(rule, step=9):
    out = []
    for ci_ in range(4):
        rows = np.flatnonzero((D["ci"] == ci_) & np.isfinite(D["netX"]))
        rows = rows[np.argsort(D["ii"][rows])][::step]
        for r in rows:
            res = trade(ci_, int(D["ii"][r]), PEND[(ci_, int(D["fold"][r]))], rule)
            if res is not None:
                out.append(res[0])
    return np.array(out)


# mismas entradas para todas las reglas: ocupacion segun la regla base (harness.simulate)
T0, s0 = B.simulate_entries(D, D["p"] >= D["thr"])
BUSY = {}
for k in range(len(T0)):
    BUSY[(H.SYMBOLS.index(s0[k]), int(T0.sig_idx[k]))] = int(T0.exit_idx[k])
lines = ["# E12/E30 gestion de la operacion (diseno, ENS13, senales v2, X5)\n",
         "| Regla | n | WR contable % [Wilson] | E neta % | E_R | t día | ganancia media / pérdida media % | peor op % | Azar misma regla: WR % / E % | ΔWR pt / ΔE % |",
         "|---|---|---|---|---|---|---|---|---|---|"]
res = {}
for rule in ("base", "BE", "PARCIAL", "TIEMPO24", "SL_ANCHO", "TESIS_ROTA"):
    a = run_signals(rule)
    x, rk, day = a[:, 0], a[:, 1], a[:, 2]
    k = int(np.sum(x > 0)); n = len(x)
    wr, lo, hi = B.wilson(k, n)
    rr = run_random(rule)
    rw, re_ = float(np.mean(rr > 0)), float(rr.mean() * 100)
    lines.append(f"| {rule} | {n} | {wr*100:.1f} [{lo*100:.1f}, {hi*100:.1f}] | {x.mean()*100:+.2f} | {np.mean(x/rk):+.3f} | "
                 f"{B.cluster_t(x, day):.2f} | {x[x>0].mean()*100:.2f} / {-x[x<=0].mean()*100:.2f} | {x.min()*100:.1f} | "
                 f"{rw*100:.1f} / {re_:+.2f} | {(wr-rw)*100:+.1f} / {x.mean()*100-re_:+.2f} |")
    res[rule] = dict(n=n, wr=wr, wr_lo=lo, wr_hi=hi, E=float(x.mean() * 100), rand_wr=rw, rand_E=re_,
                     worst=float(x.min() * 100))
    print(lines[-1])
B.log_once("manage", 5, "E12/E30 gestion: BE, parcial+BE, salida 24h, SL 2.5sd, tesis rota (diseno)")
with open(os.path.join(B.OUT, "be_manage.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_manage.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
