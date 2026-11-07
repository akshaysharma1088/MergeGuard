from openpyxl import load_workbook

from mergeguard.bench.generate import generate
from mergeguard.cards import load_side
from mergeguard.evaluate import evaluate, name_only_baseline
from mergeguard.match import match_sides
from mergeguard.report import write_mapping


def _scenario(tmp_path):
    d = generate(tmp_path / "mb", seed=11, n_acquirer=800, n_acquired=600)
    src = load_side(d / "acquired", "acquired", "oracle")
    tgt = load_side(d / "acquirer", "acquirer")
    return d, src, tgt


def test_matcher_beats_name_baseline(tmp_path):
    d, src, tgt = _scenario(tmp_path)
    res = match_sides(src, tgt)
    ours = evaluate(res, d / "ground_truth.json")
    base = evaluate(name_only_baseline(src, tgt), d / "ground_truth.json",
                    auto_accept=lambda m: m.target is not None)
    assert ours["target_accuracy"] > base["target_accuracy"]
    assert ours["harmful_auto_accepts"] == 0
    assert base["harmful_auto_accepts"] > 0


def test_false_friends_and_ddr(tmp_path):
    d, src, tgt = _scenario(tmp_path)
    res = {m.source: m for m in match_sides(src, tgt)}
    assert res["xfer.transfer_amount"].false_friend["target"] == "transfer.transfer_amount"
    assert res["xfer.xfer_amt_net"].target == "transfer.transfer_amount"
    assert res["xfer.settle_dt"].target == "transfer.posted_date"
    assert "temporal" in res["xfer.posted_date"].false_friend["reasons"]
    ddr = res["cust.active_flag"].ddr
    assert ddr["available"] and 0.05 < ddr["rate"] < 0.4


def test_excel_report_is_editable(tmp_path):
    d, src, tgt = _scenario(tmp_path)
    path = write_mapping(match_sides(src, tgt), src, tgt, tmp_path / "m.xlsx")
    wb = load_workbook(path)
    ws = wb["Mapping"]
    headers = [c.value for c in ws[1]]
    assert "decision" in headers and "target_attribute" in headers
    assert len(ws.data_validations.dataValidation) == 3
    assert "trap_identified" in headers and "finance_risk_signoff" in headers
    assert "SME questions" in wb.sheetnames
    assert ws.max_row == 24


def test_sme_workbook_export(tmp_path):
    from mergeguard.sme_export import export_sme
    d, src, tgt = _scenario(tmp_path)
    res = match_sides(src, tgt)
    path = export_sme(res, src, tgt, tmp_path / "sme.xlsx")
    wb = load_workbook(path)
    ws = wb["Semantic Mapping Matrix"]
    ids = [ws.cell(row=r, column=1).value for r in range(5, 5 + len(res))]
    assert ids[0] == "MG-0001" and all(ids)
    gates = {ws.cell(row=r, column=22).value for r in range(5, 5 + len(res))}
    assert "Approved - Ready for ETL" not in gates          # MergeGuard never approves on its own
    assert "Blocked - Trap Unresolved" in gates
    assert "MergeGuard Evidence" in wb.sheetnames
    assert str(max(len(res) + 4, 29)) in wb["Executive Dashboard"]["A5"].value


def test_trial_load_verification(tmp_path):
    from mergeguard.bench.round3 import SPEC_G
    from mergeguard.bench.spec import generate_spec
    from mergeguard.verify import Verifier
    d = generate_spec(SPEC_G, tmp_path / "g", seed=571, n_acquirer=800, n_acquired=600)
    src = load_side(d / "acquired", "acquired", "oracle")
    tgt = load_side(d / "acquirer", "acquirer", "snowflake")
    res = match_sides(src, tgt)
    checks = {c.source: c for c in Verifier(src, tgt, d / "parallel").run(res)}
    assert checks["MTG_LN.ESCROW_BAL"].status == "FAIL" and "sign" in checks["MTG_LN.ESCROW_BAL"].flags
    assert checks["MTG_LN.HMDA_ACTN_DT"].status == "FAIL" and "temporal" in checks["MTG_LN.HMDA_ACTN_DT"].flags
    assert checks["MTG_LN.ESCROW_BAL"].edge_cases
    assert all(checks[s].status != "FAIL" for s in ("CUSTOMER.CUST_NO", "CUSTOMER.CUST_NAME", "MTG_LN.PRIN_BAL"))
