"""Language-model baseline (post-hoc, not pre-registered): can an off-the-shelf LLM that reads both banks'
metadata spot semantic traps?

Two prompts per source column, against a local Ollama server (no paid API):
  1. match: the source column card and every target column (name, type, description) -> best target or none
  2. judge: both full cards (name, type, description, sample values, derivation SQL) -> same meaning or not

Scored like the other baselines:
  llm_trust_all   every proposed target counts as approved
  llm_judged      approved only if the judge says the meaning is the same
  llm_judged_ids  as llm_judged, with identifiers sent to review (MergeGuard's rule)

    python experiments/run_llm_baseline.py <out_dir> <scenario letter> [model]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from mergeguard.bench.generate import generate
from mergeguard.bench.round3 import SPECS
from mergeguard.bench.round4 import SPEC_L
from mergeguard.bench.spec import generate_spec
from mergeguard.evaluate import evaluate
from mergeguard.match import Match

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import load  # noqa: E402

SEEDS = {"E": 303, "F": 404, "G": 571, "H": 572, "I": 573, "J": 574, "K": 575, "L": 612}
URL = "http://127.0.0.1:11434/api/generate"

MATCH_PROMPT = """You are mapping columns from an acquired bank's database to the acquiring bank's database.

Source column:
{source}

Target columns:
{targets}

Which single target column should this source column be loaded into? Answer with JSON only:
{{"target": "<table.column from the list, or null if none fits>"}}"""

JUDGE_PROMPT = """Two banks are merging. A data engineer proposes to load the source column into the target column.
Decide whether the two columns have the same business meaning, so that values can be copied (after at most a
simple format change) without changing what the numbers, dates, flags or codes mean.

Source column (acquired bank):
{source}

Target column (acquiring bank):
{target}

Answer with JSON only:
{{"same_meaning": true or false, "difference": "<one short sentence, or empty if the same>"}}"""


def ask(model: str, prompt: str) -> tuple[dict, str]:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json",
                       "options": {"temperature": 0, "seed": 7, "num_ctx": 8192, "num_predict": 200}}).encode()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, body, {"Content-Type": "application/json"}),
                                        timeout=1800) as r:
                text = json.loads(r.read())["response"]
            try:
                return json.loads(text), text
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}", text, re.S)
                return (json.loads(m.group(0)) if m else {}), text
        except Exception as e:  # server hiccup: wait and retry
            err = repr(e)
            time.sleep(10 * (attempt + 1))
    return {}, f"ERROR {err}"


def samples(side, card, n=6) -> list:
    rows = side.con.execute(f'SELECT DISTINCT CAST("{card.column}" AS VARCHAR) FROM "{card.table}" '
                            f'WHERE "{card.column}" IS NOT NULL LIMIT {n}').fetchall()
    return [r[0] for r in rows]


def brief(card) -> str:
    return f"- {card.qname} ({card.sql_type}): {card.description or 'no description'}"


def full(side, card) -> str:
    lines = [f"name: {card.qname}", f"type: {card.sql_type}", f"description: {card.description or 'none'}",
             f"sample values: {', '.join(map(str, samples(side, card)))}"]
    if card.derivation:
        lines.append(f"computed as: {card.derivation}")
    return "\n".join(lines)


def main(out_dir: str, letter: str, model: str = "qwen2.5:7b"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d = out / "scenarios" / letter
    if letter == "E":
        generate(d, seed=SEEDS[letter], scenario="practitioner")
    elif letter == "F":
        generate(d, seed=SEEDS[letter], scenario="practitioner2")
    else:
        generate_spec(SPEC_L if letter == "L" else SPECS[letter], d, seed=SEEDS[letter])
    src, tgt, gt_path, _ = load(d)
    targets = "\n".join(brief(c) for c in tgt.cards)
    valid = {c.qname.lower(): c.qname for c in tgt.cards}
    results, log, t0 = [], [], time.time()
    for i, a in enumerate(src.cards):
        ans, raw1 = ask(model, MATCH_PROMPT.format(source=full(src, a), targets=targets))
        t = valid.get(str(ans.get("target") or "").strip().lower())
        same, raw2, diff = None, "", ""
        if t:
            j, raw2 = ask(model, JUDGE_PROMPT.format(source=full(src, a), target=full(tgt, tgt.card(t))))
            same, diff = j.get("same_meaning"), str(j.get("difference", ""))
            same = same if isinstance(same, bool) else str(same).lower() == "true"
        results.append(Match(a.qname, t, 1.0 if t else 0.0, "exact" if same else ("conflict" if t else "unmatched"),
                             [], {}, "", []))
        log.append({"source": a.qname, "target": t, "same_meaning": same, "difference": diff, "raw_match": raw1,
                    "raw_judge": raw2})
        print(f"{letter} {i + 1}/{len(src.cards)} {a.qname} -> {t} same={same} ({time.time() - t0:.0f}s)", flush=True)
    said_same = {r["source"] for r in log if r["target"] and r["same_meaning"]}
    is_id = lambda m: src.card(m.source).is_identifier or bool(m.target and tgt.card(m.target).is_identifier)
    gt = {g["source"]: g for g in json.loads(Path(gt_path).read_text())["attributes"]}
    risky = {s for s, g in gt.items() if g["conflicts"] or g["false_friend_of"]}
    clean = {s for s, g in gt.items() if s not in risky and g["match_type"] in ("exact", "transform", "structural")}
    proposed = {r["source"] for r in log if r["target"]}
    variants = {"llm_trust_all": lambda m: m.target is not None,
                "llm_judged": lambda m: m.source in said_same,
                "llm_judged_ids": lambda m: m.source in said_same and not is_id(m)}
    summary = {"scenario": letter, "model": model, "columns": len(gt), "risky": len(risky), "clean": len(clean),
               "seconds": round(time.time() - t0),
               "traps_flagged_different": len(risky & (proposed - said_same)),
               "traps_proposed": len(risky & proposed),
               "clean_flagged_different": len(clean & (proposed - said_same)),
               "clean_proposed": len(clean & proposed)}
    for name, acc in variants.items():
        r = evaluate(results, gt_path, auto_accept=acc)
        summary[name] = {"approved": r["auto_accepted"], "wrong": r["harmful_auto_accepts"]}
        summary["target_accuracy"] = r["target_accuracy"]
    print(json.dumps(summary), flush=True)
    (out / f"llm_{letter}.json").write_text(json.dumps({"summary": summary, "rows": log}, indent=2, default=str))


if __name__ == "__main__":
    main(*sys.argv[1:4])
