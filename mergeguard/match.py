"""Evidence-based attribute matching with false-friend detection.

Every source x target pair is scored on six signals. Names get the least weight; value and
logic evidence decide. Conflict detectors then explain what differs, and the definition
disagreement rate (DDR) measures how many entities a definition conflict would flip.
"""
from __future__ import annotations

import difflib
import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.stats import ks_2samp

from .cards import Card, Side

WEIGHTS = {"name": 0.10, "definition": 0.15, "type": 0.10, "value": 0.25, "logic": 0.25, "context": 0.15}
MEANING_CONFLICTS = {"population", "grain", "null_semantics", "inclusion", "temporal", "definition"}
TRANSFORM_FLAGS = {"unit", "scale", "sign", "code_set", "cast", "format"}
ACCEPT_THRESHOLD = 0.50
FACTORS = (1.0, 100.0, 0.01, 1000.0, 0.001, 12.0, 1 / 12)
AUTO_ACCEPT = 0.90
DDR_THRESHOLD = 0.01   # a yes/no definition that flips more than 1% of entities needs review


# ---------------------------------------------------------------- signals
def _is_subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(ch in it for ch in short)


def tok_match(x: str, y: str) -> float:
    """1 for equal tokens, 0.8 when one abbreviates the other (crd/card, lmt/limit), 0.7 for containment."""
    if x == y:
        return 1.0
    short, long_ = sorted((x, y), key=len)
    if len(short) >= 2 and short[0] == long_[0] and len(short) < len(long_) and _is_subsequence(short, long_):
        return 0.8
    if len(short) >= 4 and short in long_:
        return 0.7
    return 0.0


def soft_sim(ta: list, tb: list) -> float:
    if not ta or not tb:
        return 0.0
    fa = sum(max(tok_match(x, y) for y in tb) for x in ta)
    fb = sum(max(tok_match(y, x) for x in ta) for y in tb)
    return (fa + fb) / (len(ta) + len(tb))


def coverage(name: list, text: list) -> float:
    """Share of a column name's tokens that a description spells out."""
    if not name or not text:
        return 0.0
    return sum(max(tok_match(x, y) for y in text) for x in name) / len(name)


def acronym_hit(name: list, text: list) -> bool:
    """A short name token spelled by the initials of consecutive description words."""
    initials = "".join(t[0] for t in text if t)
    return any(2 <= len(x) <= 5 and x.isalpha() and x in initials and x not in text for x in name)


def name_sim(a: Card, b: Card) -> float:
    seq = difflib.SequenceMatcher(None, " ".join(a.name_tokens), " ".join(b.name_tokens)).ratio()
    return max(soft_sim(a.name_tokens, b.name_tokens), seq * 0.9)


def definition_sim(a: Card, b: Card) -> float:
    ca, cb = Counter(a.desc_tokens), Counter(b.desc_tokens)
    dot = sum(ca[t] * cb[t] for t in ca)
    na, nb = math.sqrt(sum(v * v for v in ca.values())), math.sqrt(sum(v * v for v in cb.values()))
    cos = dot / (na * nb) if na and nb else 0.0
    cross = max(coverage(b.name_tokens, a.desc_tokens), coverage(a.name_tokens, b.desc_tokens)) * 0.9
    acro = 0.85 if (acronym_hit(a.name_tokens, b.desc_tokens) or acronym_hit(b.name_tokens, a.desc_tokens)) else 0.0
    return max(cos, soft_sim(a.desc_tokens, b.desc_tokens), cross, acro)


def _kind(c: Card) -> str:
    return c.profile.get("kind", c.family)


def type_sim(a: Card, b: Card) -> float:
    fa, fb = a.family, b.family
    if _kind(a) == "bool" and _kind(b) == "bool":
        return 1.0
    if fa == fb:
        return 1.0
    pair = {fa, fb}
    if pair == {"int", "decimal"} or pair == {"date", "timestamp"}:
        return 0.8
    if "string" in pair and pair & {"int", "decimal"}:
        return 0.3
    return 0.1


def _ks(x: np.ndarray, y: np.ndarray, cap: int = 5000) -> float:
    if len(x) == 0 or len(y) == 0:
        return 0.0
    rng = np.random.default_rng(0)
    x = rng.choice(x, min(cap, len(x)), replace=False)
    y = rng.choice(y, min(cap, len(y)), replace=False)
    return 1.0 - ks_2samp(x, y).statistic


