"""Corre las 5 sugerencias en orden y deja los resúmenes en output/. Uso: python run_all.py [s1 s2 ...]"""
import sys
import time

import s1_knn, s2_dtw, s3_estado, s4_palabras, s5_multi

STEPS = {"s1": lambda: s1_knn.main([]), "s2": lambda: s2_dtw.main([]), "s3": lambda: s3_estado.main([]),
         "s4": s4_palabras.main, "s5": s5_multi.main}

if __name__ == "__main__":
    for name in (sys.argv[1:] or list(STEPS)):
        t0 = time.time()
        STEPS[name]()
        print(f"[RUN] {name} listo en {time.time() - t0:.0f} s", flush=True)
