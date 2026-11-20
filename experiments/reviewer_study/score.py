"""Score completed reviewer-study responses against ground truth (study_pool.json).

Usage: python score.py responses/*.xlsx
Prints per-respondent and pooled catch rates, split by whether a diagnosis
note was actually shown for that row (not by which design group the column
was assigned to -- two "clean" picks turned out to be undetected ground-truth
traps and never carry a note either way).
"""
import json
import sys

import openpyxl

POOL = {r["source"]: r for r in json.load(open("study_pool.json"))}


def score_file(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet_name = next(n for n in ("Form 1", "Form 2") if any(
        wb[n].cell(r, 5).value for r in range(6, 30)
    ))
    ws = wb[sheet_name]
    rows = []
    for r in range(6, 30):
        n = ws.cell(r, 1).value
        if not n:
            continue
        src = str(ws.cell(r, 2).value).splitlines()[0]
        k = POOL[src]
        rows.append({
            "src": src,
            "is_trap": k["is_trap"],
            "note_shown": bool(ws.cell(r, 4).value),
            "decision": ws.cell(r, 5).value,
        })
    return sheet_name, rows


def summarize(rows, label):
    traps = [r for r in rows if r["is_trap"]]
    clean = [r for r in rows if not r["is_trap"]]
    harmful = [r for r in traps if r["decision"] == "Approve"]
    fa = sum(1 for r in clean if r["decision"] != "Approve")
    caught = len(traps) - len(harmful)
    print(f"{label:22s} traps={len(traps):2d} caught={caught}/{len(traps)} "
          f"harmful={len(harmful)}/{len(traps)} clean={len(clean)} false-alarms={fa}")


if __name__ == "__main__":
    all_rows = []
    for path in sys.argv[1:]:
        sheet, rows = score_file(path)
        print(f"\n{path} ({sheet})")
        summarize([r for r in rows if r["note_shown"]], "  with note")
        summarize([r for r in rows if not r["note_shown"]], "  without note")
        all_rows.extend(rows)

    print("\nPooled across all files (includes 2 traps that never carry a note either way --")
    print("this comparison is NOT matched on item identity, see below)")
    summarize([r for r in all_rows if r["note_shown"]], "  with note")
    summarize([r for r in all_rows if not r["note_shown"]], "  without note")

    # Matched comparison: restrict to traps that are actually counterbalanced
    # (shown with a note under one form, without under the other). Two traps
    # in this study never carry a note under either form -- they're taxonomy
    # types (methodology, population) MergeGuard's checks never flag -- so
    # including them in the "without note" bucket compares unlike items.
    # This is the number reported in the paper.
    eligible = {r["src"] for r in all_rows if r["is_trap"] and r["note_shown"]}
    matched = [r for r in all_rows if r["src"] in eligible]
    print(f"\nMatched comparison: {len(eligible)} note-eligible traps, "
          f"{len(matched)} judgments -- each trap seen by 2 respondents with")
    print("a note and 2 without (this is the reported result)")
    summarize([r for r in matched if r["note_shown"]], "  with note")
    summarize([r for r in matched if not r["note_shown"]], "  without note")

    # Per-respondent breakdown on the matched set, by file order given on the
    # command line (needed to tell improved/tied/decreased apart -- the pooled
    # totals alone can't show this).
    print("\nPer-respondent (matched, eligible traps only):")
    for path in sys.argv[1:]:
        _, rows = score_file(path)
        elig = [r for r in rows if r["src"] in eligible]
        w = [r for r in elig if r["note_shown"]]
        wo = [r for r in elig if not r["note_shown"]]
        wc = sum(1 for r in w if r["decision"] != "Approve")
        woc = sum(1 for r in wo if r["decision"] != "Approve")
        tag = "improved" if wc > woc else ("tied" if wc == woc else "decreased")
        print(f"  {path:30s} with={wc}/{len(w)} without={woc}/{len(wo)}  {tag}")
