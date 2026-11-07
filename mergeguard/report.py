"""Editable Excel mapping report.

Grey columns are evidence the tool fills; white columns are for the analyst. The workbook
is the input to the next step: edit it, upload it back, and MergeGuard validates and migrates.
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side as BSide
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .cards import Side
from .match import AUTO_ACCEPT, Match

READ_ONLY = [
    ("source_attribute", 26), ("source_type", 14), ("sample_values", 26), ("suggested_target", 34),
    ("score", 7), ("match_type", 11), ("flags", 22), ("false_friend", 46), ("ddr", 22),
    ("evidence", 44), ("suggested_transform", 44), ("alternatives", 40),
]
STRESS = [  # semantic stress test: each must be answered by the SMEs before coding
    ("trigger", "Population trigger: which event writes or updates the value"),
    ("mutability", "Lifecycle: static, overwritten on renewal/reissue/modification, or reset"),
    ("granularity", "Granularity and scope: card vs account, tranche vs facility, person vs household"),
    ("inclusion_netting", "Gross vs net; principal only vs P&I and fees; settled vs pending"),
    ("sign_scale", "Sign convention and scale: debit sign, D/C flag, decimal vs percent, units"),
    ("null_sentinel", "Meaning of NULL, 0, 999999, 1900-01-01, 2099-12-31"),
]
EDITABLE = [
    ("decision", 11), ("target_attribute", 34),
    ("source_business_rule", 36), ("target_business_rule", 36), ("downstream_consumers", 26),
    *[(k, 16) for k, _ in STRESS], ("trap_identified", 10),
    ("transform", 40), ("value_crosswalk", 30), ("verify_rule", 26), ("edge_case_test_ids", 20),
    ("source_ops_signoff", 16), ("target_ops_signoff", 16), ("finance_risk_signoff", 16),
    ("data_profiling_signoff", 16), ("comments", 30),
]
STRESS_CHOICES = ["Same", "Differs", "Not applicable", "Unknown"]
FLAG_TO_STRESS = {"temporal": "trigger", "population": "trigger", "grain": "granularity",
                  "inclusion": "inclusion_netting", "definition": "inclusion_netting", "sign": "sign_scale",
                  "unit": "sign_scale", "scale": "sign_scale", "null_semantics": "null_sentinel"}
DECISIONS = ["Accept", "Change", "Reject", "Skip"]

GREY = PatternFill("solid", fgColor="EEF1F4")
HEAD = PatternFill("solid", fgColor="1F2A37")
EDIT_HEAD = PatternFill("solid", fgColor="0F766E")
RED = PatternFill("solid", fgColor="FDE2E1")
AMBER = PatternFill("solid", fgColor="FEF3C7")
GREEN = PatternFill("solid", fgColor="DCFCE7")
THIN = Border(bottom=BSide(style="thin", color="D1D5DB"))


def _samples(side: Side, qname: str, k: int = 3) -> str:
    t, c = qname.split(".")
    rows = side.con.execute(f"SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL LIMIT {k}").fetchall()
    return ", ".join(str(r[0]) for r in rows)


def _verify_rule(m: Match) -> str:
    if m.match_type == "unmatched" or not m.target:
        return ""
    if m.match_type == "conflict":
        return "BLOCK until definition resolved"
    if m.match_type == "structural":
        return "concat(first, last) = source"
    if "unit" in m.flags or "scale" in m.flags or "sign" in m.flags:
        return "daily total within 0.01%"
    if "code_set" in m.flags:
        return "every code mapped"
    return "exact match on key"


def write_mapping(results: list[Match], src: Side, tgt: Side, path: str | Path) -> Path:
    path = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Mapping"
    cols = READ_ONLY + EDITABLE
    for i, (name, width) in enumerate(cols, 1):
        cell = ws.cell(row=1, column=i, value=name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEAD if i <= len(READ_ONLY) else EDIT_HEAD
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "B2"

    # target list for the dropdown lives on a hidden sheet
    lists = wb.create_sheet("Lists")
    targets = ["(none)"] + [c.qname for c in tgt.cards]
    for r, t in enumerate(targets, 1):
        lists.cell(row=r, column=1, value=t)
    lists.sheet_state = "hidden"

    order = {"conflict": 0, "unmatched": 1, "transform": 2, "structural": 3, "exact": 4}
    rows = sorted(results, key=lambda m: (order[m.match_type], -m.score if m.match_type == "exact" else m.score))
    for r, m in enumerate(rows, 2):
        ff = ""
        if m.false_friend:
            f = m.false_friend
            ff = f"Same name as {f['target']} but differs: {', '.join(f['reasons']) or 'meaning'}"
            if f.get("best_source_for_target"):
                ff += f". Better source for it: {f['best_source_for_target']}"
        ddr = ""
        if m.ddr and m.ddr.get("available"):
            ddr = f"{m.ddr['rate']:.1%} of {m.ddr['entities']:,} entities flip"
        elif m.ddr:
            ddr = "not computable: " + ", ".join(m.ddr.get("missing", [])) if m.ddr.get("missing") else "not computable"
        ev = " | ".join(f"{k} {v:.2f}" for k, v in m.signals.items() if v is not None)
        src_card = src.card(m.source)
        tgt_card = tgt.card(m.target) if m.target and "+" not in m.target else None
        stress = {k: None for k, _ in STRESS}
        for f in m.flags:
            if f in FLAG_TO_STRESS:
                stress[FLAG_TO_STRESS[f]] = "Differs"
        if m.false_friend:
            for f in m.false_friend.get("reasons", []):
                if f in FLAG_TO_STRESS:
                    stress[FLAG_TO_STRESS[f]] = "Differs"
        if m.identifier:
            stress["mutability"] = stress["mutability"] or "Unknown"
        def rule(card):
            if card is None:
                return None
            return card.description + (f" | derived: {card.derivation}" if card.derivation else "")
        row_no = r
        first_stress = len(READ_ONLY) + 6
        rng_ = f"{get_column_letter(first_stress)}{row_no}:{get_column_letter(first_stress + len(STRESS) - 1)}{row_no}"
        values = [
            m.source, src_card.sql_type, _samples(src, m.source), m.target or "(none)", round(m.score, 2),
            m.match_type, ", ".join(m.flags), ff, ddr, ev, m.transform, "; ".join(m.alternatives),
            "Accept" if m.auto_accept else None,
            None if m.match_type == "conflict" else (m.target or "(none)"),
            rule(src_card), rule(tgt_card), None,
            *[stress[k] for k, _ in STRESS],
            f'=IF(COUNTIF({rng_},"Differs")>0,"YES",IF(COUNTBLANK({rng_})>0,"OPEN","NO"))',
            m.transform or None, None, _verify_rule(m), None, None, None, None, None, None,
        ]
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = THIN
            if c <= len(READ_ONLY):
                cell.fill = GREY
        status = ws.cell(row=r, column=6)
        status.fill = (RED if m.match_type == "conflict" or m.false_friend
                       else AMBER if m.match_type in ("transform", "unmatched", "structural") or m.score < AUTO_ACCEPT
                       else GREEN)
        if m.ddr and m.ddr.get("rule"):
            ws.cell(row=r, column=9).comment = Comment(f"Target rule run on source data:\n{m.ddr['rule']}", "MergeGuard")

    n = len(rows) + 1
    dec_col = get_column_letter(len(READ_ONLY) + 1)
    tgt_col = get_column_letter(len(READ_ONLY) + 2)
    dv = DataValidation(type="list", formula1='"' + ",".join(DECISIONS) + '"', allow_blank=True)
    dv.add(f"{dec_col}2:{dec_col}{n}")
    dv2 = DataValidation(type="list", formula1=f"Lists!$A$1:$A${len(targets)}", allow_blank=True)
    dv2.add(f"{tgt_col}2:{tgt_col}{n}")
    ws.add_data_validation(dv)
    ws.add_data_validation(dv2)
    first_stress = len(READ_ONLY) + 6
    a, b = get_column_letter(first_stress), get_column_letter(first_stress + len(STRESS) - 1)
    dv3 = DataValidation(type="list", formula1='"' + ",".join(STRESS_CHOICES) + '"', allow_blank=True)
    dv3.add(f"{a}2:{b}{n}")
    ws.add_data_validation(dv3)
    ws.conditional_formatting.add(f"{a}2:{b}{n}", FormulaRule(formula=[f'{a}2="Differs"'], fill=RED))
    ws.conditional_formatting.add(f"{a}2:{b}{n}", FormulaRule(formula=[f'LEN({a}2)=0'], fill=AMBER))
    for i, (k, help_) in enumerate(STRESS):
        ws.cell(row=1, column=first_stress + i).comment = Comment(help_, "MergeGuard")
    # highlight rows still waiting for a decision
    ws.conditional_formatting.add(f"{dec_col}2:{dec_col}{n}",
                                  FormulaRule(formula=[f'LEN({dec_col}2)=0'], fill=AMBER))
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{n}"

    qs = wb.create_sheet("SME questions")
    questions = [
        ("Amounts and rates", [
            "Sign: is a normal debit or obligation positive, negative, or unsigned with a D/C flag?",
            "Basis: gross, net of waivers or refunds, or net of participations sold?",
            "Credit lines: approved limit, drawn principal, or available to spend (including shadow overlimit)?",
            "Currency: transaction currency, account base currency, or reporting currency (USD)?",
            "Scale: decimal (0.0525), percent (5.25), basis points, cents or thousands?"]),
        ("Dates and timestamps", [
            "Trigger: application, approval, closing, funding, first payment, renewal, or charge-off?",
            "Overwrite: does the date stay locked or overwrite on modification, renewal or reissue?",
            "Calendar: calendar day, business or posting day, or clearinghouse settlement day? Which time zone?",
            "Placeholders: are 1900-01-01, 2099-12-31 or 9999-12-31 used for open-ended or missing values?"]),
        ("Statuses, codes and flags", [
            "Threshold: what day count or dollar amount flips the status?",
            "Stage: does TRUE mean requested or qualified, or completed by back office or legal?",
            "Scope: does it apply to the channel, card, account, person or household?"]),
        ("Identifiers", [
            "Persistence: does the ID survive card reissue, loan modification or CD rollover?",
            "Entity: person, household, trust grantor, corporate parent or project entity?"]),
        ("Sign-off", [
            "Four sign-offs per high-risk field: source operations, target operations, finance or risk, data profiling engineer.",
            "Edge-case test IDs: 3 to 5 real account keys that prove the transformation."]),
    ]
    r_ = 1
    for group, items in questions:
        qs.cell(row=r_, column=1, value=group).font = Font(bold=True)
        r_ += 1
        for q in items:
            qs.cell(row=r_, column=1, value=q)
            r_ += 1
        r_ += 1
    qs.column_dimensions["A"].width = 110

    # summary sheet
    sm = wb.create_sheet("Summary", 0)
    counts = {}
    for m in results:
        counts[m.match_type] = counts.get(m.match_type, 0) + 1
    ff = sum(1 for m in results if m.false_friend)
    auto = sum(1 for m in results if m.auto_accept)
    lines = [
        ("MergeGuard mapping report", None),
        (f"Source: {src.name} ({src.path.name})   Target: {tgt.name} ({tgt.path.name})", None),
        ("", None),
        ("Source attributes", len(results)),
        ("Auto-accepted (exact, score >= 0.90)", auto),
        ("Need review", len(results) - auto),
        ("False friends (same name, different meaning)", ff),
        *[(f"Match type: {k}", v) for k, v in sorted(counts.items())],
        ("", None),
        ("How to use", None),
        ("1. Review rows on the Mapping sheet, conflicts first (red).", None),
        ("2. Fill the teal columns: decision, target, business rules, the six stress-test answers, transform, sign-offs.", None),
        ("   Stress-test cells MergeGuard already found different are pre-set to Differs. Blank cells are open questions.", None),
        ("   trap_identified turns YES when any stress-test answer is Differs, OPEN while any is blank.", None),
        ("3. Save the file and run: mergeguard apply review.xlsx <source> <target> --parallel <mock conversion>", None),
        ("   The gate blocks undecided rows, unsigned risky rows and broken transforms before anything moves.", None),
        ("Conflicts and false friends need a named approver before migration.", None),
    ]
    for r, (k, v) in enumerate(lines, 1):
        sm.cell(row=r, column=1, value=k)
        if v is not None:
            sm.cell(row=r, column=2, value=v)
    sm["A1"].font = Font(bold=True, size=14)
    sm.column_dimensions["A"].width = 70
    sm.column_dimensions["B"].width = 10
    wb.save(path)
    return path


def write_json(results: list[Match], path: str | Path) -> Path:
    path = Path(path)
    data = [{"source": m.source, "target": m.target, "score": round(float(m.score), 4), "match_type": m.match_type,
             "flags": m.flags, "false_friend": m.false_friend, "ddr": m.ddr, "transform": m.transform,
             "alternatives": m.alternatives, "auto_accept": m.auto_accept,
             "signals": {k: (round(float(v), 4) if v is not None else None) for k, v in m.signals.items()}}
            for m in results]
    path.write_text(json.dumps(data, indent=2, default=str))
    return path
