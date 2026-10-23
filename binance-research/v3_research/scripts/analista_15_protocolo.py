"""Ronda 2 - Protocolo P4 del Validador aplicado a C1 (solo DISEÑO).
(i)  WF 12/3/3 fiel al protocolo: 6 pliegues (prueba 2024-01..2025-06), entrenamiento con los 12 meses previos,
     un ajuste por pliegue, purga (objetivo conocido antes del pliegue) y embargo de 96 velas al inicio de la prueba.
(ii) La especificación congelada (re-ajuste mensual expansivo) evaluada en los mismos 6 bloques de 3 meses.
(iii) Estrés: costos 0.30 % y entrada en apertura siguiente.
(iv) PBO (CSCV, S=6) de la familia de la ronda 1 (h{48,96} x q{0.8,0.9} x 5 geometrías = 20) con sumas mensuales.
(v)  DSR y Bonferroni con el número total de configuraciones registradas por el Analista."""
import os, sys, csv
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
Fs = af.add_cross({s: af.build(data[s], 20) for s in syms}, syms)
ST = C1.signal_table(data, Fs)
b0 = bars["BTCUSDT"]
folds = H.walk_forward(b0, "design", 12, 3, 3, embargo_bars=96)
GEO = {"PRIMARIA_G3H96": dict(m_sl=3.0, max_hold=96), "SECUNDARIA_T48": dict(m_sl=None, max_hold=48)}
n_cfg = 0


def fmt(m):
    return (f"N={m['n']:4d} WR={m['wr']*100:5.1f}% [{m['wr_lo']*100:4.1f},{m['wr_hi']*100:4.1f}] b={m['b_eff']:.2f} "
            f"E={m['E_pct']:+.3f}% (t={m['t']:+.2f}) PF={m['pf']:.2f}")


# (i) WF 12/3/3 fiel
P("(i) WF 12/3/3 con embargo de 96 velas (un ajuste por pliegue, ventana de entrenamiento de 12 meses)")
res_i = {g: [] for g in GEO}
stress = {"c030": [], "next_open": []}
for f in folds:
    t_tr0 = b0.t[f["train"][0]]
    t_te_raw = b0.t[f["train"][1]] if f["train"][1] < len(b0) else END   # inicio real del pliegue de prueba
    t_te0 = b0.t[f["test"][0]]                                              # tras el embargo
    t_te1 = b0.t[f["test"][1]] if f["test"][1] < len(b0) else END
    tr = (ST["t"] >= t_tr0) & (ST["t_known"] <= t_te_raw) & np.isfinite(ST["y"])
    te = (ST["t"] >= t_te0) & (ST["t"] < t_te1)
    p, th, _ = C1.fit_predict(ST["X"][tr], ST["y"][tr], ST["X"][te])
    take = np.zeros(len(ST["t"]), bool)
    take[np.flatnonzero(te)[p >= th]] = True
    row = []
    for g, gd in GEO.items():
        trs = C1.simulate_all(bars, data, ST, take, t_te0, t_te1, gd)
        res_i[g].append(H.Trades.concat(trs))
        m = H.metrics(res_i[g][-1])
        row.append(f"{g[:4]}: N={m['n']:3d} WR={m['wr']*100:4.1f}% E={m['E_pct']:+.3f}%")
    stress["c030"].append(H.Trades.concat(C1.simulate_all(bars, data, ST, take, t_te0, t_te1, GEO["PRIMARIA_G3H96"], slip=0.0005)))
    stress["next_open"].append(H.Trades.concat(C1.simulate_all(bars, data, ST, take, t_te0, t_te1, GEO["PRIMARIA_G3H96"], entry_mode="next_open")))
    P(f"  prueba {f['test_months'][0]}..{f['test_months'][1]} (entren. {f['train_months'][0]}..{f['train_months'][1]}, N_train={tr.sum()}): " + " | ".join(row))
for g in GEO:
    pos = sum(H.metrics(t)["E_pct"] > 0 for t in res_i[g])
    m = H.metrics(H.Trades.concat(res_i[g]))
    P(f"  OOS concatenado {g}: {fmt(m)} | pliegues con E>0: {pos}/6")
for k, v in stress.items():
    m = H.metrics(H.Trades.concat(v))
    P(f"  estrés {k} (primaria): {fmt(m)} | pliegues con E>0: {sum(H.metrics(t)['E_pct'] > 0 for t in v)}/6")
n_cfg += 4

