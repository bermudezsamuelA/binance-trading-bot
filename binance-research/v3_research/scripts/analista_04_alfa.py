"""Ronda 1 - Paso 4: alfa bruto de las señales a horizonte fijo (sin TP/SL).
Argumento: si el precio fuera una martingala, cualquier regla de salida (TP/SL/tiempo) tiene E[bruto] = 0
(teorema de parada opcional). La geometría solo reparte el resultado entre acierto (p) y tamaño (b).
Por eso la cota útil es: E_neto <= max_h E[ret_h | señal] - c. Aquí se mide E[ret_h | señal] frente a
E[ret_h] incondicional (deriva) en DISEÑO-A y DISEÑO-B, con selección no solapada (una señal cada h velas)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac
import analista_features as af

HS = [4, 16, 48, 96, 192]


def nonoverlap(idx, h):
    out = []
    last = -10 ** 9
    for i in idx:
        if i >= last + h:
            out.append(i)
            last = i
    return np.array(out, dtype=np.int64)


def fwd_stats(c, idx, h):
    idx = idx[idx + h < len(c)]
    sel = nonoverlap(idx, h)
    r = c[sel + h] / c[sel] - 1
    if len(r) < 5:
        return np.nan, np.nan, len(r)
    return r.mean() * 100, r.mean() / (r.std(ddof=1) / np.sqrt(len(r))), len(r)


def main():
    lines = []
    P = lambda s: (print(s), lines.append(s))
    data = {s: ac.load(s) for s in ac.SYMS}
    Fs = {s: af.build(data[s], 20) for s in ac.SYMS}
    Fs = af.add_cross(Fs, ac.SYMS)
    P("Retorno futuro BRUTO medio (%) a h velas tras la señal, no solapado; entre paréntesis t y N. c = 0.24 %.")
    P("h: 4=1h, 16=4h, 48=12h, 96=24h, 192=48h\n")
    n_cfg = 0
    for part in ("A", "B"):
        P(f"=================== DISEÑO-{part} ===================")
        for s in ac.SYMS:
            d = data[s]
            c = d["c"]
            inpart = (d["t"] < ac.SPLIT_AB_MS) if part == "A" else (d["t"] >= ac.SPLIT_AB_MS)
            allidx = np.where(inpart)[0][900:]
            row = []
            for h in HS:
                m, t, n = fwd_stats(c, allidx, h)
                row.append(f"{m:+.3f}")
            P(f"{s} incondicional: " + " ".join(row))
            for n_w in (20, 96, 384):
                mu, sd = ac.roll_mean_std(c, n_w)
                z = (c - mu) / sd
                for k in (2.0, 2.5, 3.0):
                    with np.errstate(invalid="ignore"):
                        idx = np.where(inpart & (z < -k))[0]
                    row = []
                    for h in HS:
                        m, t, n = fwd_stats(c, idx, h)
                        row.append(f"{m:+.3f}({t:+.1f},{n})")
                    n_cfg += 1
                    P(f"   z{n_w}<-{k}: " + " ".join(row))
            # señal estándar + filtros que replicaron en el cribado (paso 3)
            F = Fs[s]
            base = (F["z"] < -2) & (F["R_pct"] >= 0.005)
            filt = {
                "MR20 base": base,
                "+slope_sma800>0": base & (F["slope_sma800"] > 0),
                "+ret_7d>0": base & (F["ret_7d"] > 0),
                "+sig96>med": base & (F["sig96"] > np.nanmedian(F["sig96"][:40000])),
                "+VR16 en [0.9,1.2]": base & (F["VR16"] > 0.9) & (F["VR16"] < 1.2),
                "+slope>0 y sig96>med": base & (F["slope_sma800"] > 0) & (F["sig96"] > np.nanmedian(F["sig96"][:40000])),
            }
            for name, mk in filt.items():
                with np.errstate(invalid="ignore"):
                    idx = np.where(inpart & mk)[0]
                row = []
                for h in HS:
                    m, t, n = fwd_stats(c, idx, h)
                    row.append(f"{m:+.3f}({t:+.1f},{n})")
                n_cfg += 1
                P(f"   {name:22s}: " + " ".join(row))
    P(f"\nConfiguraciones (señal x moneda x parte) en este script: {n_cfg}")
    with open(os.path.join(ac.OUTDIR, "04_alfa.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
