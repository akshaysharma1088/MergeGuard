"""Post-hoc: wrong approvals against number of approvals, pooled over scenarios E to L (203 columns).

Every method's proposals (identifier columns excluded, as in the abstention analysis) are pooled across the eight
scenarios and ranked by that method's own score. An approval is wrong if the target is wrong or the column is a trap.

  coma              COMA pairs ranked by COMA score
  mergeguard_score  MergeGuard pairs ranked by matcher score, ignoring its flags
  mergeguard_flags  MergeGuard pairs with unflagged exact matches first (by score), flagged ones after
Operating points: MergeGuard's auto-accept rule, COMA + MergeGuard detectors, the LLM (from the recorded run).

Note: the earlier "COMA top 55" number took the top k inside each scenario; this pooled ranking is a different cut.

    python experiments/run_coverage_curves.py <out_dir> [figure.pdf]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import load  # noqa: E402
from run_review_baselines import build  # noqa: E402

from mergeguard.baselines import valentine_predictions
from mergeguard.match import match_sides

LLM = Path(__file__).parent / "results_v0.0.9_llm_baseline"


def pooled(out: Path) -> dict:
    rows = {"coma": [], "mg": []}
    for k, d in build(out / "scenarios").items():
        src, tgt, gt_path, _ = load(d)
        gt = {g["source"]: g for g in json.loads(Path(gt_path).read_text())["attributes"]}
        is_id = lambda m: src.card(m.source).is_identifier or tgt.card(m.target).is_identifier
        for name, res in (("mg", match_sides(src, tgt)), ("coma", valentine_predictions(src, tgt, "coma"))):
            for m in res:
                if not m.target or "+" in m.target or is_id(m):
                    continue
                g = gt[m.source]
                wrong = bool(m.target != g["target"] or g["conflicts"] or g["false_friend_of"])
                clear = name == "mg" and m.match_type == "exact" and not m.false_friend
                rows[name].append({"scenario": k, "source": m.source, "score": float(m.score), "wrong": wrong,
                                   "clear": clear, "auto": bool(name == "mg" and m.auto_accept)})
    return rows


def curve(items) -> list[int]:
    c, h = [0], 0
    for r in items:
        h += r["wrong"]
        c.append(h)
    return c


def main(out_dir, fig=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = pooled(out)
    by = lambda r: -r["score"]
    mg = rows["mg"]
    res = {
        "coma": curve(sorted(rows["coma"], key=by)),
        "mergeguard_score": curve(sorted(mg, key=by)),
        "mergeguard_flags": curve(sorted([r for r in mg if r["clear"]], key=by) + sorted([r for r in mg if not r["clear"]], key=by)),
        "n_clear": sum(r["clear"] for r in mg),
        "points": {"mergeguard_auto": [sum(r["auto"] for r in mg), sum(r["auto"] and r["wrong"] for r in mg)]},
    }
    a = w = 0
    for f in sorted(LLM.glob("llm_*.json")):
        s = json.loads(f.read_text())["summary"]["llm_judged_ids"]
        a, w = a + s["approved"], w + s["wrong"]
    res["points"]["llm"] = [a, w]
    prev = json.loads((Path(__file__).parent / "results_v0.0.9_review_baselines/results.json").read_text())["abstention"]
    res["points"]["coma_plus_detectors"] = [sum(v["coma_plus_detectors"]["accepted"] for v in prev.values()),
                                            sum(v["coma_plus_detectors"]["harmful"] for v in prev.values())]
    for k in ("coma", "mergeguard_score", "mergeguard_flags"):
        c = res[k]
        print(k, "n", len(c) - 1, {n: c[n] for n in (10, 20, 30, 40, 55, 78, 100) if n < len(c)}, "all", c[-1])
    print(res["points"], "clear", res["n_clear"])
    (out / "results.json").write_text(json.dumps(res, indent=1))
    if fig:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.size": 8, "font.family": "serif"})
        f, ax = plt.subplots(figsize=(3.3, 2.5))
        ax.plot(res["coma"], color="#eb6834", ls="--", lw=1.5, label="COMA, by score")
        ax.plot(res["mergeguard_score"], color="#777", ls=":", lw=1.5, label="MergeGuard, score only")
        ax.plot(res["mergeguard_flags"], color="#2a78d6", lw=1.5, label="MergeGuard, unflagged first")
        for key, mk, lab in (("mergeguard_auto", "o", "MergeGuard auto-accept"), ("llm", "s", "LLM judge"),
                             ("coma_plus_detectors", "^", "COMA + detectors")):
            x, y = res["points"][key]
            ax.plot([x], [y], mk, color="#222", ms=5, mfc="white", mew=1.2, label=lab, ls="none")
        ax.set_xlabel("columns approved")
        ax.set_ylabel("wrong approvals")
        ax.grid(alpha=0.25, lw=0.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.legend(frameon=False, fontsize=6.5, loc="upper left", handlelength=2.4)
        f.tight_layout(pad=0.3)
        f.savefig(fig)
        f.savefig(str(fig).replace(".pdf", ".png"), dpi=200)


if __name__ == "__main__":
    main(*sys.argv[1:3])
