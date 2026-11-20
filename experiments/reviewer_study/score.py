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

    print("\nPooled across all files")
    summarize([r for r in all_rows if r["note_shown"]], "  with note")
    summarize([r for r in all_rows if not r["note_shown"]], "  without note")
