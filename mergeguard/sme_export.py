"""Fill the Banking Semantic Data Mapping & SME Sign-Off workbook from MergeGuard results.

MergeGuard writes what the data can show: the technical baseline (group A), business rules from the
data dictionary and derivations (group B), mismatches its detectors found in the stress-test columns
(group C), and a trap verdict with suggested transformation logic (group D). Lifecycle, granularity,
downstream consumers, edge cases and every sign-off (group E) stay with the SMEs. No row is ever
marked Approved: the gate starts at Blocked, Pending or Draft.
"""
from __future__ import annotations

import re
from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.cell_range import MultiCellRange

from .cards import Side
from .match import Match

TEMPLATE = Path(__file__).parent / "templates" / "Banking_Semantic_Data_Mapping_and_SME_SignOff_Template.xlsx"
MATRIX, DASH, REF = "Semantic Mapping Matrix", "Executive Dashboard", "Dropdowns & Reference"
FIRST = 5

DOMAIN_WORDS = [
    ("Mortgages & Escrow", ("mortgage", "mtg", "escrow", "hmda")),
    ("Cards & Payments", ("card", "crd", "mcc")),
    ("Deposits & ACH", ("deposit", "dep", "dda", "ach", "pmt", "payment", "sav")),
    ("Commercial & Syndicated Loans", ("synd", "commercial", "lease", "loan", "ln", "lc", "auto", "stu")),
    ("Wealth, Treasury & FX", ("portf", "portfolio", "trade", "trd", "fx", "wealth", "client", "clnt")),
    ("AML, Fraud & Compliance", ("fraud", "frd", "aml", "ctr", "sar", "pep", "kyc")),
    ("Capital Markets & Risk (RWA/CECL)", ("repo", "swap", "bond", "cpty", "margin", "mrgn", "rwa", "cecl", "line")),
]
DEFAULT_DOMAIN = "Core Ledger & Customer CIF"

TRAP_CATEGORY = [  # first matching flag wins
    ("sign", "Sign Inversion & Netting Basis"),
    ("inclusion", "Gross vs. Net / Holds Inclusion"),
    ("null_semantics", "Sentinel / Dummy Date Trap"),
    ("grain", "Aggregation Scope & Entity Granularity"),
    ("temporal", "Event Trigger Timing Mismatch"),
    ("population", "Channel Scope & Boolean Meaning"),
    ("scale", "Scale & Precision Factor (100x)"),
    ("unit", "Scale & Precision Factor (100x)"),
    ("definition", "Gross vs. Net / Holds Inclusion"),
    ("aggregation", "Aggregation Scope & Entity Granularity"),
    ("identity", "ID Persistence & Entity Granularity"),
]
CRITICAL = {"population", "grain", "null_semantics", "inclusion", "temporal", "definition", "sign", "aggregation", "identity"}
VERIFY_STRESS = {"temporal": "I", "population": "I", "inclusion": "L", "aggregation": "L", "definition": "L",
                 "sign": "M", "scale": "M", "unit": "M", "format": "M", "null_semantics": "N"}


def domain_for(table: str) -> str:
    toks = re.split(r"[^a-z]+", table.lower())
    for dom, words in DOMAIN_WORDS:
        if any(w in toks or any(t.startswith(w) for t in toks if len(w) >= 4) for w in words):
            return dom
    return DEFAULT_DOMAIN


def _rule(card) -> str | None:
    if card is None:
        return None
    return card.description + (f" | Derived: {card.derivation}" if card.derivation else "")


def _verdict(m: Match) -> tuple[str | None, str | None, str]:
    flags = set(m.flags) | set((m.false_friend or {}).get("reasons", []))
    category = next((c for f, c in TRAP_CATEGORY if f in flags), None)
    if m.identifier and not category:
        category = "ID Persistence & Entity Granularity"
    if flags & CRITICAL or m.match_type == "conflict" or m.false_friend:
        return category, "YES - CRITICAL", "Blocked - Trap Unresolved"
    if flags - {"cast"} or m.match_type in ("transform", "structural"):
        return category, "YES - MODERATE", "Pending SME Sign-Off"
    if m.auto_accept:
        return "No Trap - Semantically Aligned", "NO - ALIGNED", "Pending SME Sign-Off"
    return category, None, "Draft - Profiling in Progress"


