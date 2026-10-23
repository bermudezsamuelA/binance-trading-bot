"""R2-E2/E3 Orden dentro del episodio y variantes de compuerta (DISENO). Pre-registro (escrito antes de correr):

Episodio de mercado: racha de senales (p >= theta) de CUALQUIERA de las 4 monedas; empieza uno nuevo si pasan > 48 velas
sin senal de ninguna moneda (causal). Variables en la vela de senal t de la moneda i (episodio e):
  rank = 1 + n.o de OTRAS monedas cuya primera senal en e es ANTERIOR (estricto) a la primera senal de i en e;
  tsf  = velas desde la primera senal de e;  nprev = senales propias de i en e antes de t.
Reglas (todas se anaden a la pila p >= theta y A(W=48) >= 1; cortes fijos):
  E2  F_rank1 (rank = 1), F_rank2 (rank >= 2, = "la otra moneda dio senal ANTES"), F_rank23 (rank in {2, 3}),
      F_tsf_le48 (tsf <= 48), F_tsf_gt48 (tsf > 48), F_nprev0 (nprev = 0), F_nprev1 (nprev >= 1).
  E3  G_exc  : suma sobre j != i de max_{ultimas 48} (p_j - theta)+  >= mediana de esa suma en las senales con
               compuerta de la VALIDACION del pliegue;
      G_BE   : la co-senal viene de BTC o ETH (A sobre {BTC, ETH} \\ {i} >= 1);
      G_prev : co-senal estrictamente anterior (otra moneda con senal en [t-48, t-1], sin contar la vela t);
      G_p25 / G_p50 : p propio >= cuantil 0.25 / 0.50 de p en las senales con compuerta de la VALIDACION del pliegue.
Azar condicionado: A >= 1 y la parte de mercado de la regla (tsf, G_exc, G_BE, G_prev); para rank, nprev y p, solo A >= 1.
12 reglas x 3 ensambles. Se registra 12.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
B, H = E.B, E.H


def episode_feats(D, sig):
    """Devuelve grids (4, N): rank, tsf, nprev (NaN fuera de senal) y tsf_mkt (para cualquier vela en episodio activo)."""
    N = len(D["tg"])
    S = E.to_grid(D, sig, False, bool)
    anyb = np.where(S.any(0))[0]
    rank = np.full((4, N), np.nan); tsf = np.full((4, N), np.nan); nprev = np.full((4, N), np.nan)
    tsf_mkt = np.full(N, np.nan)
    if len(anyb) == 0:
        return rank, tsf, nprev, tsf_mkt
    # episodios
    starts = [0]
    for k in range(1, len(anyb)):
        if anyb[k] - anyb[k - 1] > E.W:
            starts.append(k)
    starts.append(len(anyb))
    for e in range(len(starts) - 1):
        bars = anyb[starts[e]:starts[e + 1]]
        t0, t1 = bars[0], bars[-1]
        tsf_mkt[t0:min(N, t1 + E.W)] = np.arange(t0, min(N, t1 + E.W)) - t0
        first = {}
        for i in range(4):
            bi = bars[S[i, bars]]
            if len(bi):
                first[i] = bi[0]
        for i in range(4):
            bi = bars[S[i, bars]]
            if not len(bi):
                continue
            rk = 1 + sum(1 for j, fj in first.items() if j != i and fj < first[i])
            rank[i, bi] = rk
            tsf[i, bi] = bi - t0
            nprev[i, bi] = np.arange(len(bi))
    return rank, tsf, nprev, tsf_mkt


def excess_sum(D, p, thr, ci, jrow, N):
    G = np.zeros((4, N))
    G[ci, jrow] = np.maximum(p - thr, 0)
    Rm = np.array([np.nan_to_num(H.rolling_max(g, E.W), nan=0.0) for g in G])
    tot = Rm.sum(0)
    return tot[jrow] - Rm[ci, jrow]


def val_quantities(D):
    """Por pliegue: mediana de G_exc y cuantiles de p en las senales con compuerta de la validacion."""
    N = len(D["tg"])
    out = []
    for k in range(6):
        v = D["vals"][k]
        j = np.searchsorted(D["tg"], v["t"]); assert np.all(D["tg"][j] == v["t"])
        sigv = v["p"] >= v["thr"]
        S = np.zeros((4, N), bool); S[v["ci"], j] = sigv
        per = E.roll_any(S, E.W)
        A = per.sum(0)[j] - per[v["ci"], j]
        gated = sigv & (A >= 1)
        exc = excess_sum(D, v["p"], v["thr"], v["ci"], j, N)
        out.append(dict(n_gated=int(gated.sum()), exc_med=float(np.median(exc[gated])) if gated.any() else 0.0,
                        p25=float(np.quantile(v["p"][gated], .25)) if gated.any() else -np.inf,
                        p50=float(np.quantile(v["p"][gated], .50)) if gated.any() else -np.inf))
    return out


def rules(D):
    sig, A = D["sig"], D["A"]
    g1 = A >= 1
    rank, tsf, nprev, tsf_mkt = episode_feats(D, sig)
    rk, ts, npv = E.from_grid(D, rank), E.from_grid(D, tsf), E.from_grid(D, nprev)
    tsm = tsf_mkt[D["jrow"]]
    vq = val_quantities(D)
    fold = D["fold"]
    exc = excess_sum(D, D["p"], D["thr"], D["ci"], D["jrow"], len(D["tg"]))
    exc_thr = np.array([vq[k]["exc_med"] for k in range(6)])[fold]
    p25 = np.array([vq[k]["p25"] for k in range(6)])[fold]
    p50 = np.array([vq[k]["p50"] for k in range(6)])[fold]
    A_BE = E.gate_count(D, sig, coins=(0, 1))
    A_prev = E.gate_count(D, sig, before_only=True)
    R = {
        "F_rank1 (primera moneda del episodio)": (rk == 1, g1),
        "F_rank2 (otra moneda dio señal antes)": (rk >= 2, g1),
        "F_rank23 (2.ª o 3.ª moneda)": ((rk == 2) | (rk == 3), g1),
        "F_tsf_le48 (≤ 12 h desde la 1.ª señal)": (ts <= 48, g1 & (tsm <= 48)),
        "F_tsf_gt48 (> 12 h desde la 1.ª señal)": (ts > 48, g1 & (tsm > 48)),
        "F_nprev0 (1.ª señal propia del episodio)": (npv == 0, g1),
        "F_nprev1 (señales propias previas ≥ 1)": (npv >= 1, g1),
        "G_exc (suma de excesos ≥ mediana val.)": (exc >= exc_thr, g1 & (exc >= exc_thr)),
        "G_BE (co-señal de BTC o ETH)": (A_BE >= 1, A_BE >= 1),
        "G_prev (co-señal estrictamente anterior)": (A_prev >= 1, A_prev >= 1),
        "G_p25 (p ≥ q25 val. con compuerta)": (D["p"] >= p25, g1),
        "G_p50 (p ≥ q50 val. con compuerta)": (D["p"] >= p50, g1),
    }
    feats = dict(rank=rank, tsf=tsf, nprev=nprev, exc=exc, A_BE=A_BE, A_prev=A_prev)
    return R, feats, vq


def run(ens):
    D = E.load(ens)
    ref = E.trade_table(D, D["stack"], D["A"] >= 1)
    rref = E.summ(ref, "pila v2 + A≥1")
    R, feats, vq = rules(D)
    res = {"pila": dict(summary=rref)}
    for lab, (cond, gate) in R.items():
        t = E.trade_table(D, D["stack"] & cond, gate)
        r = E.summ(t, lab)
        c = E.compare(t, ref) if t is not None else None
        res[lab] = dict(summary=r, compare=c)
        if r.get("n"):
            print(ens, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}", f"cond {r['cond_wr']*100:.1f}/{r['cond_E']:+.2f}",
                  f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f} folds {c['folds_imp']}", flush=True)
    # descriptivo de las operaciones de la pila por rank / tsf / nprev
    desc = {}
    rank, tsf, nprev = feats["rank"], feats["tsf"], feats["nprev"]
    x = ref["x"]
    fr = rank[ref["sidx"], ref["sig_idx"]]; ft = tsf[ref["sidx"], ref["sig_idx"]]; fn = nprev[ref["sidx"], ref["sig_idx"]]
    for nm, arr, cuts in (("rank", fr, [(1, 1), (2, 2), (3, 3), (4, 4)]),
                          ("tsf (velas)", ft, [(0, 0), (1, 16), (17, 48), (49, 96), (97, 10 ** 9)]),
                          ("nprev", fn, [(0, 0), (1, 3), (4, 10), (11, 10 ** 9)])):
        for lo, hi in cuts:
            s = (arr >= lo) & (arr <= hi)
            if s.any():
                desc[f"{nm} {lo}-{hi}"] = (int(s.sum()), float(np.mean(x[s] > 0)), float(x[s].mean() * 100))
    res["desc"] = desc
    res["val_q"] = vq
    return res


if __name__ == "__main__":
    ens_list = sys.argv[1:] or ["ENS13", "ENS12", "ENS12U"]
    res = {ens: run(ens) for ens in ens_list}
    E.log_once("gatevar", 12, "R2-E2/E3 orden en el episodio (rank, tsf, nprev; 7 cortes) y variantes de compuerta (exc, BE, prev, p25, p50)")
    tag = "_".join(ens_list)
    E.jdump(res, os.path.join(E.OUT2, f"be2_gatevar_{tag}.json"))
    L = [f"# R2-E2/E3 orden dentro del episodio y variantes de compuerta ({', '.join(ens_list)})\n", E.HEAD, E.HEAD2]
    labs = [k for k in res[ens_list[0]] if k not in ("desc", "val_q")]
    for lab in labs:
        for ens in ens_list:
            o = res[ens][lab]
            L.append(E.row(ens, o["summary"], o.get("compare")))
    L.append("\nCandidatas (criterio: ΔWR ≥ +1 pt y ΔE ≥ 0 en ENS13, ≥ 4/6 pliegues, P(ΔWR≤0) ≤ 0.20, réplica en ≥ 2/3):\n")
    for lab in labs:
        if lab == "pila":
            continue
        ok, why = E.candidate({ens: res[ens][lab]["compare"] for ens in ens_list if res[ens][lab].get("compare")})
        L.append(f"- {lab}: {'CANDIDATA' if ok else 'no'} — {why}")
    L.append("\nDetalle por pliegue y moneda:\n")
    for lab in labs:
        for ens in ens_list:
            L.append(E.detail(ens, res[ens][lab]["summary"], res[ens][lab].get("compare")))
    L.append("\nDescriptivo de las operaciones de la pila (n, WR, E %):\n")
    for ens in ens_list:
        L.append(f"- {ens}: " + "; ".join(f"{k}: {n}·{w*100:.0f}%·{e:+.2f}" for k, (n, w, e) in res[ens]["desc"].items()))
    with open(os.path.join(E.OUT2, f"be2_gatevar_{tag}.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