def value_sim(a: Card, b: Card) -> tuple[float, dict]:
    """Similarity of value profiles plus what transform makes them line up."""
    pa, pb = a.profile, b.profile
    ka, kb = _kind(a), _kind(b)
    info: dict = {}
    if a.is_identifier or b.is_identifier:
        if a.is_identifier and b.is_identifier:
            return 1 - abs(pa["uniq_ratio"] - pb["uniq_ratio"]), info
        return 0.2, info
    da, db = pa.get("digits"), pb.get("digits")
    if da and db and "string" in (a.family, b.family):
        len_sim = max(0.0, 1 - abs(da["length"] - db["length"]) / max(da["length"], db["length"]))
        sim = 0.7 * _ks(da["values"], db["values"]) + 0.3 * len_sim
        if da["shape"] != db["shape"] or a.family != b.family:
            info["format"] = {"source_shape": da["shape"], "target_shape": db["shape"]}
        return sim, info
    if ka == "numeric" and kb == "numeric":
        cands = []
        for f in FACTORS:
            for absolute in (False, True):
                x = pa["values"] * f
                x = np.abs(x) if absolute else x
                cands.append((_ks(x, pb["values"]), f, absolute))
        plain = max(c for c in cands if c[1] == 1.0)
        best = max(cands)
        sim, factor, absolute = best if best[0] >= plain[0] + 0.15 else plain
        info.update(factor=factor, absolute=absolute)
        off = _offset(pa, pb) if factor == 1.0 else None
        if off:
            info["offset"] = off
        x = pa["values"] * factor
        x = np.abs(x) if absolute else x
        y = pb["values"]
        if len(x) > 20 and len(y) > 20 and (x >= 0).all() and (y >= 0).all() and not off:
            zx, zy = (x == 0).mean(), (y == 0).mean()
            if abs(zx - zy) > 0.03 and min(zx, zy) > 0.05:      # refunds or write-downs zero some amounts
                info["netting"] = round(zx - zy, 3)
            # values the other side's discrete schedule never produces (half refunds, partial waivers)
            if pb["distinct"] <= 30 and pa["distinct"] > pb["distinct"]:
                sched = set(np.round(y, 2))
                outside = float(np.mean([v not in sched for v in np.round(x[x > 0], 2)])) if (x > 0).any() else 0.0
                if outside > 0.02:
                    info["netting"] = round(outside, 3)
        if pa["null_rate"] - pb["null_rate"] > 0.2 and "values_fill0" in pa:
            s0 = _ks(pa["values_fill0"] * factor, pb["values"])
            if s0 > sim + 0.15:
                info["null_as_zero"] = True
                sim = s0
        return sim, info
    if ka == "date" and kb == "date":
        wk = abs(pa["weekend_share"] - pb["weekend_share"])
        lo, hi = max(pa["min"], pb["min"]), min(pa["max"], pb["max"])
        span = max((max(pa["max"], pb["max"]) - min(pa["min"], pb["min"])).days, 1)
        overlap = max((hi - lo).days, 0) / span
        info["weekend_gap"] = wk
        oa, ob = pa.get("ordinals"), pb.get("ordinals")
        if oa is not None and ob is not None and len(oa) > 20 and len(ob) > 20:
            shift = float(np.median(oa) - np.median(ob))
            if abs(shift) > 180 and _ks(oa, ob) < 0.75:
                info["date_shift_days"] = int(shift)
        return 0.5 * max(0.0, 1 - wk * 3) + 0.5 * overlap, info
    if ka == "bool" and kb == "bool":
        ra, rb = pa["true_rate"], pb["true_rate"]
        if _rates_differ(ra, rb):
            info["rate_ratio"] = round(max(ra, rb) / max(min(ra, rb), 0.005), 1)
        return max(0.0, 1 - abs(ra - rb) * 2), info
    if {ka, kb} == {"bool", "categorical"}:
        cat, bo = (pa, pb) if ka == "categorical" else (pb, pa)
        if len(cat["freqs"]) == 2:
            share = max(cat["freqs"].values())
            info["two_value_code"] = True
            minority = min(cat["freqs"].values())
            if _rates_differ(minority, bo["true_rate"]) and _rates_differ(1 - minority, bo["true_rate"]):
                info["rate_ratio"] = round(max(minority, bo["true_rate"]) / max(min(minority, bo["true_rate"]), 0.005), 1)
            return max(0.0, 1 - min(abs(share - bo["true_rate"]), abs(1 - share - bo["true_rate"])) * 2) * 0.9, info
    int_code = {ka, kb} == {"numeric", "categorical"} and pa.get("freqs") and pb.get("freqs")
    if (ka == "categorical" and kb == "categorical") or int_code:
        fa, fb = pa["freqs"], pb["freqs"]
        jac = len(set(fa) & set(fb)) / len(set(fa) | set(fb))
        va, vb = sorted(fa.values(), reverse=True), sorted(fb.values(), reverse=True)
        n = max(len(va), len(vb))
        va, vb = va + [0] * (n - len(va)), vb + [0] * (n - len(vb))
        shape = 1 - sum(abs(x - y) for x, y in zip(va, vb)) / 2
        if jac < 0.5 and shape > 0.7:
            info["crosswalk"] = crosswalk(fa, fb)
        elif jac < 0.5:
            info["crosswalk_many_to_one" if len(fa) > len(fb) else "crosswalk_unknown"] = True
        return max(jac, 0.85 * shape), info
    if ka == "text" and kb == "text":
        d = (abs(pa["at_share"] - pb["at_share"]) + abs(pa["space_share"] - pb["space_share"])
             + min(abs(pa["avg_len"] - pb["avg_len"]) / 30, 1)) / 3
        return 1 - d, info
    return 0.1, info