def _stress(m: Match) -> dict:
    flags = set(m.flags) | set((m.false_friend or {}).get("reasons", []))
    ddr = m.ddr or {}
    out = {}
    if "temporal" in flags:
        out["I"] = "Mismatch (MergeGuard): dates come from a different business event or are shifted"
    if "population" in flags:
        rate = f" Target rule flips {ddr['rate']:.1%} of source records." if ddr.get("available") and "rate" in ddr else ""
        out["I"] = "Mismatch (MergeGuard): different rule decides who qualifies." + rate
    if "grain" in flags:
        out["L"] = "Mismatch (MergeGuard): aggregated at a different level (see granularity)"
    if "inclusion" in flags or "definition" in flags:
        out["L"] = "Mismatch (MergeGuard): one side includes components or nets amounts the other does not"
    if flags & {"sign", "unit", "scale", "format"}:
        parts = [p for p, f in (("sign convention", "sign"), ("unit", "unit"), ("scale", "scale"), ("format", "format")) if f in flags]
        out["M"] = "Mismatch (MergeGuard): " + ", ".join(parts) + " differs"
    if "null_semantics" in flags:
        out["N"] = "Mismatch (MergeGuard): NULL, zero or placeholder values mean different things"
    return out


def _copy_style(ws, src_row: int, dst_row: int, ncols: int = 22) -> None:
    for c in range(1, ncols + 1):
        s, d = ws.cell(row=src_row, column=c), ws.cell(row=dst_row, column=c)
        d.font, d.fill, d.border = copy(s.font), copy(s.fill), copy(s.border)
        d.alignment, d.number_format = copy(s.alignment), s.number_format
    ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height


