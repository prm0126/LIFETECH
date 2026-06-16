# Oracle Filter & Update

A small web UI to connect to an Oracle database, filter rows with conditions
you build in the browser, and set **one column to `1` or `0`** for every
matching row.

## What it does

1. **Connect** — enter host / port / service name / user / password.
2. **Pick a table** — the app lists your tables and loads the columns.
3. **Build filter conditions** — one or more `column operator value` rules,
   combined with `AND` (ALL) or `OR` (ANY).
   Operators: `=`, `!=`, `<`, `>`, `<=`, `>=`, `LIKE`, `NOT LIKE`, `IN`,
   `IS NULL`, `IS NOT NULL`.
4. **Preview** — see the matching rows and the total count.
5. **Update** — choose the target column, set it to `1` or `0`; the same
   filter is used to `UPDATE` and `COMMIT` every matching row. You're asked
   to confirm, and the affected row count is shown afterwards.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

> The Oracle driver's pip package is named **`oracledb`** (not `python-oracledb`).
> On Windows use `py -m pip install flask oracledb` and `py app.py`.

Then open <http://127.0.0.1:5000>.

`python-oracledb` runs in **thin mode**, so no Oracle Instant Client install
is required.

## Notes on safety

- Filter **values** are always sent as Oracle **bind variables** (no string
  concatenation of user values into SQL).
- Table and column **names** can't be bound, so they are validated against a
  strict identifier pattern *and* checked against the table's real columns
  before being used.
- The update always runs inside the same WHERE filter you previewed, and the
  number of affected rows is reported back. A `0`-condition filter updates the
  whole table — preview first to confirm the count.
- For `IN`, enter a comma-separated list (e.g. `A,B,C`).
