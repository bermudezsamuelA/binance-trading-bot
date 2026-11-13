"""R2B prueba formal de las fuentes nuevas del Investigador A (DISENO). Pre-registro (escrito antes de correr; corte y signo
FIJADOS por el Investigador A, que ya miro las 131 operaciones de ENS13: ver el registro 'bleeding_edge_r2_A_peek'):

Variable: z30 = (DVOL_h - media de las ultimas 720 horas cerradas) / desviacion (ddof 0), con la ultima hora cuya marca
ts + 1 h <= apertura de la vela de senal. Datos: E:/tmp/r2_data/deribit/dvol_{BTC,ETH}_1h.json (solo lectura, JSON).
D1 (principal, regla de EPISODIO): no comprar si z30(DVOL BTC) < -1.
D1-ETH: igual, pero las operaciones de ETH usan el z30 del DVOL de ETH.
D2: no comprar si z30(BTC) < cuantil 1/3 de z30(BTC) horario calculado SOLO con las horas desde 2023-01-31 hasta el inicio
    de la prueba del pliegue (entrenamiento + validacion; distribucion incondicional, sin resultados).
C1: no comprar si z30 de usdt_dev < -1, con usdt_dev = cierre de USDT-USD en Coinbase - 1 (media de 1 h = 4 velas) y
    z30 = (x - mediana de 30 d) / desviacion de 30 d (2880 velas), velas de Coinbase cerradas antes de la apertura.
    Solo si el historial completo esta en E:/tmp/r2_data/coinbase_full/.
B1 (dos colas, Holm): cambio de 4 h del margen long de BTC en Bitfinex (ultimo minuto cerrado antes de la apertura
    frente a 4 h antes). B1-bajo: no comprar si esta en el tercil bajo; B1-alto: no comprar si esta en el tercil alto.
    Cortes: terciles de la serie disponible (ventanas; sin resultados). Solo si las ventanas cubren las 131 operaciones.
Bases: pila X5 y pila v3 (H 384). Ensambles: ENS13 (CONTAMINADO), ENS12, ENS12U y ENS6 (miembros v1; salida X5, regla
v2): estos tres dan operaciones distintas que el Investigador A no miro. Segunda muestra: senales aisladas (A = 0).
Comparadores: azar condicionado (A >= 1 y la condicion de la regla); quitar al azar el mismo numero de operaciones (1000
sorteos); complemento (entradas solo en velas vetadas). Controles: terciles de s_d del modelo y p del modelo en vetadas.
Bootstrap por episodio, IC beta-binomial, consistencia por pliegue, episodios de las vetadas.
Tamiz por ensamble (fijado aqui): dWR >= +1 pt, dE >= 0, P_ep(dWR <= 0) <= 0.20, entre los pliegues que cambian
>= 2/3 mejoran (dWR > 0 y dE >= 0), y el azar condicionado explica <= 1/2 de dWR (es regla de seleccion).
Combinacion final (unica): pila v3 (H 384) + D1 si D1 pasa el tamiz con base H 384 en >= 2 de ENS12, ENS12U y ENS6.
Holm sobre las reglas de esta parte (D1, D1-ETH, D2, C1, B1-bajo, B1-alto) con p = P_ep(dWR <= 0).
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be2_common as E
import be2b_common as K
B, H, C, R = E.B, E.H, E.C, E.R

E.ENSEMBLES["ENS6"] = (B.ENS6, None)
_mk = os.path.join(K.OUT2, ".trials", "A_peek.done")
if not os.path.exists(_mk):
    H.log_trials("bleeding_edge_r2_A_peek", 30, "chequeo descriptivo de fuentes nuevas, investigador A")
    os.makedirs(os.path.dirname(_mk), exist_ok=True); open(_mk, "w").write("30\n")
E.log_once("r2b_dvol", 13, "R2B D1 DVOL z30<-1, D1-ETH, D2 tercil train+val, C1 USDT-USD Coinbase z30<-1, B1 Bitfinex 2 colas; x2 bases (X5, H384); + combinacion v3+D1")

DVOL = r"E:/tmp/r2_data/deribit"
CB = r"E:/tmp/r2_data/coinbase_full/USDT-USD_15m.json"
BFX = r"E:/tmp/r2_data/bitfinex/pos_long_1m_win.json"


def dvol_series(cur):
    d = np.array(json.load(open(os.path.join(DVOL, f"dvol_{cur}_1h.json"))), float)
    ct = d[:, 0].astype(np.int64) + 3_600_000
    dv = d[:, 4]
    n = len(dv)
    z = np.full(n, np.nan)
    cs, cs2 = np.cumsum(np.r_[0, dv]), np.cumsum(np.r_[0, dv * dv])
    for i in range(719, n):
        m = (cs[i + 1] - cs[i - 719]) / 720
        v = (cs2[i + 1] - cs2[i - 719]) / 720 - m * m
        z[i] = (dv[i] - m) / (np.sqrt(max(v, 0)) + 1e-9)
    return ct, z


def at_open(ct, z, t_open):
    i = np.searchsorted(ct, t_open, side="right") - 1
    return np.where(i >= 0, z[np.maximum(i, 0)], np.nan)


def usdt_z(t_open):
    if not os.path.exists(CB):
        return None
    d = np.array(json.load(open(CB)), float)  # [t_s, low, high, open, close, vol]
    d = d[np.argsort(d[:, 0])]
    t = (d[:, 0] * 1000).astype(np.int64); c = d[:, 4]
    # rejilla regular de 15 min
    g0 = t[0]; idx = ((t - g0) // 900_000).astype(int)
    N = idx[-1] + 1
    x = np.full(N, np.nan); x[idx] = (c - 1) * 1e4
    # relleno hacia adelante de huecos cortos
    for k in range(1, N):
        if np.isnan(x[k]):
            x[k] = x[k - 1]
    x1 = np.convolve(x, np.ones(4) / 4, mode="full")[:N]; x1[:3] = np.nan
    import pandas as pd
    s = pd.Series(x1)
    med = s.rolling(2880, min_periods=2000).median().to_numpy()
    sd = s.rolling(2880, min_periods=2000).std().to_numpy()
    z = (x1 - med) / (sd + 1e-9)
    tg = g0 + np.arange(N) * 900_000
    close_t = tg + 900_000
    return at_open(close_t, z, t_open), int(N), float(np.mean(np.isfinite(z)))


def bfx_d4h(t_open):
    if not os.path.exists(BFX):
        return None
    d = np.array(json.load(open(BFX)), float)
    d = d[np.argsort(d[:, 0])]
    t = d[:, 0].astype(np.int64); v = d[:, 1]

    def val(tt):
        i = np.searchsorted(t, tt - 60_000, side="right") - 1  # minuto cerrado antes de tt
        ok = (i >= 0) & (np.abs(t[np.maximum(i, 0)] - (tt - 60_000)) <= 5 * 60_000)
        return np.where(ok, v[np.maximum(i, 0)], np.nan)
    now, past = val(t_open), val(t_open - 4 * 3_600_000)
    dd = (now / past - 1) * 100
    # cortes: terciles de la serie disponible (cada 15 min en las ventanas)
    grid = t[::15]
    allv = (val(grid) / val(grid - 4 * 3_600_000) - 1) * 100
    allv = allv[np.isfinite(allv)]
    return dd, (float(np.quantile(allv, 1 / 3)), float(np.quantile(allv, 2 / 3)))


def fold_info(D, base_tab, keep):
    rowg = E.to_grid(D, np.arange(len(D["rows"])), -1, int)
    rr = rowg[base_tab["sidx"], base_tab["sig_idx"]]
    vet = ~keep[rr]
    x = base_tab["x"]
    out = []
    for f in range(6):
        s = base_tab["fold"] == f
        if (s & vet).any() and (s & ~vet).any():
            out.append((f, int((s & vet).sum()), float(np.mean(x[s & ~vet] > 0) - np.mean(x[s & vet] > 0))))
    # volatilidad del modelo (s_d) y p del modelo
    sd = np.array([D["cache"][H.SYMBOLS[i]]["s15"][b] * np.sqrt(96) for i, b in zip(base_tab["sidx"], base_tab["sig_idx"])])
    q = np.nanquantile(sd, [1 / 3, 2 / 3])
    vol = []
    for lo, hi, nm in ((-np.inf, q[0], "s_d baja"), (q[0], q[1], "s_d media"), (q[1], np.inf, "s_d alta")):
        s = (sd >= lo) & (sd < hi)
        a, b = s & ~vet, s & vet
        vol.append((nm, int(a.sum()), float(np.mean(x[a] > 0)) if a.any() else np.nan, float(x[a].mean() * 100) if a.any() else np.nan,
                    int(b.sum()), float(np.mean(x[b] > 0)) if b.any() else np.nan, float(x[b].mean() * 100) if b.any() else np.nan))
    pm = D["p"][rr] - D["thr"][rr]
    days = sorted(set(str(np.datetime64(int(t), "ms").astype("datetime64[D]")) for t in base_tab["et"][vet]))
    return dict(folds=out, vol=vol, n_vet=int(vet.sum()), wr_vet=float(np.mean(x[vet] > 0)) if vet.any() else np.nan,
                E_vet=float(x[vet].mean() * 100) if vet.any() else np.nan, wr_keep=float(np.mean(x[~vet] > 0)),
                p_vet=float(np.nanmean(pm[vet])) if vet.any() else np.nan, p_keep=float(np.nanmean(pm[~vet])), days=days, vet_mask=vet)


def rand_removal(base_tab, k, nd=1000, seed=11):
    rng = np.random.default_rng(seed)
    x = base_tab["x"]; n = len(x)
    wr, e = [], []
    for _ in range(nd):
        keep = np.ones(n, bool); keep[rng.choice(n, size=k, replace=False)] = False
        wr.append(np.mean(x[keep] > 0)); e.append(x[keep].mean() * 100)
    return np.array(wr), np.array(e)


def screen(r, rb, c):
    if not r.get("n") or not np.isfinite(c.get("dWR", np.nan)):
        return False, {}
    ch = [(dw, de) for dw, de in c["folds"] if np.isfinite(dw) and not (dw == 0 and abs(de) < 1e-12)]
    imp = sum(1 for dw, de in ch if dw > 0 and de >= 0)
    frac = (r["cond_wr"] - rb["cond_wr"]) / c["dWR"] if c["dWR"] > 0 and "cond_wr" in r and "cond_wr" in rb else np.nan
    ok = (c["dWR"] >= 0.01 and c["dE"] >= 0 and c["p_dWR_le0"] <= 0.20 and len(ch) > 0 and imp >= 2 / 3 * len(ch)
          and (not np.isfinite(frac) or frac <= 0.5))
    return bool(ok), dict(folds_changed=len(ch), folds_improved=imp, frac_cond=float(frac) if np.isfinite(frac) else None)


def run(ens, zfun):
    D = E.load(ens)
    g1 = D["A"] >= 1
    zb, ze, cut2, uz, bfx = zfun(D)
    keeps = {"D1 z30(BTC) ≥ −1": ~(zb < -1)}
    z_eth = np.where(D["ci"] == 1, ze, zb)
    keeps["D1-ETH (ETH usa su DVOL)"] = ~(z_eth < -1)
    keeps["D2 z30 ≥ tercil de train+val"] = ~(zb < cut2[D["fold"]])
    if uz is not None:
        keeps["C1 z30(USDT-USD) ≥ −1"] = ~(uz < -1)
    if bfx is not None:
        dd, (q1, q2) = bfx
        keeps["B1-bajo: longs Bitfinex 4 h no en tercil bajo"] = ~(dd <= q1)
        keeps["B1-alto: longs Bitfinex 4 h no en tercil alto"] = ~(dd >= q2)
    res = {}
    bases = K.bases(D)
    for bname, (Dx, ref) in bases.items():
        rb = E.summ(ref, f"pila {bname}")
        res[f"pila {bname}"] = dict(summary=rb, bb=K.betabin_ci(ref), base=bname)
        iso_ref = E.trade_table(Dx, D["sig"] & (D["A"] == 0), D["A"] == 0)
        res[f"aisladas {bname}"] = dict(summary=E.summ(iso_ref, f"aisladas A=0 {bname}"), base=bname)
        for lab, keep in keeps.items():
            t = E.trade_table(Dx, D["stack"] & keep, g1 & keep)
            r = E.summ(t, lab); c = K.compare_ep(t, ref)
            fi = fold_info(D, ref, keep)
            wr_r, e_r = rand_removal(ref, fi["n_vet"]) if fi["n_vet"] > 0 else (np.array([np.nan]), np.array([np.nan]))
            comp = E.trade_table(Dx, D["stack"] & ~keep, g1 & ~keep)
            ti = E.trade_table(Dx, D["sig"] & (D["A"] == 0) & keep, (D["A"] == 0) & keep)
            ri = E.summ(ti, lab + " (aisladas)"); ci_ = K.compare_ep(ti, iso_ref)
            ok, sc = screen(r, rb, c)
            res[f"{lab} [{bname}]"] = dict(
                summary=r, compare=c, bb=K.betabin_ci(t), base=bname, screen=ok, screen_info=sc,
                complement=E.summ(comp, "complemento"), iso=ri, iso_cmp=ci_,
                rand_removal=dict(wr_mean=float(np.nanmean(wr_r)), E_mean=float(np.nanmean(e_r)),
                                  pct_wr=float(np.mean(wr_r < r["wr"])) if r.get("n") else None,
                                  pct_E=float(np.mean(e_r < r["E_pct"])) if r.get("n") else None),
                fold_info={k: v for k, v in fi.items() if k != "vet_mask"})
            print(ens, bname, lab, r["n"], f"{r['wr']*100:.1f}", f"{r['E_pct']:+.2f}",
                  f"dWR {c['dWR']*100:+.1f} dE {c['dE']:+.2f} P {c['p_dWR_le0']:.2f}/{c['p_dE_le0']:.2f}",
                  f"vetadas {fi['n_vet']} WR {fi['wr_vet']*100 if fi['n_vet'] else float('nan'):.0f}% E {fi['E_vet']:+.2f}",
                  f"| aisladas dWR {ci_.get('dWR', np.nan)*100:+.1f} dE {ci_.get('dE', np.nan):+.2f}", "| tamiz", ok, sc, flush=True)
    return res


def make_zfun():
    ctb, zbh = dvol_series("BTC")
    cte, zeh = dvol_series("ETH")
    cuts = []
    for k in range(6):
        t0 = H.ms(*B.TESTS[k][0], 1)
        s = (ctb <= t0) & np.isfinite(zbh)
        cuts.append(float(np.quantile(zbh[s], 1 / 3)))
    cuts = np.array(cuts)
    cache = {}

    def zfun(D):
        zb = at_open(ctb, zbh, D["t"]); ze = at_open(cte, zeh, D["t"])
        if "uz" not in cache:
            u = usdt_z(D["t"])
            cache["uz"] = u
            b = bfx_d4h(D["t"])
            cache["bfx"] = b
        u = cache["uz"]; b = cache["bfx"]
        uz = u[0] if u is not None else None
        bf = None
        if b is not None:
            dd = b[0]
            # cobertura: velas de la pila con dato
            cov = float(np.mean(np.isfinite(dd[D["stack"]])))
            cache.setdefault("bfx_cov", {})[D.get("name")] = cov
            if cov >= 0.99:
                bf = b
        return zb, ze, cuts, uz, bf
    return zfun, cuts, cache


if __name__ == "__main__":
    zfun, cuts, cache = make_zfun()
    ens_list = ["ENS13", "ENS12", "ENS12U", "ENS6"]
    res = {e: run(e, zfun) for e in ens_list}
    info = dict(cuts_D2=cuts.tolist(), bfx_cov=cache.get("bfx_cov"),
                usdt=None if cache.get("uz") is None else dict(n=cache["uz"][1], frac_finite=cache["uz"][2]),
                bfx_cuts=None if cache.get("bfx") is None else cache["bfx"][1])
    res["_info"] = info
    print("info", info)
    E.jdump(res, os.path.join(K.OUT2, "be2c_dvol.json"))
