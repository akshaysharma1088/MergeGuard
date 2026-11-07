"""Score a matcher's output against MergeBench ground truth."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .cards import Side
from .match import Match, name_sim


def name_only_baseline(src: Side, tgt: Side, threshold: float = 0.6) -> list[Match]:
    """What a name-driven matcher does: best name wins, accepted as an exact match."""
    out = []
    for a in src.cards:
        b = max(tgt.cards, key=lambda c: name_sim(a, c))
        s = name_sim(a, b)
        if s >= threshold:
            out.append(Match(a.qname, b.qname, s, "exact", [], {"name": s}, "", []))
        else:
            out.append(Match(a.qname, None, s, "unmatched", [], {"name": s}, "", []))
    return out


def evaluate(results: list[Match], ground_truth: str | Path, auto_accept=None) -> dict:
    gt = json.loads(Path(ground_truth).read_text())["attributes"]
    by_src = {m.source: m for m in results}
    accept = auto_accept or (lambda m: m.auto_accept)
    correct = harmful = risky = auto = false_alarm = clean = surfaced = 0
    meaning = {"population", "grain", "null_semantics", "inclusion", "temporal", "definition"}
    found, total = defaultdict(int), defaultdict(int)
    rows = []
    for g in gt:
        m = by_src[g["source"]]
        ok = (m.target == g["target"]
              or (g["target"] is None and g["false_friend_of"] == m.target and m.match_type == "conflict"))
        correct += ok
        detected = set(m.flags) | set((m.false_friend or {}).get("reasons", []))
        for c in g["conflicts"]:
            total[c] += 1
            found[c] += c in detected
        is_risky = bool(g["conflicts"] or g["false_friend_of"])
        risky += is_risky
        surfaced += bool(is_risky and (m.match_type == "conflict" or m.false_friend
                                      or set(m.flags) & (meaning | {"unit", "scale", "sign", "code_set", "format"})))
        bad_accept = bool(accept(m) and (is_risky or not ok))
        harmful += bad_accept
        if not is_risky and g["match_type"] in ("exact", "transform", "structural"):
            clean += 1
            false_alarm += bool(set(m.flags) & meaning or m.match_type == "conflict")
        auto += bool(accept(m))
        rows.append({"source": g["source"], "predicted": m.target, "truth": g["target"], "correct": bool(ok),
                     "conflicts": g["conflicts"], "detected": sorted(detected & set(g["conflicts"])),
                     "harmful_accept": bad_accept})
    n_conf = sum(total.values())
    return {
        "attributes": len(gt),
        "target_accuracy": correct / len(gt),
        "conflict_recall": sum(found.values()) / n_conf if n_conf else 1.0,
        "conflict_recall_by_type": {k: found[k] / total[k] for k in sorted(total)},
        "risky_attributes": risky,
        "harmful_auto_accepts": harmful,
        "auto_accepted": auto,
        "false_alarms": false_alarm,
        "surfaced": surfaced,
        "clean_attributes": clean,
        "rows": rows,
    }
