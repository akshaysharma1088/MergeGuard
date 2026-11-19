"""Scenario M, from an outside practitioner's trap list (not the author of this tool or benchmark).

The practitioner was given only the bare definition of a semantic trap (no taxonomy, no examples from this
paper or benchmark) and wrote twelve examples from their own experience across core banking, deposits, cards,
lending and mortgage servicing. Their write-up is frozen at experiments/trap_author/ alongside its hash.
Each trap below is a direct encoding of one of their twelve examples; comments give the number in their list.
No derivation SQL is written for any target field (the practitioner's examples describe stored behaviour, not
a recomputation the target system performs), so this scenario tests stage one (profiling) only, like scenario R.

Crestline National (acquirer) buys Vanguard Community Bank (acquired).
"""
from __future__ import annotations

SPEC_M = {
    "names": ("crestline_vanguard", "Crestline National", "Vanguard Community Bank"),
    "dialects": ("oracle", "snowflake"),
    "entities": [
        {"name": "customer", "per_base": 1.0,
         "latent": {"nm": "name:full", "entity_type": "code:person=0.92|business=0.05|trust_estate=0.03",
                    "dob_raw": "date:1945-01-01..2004-12-31", "incorp_dt": "date:1980-01-01..2026-06-30"},
         "target": {"table": "customer", "key": "customer_id", "columns": [
             ("customer_id", "NUMBER(38,0)", "Customer identifier", "ID"),
             ("full_name", "VARCHAR(120)", "Customer name", "nm"),
             ("birth_date", "DATE", "Date of birth; non-null required",
              "where(entity_type == 'person', dob_raw, where(entity_type == 'business', incorp_dt, pd.Timestamp('1900-01-01')))"),  # M12
             ("customer_status", "VARCHAR(1)", "A active, I involuntary close, C closed", "hint:code:A=0.80|I=0.05|C=0.15")]},  # M4
         "source": {"table": "CUST", "key": "CUST_NO", "columns": [
             ("CUST_NO", "NUMBER(10)", "Customer number", "ID"),
             ("CUST_NM", "VARCHAR2(120)", "Customer name", "nm"),
             ("DOB", "DATE", "Date of birth; null for non-personal entities", "dob_raw.where(entity_type == 'person')"),  # M12
             ("CUST_STAT_CD", "CHAR(1)", "A active, I inactive (dormant, open), C closed", "hint:code:A=0.75|I=0.17|C=0.08")]}},  # M4
        {"name": "deposit", "per_base": 1.3,
         "latent": {"owner": "fk:customer", "opened": "date:2008-01-01..2026-09-30", "upgraded": "bool:0.25",
                    "up_days": "int:60-2500", "ledger": "money:3200,sigma=1.0", "holds": "money:150,sigma=1.0;null:0.5",
                    "uncollected": "money:300,sigma=1.2;null:0.7", "cust_evt": "date:2026-01-01..2026-10-30",
                    "extra_days": "int:0-400", "nominal": "uniform:0.005~0.06",
                    "orig_branch": "int:1000-1099", "moved": "bool:0.2", "new_branch": "int:1000-1099"},
         "target": {"table": "deposit", "key": "account_id", "columns": [
             ("account_id", "NUMBER(38,0)", "Deposit account identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Owner", "owner"),
             ("acct_open_date", "DATE", "Open date; overwritten on a product-tier conversion",
              "where(upgraded, opened + days(up_days), opened)"),                                                   # M1
             ("current_balance", "NUMBER(14,2)", "Available balance net of holds and uncollected funds",
              "np.maximum(ledger - holds.fillna(0) - uncollected.fillna(0), 0).round(2)"),                          # M2
             ("last_activity_date", "DATE", "Date of the most recent posting of any kind",
              "cust_evt + days(extra_days)"),                                                                       # M5
             ("interest_rate", "NUMBER(8,6)", "Annual percentage yield, monthly compounding",
              "(((1 + nominal / 12) ** 12) - 1).round(6)"),                                                         # M7
             ("branch_code", "NUMBER(4,0)", "Current servicing branch", "where(moved, new_branch, orig_branch)"),   # M9
             ("account_tier", "VARCHAR(10)", "Pricing tier", "hint:code:BASIC=0.55|PLUS=0.3|PREMIER=0.15")]},
         "source": {"table": "ACCT", "key": "ACCT_NO", "columns": [
             ("ACCT_NO", "NUMBER(10)", "Account number", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "owner"),
             ("OPEN_DT", "DATE", "Date the customer originally opened the account", "opened"),                     # M1
             ("CURR_BAL", "NUMBER(14,2)", "End-of-day ledger balance, posted transactions only", "ledger.round(2)"),  # M2
             ("LAST_TRANS_DT", "DATE", "Date of the most recent customer-initiated transaction", "cust_evt"),       # M5
             ("INT_RATE", "NUMBER(8,6)", "Nominal interest rate", "nominal.round(6)"),                              # M7
             ("BRANCH_ID", "NUMBER(4,0)", "Originating branch", "orig_branch"),                                     # M9
             ("ACCT_TIER_CD", "VARCHAR2(10)", "Pricing tier", "hint:code:BASIC=0.55|PLUS=0.3|PREMIER=0.15")]}},
        {"name": "card", "per_base": 0.6,
         "latent": {"owner": "fk:customer", "limit0": "money:8000,sigma=0.5", "closed": "bool:0.12",
                    "last4": "pattern:####"},
         "target": {"table": "card", "key": "card_id", "columns": [
             ("card_id", "NUMBER(38,0)", "Card identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Owner", "owner"),
             ("credit_limit", "NUMBER(10,2)", "Credit limit, kept as a historical attribute after closure",
              "limit0.round(2)"),                                                                                   # M6
             ("card_status", "VARCHAR(8)", "Card status", "where(closed, 'CLOSED', 'OPEN')"),
             ("card_last4", "VARCHAR(4)", "Last four digits", "last4")]},
         "source": {"table": "CARD", "key": "CARD_ID", "columns": [
             ("CARD_ID", "NUMBER(10)", "Card identifier", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "owner"),
             ("CR_LIMIT_AMT", "NUMBER(10,2)", "Credit limit, zeroed on closure or charge-off",
              "where(closed, 0.0, limit0).round(2)"),                                                               # M6
             ("CARD_STAT_CD", "VARCHAR2(8)", "Card status", "where(closed, 'CLOSED', 'OPEN')"),
             ("CARD_LAST4", "VARCHAR2(4)", "Last four digits", "last4")]}},
        {"name": "loan", "per_base": 0.5,
         "latent": {"owner": "fk:customer", "bal": "money:140000,sigma=0.6", "rate": "uniform:0.04~0.09",
                    "orig": "date:2015-01-01..2026-06-30", "delinquent": "bool:0.15", "since_due_pos": "int:1-150",
                    "chgoff_flag": "bool:0.07", "principal_loss": "money:9000,sigma=0.6",
                    "interest_loss": "money:900,sigma=0.6", "fee_loss": "money:250,sigma=0.6"},
         "target": {"table": "loan", "key": "loan_id", "columns": [
             ("loan_id", "NUMBER(38,0)", "Loan identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Borrower", "owner"),
             ("principal_balance", "NUMBER(14,2)", "Principal balance", "bal.round(2)"),
             ("note_rate", "NUMBER(6,4)", "Note rate", "rate.round(4)"),
             ("origination_date", "DATE", "Origination date", "orig"),
             ("dpd", "NUMBER(5,0)", "Days past due, counted from the end of the 15-day grace period",
              "where(delinquent, np.maximum(since_due_pos - 15, 0), 0)"),                                           # M3
             ("chargeoff_balance", "NUMBER(12,2)", "Gross charge-off: principal, accrued interest and fees",
              "where(chgoff_flag, (principal_loss + interest_loss + fee_loss).round(2), 0.0)")]},                   # M8
         "source": {"table": "LN", "key": "LN_NO", "columns": [
             ("LN_NO", "NUMBER(10)", "Loan number", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "owner"),
             ("PRIN_BAL", "NUMBER(14,2)", "Principal balance", "bal.round(2)"),
             ("INT_RT", "NUMBER(6,4)", "Interest rate", "rate.round(4)"),
             ("ORIG_DT", "DATE", "Origination date", "orig"),
             ("DAYS_PAST_DUE", "NUMBER(5,0)", "Days past due, counted from the day after the due date",
              "where(delinquent, since_due_pos, 0)"),                                                               # M3
             ("CHG_OFF_AMT", "NUMBER(12,2)", "Charge-off amount, principal only",
              "where(chgoff_flag, principal_loss.round(2), 0.0)")]}},                                               # M8
        {"name": "mortgage", "per_base": 0.3,
         "latent": {"owner": "fk:customer", "pi": "money:1450,sigma=0.4", "escrow": "money:380,sigma=0.6;null:0.2",
                    "orig": "date:2012-01-01..2026-06-30"},
         "target": {"table": "mortgage", "key": "mortgage_id", "columns": [
             ("mortgage_id", "NUMBER(38,0)", "Mortgage identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Borrower", "owner"),
             ("origination_date", "DATE", "Origination date", "orig"),
             ("property_state", "VARCHAR(2)", "Property state", "hint:code:IL=0.2|TX=0.15|CA=0.15|FL=0.12|OH=0.1|OTH=0.28"),
             ("last_payment_amount", "NUMBER(10,2)", "Most recent payment, full PITI including escrow",
              "(pi + escrow.fillna(0)).round(2)")]},                                                                # M10
         "source": {"table": "MTG", "key": "MTG_NO", "columns": [
             ("MTG_NO", "NUMBER(10)", "Mortgage number", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "owner"),
             ("ORIG_DT", "DATE", "Origination date", "orig"),
             ("PROP_ST_CD", "VARCHAR2(2)", "Property state", "hint:code:IL=0.2|TX=0.15|CA=0.15|FL=0.12|OH=0.1|OTH=0.28"),
             ("LAST_PMT_AMT", "NUMBER(10,2)", "Most recent payment, principal and interest only", "pi.round(2)")]}},  # M10
        {"name": "wire", "per_base": 1.5,
         "latent": {"owner": "fk:customer", "ts_utc": "timestamp:2026-09-01..2026-10-30", "amt": "money:18000,sigma=1.0"},
         "target": {"table": "wire", "key": "wire_id", "columns": [
             ("wire_id", "NUMBER(38,0)", "Wire identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Customer", "owner"),
             ("wire_amount", "NUMBER(14,2)", "Wire amount", "amt.round(2)"),
             ("wire_type", "VARCHAR(10)", "Wire type", "hint:code:DOMESTIC=0.7|INTL=0.3"),
             ("trans_dt_tm", "TIMESTAMP_NTZ", "Transaction time, bank headquarters time (Eastern)",
              "ts_utc - pd.to_timedelta(5, unit='h')")]},                                                           # M11
         "source": {"table": "WIRE", "key": "WIRE_ID", "columns": [
             ("WIRE_ID", "NUMBER(10)", "Wire identifier", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "owner"),
             ("WIRE_AMT", "NUMBER(14,2)", "Wire amount", "amt.round(2)"),
             ("WIRE_TYPE_CD", "VARCHAR2(10)", "Wire type", "hint:code:DOMESTIC=0.7|INTL=0.3"),
             ("TXN_TIMESTAMP", "TIMESTAMP", "Transaction time, UTC", "ts_utc")]}},                                  # M11
    ],
    "derivations": {"target": {}, "source": {}},
    "truth": [
        ("CUST.CUST_NO", "customer.customer_id", "exact", [], None),
        ("CUST.CUST_NM", "customer.full_name", "exact", [], None),
        ("CUST.DOB", "customer.birth_date", "conflict", ["null_semantics"], None),                                   # M12
        ("CUST.CUST_STAT_CD", "customer.customer_status", "conflict", ["code_set"], None),                           # M4
        ("ACCT.ACCT_NO", "deposit.account_id", "exact", [], None),
        ("ACCT.CUST_NO", "deposit.customer_id", "exact", [], None),
        ("ACCT.OPEN_DT", "deposit.acct_open_date", "conflict", ["temporal"], None),                                  # M1
        ("ACCT.CURR_BAL", "deposit.current_balance", "conflict", ["inclusion"], None),                               # M2
        ("ACCT.LAST_TRANS_DT", "deposit.last_activity_date", "conflict", ["temporal"], None),                        # M5
        ("ACCT.INT_RATE", "deposit.interest_rate", "conflict", ["methodology"], None),                               # M7
        ("ACCT.BRANCH_ID", "deposit.branch_code", "conflict", ["identity"], None),                                   # M9
        ("ACCT.ACCT_TIER_CD", "deposit.account_tier", "exact", [], None),
        ("CARD.CARD_ID", "card.card_id", "exact", [], None),
        ("CARD.CUST_NO", "card.customer_id", "exact", [], None),
        ("CARD.CR_LIMIT_AMT", "card.credit_limit", "conflict", ["methodology"], None),                               # M6
        ("CARD.CARD_STAT_CD", "card.card_status", "exact", [], None),
        ("CARD.CARD_LAST4", "card.card_last4", "exact", [], None),
        ("LN.LN_NO", "loan.loan_id", "exact", [], None),
        ("LN.CUST_NO", "loan.customer_id", "exact", [], None),
        ("LN.PRIN_BAL", "loan.principal_balance", "exact", [], None),
        ("LN.INT_RT", "loan.note_rate", "exact", [], None),
        ("LN.ORIG_DT", "loan.origination_date", "exact", [], None),
        ("LN.DAYS_PAST_DUE", "loan.dpd", "conflict", ["temporal"], None),                                            # M3
        ("LN.CHG_OFF_AMT", "loan.chargeoff_balance", "conflict", ["inclusion"], None),                               # M8
        ("MTG.MTG_NO", "mortgage.mortgage_id", "exact", [], None),
        ("MTG.CUST_NO", "mortgage.customer_id", "exact", [], None),
        ("MTG.ORIG_DT", "mortgage.origination_date", "exact", [], None),
        ("MTG.PROP_ST_CD", "mortgage.property_state", "exact", [], None),
        ("MTG.LAST_PMT_AMT", "mortgage.last_payment_amount", "conflict", ["inclusion"], None),                       # M10
        ("WIRE.WIRE_ID", "wire.wire_id", "exact", [], None),
        ("WIRE.CUST_NO", "wire.customer_id", "exact", [], None),
        ("WIRE.WIRE_AMT", "wire.wire_amount", "exact", [], None),
        ("WIRE.WIRE_TYPE_CD", "wire.wire_type", "exact", [], None),
        ("WIRE.TXN_TIMESTAMP", "wire.trans_dt_tm", "conflict", ["temporal"], None),                                  # M11
    ],
}