def export_sme(results: list[Match], src: Side, tgt: Side, path, template=TEMPLATE, prefix: str = "MG",
               checks: dict | None = None, scorecard_path=None) -> Path:
    wb = load_workbook(template)
    ws = wb[MATRIX]
    style_row = FIRST + 1
    old_last = ws.max_row
    for r in range(FIRST, old_last + 1):                      # clear the worked examples
        for c in range(1, 23):
            ws.cell(row=r, column=c).value = None
    order = {"conflict": 0, "unmatched": 1, "transform": 2, "structural": 3, "exact": 4}
    rows = sorted(results, key=lambda m: (order[m.match_type], m.source))
    last = FIRST + len(rows) - 1
    for i, m in enumerate(rows):
        r = FIRST + i
        _copy_style(ws, style_row, r)
        s_card = src.card(m.source)
        t_card = tgt.card(m.target) if m.target and "+" not in m.target else None
        category, flag, gate = _verdict(m)
        stress = _stress(m)
        logic = m.transform or ""
        if m.false_friend:
            ff = m.false_friend
            logic = (f"False friend of {ff['target']} ({', '.join(ff['reasons']) or 'meaning differs'}). " + logic).strip()
        if m.identifier:
            logic = (logic + " Confirm ID persistence across reissue, modification and rollover.").strip()
        values = {
            "A": f"{prefix}-{i + 1:04d}", "B": domain_for(s_card.table), "C": m.source, "D": m.target or "(no target)",
            "E": f"{s_card.sql_type} -> {t_card.sql_type}" if t_card else s_card.sql_type,
            "F": _rule(s_card), "G": _rule(t_card),
            "I": stress.get("I"), "L": stress.get("L"), "M": stress.get("M"), "N": stress.get("N"),
            "O": category, "P": flag, "Q": logic or None, "V": gate,
        }
        c = (checks or {}).get(m.source)
        if c is not None and c.status in ("FAIL", "REVIEW"):
            for f in c.flags:
                col = VERIFY_STRESS.get(f)
                if col:
                    values[col] = f"Trial load ({c.status}): {c.diagnosis}"
            values["Q"] = ((values["Q"] or "") + f" Trial load {c.status}: {c.mismatch_rate:.1%} of {c.records:,} "
                           f"matched records differ. {c.diagnosis}").strip()
            values["R"] = ", ".join(c.edge_cases) or None
            if c.status == "FAIL":
                cat = next((cc for f, cc in TRAP_CATEGORY if f in c.flags), values["O"])
                values.update(O=cat, P="YES - CRITICAL", V="Blocked - Trap Unresolved")
        for col, v in values.items():
            ws[f"{col}{r}"] = v
    if last < old_last:
        for r in range(last + 1, old_last + 1):
            ws.row_dimensions[r].height = ws.row_dimensions[style_row].height
    end = max(last, old_last)
    # stretch validations, conditional formats and the dashboard to the new row count
    for dv in ws.data_validations.dataValidation:
        col = str(dv.sqref).split(":")[0].rstrip("0123456789")
        dv.sqref = MultiCellRange(f"{col}{FIRST}:{col}{end}")
    old_cf = list(ws.conditional_formatting._cf_rules.items())
    ws.conditional_formatting._cf_rules.clear()
    for rng, rules in old_cf:
        col = str(rng.sqref).split(":")[0].rstrip("0123456789")
        for rule in rules:
            ws.conditional_formatting.add(f"{col}{FIRST}:{col}{end}", rule)
    ws.auto_filter.ref = f"A4:V{end}"
    dash = wb[DASH]
    for row in dash.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.value = re.sub(r"(\$?[A-V]\$?)(29|30)\b", lambda mm: f"{mm.group(1)}{end}", c.value)
    # evidence sheet: what MergeGuard measured for each Mapping_ID
    ev = wb.create_sheet("MergeGuard Evidence")
    head = ["Mapping_ID", "Source", "Target", "Score", "Match type", "Flags", "False friend", "Disagreement rate",
            "Name", "Definition", "Type", "Value", "Logic", "Context", "Alternatives"]
    for j, h in enumerate(head, 1):
        cell = ev.cell(row=1, column=j, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F2A37")
    for i, m in enumerate(rows, 2):
        sig = m.signals or {}
        ddr = m.ddr or {}
        vals = [f"{prefix}-{i - 1:04d}", m.source, m.target, round(float(m.score), 3), m.match_type, ", ".join(m.flags),
                (m.false_friend or {}).get("target"),
                f"{ddr['rate']:.1%} of {ddr.get('entities', 0):,}" if ddr.get("available") and "rate" in ddr else None,
                *[round(float(sig[k]), 2) if sig.get(k) is not None else None
                  for k in ("name", "definition", "type", "value", "logic", "context")],
                "; ".join(m.alternatives)]
        for j, v in enumerate(vals, 1):
            ev.cell(row=i, column=j, value=v).alignment = Alignment(vertical="top", wrap_text=j in (6, 15))
    for j, w in enumerate([12, 30, 34, 8, 11, 26, 30, 18, 7, 9, 7, 7, 7, 8, 50], 1):
        ev.column_dimensions[ev.cell(row=1, column=j).column_letter].width = w
    ev.freeze_panes = "B2"
    if checks:
        vs = wb.create_sheet("Trial-Load Verification")
        head = ["Mapping_ID", "Source", "Target", "Status", "Mismatch rate", "Records", "Diagnosis", "Edge-case keys", "SQL"]
        for j, h in enumerate(head, 1):
            cell = vs.cell(row=1, column=j, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F2A37")
        fills = {"FAIL": "FDE2E1", "REVIEW": "FEF3C7", "PASS": "DCFCE7"}
        for i, m in enumerate(rows, 2):
            c = checks.get(m.source)
            if c is None:
                continue
            vals = [f"{prefix}-{i - 1:04d}", c.source, c.target, c.status, c.mismatch_rate, c.records, c.diagnosis,
                    ", ".join(c.edge_cases), c.sql]
            for j, v in enumerate(vals, 1):
                cell = vs.cell(row=i, column=j, value=v)
                cell.alignment = Alignment(vertical="top", wrap_text=j in (7, 9))
            if c.status in fills:
                vs.cell(row=i, column=4).fill = PatternFill("solid", fgColor=fills[c.status])
        for j, w in enumerate([12, 28, 32, 9, 12, 9, 60, 30, 60], 1):
            vs.column_dimensions[vs.cell(row=1, column=j).column_letter].width = w
        vs.freeze_panes = "B2"
        if scorecard_path:
            from .verify import scorecard_sql
            ordered = [checks[m.source] for m in rows if m.source in checks]
            Path(scorecard_path).write_text(scorecard_sql(ordered, prefix))
    path = Path(path)
    wb.save(path)
    return path
