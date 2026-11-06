"""E01 (Explorador) - Compuerta de AMPLITUD DEL PANICO, causal, en DISENO.

Hipotesis (externa: salio del holdout gastado, aqui se prueba por primera vez en diseno): las senales del ensamble
ganan mas cuando el panico es multi-moneda. Dos medidas causales:
  * B_price(W): fraccion de 18 monedas spot (4 de diseno + 14 del verificador, solo velas spot 2023-2025, nunca
    usadas para decidir nada en diseno) con una caida de 1 h <= -2 sigma_1h en alguna vela de las ultimas W velas.
  * A_model(W): numero de OTRAS monedas de diseno (de 4) con p_hat >= umbral del pliegue en las ultimas W velas.
Se compara contra el azar de la misma moneda y mes y contra el azar CONDICIONADO a la misma compuerta (entradas
al azar solo cuando la compuerta esta activa): asi se separa "el dia es bueno para cualquier compra" de
"el modelo elige bien".
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H
C = B.C

D = B.load_ens()
T_ALL = None


def coin_panic_flags(t_grid):
    """Matriz (n_coins, len(t_grid)) con la bandera de caida de 1 h <= -2 sigma (causal)."""
    flags = []
    names = list(H.SYMBOLS) + B.OTHER18
    for s in names:
        p = os.path.join(B.RESEARCH, "klines", f"{s}_15m.npy")
        if not os.path.exists(p):
            p = os.path.join(B.RESEARCH, "verificador", "data", f"{s}_15m.npy")
        a = np.load(p)
        a = a[a[:, 0] < H.DESIGN[1]]
        c = a[:, 4]
        lr = H.log_returns(c)
        s15 = H.rolling_std(np.nan_to_num(lr), 672)
        lc = np.log(c)
        z4 = (lc - H.shift(lc, 4)) / (s15 * 2.0)
        f = np.nan_to_num(z4) <= -2.0
        j = np.searchsorted(a[:, 0], t_grid)
        j = np.minimum(j, len(a) - 1)
        ok = a[j, 0] == t_grid
        flags.append(np.where(ok, f[j], False))
    return np.array(flags), names


def roll_any(x, W):
    """max causal de x (bool) en las ultimas W velas (incluida la actual)."""
    x = x.astype(float)
    return H.rolling_max(x, W) > 0


def main():
    out_lines = []
    log = []
    # malla temporal comun = la de BTC en cache (las 4 monedas comparten open_time en diseno)
    tg = D["cache"]["BTCUSDT"]["t"].astype(np.int64)
    flags, names = coin_panic_flags(tg)
    res_json = {}
    # amplitud de precio por W
    Bp = {}
    for W in (16, 48, 96):
        anyW = np.array([roll_any(f, W) for f in flags])
        Bp[W] = anyW.mean(0)                      # fraccion de 18 monedas
    # mapear a filas de test
    jrow = np.searchsorted(tg, D["t"])
    # amplitud por modelo: otras monedas con p >= thr en las ultimas W velas
    sig = D["p"] >= D["thr"]
    Am = {}
    for W in (16, 48, 96):
        cnt = np.zeros(len(tg))
        per = []
        for ci_ in range(4):
            m = D["ci"] == ci_
            v = np.zeros(len(tg), bool)
            v[jrow[m][sig[m]]] = True
            per.append(roll_any(v, W))
        per = np.array(per)
        tot = per.sum(0)
        Am[W] = tot[jrow] - per[D["ci"], jrow]    # otras monedas
    # --- descriptivo: distribucion de la amplitud
    out_lines.append("## Distribucion de la amplitud de precio (fraccion de 18 monedas con caida 1 h <= -2 sigma en W)\n")
    for W in (16, 48, 96):
        b = Bp[W][jrow]
        out_lines.append(f"- W={W} velas: P(B>=0.2)={np.mean(b>=0.2):.3f}, P(B>=0.4)={np.mean(b>=0.4):.3f}, "
                         f"P(B>=0.6)={np.mean(b>=0.6):.3f}; en las velas de senal: P(B>=0.2)={np.mean(b[sig]>=0.2):.3f}, "
                         f"P(B>=0.4)={np.mean(b[sig]>=0.4):.3f}")
    # --- gradiente a nivel de vela (todas las velas que pasan el umbral; resultado X5 por vela; t por dia)
    out_lines.append("\n## Gradiente por vela (velas de senal p >= umbral del pliegue; resultado X5 por vela, solapado)\n")
    out_lines.append("| Medida | Nivel | velas | dias | WR vela % | E vela % | azar condicionado WR / E % |")
    out_lines.append("|---|---|---|---|---|---|---|")
    okx = np.isfinite(D["netX"])
    for W in (16, 48, 96):
        b = Bp[W][jrow]
        for lo, hi in ((0, 0.2), (0.2, 0.4), (0.4, 1.01)):
            g = (b >= lo) & (b < hi)
            s = sig & g & okx
            r = g & okx
            if s.sum() == 0:
                continue
            out_lines.append(f"| B_price W={W} | [{lo}, {hi}) | {s.sum()} | {len(np.unique(D['day'][s]))} | "
                             f"{np.mean(D['netX'][s]>0)*100:.1f} | {np.mean(D['netX'][s])*100:+.2f} | "
                             f"{np.mean(D['netX'][r]>0)*100:.1f} / {np.mean(D['netX'][r])*100:+.2f} |")
    for W in (16, 48, 96):
        a = Am[W]
        for lv in (0, 1, 2):
            g = (a == lv) if lv < 2 else (a >= 2)
            s = sig & g & okx
            if s.sum() == 0:
                continue
            out_lines.append(f"| A_model W={W} | {'≥2' if lv == 2 else lv} | {s.sum()} | {len(np.unique(D['day'][s]))} | "
                             f"{np.mean(D['netX'][s]>0)*100:.1f} | {np.mean(D['netX'][s])*100:+.2f} | – |")
    # --- simulacion con una posicion por moneda: compuertas
    out_lines.append("\n## Simulacion (una posicion por moneda, X5, c = 0.24 %), compuertas sobre el umbral v2\n")
    out_lines += list(B.MD_HEAD_C)
    base = B.summarize_trades(*B.simulate_entries(D, sig), D, label="v2 sin compuerta (referencia)")
    out_lines.append(B.md_row(base)); print(B.fmt(base))
    res_json["base"] = base
    n_cfg = 0
    for W in (16, 48, 96):
        b = Bp[W][jrow]
        for k in (0.2, 0.4):
            g = b >= k
            n_cfg += 1
            T, s = B.simulate_entries(D, sig & g)
            r = B.summarize_trades(T, s, D, label=f"B_price W={W} ≥ {k}", cond_base=B.cond_base(D, g))
            out_lines.append(B.md_row(r)); print(B.fmt(r)); res_json[r["label"]] = r
            # complemento (panico idiosincratico)
            T, s = B.simulate_entries(D, sig & ~g)
            r = B.summarize_trades(T, s, D, label=f"  complemento B_price W={W} < {k}", cond_base=B.cond_base(D, ~g))
            out_lines.append(B.md_row(r)); print(B.fmt(r)); res_json[r["label"]] = r
    for W in (16, 48, 96):
        g = Am[W] >= 1
        n_cfg += 1
        T, s = B.simulate_entries(D, sig & g)
        r = B.summarize_trades(T, s, D, label=f"A_model W={W} ≥ 1 otra moneda", cond_base=B.cond_base(D, g))
        out_lines.append(B.md_row(r)); print(B.fmt(r)); res_json[r["label"]] = r
    # --- umbral bajo + compuerta (E05: exigir menos cuando hay panico de mercado): p >= cuantil 0.95 del test-free?
    # El umbral bajo se fija como thr_pliegue - 0.03 (regla fija, sin ajuste) y se combina con B_price W=48 >= 0.2
    out_lines.append("\n## Umbral relajado SOLO con panico de mercado (E05): p >= thr - 0.03 y B_price(48) >= 0.2\n")
    out_lines += list(B.MD_HEAD_C)
    for dlt in (0.03, 0.06):
        g = Bp[48][jrow] >= 0.2
        m = (D["p"] >= D["thr"] - dlt) & g
        n_cfg += 1
        T, s = B.simulate_entries(D, m | sig)
        r = B.summarize_trades(T, s, D, label=f"thr-{dlt} con panico ∪ v2")
        out_lines.append(B.md_row(r)); print(B.fmt(r)); res_json[r["label"]] = r
        T, s = B.simulate_entries(D, m)
        r = B.summarize_trades(T, s, D, label=f"thr-{dlt} solo con panico", cond_base=B.cond_base(D, g))
        out_lines.append(B.md_row(r)); print(B.fmt(r)); res_json[r["label"]] = r
    B.log_once("breadth", n_cfg, "E01 amplitud del panico: B_price W{16,48,96}xk{0.2,0.4}, A_model W{16,48,96}, "
                 "umbral relajado con panico d{0.03,0.06} (diseno, ENS13 X5)")
    with open(os.path.join(B.OUT, "be_breadth.md"), "w", encoding="utf-8") as f:
        f.write("# E01 amplitud del panico (diseno 2024-01..2025-06, ENS13, salida X5)\n\n" + "\n".join(out_lines) + "\n")
    with open(os.path.join(B.OUT, "be_breadth.json"), "w", encoding="utf-8") as f:
        json.dump(res_json, f, default=float, indent=1)
    print("\n".join(out_lines[:20]))


if __name__ == "__main__":
    main()