def _offset(pa: dict, pb: dict) -> int | None:
    """Counters floored at zero that start from different events (due date vs end of grace period).

    Tests whether one side equals max(0, other - k) for some k days, using the whole distribution.
    """
    x, y = pa["values"], pb["values"]
    if not len(x) or not len(y) or (x % 1).any() or (y % 1).any():
        return None
    zx, zy = (x == 0).mean(), (y == 0).mean()
    if min(zx, zy) < 0.3 or abs(zx - zy) < 0.01:
        return None
    def fit(a, b):  # how well a matches b once b is shifted: nonzero shape and zero share
        nz = b[b > 0]
        if len(nz) < 20 or (a > 0).sum() < 20:
            return -1.0
        return _ks(a[a > 0], nz) - abs((a == 0).mean() - (b == 0).mean())

    base = fit(x, y)
    best_k, best = 0, base
    for k in range(1, 61):
        for sim, kk in ((fit(x, np.maximum(y - k, 0)), k), (fit(np.maximum(x - k, 0), y), -k)):
            if sim > best:
                best, best_k = sim, kk
    return best_k if best_k and best >= base + 0.05 else None


def _rates_differ(a: float, b: float) -> bool:
    """A yes/no definition that marks at least twice as many records on one side as the other."""
    lo, hi = sorted((a, b))
    return hi - lo >= 0.03 and hi / max(lo, 0.005) >= 2.0


def crosswalk(src: dict, tgt: dict) -> dict:
    """Propose a code mapping by frequency rank. Always needs human review."""
    s = sorted(src, key=src.get, reverse=True)
    t = sorted(tgt, key=tgt.get, reverse=True)
    return {a: (t[i] if i < len(t) else None) for i, a in enumerate(s)}


def grain_of(c: Card) -> str:
    return c.extra.get("cgrain", c.grain)


def entity_of_card(c: Card) -> str:
    return c.extra.get("centity", c.entity)


def logic_of(c: Card) -> set:
    return c.extra.get("clogic", c.logic)


def logic_sim(a: Card, b: Card) -> float | None:
    if not (a.derived or b.derived):
        return None
    la, lb = sorted(logic_of(a)), sorted(logic_of(b))
    return soft_sim(la, lb)


def context_sim(a: Card, b: Card) -> float | None:
    if "cgrain" not in a.extra:
        return None          # tables not aligned yet
    return 1.0 if grain_of(a) == grain_of(b) else 0.25


# ---------------------------------------------------------------- scoring
@dataclass
class PairScore:
    source: Card
    target: Card
    signals: dict
    score: float
    value_info: dict = field(default_factory=dict)


