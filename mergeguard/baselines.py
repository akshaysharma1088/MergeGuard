"""Baseline matchers for MergeBench.

Valentine's classic matchers run here. Magneto (BDI-Kit) and Schemora need model downloads or
an LLM API; ``bdikit_predictions`` is written for running Magneto on your own machine.
Every baseline returns ``Match`` objects with no conflict flags: they only propose a target, so any
accepted mapping is treated as an exact match, as a name- or similarity-driven pipeline would.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy.optimize import linear_sum_assignment

from .cards import Side
from .match import Match


def _frame(side: Side, table: str, n: int = 1000):
    df = side.con.execute(f"SELECT * FROM {table} USING SAMPLE {n} ROWS (reservoir, 42)").df()
    for c in df.columns:
        if str(df[c].dtype).startswith(("datetime", "object")) or df[c].dtype == "bool":
            df[c] = df[c].astype(str)
    return df


def _assign(scores: dict, src: Side, tgt: Side, label: str) -> list[Match]:
    S = [c.qname for c in src.cards]
    T = [c.qname for c in tgt.cards]
    M = np.zeros((len(S), len(T)))
    for (s, t), v in scores.items():
        M[S.index(s), T.index(t)] = v
    rows, cols = linear_sum_assignment(-M)
    pick = {r: c for r, c in zip(rows, cols) if M[r, c] > 0}
    out = []
    for i, s in enumerate(S):
        j = pick.get(i)
        if j is None:
            out.append(Match(s, None, 0.0, "unmatched", [], {label: 0.0}, "", []))
        else:
            out.append(Match(s, T[j], float(M[i, j]), "exact", [], {label: float(M[i, j])}, "", []))
    return out


def valentine_matcher(name: str):
    from valentine.algorithms import Coma, Cupid, DistributionBased, JaccardDistanceMatcher, SimilarityFlooding
    return {"coma": lambda: Coma(use_instances=True), "cupid": Cupid, "similarity_flooding": SimilarityFlooding,
            "distribution_based": DistributionBased, "jaccard_distance": JaccardDistanceMatcher}[name]()


def valentine_predictions(src: Side, tgt: Side, method: str) -> list[Match]:
    from valentine import valentine_match
    scores: dict = {}
    for st in src.schema:
        a = _frame(src, st)
        for tt in tgt.schema:
            b = _frame(tgt, tt)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = valentine_match([a, b], valentine_matcher(method), df_names=["s", "t"])
            for pair, v in dict(res).items():
                lc, rc = pair.source_column, pair.target_column
                if pair.source_table == "t":  # normalize orientation
                    lc, rc = rc, lc
                key = (f"{st}.{lc}", f"{tt}.{rc}")
                scores[key] = max(scores.get(key, 0.0), float(v))
    return _assign(scores, src, tgt, method)


def bdikit_predictions(src: Side, tgt: Side, method: str = "magneto_zs_bp") -> list[Match]:
    """Magneto via BDI-Kit. Needs `pip install bdi-kit` and Hugging Face access (run locally)."""
    import bdikit as bdi
    scores: dict = {}
    for st in src.schema:
        a = _frame(src, st)
        for tt in tgt.schema:
            b = _frame(tgt, tt)
            res = bdi.match_schema(a, target=b, method=method)
            for _, r in res.iterrows():
                key = (f"{st}.{r['source']}", f"{tt}.{r['target']}")
                scores[key] = max(scores.get(key, 0.0), float(r.get("similarity", 1.0)))
    return _assign(scores, src, tgt, method)


# distribution_based is left out: its PuLP 4 / CBC solver fails in this sandbox (run it locally)
VALENTINE_METHODS = ["coma", "cupid", "similarity_flooding", "jaccard_distance"]
