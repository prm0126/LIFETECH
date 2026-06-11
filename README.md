# LIFETECH · Oracle DB Explorer

A lightweight web app to connect to an Oracle database, browse tables, search
column data, edit cells inline, and run conditional bulk updates (e.g. flip a
flag column to `1` or `0` where a condition matches).

## Features

- **Connect to Oracle** using a simple `.env` config (thin mode — no Oracle
  client install required).
- **Browse tables/views** — the sidebar lists everything in your schema; filter
  by name.
- **View column data** in a paginated grid with column metadata.
- **Per-header search** — every column has its own search box (case-insensitive
  substring match) so you can filter rows by any combination of columns.
- **Inline editing** — double-click any cell to edit and save a single value.
- **Conditional update** — set a column to a value (e.g. `1` or `0`) for all
  rows matching a `WHERE` condition you write, with a preview count before you
  commit.

## Setup

1. **Install dependencies** (Python 3.9+):

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure the connection** — copy the example env file and edit it:

   ```bash
   cp .env.example .env
   # then edit .env with your Oracle user, password, and DSN
   ```

   The DSN is either `host:port/service_name` (e.g.
   `db.example.com:1521/ORCLPDB1`) or a `tnsnames.ora` alias.

3. **Run the app**:

   ```bash
   python app.py
   ```

   Open <http://localhost:5000> in your browser.

## How to use

1. Pick a table from the left sidebar (use the filter box to find it fast).
2. The grid shows the rows. Type in any column's **search box** to filter.
3. **Double-click a cell** to edit a single value; press Enter to save,
   Escape to cancel.
4. For the "set a column to 1 or 0 with a condition" case, click
   **Conditional update…**:
   - Choose the **column** (e.g. your flag column).
   - Enter the **new value** (`1` or `0`).
   - Enter a **WHERE condition** (e.g. `STATUS = 'EXPIRED' AND TYPE = 'A'`).
     Use `1=1` to match every row.
   - Click **Preview count** to see how many rows match, then **Apply update**.

## How it handles SQL safety

- Table and column names are validated against the live data dictionary
  (`all_tables`, `all_views`, `all_tab_columns`) — only real objects in your
  schema are accepted, and identifiers must match a strict pattern.
- All **values** (search filters and new cell/bulk values) are passed as bind
  variables, never string-concatenated.
- The **WHERE condition** in the conditional-update form is raw SQL by design
  (so you can express arbitrary conditions). This is an internal admin tool —
  semicolons are rejected and a preview count is shown, but treat write access
  to this app the same as write access to the database. Run it behind your own
  authentication/network controls.

## Architecture

| File                 | Purpose                                            |
|----------------------|----------------------------------------------------|
| `app.py`             | Flask backend + Oracle access (connection pool, REST API). |
| `templates/index.html` | Single-page UI.                                  |
| `static/style.css`   | Styling.                                           |
| `static/app.js`      | Frontend logic (grid, search, inline edit, bulk update). |

### API endpoints

| Method | Path                              | Description                       |
|--------|-----------------------------------|-----------------------------------|
| GET    | `/api/config`                     | Non-secret connection info.       |
| GET    | `/api/tables`                     | List tables/views in the schema.  |
| GET    | `/api/tables/<table>/columns`     | Column metadata.                  |
| GET    | `/api/tables/<table>/data`        | Paginated rows + per-column filters. |
| POST   | `/api/tables/<table>/cell`        | Update one cell (by ROWID).       |
| POST   | `/api/tables/<table>/bulk-update` | Conditional update (with preview).|