def score_pair(a: Card, b: Card) -> PairScore:
    v, vinfo = value_sim(a, b)
    sig = {"name": name_sim(a, b), "definition": definition_sim(a, b), "type": type_sim(a, b),
           "value": v, "logic": logic_sim(a, b), "context": context_sim(a, b)}
    w = {k: wt for k, wt in WEIGHTS.items() if sig[k] is not None}
    total = sum(w.values())
    score = sum(sig[k] * wt for k, wt in w.items()) / total
    return PairScore(a, b, sig, score, vinfo)


def detect_conflicts(p: PairScore) -> list[str]:
    a, b, vi = p.source, p.target, p.value_info
    flags = []
    f = vi.get("factor", 1.0)
    if f != 1.0:
        pct = {"percent", "rate", "apr"} & (set(a.name_tokens) | set(b.name_tokens))
        flags.append("unit" if f in (12.0, 1 / 12) else "scale" if (pct or f in (1000.0, 0.001)) else "unit")
    pa, pb = a.profile, b.profile
    if _kind(a) == "numeric" and _kind(b) == "numeric" and (
            abs(pa["neg_share"] - pb["neg_share"]) > 0.2
            or min(pa["neg_share"], pb["neg_share"]) == 0 and max(pa["neg_share"], pb["neg_share"]) >= 0.05):
        flags.append("sign")
    if "crosswalk" in vi or "crosswalk_many_to_one" in vi or "crosswalk_unknown" in vi:
        flags.append("code_set")
    if _kind(a) == "date" and _kind(b) == "date":
        sa, sb = pa.get("sentinel_share", 0), pb.get("sentinel_share", 0)
        if (pa["null_rate"] - pb["null_rate"] > 0.05 and sb > 0.05) or (pb["null_rate"] - pa["null_rate"] > 0.05 and sa > 0.05):
            flags.append("null_semantics")
    na_, nb_ = pa["null_rate"], pb["null_rate"]
    if vi.get("null_as_zero") or (abs(na_ - nb_) > 0.05 and max(na_, nb_) / max(min(na_, nb_), 0.005) >= 3):
        flags.append("null_semantics")
    if vi.get("weekend_gap", 0) > 0.1 or ((a.derived or b.derived) and _events_differ(a, b)):
        flags.append("temporal")
    fa = {f for f in a.logic if f.startswith("fee:")}
    fb = {f for f in b.logic if f.startswith("fee:")}
    if fa and fb and fa != fb:
        flags.append("inclusion")
    elif fa != fb and (a.derived or b.derived) and _kind(a) == "numeric" and (fa | fb) and "fee:included" in (fa | fb):
        flags.append("inclusion")
    if "inclusion" not in flags and _kind(a) == "numeric" and _kind(b) == "numeric" and (a.derived or b.derived):
        if _extra_terms(a.extra.get("terms", []), b.extra.get("terms", [])):
            flags.append("inclusion")
    if "format" in vi:
        flags.append("format")
    if vi.get("offset") or vi.get("date_shift_days"):
        flags.append("temporal")
    if vi.get("netting"):
        flags.append("inclusion")

    if grain_of(a) != grain_of(b):
        flags.append("grain")
    ba = {f for f in logic_of(a) if f.startswith("basis:")}
    bb = {f for f in logic_of(b) if f.startswith("basis:")}
    if _kind(a) == "bool" and _kind(b) == "bool" and ba != bb:
        flags.append("population")
    if vi.get("two_value_code"):
        flags.append("code_set")
    if vi.get("rate_ratio"):
        flags.append("population")
    if a.family != b.family and not (_kind(a) == "bool" and _kind(b) == "bool" and a.family == b.family):
        flags.append("cast")
    return flags


def _extra_terms(ta: list, tb: list) -> bool:
    """One side adds terms the other leaves out (escrow, accrued interest, expenses)."""
    if not ta or not tb or len(ta) == len(tb):
        return False
    small, large = sorted((ta, tb), key=len)
    if len(small) == 1 and len(large) >= 2:
        return True
    used = set()
    for t in small:
        best = max(range(len(large)), key=lambda i: soft_sim(list(t), list(large[i])) if i not in used else -1)
        if soft_sim(list(t), list(large[best])) < 0.6:
            return False
        used.add(best)
    return True