# (ii) especificación congelada en los mismos bloques
P("\n(ii) Especificación congelada (re-ajuste mensual expansivo) en los mismos 6 bloques")
take_s, _, _, _ = C1.scores(ST, H.ms(2023, 10, 1), END)
for g, gd in GEO.items():
    per = []
    allt = []
    for f in folds:
        t0 = b0.t[f["train"][1]]
        t1 = b0.t[f["test"][1]] if f["test"][1] < len(b0) else END
        T = H.Trades.concat(C1.simulate_all(bars, data, ST, take_s, t0, t1, gd))
        allt.append(T)
        per.append(H.metrics(T)["E_pct"])
    m = H.metrics(H.Trades.concat(allt))
    P(f"  {g}: E por bloque = " + ", ".join(f"{x:+.2f}%" for x in per) + f" | {sum(x > 0 for x in per)}/6 | total 2024-01..2025-06: {fmt(m)}")
n_cfg += 2

# (iv) PBO de la familia de la ronda 1
P("\n(iv) PBO (CSCV, S=6) de la familia de la ronda 1: 20 configuraciones, 21 meses (2023-10..2025-06)")
fam_geo = {"T48": dict(m_sl=None, max_hold=48), "T96": dict(m_sl=None, max_hold=96), "G1H48": dict(m_sl=1.0, max_hold=48),
           "G2H96": dict(m_sl=2.0, max_hold=96), "G3H96": dict(m_sl=3.0, max_hold=96)}
months = np.array([y * 100 + m for y in (2023, 2024, 2025) for m in range(1, 13) if 202310 <= y * 100 + m <= 202506])
trs_fam, names, srs = [], [], []
for hz in (48, 96):
    C1.HZ = hz
    STh = C1.signal_table(data, Fs)
    for q in (0.8, 0.9):
        tk, _, _, _ = C1.scores(STh, H.ms(2023, 10, 1), END, q=q)
        for gname, gd in fam_geo.items():
            T = H.Trades.concat(C1.simulate_all(bars, data, STh, tk, H.ms(2023, 10, 1), END, gd))
            trs_fam.append(T); names.append(f"h{hz}_q{q}_{gname}"); srs.append(H.sharpe(T.net_ret))
C1.HZ = 96
M = H.monthly_matrix(trs_fam, months, "net_ret")
for stat in ("mean", "sharpe"):
    pb = H.pbo_cscv(M, S=6, stat=stat)
    P(f"  stat={stat}: PBO={pb['pbo']:.2f}  P(elegido IS pierde OOS)={pb['p_oos_loss']:.2f}  media OOS del elegido={pb['oos_best_mean']*100:+.2f}%/mes "
      f"pendiente OOS~IS={pb['slope_oos_on_is']:+.2f}  ({pb['n_combinations']} combinaciones)")
P(f"  configuraciones de la familia con E>0 en 2023-10..2025-06: {sum(H.metrics(t)['E_pct'] > 0 for t in trs_fam)}/20; "
  f"rango de E: {min(H.metrics(t)['E_pct'] for t in trs_fam):+.3f}% .. {max(H.metrics(t)['E_pct'] for t in trs_fam):+.3f}%")

# (v) DSR y Bonferroni
n_trials = 0
with open(H.TRIALS_LOG, encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        if r["agent"] == "analista":
            n_trials += int(r["n_configs"])
n_trials += n_cfg + 20
prim = take_s
Tp = H.Trades.concat(C1.simulate_all(bars, data, ST, prim, H.ms(2023, 10, 1), END, GEO["PRIMARIA_G3H96"]))
mp = H.metrics(Tp, n_configs=n_trials)
for nt, lab in ((n_trials, "todas las del Analista"), (20, "familia C1"), (76, "familia ridge R1+R2")):
    ds = H.deflated_sharpe(Tp.net_ret, nt, sr_trials=np.array(srs))
    P(f"(v) DSR primaria con n_trials={nt} ({lab}): SR/op={ds['sr']:.3f} SR0={ds['sr0']:.3f} DSR={ds['dsr']:.3f} (PSR vs 0 = {ds['psr0']:.3f})")
P(f"(v) Bonferroni: p={mp['p_value']:.4f} x N={n_trials} -> {mp['p_bonf']:.3f}  (familia de 20: {min(1, mp['p_value']*20):.3f})")
H.log_trials("analista", n_cfg + 20, "R2 protocolo C1: WF12/3/3 (2 geom + 2 estres), spec por bloques, familia PBO (20)", "design")
with open(os.path.join(C1.HERE, "..", "output", "analista", "15_protocolo.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
