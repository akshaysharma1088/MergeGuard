import json, random
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side as XSide
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

pool = {r["source"]: r for r in json.load(open('/tmp/study_pool.json'))}

X_traps = ["CUST.DECEASED_IND","DDA_ACCT.MAIL_ADDR","STOP_PMT.EXPR_DT","LN_MSTR.MIN_PMT_DUE","LN_MSTR.ESCR_CUSH_AMT","SDB.BOX_STAT"]
Y_traps = ["DDA_ACCT.OD_LMT","CHK_ITEM.CHK_NBR","LN_MSTR.ACCR_INT","LN_MSTR.NON_ACCR_IND","LN_MSTR.AUTOPAY_AMT","WIRE_TXN.CUTOFF_TS"]
X_clean = ["CUST.CUST_NO","CUST.BIRTH_DT","DDA_ACCT.ACCT_NO","STOP_PMT.STOP_ID","LN_MSTR.INT_RT","SDB.BOX_SZ"]
Y_clean = ["CUST.CUST_NM","CUST.CR_SCORE","CHK_ITEM.ITEM_ID","LN_MSTR.LN_NO","LN_MSTR.PPMT_PNLTY_IND","WIRE_TXN.WIRE_ID"]
X = X_traps + X_clean
Y = Y_traps + Y_clean

FONT = "Arial"
HEAD = Font(name=FONT, bold=True, size=10, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="2F5597")
BODY = Font(name=FONT, size=10)
BODY_B = Font(name=FONT, size=10, bold=True)
NOTE = Font(name=FONT, size=10, italic=True, color="1F6F3E")
WRAP = Alignment(wrap_text=True, vertical="top")
WRAP_C = Alignment(wrap_text=True, vertical="top", horizontal="center")
thin = XSide(style="thin", color="D9D9D9")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)

def card_text(row, side):
    name = row["source"] if side == "source" else row["target"]
    key = "src" if side == "source" else "tgt"
    desc = row[f"{key}_desc"] or "(no description given)"
    samples = ", ".join(row["samples"]) if side == "source" and row.get("samples") else ""
    txt = f"{name}\n{desc}"
    if samples:
        txt += f"\nSample values: {samples}"
    return txt

def build_sheet(wb, title, items, diagnosis_set, rng):
    ws = wb.create_sheet(title)
    ws.sheet_view.showGridLines = False
    headers = ["#", "Source column (acquired bank)", "Target column (acquiring bank)",
               "System note (only shown for some pairs)", "Your decision", "Confidence (1-5)"]
    widths = [4, 34, 34, 42, 16, 14]
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=5, column=i, value=h)
        c.font = HEAD
        c.fill = HEAD_FILL
        c.alignment = WRAP_C
        c.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = w

    order = items[:]
    rng.shuffle(order)
    dv = DataValidation(type="list", formula1='"Approve,Reject,Need more info"', allow_blank=True)
    ws.add_data_validation(dv)
    conf = DataValidation(type="list", formula1='"1,2,3,4,5"', allow_blank=True)
    ws.add_data_validation(conf)

    r = 6
    for n, key in enumerate(order, 1):
        row = pool[key]
        ws.cell(row=r, column=1, value=n).font = BODY_B
        c2 = ws.cell(row=r, column=2, value=card_text(row, "source")); c2.font = BODY; c2.alignment = WRAP
        c3 = ws.cell(row=r, column=3, value=card_text(row, "target")); c3.font = BODY; c3.alignment = WRAP
        note = row["diagnosis"] if (key in diagnosis_set and row["diagnosis"]) else ""
        c4 = ws.cell(row=r, column=4, value=note); c4.font = NOTE; c4.alignment = WRAP
        c5 = ws.cell(row=r, column=5); c5.alignment = WRAP_C
        c6 = ws.cell(row=r, column=6); c6.alignment = WRAP_C
        dv.add(c5)
        conf.add(c6)
        for col in range(1, 7):
            ws.cell(row=r, column=col).border = BORDER
        ws.row_dimensions[r].height = 56
        r += 1

    ws.cell(row=1, column=1, value=f"{title}: column-mapping review").font = Font(name=FONT, bold=True, size=14)
    ws.cell(row=2, column=1, value=("For each row, decide whether you would APPROVE this mapping as written, REJECT it, "
            "or mark NEED MORE INFO before you'd sign off. A few rows include a system-generated note about what was "
            "found when the same records were compared on both sides after a test load; most rows have no such note. "
            "Please don't skip rows, and don't look anything up — judge from what's on the sheet.")).font = Font(name=FONT, italic=True, size=10)
    ws.cell(row=2, column=1).alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=6)
    ws.row_dimensions[2].height = 48
    ws.cell(row=3, column=1, value="Your background (one line, anonymous — e.g. \"data engineer, 8 years, lending systems\"):").font = Font(name=FONT, size=10, bold=True)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=4)
    ws.cell(row=4, column=5, value="Total time (minutes):").font = Font(name=FONT, size=10, bold=True)
    ws.freeze_panes = "A6"
    return ws

wb = openpyxl.Workbook()
wb.remove(wb.active)

build_sheet(wb, "Form 1", X + Y, diagnosis_set=set(Y), rng=random.Random(11))
build_sheet(wb, "Form 2", X + Y, diagnosis_set=set(X), rng=random.Random(22))

ins = wb.create_sheet("Read me first", 0)
ins.sheet_view.showGridLines = False
ins.column_dimensions["A"].width = 100
lines = [
 ("Thanks for doing this", True, 14),
 ("", False, 10),
 ("This is a short, anonymous exercise for a research study on reviewing data-mapping decisions after a "
  "bank acquisition. It should take 20–30 minutes. Nothing here identifies you, your employer, or any "
  "real bank — all data is synthetic (two made-up banks, “Lakeside Federal” and “Oak Hollow Bank”).", False, 11),
 ("", False, 10),
 ("What to do", True, 12),
 ("1. Open the sheet you were sent — either “Form 1” or “Form 2”, not both. If you weren't told "
  "which one, use Form 1.", False, 11),
 ("2. Fill in the one-line background field at the top (optional, no names).", False, 11),
 ("3. For each of the 24 rows, you'll see a source column and a target column that someone has proposed "
  "mapping to each other during a migration. Some rows also show a system note describing what was found "
  "when the two sides were compared on real test data; most rows don't.", False, 11),
 ("4. For each row, pick Approve, Reject, or Need more info, and optionally a 1–5 confidence rating.", False, 11),
 ("5. Note roughly how long the whole sheet took you, in the box near the top.", False, 11),
 ("6. Send the filled-in file back the way it was shared with you.", False, 11),
 ("", False, 10),
 ("A few notes", True, 12),
 ("There's no trick and no “correct” answer you're expected to know in advance — judge each row on what's "
  "in front of you, the way you would during a real mapping review.", False, 11),
 ("Please don't discuss specific rows with other reviewers before sending this back.", False, 11),
 ("You can stop at any point; a partial sheet is still useful.", False, 11),
]
r = 1
for text, bold, size in lines:
    c = ins.cell(row=r, column=1, value=text)
    c.font = Font(name=FONT, bold=bold, size=size)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ins.row_dimensions[r].height = 18 if not text else (26 if len(text) > 90 else 18)
    r += 1

wb.save('/home/claude/study/MergeGuard_reviewer_study.xlsx')
print("saved")