def _events_differ(a: Card, b: Card) -> bool:
    """Date columns built from different events (request vs settlement), compared with abbreviations."""
    ea = [e[6:] for e in _event(a)]
    eb = [e[6:] for e in _event(b)]
    if not ea or not eb:
        return False
    return max(tok_match(x, y) for x in ea for y in eb) < 0.7


def _event(c: Card) -> set:
    return {f for f in c.logic if f.startswith("event:")}


# ---------------------------------------------------------------- results
@dataclass
class Match:
    source: str
    target: str | None
    score: float
    match_type: str
    flags: list
    signals: dict
    transform: str
    alternatives: list
    false_friend: dict | None = None
    ddr: dict | None = None
    note: str = ""

    identifier: bool = False

    @property
    def auto_accept(self) -> bool:
        return (self.match_type == "exact" and self.score >= AUTO_ACCEPT and not self.false_friend
                and not self.identifier)


def suggest_transform(p: PairScore, flags: list, tgt_side: Side, src_side: Side | None = None) -> str:
    a, b, vi = p.source, p.target, p.value_info
    expr = a.column
    if vi.get("null_as_zero"):
        expr = f"COALESCE({expr}, 0)"
    if vi.get("absolute"):
        expr = f"ABS({expr})"
    f = vi.get("factor", 1.0)
    if f == 100.0:
        expr = f"ROUND({expr} * 100)"
    elif f == 0.01:
        expr = f"{expr} / 100"
    parts = [expr if expr != a.column else ""]
    if "sign" in flags and any(c.column == "direction" and c.table == b.table for c in tgt_side.cards):
        parts.append(f"direction = CASE WHEN {a.column} < 0 THEN 'OUT' ELSE 'IN' END")
    if "sign" in flags and a.profile.get("neg_share", 1) == 0 and src_side is not None:
        want = b.profile.get("neg_share", 0)
        for c in src_side.cards:          # a two-value indicator whose minority share matches the negatives
            fr = c.profile.get("freqs", {})
            if c.table == a.table and len(fr) == 2 and abs(min(fr.values()) - want) < 0.03:
                minority = min(fr, key=fr.get)
                parts.append(f"CASE WHEN {c.column} = '{minority}' THEN -{a.column} ELSE {a.column} END")
                break
    if "crosswalk" in vi:
        parts.append("crosswalk " + ", ".join(f"{k}->{v}" for k, v in vi["crosswalk"].items()))
    if "crosswalk_many_to_one" in vi:
        parts.append("many-to-one crosswalk needed: map every source code to a target category")
    if _kind(a) == "bool" and a.family == "string":
        parts.append(f"CASE WHEN {a.column} = 'Y' THEN TRUE ELSE FALSE END")
    if "format" in flags:
        if b.family == "string" and a.family != "string":
            width = int(round(b.profile.get("digits", {}).get("length", 0)))
            parts.append(f"LPAD(CAST({a.column} AS VARCHAR), {width}, '0')")
        else:
            parts.append(f"REGEXP_REPLACE({a.column}, '[^0-9]', '')")
    if "cast" in flags and b.family == "timestamp":
        parts.append(f"CAST({a.column} AS TIMESTAMP)")
    return "; ".join(x for x in parts if x)


def align_tables(src: Side, tgt: Side) -> dict:
    """Line up tables by their column evidence, so naming (Borrower vs member) does not matter."""
    for c in src.cards:
        for k in ("cgrain", "centity", "clogic"):
            c.extra.pop(k, None)
    S, T = src.cards, tgt.cards
    pre = [[score_pair(a, b) for b in T] for a in S]
    st, tt = list(src.schema), list(tgt.schema)
    W = np.zeros((len(st), len(tt)))
    for i, a in enumerate(S):
        for j_t, tname in enumerate(tt):
            best = max((pre[i][j].score for j, b in enumerate(T) if b.table == tname), default=0)
            W[st.index(a.table), j_t] += best
    r, c = linear_sum_assignment(-W)
    from .cards import entity_of
    tmap = {st[i]: tt[j] for i, j in zip(r, c)}
    emap = {entity_of(st[i]): entity_of(tt[j]) for i, j in zip(r, c)}
    for a in S:
        a.extra["centity"] = entity_of(tmap[a.table]) if a.table in tmap else a.entity
        a.extra["cgrain"] = a.extra["centity"] if a.grain == a.entity else emap.get(a.grain, a.grain)
        a.extra["clogic"] = {f"grain:{emap.get(f[6:], f[6:])}" if f.startswith("grain:") else f for f in a.logic}
    for b in T:
        b.extra["cgrain"] = b.grain
    return {st[i]: tt[j] for i, j in zip(r, c)}


