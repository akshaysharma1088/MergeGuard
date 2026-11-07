# MergeGuard

**Catch false-friend attributes before a post-acquisition data migration.**

When one company acquires another, the two data estates often share column names that do not
share a meaning. Both banks have `transfer_amount`; one stores dollars including fees with a sign,
the other stores cents net of fees with a separate direction column. Name-based matchers accept the
pair, row counts reconcile, and every downstream report is wrong.

MergeGuard scores every source and target attribute pair on six kinds of evidence (name, documented
meaning, type, value profile, derivation logic, and context) and weights logic and values over names.
It flags:

- **False friends**: same name, different meaning, with the reasons (unit, sign, inclusion, temporal...)
- **Hidden matches**: different names, same meaning (`xfer_amt_net` is the real `transfer_amount`)
- **Definition conflicts**, measured with the **definition disagreement rate (DDR)**: the target's rule is
  run on source entities. Example: 18.7% of Riverbend customers flip status under Keystone's "active" rule.

The output is an editable Excel mapping. Analysts review it, fix it, and upload it back.

## Quick start

```bash
pip install -e .
mergeguard bench mb                                 # generate a MergeBench scenario
mergeguard match mb/acquired mb/acquirer -o mapping.xlsx
mergeguard eval mb                                  # compare with a name-only baseline
```

## Connecting to real systems

MergeGuard reads each bank through a small YAML config, so nothing has to be exported by hand.

| Connector | Reads | Install |
|---|---|---|
| `snowflake` | Tables and views, column comments, declared primary keys, view logic, a row sample | `pip install mergeguard[snowflake]` |
| `sql` | Any SQLAlchemy database: Postgres, Oracle, SQL Server, MySQL, SQLite | `pip install mergeguard[sql]` + driver |
| `excel` | One sheet per table, plus an optional "Data Dictionary" sheet | built in |
| `csv` / `parquet` | A folder of extracts | built in |

A data dictionary (Excel or CSV) is optional. Its headers are matched loosely ("Field", "Column Name", "Business Definition", "PK" all work), and it overrides catalog comments. Computed columns in views are captured as derivation logic. Credentials are written as `${ENV_VAR}` and never stored in the config.

```bash
mergeguard ingest examples/connectors/snowflake_acquired.yml -o out/acquired  # optional snapshot
mergeguard match acquired.yml acquirer.yml --sme-workbook review.xlsx      # configs work anywhere a folder does
```

Examples are in `examples/connectors/`. The Snowflake connector is tested against a mocked driver; run it on a non-production account first.

## MergeBench

A generator for paired synthetic enterprises. v0 ships one scenario: Keystone Bank (acquirer) buys
Riverbend Financial (acquired). Planted cases cover the nine-type conflict taxonomy: unit, scale, sign,
inclusion, temporal, population, grain, null semantics and code set, plus hidden matches, a 1:N split and an
unmatched attribute. Ground truth records the correct target and conflict types for every source attribute.

All data is synthetic.

## Status

v0.0.1, research prototype. Implemented: MergeBench generator, evidence matcher, false-friend and conflict
detection, DDR, Excel mapping report, evaluation. Next: upload and validation of the edited mapping,
migration code generation, pipeverify verification, audit evidence bundle.

## License

Apache-2.0
