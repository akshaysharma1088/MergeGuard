"""Scenario L from the fourth practitioner trap list (experiments/practitioner_inputs/traps_round4.txt).

Written after MergeGuard v0.0.7 was frozen. Lakeside Federal (acquirer) buys Oak Hollow Bank (acquired).
Traps tagged L1..L15 in list order. "loaded" marks target fields a real target system stores as loaded
rather than recomputing in a parallel run.
"""
from __future__ import annotations

SPEC_L = {
    "names": ("lakeside_oakhollow", "Lakeside Federal", "Oak Hollow Bank"),
    "dialects": ("oracle", "snowflake"),
    "loaded": ["deposit_account.overdraft_limit", "deposit_account.mailing_address", "loan.prepayment_penalty_flag",
               "loan.autopay_amount", "customer.credit_score"],
    "entities": [
        {"name": "customer", "per_base": 1.0,
         "latent": {"nm": "name:full", "dob": "date:1945-01-01..2004-12-31", "u_dec": "uniform:0~1",
                    "fico": "normal:715,55", "drift": "normal:0,35", "u_bk": "uniform:0~1"},
         "target": {"table": "customer", "key": "customer_id", "columns": [
             ("customer_id", "NUMBER(38,0)", "Customer identifier", "ID"),
             ("full_name", "VARCHAR(120)", "Customer name", "nm"),
             ("birth_date", "DATE", "Date of birth", "dob"),
             ("is_deceased", "BOOLEAN", "Deceased: death certificate verified by legal operations", "u_dec < 0.018"),   # L11
             ("credit_score", "NUMBER(3,0)", "FICO 8 at origination; never refreshed", "fico.clip(300, 850).round().astype(int)"),  # L9
             ("in_bankruptcy", "BOOLEAN", "Borrower currently under an active bankruptcy court stay", "u_bk < 0.015")]},  # L15
         "source": {"table": "CUST", "key": "CUST_NO", "columns": [
             ("CUST_NO", "NUMBER(10)", "Customer number", "ID"),
             ("CUST_NM", "VARCHAR2(120)", "Customer name", "nm"),
             ("BIRTH_DT", "DATE", "Birth date", "dob"),
             ("DECEASED_IND", "CHAR(1)", "Deceased indicator", "where(u_dec < 0.03, 'Y', 'N')"),                          # L11
             ("CR_SCORE", "NUMBER(3)", "Credit score", "(fico + drift).clip(300, 850).round().astype(int)"),               # L9
             ("BKRPT_IND", "CHAR(1)", "Bankruptcy", "where(u_bk < 0.06, 'Y', 'N')")]}},                                    # L15
        {"name": "deposit", "per_base": 1.2,
         "latent": {"owner": "fk:customer", "opened": "date:2008-01-01..2026-09-30", "od": "money:500,sigma=0.5",
                    "sweep": "money:3000,sigma=1.0;null:0.6", "joint": "bool:0.3",
                    "addr1": "pattern:#### AAAAAA Rd", "addr2": "pattern:## AAAAA Ave", "bal": "money:4200,sigma=1.2"},
         "target": {"table": "deposit_account", "key": "account_id", "columns": [
             ("account_id", "NUMBER(38,0)", "Deposit account identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Primary tax-reporting owner", "owner"),
             ("open_date", "DATE", "Open date", "opened"),
             ("ledger_balance", "NUMBER(14,2)", "Ledger balance", "bal"),
             ("overdraft_limit", "NUMBER(10,2)", "Standalone checking overdraft cap", "od"),                              # L3
             ("mailing_address", "VARCHAR(120)", "Mailing address of the primary tax-reporting owner", "addr1")]},        # L10
         "source": {"table": "DDA_ACCT", "key": "ACCT_NO", "columns": [
             ("ACCT_NO", "NUMBER(10)", "Account number", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "owner"),
             ("OPEN_DT", "DATE", "Open date", "opened"),
             ("LEDGER_BAL", "NUMBER(14,2)", "Ledger balance", "bal"),
             ("OD_LMT", "NUMBER(10,2)", "Overdraft limit", "(od + sweep.fillna(0)).round(2)"),                           # L3
             ("MAIL_ADDR", "VARCHAR2(120)", "Mailing address", "where(joint, addr2, addr1)")]}},                           # L10
        {"name": "check", "per_base": 3.0,
         "latent": {"acct": "fk:deposit", "serial": "int:1001-9999", "rdc": "bool:0.4", "seq": "int:100000-999999",
                    "amt": "money:240,sigma=1.0"},
         "target": {"table": "check_item", "key": "item_id", "columns": [
             ("item_id", "NUMBER(38,0)", "Check item identifier", "ID"),
             ("account_id", "NUMBER(38,0)", "Account", "acct"),
             ("check_amount", "NUMBER(12,2)", "Check amount", "amt"),
             ("check_number", "NUMBER(10,0)", "Serial number printed on the paper check", "serial")]},                   # L4
         "source": {"table": "CHK_ITEM", "key": "ITEM_ID", "columns": [
             ("ITEM_ID", "NUMBER(12)", "Item id", "ID"),
             ("ACCT_NO", "NUMBER(10)", "Account number", "acct"),
             ("CHK_AMT", "NUMBER(12,2)", "Check amount", "amt"),
             ("CHK_NBR", "NUMBER(10)", "Check number", "where(rdc, seq, serial)")]}},                                     # L4
        {"name": "stop", "per_base": 0.2,
         "latent": {"acct": "fk:deposit", "req": "date:2025-03-01..2026-10-30", "auto": "bool:0.4"},
         "target": {"table": "stop_payment", "key": "stop_id", "columns": [
             ("stop_id", "NUMBER(38,0)", "Stop payment identifier", "ID"),
             ("account_id", "NUMBER(38,0)", "Account", "acct"),
             ("request_date", "DATE", "Customer request date", "req"),
             ("expiry_date", "DATE", "Six months after the request", "req + days(182)")]},                                # L5
         "source": {"table": "STOP_PMT", "key": "STOP_ID", "columns": [
             ("STOP_ID", "NUMBER(10)", "Stop id", "ID"),
             ("ACCT_NO", "NUMBER(10)", "Account number", "acct"),
             ("REQ_DT", "DATE", "Request date", "req"),
             ("EXPR_DT", "DATE", "Expiry date",
              "req + days(182 * where(auto, np.maximum(np.ceil(((AS_OF - pd.to_datetime(req)).dt.days + 1) / 182), 1), 1))")]}},  # L5
        {"name": "loan", "per_base": 0.8,
         "latent": {"owner": "fk:customer", "bal": "money:150000,sigma=0.6", "rate": "uniform:0.04~0.09",
                    "dip": "int:28-31", "inst": "money:1200,sigma=0.4", "pdn": "code:0=0.85|1=0.1|2=0.05",
                    "fee": "code:25=0.5|40=0.5", "clause": "bool:0.3", "orig": "date:2019-01-01..2026-09-30",
                    "ppy": "code:3=0.5|5=0.5", "dpd": "code:0=0.86|15=0.04|45=0.03|95=0.04|130=0.03",
                    "downgraded": "bool:0.5", "disb": "money:4800,sigma=0.4", "cush": "uniform:0~1",
                    "full": "bool:0.35"},
         "target": {"table": "loan", "key": "loan_id", "columns": [
             ("loan_id", "NUMBER(38,0)", "Loan identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Borrower", "owner"),
             ("principal_balance", "NUMBER(14,2)", "Principal balance", "bal"),
             ("interest_rate", "NUMBER(6,4)", "Note rate", "rate.round(4)"),
             ("accrued_interest", "NUMBER(12,2)", "Interest accrued this period, actual/360", "(bal * rate * dip / 360).round(2)"),  # L1
             ("minimum_payment_due", "NUMBER(12,2)", "Current billed installment", "inst"),                               # L2
             ("prepayment_penalty_flag", "BOOLEAN", "Note includes a prepayment penalty clause", "clause"),              # L6
             ("is_non_accrual", "BOOLEAN", "Non-accrual: 90 or more days past due", "dpd.astype(int) >= 90"),            # L7
             ("escrow_cushion", "NUMBER(10,2)", "RESPA maximum cushion: two months of escrow disbursements",
              "(disb / 6).round(2)"),                                                                                     # L8
             ("autopay_amount", "NUMBER(10,2)", "Autopay amount set by the borrower", "inst")]},                           # L12
         "source": {"table": "LN_MSTR", "key": "LN_NO", "columns": [
             ("LN_NO", "NUMBER(10)", "Loan number", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "owner"),
             ("PRIN_BAL", "NUMBER(14,2)", "Principal balance", "bal"),
             ("INT_RT", "NUMBER(6,4)", "Interest rate", "rate.round(4)"),
             ("ACCR_INT", "NUMBER(12,2)", "Accrued interest", "(bal * rate * dip / 365).round(2)"),                       # L1
             ("MIN_PMT_DUE", "NUMBER(12,2)", "Minimum payment due",
              "(inst * (1 + pdn.astype(int)) + fee.astype(int) * (pdn.astype(int) > 0)).round(2)"),                      # L2
             ("PPMT_PNLTY_IND", "CHAR(1)", "Prepayment penalty",
              "where(clause & ((pd.to_datetime(orig) + pd.to_timedelta(ppy.astype(int) * 365, unit='D')) > AS_OF), 'Y', 'N')"),  # L6
             ("NON_ACCR_IND", "CHAR(1)", "Non-accrual", "where((dpd.astype(int) >= 90) & downgraded, 'Y', 'N')"),        # L7
             ("ESCR_CUSH_AMT", "NUMBER(10,2)", "Escrow cushion", "(disb / 6 * cush).round(2)"),                           # L8
             ("AUTOPAY_AMT", "NUMBER(10,2)", "Autopay amount", "where(full, 0.0, inst)")]}},                               # L12
        {"name": "box", "per_base": 0.1,
         "latent": {"keys": "bool:0.9", "rent_dpd": "code:0=0.85|30=0.07|75=0.08", "size": "code:S=0.5|M=0.35|L=0.15"},
         "target": {"table": "safe_deposit_box", "key": "box_id", "columns": [
             ("box_id", "NUMBER(38,0)", "Box identifier", "ID"),
             ("box_size", "VARCHAR(1)", "Box size", "size"),
             ("box_status", "VARCHAR(12)", "RENTED while the keys are out", "where(keys, 'RENTED', 'AVAILABLE')")]},     # L13
         "source": {"table": "SDB", "key": "BOX_NO", "columns": [
             ("BOX_NO", "NUMBER(8)", "Box number", "ID"),
             ("BOX_SZ", "CHAR(1)", "Size", "size"),
             ("BOX_STAT", "VARCHAR2(20)", "Box status",
              "where(keys & (rent_dpd.astype(int) >= 60), 'DELINQ_ESCHEAT', where(keys, 'RENTED', 'AVAILABLE'))")]}},    # L13
        {"name": "wire", "per_base": 2.0,
         "latent": {"cust": "fk:customer", "submit": "timestamp:2026-09-01..2026-10-30", "ofac": "int:2-240",
                    "amt": "money:25000,sigma=1.0"},
         "target": {"table": "wire_transfer", "key": "wire_id", "columns": [
             ("wire_id", "NUMBER(38,0)", "Wire identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Customer", "cust"),
             ("wire_amount", "NUMBER(14,2)", "Wire amount", "amt"),
             ("cutoff_ts", "TIMESTAMP_NTZ", "When the customer submitted the wire in the treasury portal", "submit")]},   # L14
         "source": {"table": "WIRE_TXN", "key": "WIRE_ID", "columns": [
             ("WIRE_ID", "NUMBER(12)", "Wire id", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "cust"),
             ("WIRE_AMT", "NUMBER(14,2)", "Wire amount", "amt"),
             ("CUTOFF_TS", "TIMESTAMP", "Cutoff timestamp", "submit + pd.to_timedelta(ofac, unit='m')")]}},              # L14
    ],
    "derivations": {
        "target": {
            "loan.accrued_interest": "SELECT l.loan_id, l.principal_balance * l.interest_rate * l.days_in_period / 360 AS accrued_interest FROM loan l",
            "loan.is_non_accrual": "SELECT l.loan_id, l.days_past_due >= 90 AS is_non_accrual FROM loan l",
        },
        "source": {
            "LN_MSTR.ACCR_INT": "SELECT l.LN_NO, l.PRIN_BAL * l.INT_RT * l.DAYS_IN_PRD / 365 AS ACCR_INT FROM LN_MSTR l",
            "LN_MSTR.MIN_PMT_DUE": "SELECT l.LN_NO, l.CURR_INSTL + l.PAST_DUE_AMT + l.LATE_FEE_AMT AS MIN_PMT_DUE FROM LN_BILL l",
            "DDA_ACCT.OD_LMT": "SELECT a.ACCT_NO, a.BOUNCE_LMT + NVL(s.SWEEP_BAL, 0) AS OD_LMT FROM DDA_RAW a LEFT JOIN SWEEP s ON s.ACCT_NO = a.ACCT_NO",
            "WIRE_TXN.CUTOFF_TS": "SELECT w.WIRE_ID, w.OFAC_CLEAR_TS AS CUTOFF_TS FROM WIRE_RAW w",
        },
    },
    "truth": [
        ("CUST.CUST_NO", "customer.customer_id", "exact", [], None),
        ("CUST.CUST_NM", "customer.full_name", "exact", [], None),
        ("CUST.BIRTH_DT", "customer.birth_date", "exact", [], None),
        ("CUST.DECEASED_IND", "customer.is_deceased", "conflict", ["population"], None),
        ("CUST.CR_SCORE", "customer.credit_score", "conflict", ["methodology"], None),
        ("CUST.BKRPT_IND", "customer.in_bankruptcy", "conflict", ["population"], None),
        ("DDA_ACCT.ACCT_NO", "deposit_account.account_id", "exact", [], None),
        ("DDA_ACCT.CUST_NO", "deposit_account.customer_id", "exact", [], None),
        ("DDA_ACCT.OPEN_DT", "deposit_account.open_date", "exact", [], None),
        ("DDA_ACCT.LEDGER_BAL", "deposit_account.ledger_balance", "exact", [], None),
        ("DDA_ACCT.OD_LMT", "deposit_account.overdraft_limit", "conflict", ["inclusion"], None),
        ("DDA_ACCT.MAIL_ADDR", "deposit_account.mailing_address", "conflict", ["role"], None),
        ("CHK_ITEM.ITEM_ID", "check_item.item_id", "exact", [], None),
        ("CHK_ITEM.ACCT_NO", "check_item.account_id", "exact", [], None),
        ("CHK_ITEM.CHK_AMT", "check_item.check_amount", "exact", [], None),
        ("CHK_ITEM.CHK_NBR", "check_item.check_number", "conflict", ["identity"], None),
        ("STOP_PMT.STOP_ID", "stop_payment.stop_id", "exact", [], None),
        ("STOP_PMT.ACCT_NO", "stop_payment.account_id", "exact", [], None),
        ("STOP_PMT.REQ_DT", "stop_payment.request_date", "exact", [], None),
        ("STOP_PMT.EXPR_DT", "stop_payment.expiry_date", "conflict", ["temporal"], None),
        ("LN_MSTR.LN_NO", "loan.loan_id", "exact", [], None),
        ("LN_MSTR.CUST_NO", "loan.customer_id", "exact", [], None),
        ("LN_MSTR.PRIN_BAL", "loan.principal_balance", "exact", [], None),
        ("LN_MSTR.INT_RT", "loan.interest_rate", "exact", [], None),
        ("LN_MSTR.ACCR_INT", "loan.accrued_interest", "conflict", ["methodology"], None),
        ("LN_MSTR.MIN_PMT_DUE", "loan.minimum_payment_due", "conflict", ["inclusion"], None),
        ("LN_MSTR.PPMT_PNLTY_IND", "loan.prepayment_penalty_flag", "conflict", ["population"], None),
        ("LN_MSTR.NON_ACCR_IND", "loan.is_non_accrual", "conflict", ["population"], None),
        ("LN_MSTR.ESCR_CUSH_AMT", "loan.escrow_cushion", "conflict", ["methodology"], None),
        ("LN_MSTR.AUTOPAY_AMT", "loan.autopay_amount", "conflict", ["null_semantics"], None),
        ("SDB.BOX_NO", "safe_deposit_box.box_id", "exact", [], None),
        ("SDB.BOX_SZ", "safe_deposit_box.box_size", "exact", [], None),
        ("SDB.BOX_STAT", "safe_deposit_box.box_status", "conflict", ["population"], None),
        ("WIRE_TXN.WIRE_ID", "wire_transfer.wire_id", "exact", [], None),
        ("WIRE_TXN.CUST_NO", "wire_transfer.customer_id", "exact", [], None),
        ("WIRE_TXN.WIRE_AMT", "wire_transfer.wire_amount", "exact", [], None),
        ("WIRE_TXN.CUTOFF_TS", "wire_transfer.cutoff_ts", "conflict", ["temporal"], None),
    ],
}