def match_sides(src: Side, tgt: Side) -> list[Match]:
    S, T = src.cards, tgt.cards
    table_map = align_tables(src, tgt)
    grid = [[score_pair(a, b) for b in T] for a in S]
    M = np.array([[p.score for p in row] for row in grid])
    for i in range(len(S)):
        for j in range(len(T)):
            if M[i, j] >= ACCEPT_THRESHOLD:
                n_meaning = len(set(detect_conflicts(grid[i][j])) & MEANING_CONFLICTS)
                M[i, j] *= 0.85 ** n_meaning
    rows, cols = linear_sum_assignment(-M)
    def evidence(p):  # a match needs meaning evidence, not just a compatible type and table
        return max(p.signals["name"], p.signals["definition"], p.signals["logic"] or 0) >= 0.3
    assigned = {r: c for r, c in zip(rows, cols) if M[r, c] >= ACCEPT_THRESHOLD and evidence(grid[r][c])}
    owner = {c: r for r, c in assigned.items()}

    results = []
    for i, a in enumerate(S):
        order = np.argsort(-M[i])
        alts = [f"{T[j].qname} ({M[i, j]:.2f})" for j in order[:4] if j != assigned.get(i)][:3]
        struct = structural(a, tgt)
        j = assigned.get(i)
        if struct and (j is None or struct[1] > M[i, j]):
            comma = a.profile.get("comma_share", 0) > 0.8
            tx = (f"first = TRIM(SPLIT_PART({a.column}, ',', 2)); last = SPLIT_PART({a.column}, ',', 1)" if comma
                  else f"SPLIT_PART({a.column}, ' ', 1); SPLIT_PART({a.column}, ' ', 2)")
            results.append(Match(a.qname, struct[0], struct[1], "structural", [], {}, tx, alts))
            continue
        if j is None:
            m = Match(a.qname, None, float(M[i, order[0]]), "unmatched", [], grid[i][order[0]].signals, "", alts)
        else:
            p = grid[i][j]
            flags = detect_conflicts(p)
            mtype = ("conflict" if set(flags) & MEANING_CONFLICTS
                     else "transform" if set(flags) & TRANSFORM_FLAGS else "exact")
            m = Match(a.qname, p.target.qname, p.score, mtype, flags, p.signals,
                      suggest_transform(p, flags, tgt, src), alts,
                      identifier=bool(a.is_identifier or p.target.is_identifier))
            if m.identifier:
                m.note = "Confirm ID meaning: stable across modifications? same owner rule?"
        # false friend: the best-named target, or a strong near match, belongs to another source
        k = max(range(len(T)), key=lambda jj: grid[i][jj].signals["name"])
        near = int(order[0])
        if j is None and k != near and M[i, near] >= 0.6 and near in owner:
            k = near
        twin = grid[i][k]
        fk_pair = a.is_identifier and T[k].is_identifier  # keys legitimately repeat across tables
        if (twin.signals["name"] >= 0.8 or k == near) and k != j and not fk_pair:
            reasons = [r for r in detect_conflicts(twin) if r != "cast"]
            taken_by = S[owner[k]].qname if k in owner else None
            if reasons or (taken_by and twin.signals["name"] >= 0.8):
                m.false_friend = {"target": T[k].qname, "reasons": reasons, "score": round(twin.score, 2),
                                  "best_source_for_target": taken_by}
                if m.match_type == "unmatched":
                    m.match_type = "conflict"
        results.append(m)
    _attach_ddr(results, src, tgt)
    return results


def structural(a: Card, tgt: Side):
    """1:N split, e.g. full name -> first name + last name."""
    p = a.profile
    if _kind(a) not in ("text", "categorical") or p.get("space_share", 0) < 0.8:
        return None
    cands = [c for c in tgt.cards if _kind(c) in ("text", "categorical") and c.entity == entity_of_card(a)
             and c.profile.get("space_share", 1) < 0.1
             and max(tok_match(x, y) for x in c.name_tokens for y in a.name_tokens) >= 0.7]
    if len(cands) < 2:
        return None
    c1, c2 = cands[:2]
    lens = abs(c1.profile["avg_len"] + c2.profile["avg_len"] + 1 - p["avg_len"]) / max(p["avg_len"], 1)
    score = 0.6 + 0.4 * max(0.0, 1 - lens)
    return f"{c1.qname}+{c2.qname}", score


