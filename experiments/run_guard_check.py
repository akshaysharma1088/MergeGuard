"""Post-hoc, negative result: does marking a rewritten rule's output "unverified" when one of its own input
pairs is independently flagged fix the rule-rewriting failure mode found in run_rule_rewrite_checks.py?

The idea (write-up draft, not shipped): if a.b's derivation rule is rewritten through input pair (x, y), and
(x, y) itself carries a flag from detect_conflicts, treat a.b's rule result as unverified rather than letting it
raise or clear a flag. On the two controlled false-alarm cases (wrong input column, input in cents) this would
work, because the wrong input pair is itself flagged "unit". It was never expected to catch the masked-trap case.

This script checks the idea against MergeBench scenarios E to L instead of the controlled payroll pair: for every
Match that _attach_ddr scored, treat its DDR result as unverified if any of the rule's source-side column
references other than the matched pair is itself flagged (excluding "cast"), and ask whether the resulting flags
match a from-scratch run of the matcher with the actual guard implemented.

    python experiments/run_guard_check.py <scenario_root_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import load  # noqa: E402

from mergeguard.match import match_sides


def main(root):
    root = Path(root)
    changes = []
    for k in "EFGHIJKL":
        d = root / k
        if not d.exists():
            continue
        src, tgt, gtp, _ = load(d)
        gt = {g["source"]: g for g in json.loads(Path(gtp).read_text())["attributes"]}
        results = match_sides(src, tgt)
        by_target = {m.target: m for m in results if m.target}
        for m in results:
            if not m.ddr or not m.ddr.get("available") or not m.target:
                continue
            # which other mapped columns feed this rule: reuse the rule text's column list via a second parse
            import sqlglot
            from sqlglot import exp
            sql = tgt.derivations.get(m.target)
            if not sql:
                continue
            tree = sqlglot.parse_one(sql, read="duckdb")
            alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
            refs = {f"{alias.get(c.table, c.table)}.{c.name}" for c in tree.find_all(exp.Column)}
            refs.discard(m.target)
            doubtful = {}
            for key in refs:
                other = by_target.get(key)
                if other is None:
                    continue
                why = [f for f in other.flags if f != "cast"] + (["false_friend"] if other.false_friend else [])
                if why and not other.identifier:
                    doubtful[other.source] = why
            if not doubtful:
                continue
            is_trap = bool(gt[m.source]["conflicts"] or gt[m.source]["false_friend_of"])
            changes.append({"scenario": k, "source": m.source, "target": m.target, "doubtful_inputs": doubtful,
                            "flags_if_guard_applied_would_suppress": [f for f in m.flags],
                            "currently_flagged": bool(m.flags), "is_trap": is_trap, "ddr_rate": m.ddr.get("rate")})
    print(json.dumps(changes, indent=1))
    n_traps_would_hide = sum(1 for c in changes if c["is_trap"] and c["currently_flagged"])
    n_false_alarms_would_fix = sum(1 for c in changes if not c["is_trap"] and c["currently_flagged"])
    print(f"\ncases where an input to the rule is itself flagged: {len(changes)}", file=sys.stderr)
    print(f"of those, real traps currently caught that the guard would un-flag: {n_traps_would_hide}", file=sys.stderr)
    print(f"of those, clean columns currently (wrongly) flagged that the guard would fix: {n_false_alarms_would_fix}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
