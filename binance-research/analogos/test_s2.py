import unittest

import numpy as np

import s2_dtw as S2


def dtw_ref(a, b, R):
    L = len(a); D = np.full((L + 1, L + 1), np.inf); D[0, 0] = 0
    for i in range(1, L + 1):
        for j in range(max(1, i - R), min(L, i + R) + 1):
            D[i, j] = (a[i - 1] - b[j - 1]) ** 2 + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return np.sqrt(D[L, L])


class DtwTest(unittest.TestCase):
    def test_matches_reference(self):
        r = np.random.default_rng(0)
        A = r.normal(size=(3, 20)).astype(np.float32); B = r.normal(size=(3, 4, 20)).astype(np.float32)
        d, _ = S2.dtw_batch(A, B, 4)
        for x in range(3):
            for y in range(4):
                self.assertAlmostEqual(float(d[x, y]), dtw_ref(A[x], B[x, y], 4), places=3)

    def test_identity_and_bound(self):
        r = np.random.default_rng(1)
        A = r.normal(size=(2, 16)).astype(np.float32)
        d, _ = S2.dtw_batch(A, A[:, None, :], 3)
        self.assertTrue(np.allclose(d, 0))
        B = r.normal(size=(2, 1, 16)).astype(np.float32)
        d, _ = S2.dtw_batch(A, B, 3)
        self.assertTrue((d[:, 0] <= np.sqrt(((A - B[:, 0]) ** 2).sum(1)) + 1e-5).all())   # DTW <= euclidiana

    def test_speed_of_stretched_pattern(self):
        L = 40
        u = np.linspace(0, 1, L)
        f = lambda x: np.sin(6 * x) + x
        a = f(u); b_fast = f(np.minimum(1, u * 1.0))
        _, dirs = S2.dtw_batch(a[None].astype(np.float32), b_fast[None, None].astype(np.float32), 8, want_dirs=True)
        self.assertAlmostEqual(float(S2.path_speed(dirs)[0, 0]), 1.0, places=1)


if __name__ == "__main__":
    unittest.main()