# ---------------------------------------------------------------- DDR
def _attach_ddr(results: list[Match], src: Side, tgt: Side) -> None:
    """Apply the target's definition to source entities and count disagreements."""
    import sqlglot
    from sqlglot import exp

    t2s = {m.target: m.source for m in results if m.target and "+" not in m.target}
    table_votes: dict = {}
    for t, s in t2s.items():
        table_votes.setdefault(t.split(".")[0], Counter())[s.split(".")[0]] += 1
    tmap = {t: v.most_common(1)[0][0] for t, v in table_votes.items()}

    for m in results:
        if not m.target or "+" in m.target:
            continue
        sql = tgt.derivations.get(m.target)
        if not sql or "grain" in m.flags:  # different grain: the rule does not apply entity for entity
            continue
        tree = sqlglot.parse_one(sql, read="duckdb")
        alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
        missing = []
        for col in tree.find_all(exp.Column):
            key = f"{alias.get(col.table, col.table)}.{col.name}"
            if key in t2s:
                col.set("this", exp.to_identifier(t2s[key].split(".")[1]))
            else:
                missing.append(key)
        for t in tree.find_all(exp.Table):
            if t.name in tmap:
                t.set("this", exp.to_identifier(tmap[t.name]))
            else:
                missing.append(t.name)
        if missing:
            m.ddr = {"available": False, "missing": sorted(set(missing))}
            continue
        s_table, s_col = m.source.split(".")
        key = src.schema[s_table]["key"]
        try:
            rule = tree.sql(dialect="duckdb")
            df = src.con.execute(f"""
                WITH r AS ({rule})
                SELECT s.{s_col} AS src_val, r.* EXCLUDE ({key}) FROM {s_table} s
                LEFT JOIN r ON r.{key} = s.{key}""").df()
        except Exception as e:  # noqa: BLE001
            m.ddr = {"available": False, "error": str(e)[:200]}
            continue
        tgt_val = df.iloc[:, 1]
        src_val = df.src_val
        sp = src.card(m.source).profile
        two_value = sp.get("kind") == "categorical" and len(sp.get("freqs", {})) == 2
        if sp.get("kind") == "bool":
            from .cards import BOOL_VALUES
            src_val = src_val.map(lambda v: BOOL_VALUES.get(str(v).upper(), bool(v)))
            tgt_val = tgt_val.fillna(False).astype(bool)
        elif two_value:
            tgt_val = tgt_val.fillna(False).astype(bool)
            v0 = sorted(sp["freqs"])[0]
            a_ = src_val.astype(str) == v0
            src_val = a_ if (a_ != tgt_val).mean() <= (~a_ != tgt_val).mean() else ~a_
        disagree = float((src_val != tgt_val).mean())
        m.ddr = {"available": True, "rate": round(disagree, 4), "entities": len(df),
                 "flipped": int((src_val != tgt_val).sum()), "rule": rule}
        if sp.get("kind") == "numeric":
            sv = pd.to_numeric(df.src_val, errors="coerce")
            tv = pd.to_numeric(df.iloc[:, 1], errors="coerce")
            both = sv.notna() & tv.notna()
            if both.sum() >= 20:
                diff = (sv - tv)[both]
                tol = np.maximum(0.01, 0.005 * tv[both].abs())
                bad = diff.abs() > tol
                m.ddr.update(rate=round(float(bad.mean()), 4), entities=int(both.sum()), flipped=int(bad.sum()))
                explained = set(m.flags) & {"unit", "scale", "sign", "inclusion"}   # known transforms
                if bad.mean() > DDR_THRESHOLD and not explained:
                    one_sided = max((diff[bad] > 0).mean(), (diff[bad] < 0).mean()) >= 0.9
                    m.flags.append("inclusion" if one_sided else "definition")
                    m.match_type = "conflict"
            continue
        if (sp.get("kind") == "bool" or two_value) and disagree > DDR_THRESHOLD and "population" not in m.flags:
            m.flags.append("population")
            m.match_type = "conflict"
