# LIFETECH Management Dashboard

A lightweight web dashboard for hospital management. It has a left-hand menu
with multiple dashboards:

**Overview**
- **Total registrations** &mdash; day-wise, week-wise and month-wise (with a trend chart)
- **Encounters created today** &mdash; total, **urgent care**, **consult**, **non-consult** and **consulted**
- **Doctor-wise encounters** &mdash; trend over time split by doctor (Day / Week / Month / Year)
- Per-provider breakdown for today

**Nurse Analysis**
- Patients with **notes** entered today (a row exists in the provider-visit table)
- Patients with **vitals** entered today, total vitals records, active nurses
- **Notes vs Vitals** trend (Day / Week / Month / Year)
- **Vitals details** table (EMR date, MRNO, vital, time, entered-by nurse)

**Billing**
- KPI cards: revenue today / this week / this month, bills today, and today's
  split by **Services / Pharmacy / Consultation** plus discount
- **Revenue trend** (Day / Week / Month / Year) and **Revenue by source** charts
- **Top services by revenue** (this month) table
- Built on `GEN_PAT_BILLING` / `INV_PAT_BILLING` / `CON_PAT_BILLING` / `PH_PAT_BILLING`
  / `INV_MAST_SERVICE`, using `NET_AMOUNT`, all filtered `ISVALID = 1`

**Custom Reports** (build-your-own)
- A web page to add your own tiles by writing SQL (any tables / joins you want)
- Pick a type: **KPI card**, **table**, **bar chart**, or **line chart**, then Preview and Save
- Saved reports persist in `custom_queries.json` on the server and appear as live tiles
- Each saved report also appears in the **left menu (My Reports)** as its own page, where it can be **refreshed, edited or deleted**
- **Interactive parameters:** if the SQL uses `:date_from`, `:date_to` or `:gran`
  (granularity for `TRUNC` &mdash; `'DD'`/`'IW'`/`'MM'`/`'YYYY'`), the report shows live
  **Daily/Weekly/Monthly/Yearly** + **date-range** controls and re-runs filtered (fast,
  no full-history scan). Example:
  ```sql
  SELECT TO_CHAR(TRUNC(EMR_DATE, :gran), 'YYYY-MM-DD') AS period, COUNT(*) AS notes
  FROM EMR_PROVIDER_VISIT
  WHERE TEMPLATE_TYPE = 1 AND ISVALID = 1
    AND EMR_DATE >= :date_from AND EMR_DATE < :date_to + 1
  GROUP BY TRUNC(EMR_DATE, :gran) ORDER BY 1
  ```
- **Sample billing reports:** the **"Load sample billing reports"** button seeds a ready-made
  set (revenue trend, revenue by source, top services/pharmacy items, consultation revenue by
  provider, pharmacy trend, discount trend, revenue today) built on `GEN_PAT_BILLING` /
  `INV_PAT_BILLING` / `CON_PAT_BILLING` / `PH_PAT_BILLING` / `INV_MAST_SERVICE`, all filtered `ISVALID = 1`.
- **Read-only & safety:** only a single `SELECT`/`WITH` statement is accepted (no `;`,
  no INSERT/UPDATE/DELETE/DDL/PLSQL) and results are capped at `CUSTOM_MAX_ROWS`.
  For defense in depth, point the app at a **read-only Oracle account** for this DB.

It reads directly from the Oracle database and is meant to be hosted on an
internal server so management can open it in any browser on the same network.
The UI has **no external/CDN dependencies**, so it works on an air-gapped LAN.

## Business rules

| Metric        | Source                                         |
|---------------|------------------------------------------------|
| Registrations | `PAT_PATIENT_DEMOGRAPHICS.VISIT_DATE`          |
| Encounters    | `PAT_FIN_ENCOUNTER_DETAILS.START_DATE`         |
| Urgent care   | `ISEMERGENCY = 1`                              |
| Consult       | `NVL(ISNONCONSULTENCOUNTER, 0) = 0`            |
| Non-consult   | `ISNONCONSULTENCOUNTER = 1`                    |
| Consulted     | `IS_CONSULTED = 1`                             |
| Provider name | `GET_EMPLOYEE_NAME(PROVIDER_ID)` Oracle fn.    |

By default only valid encounters (`NVL(ISVALID,1)=1`) are counted. Table names,
column names and the employee-name function are all configurable via `.env` so
the app can point at views or renamed objects without code changes.

## Windows quick start (one click)

On the Windows server, get the code and use the bundled launcher:

```bat
git clone https://github.com/prm0126/LIFETECH.git
cd /d D:\path\to\LIFETECH
run.bat
```

`run.bat` creates a virtual environment, installs dependencies, and creates a
`.env` from the template on first run (it opens Notepad so you can fill in
`ORACLE_USER` / `ORACLE_PASSWORD` / `ORACLE_DSN`). Run it again and the
dashboard starts on `http://0.0.0.0:8080/`.

> Requires Python 3 with **"Add python.exe to PATH"** ticked during install
> (download: https://www.python.org/downloads/windows/). If `git` isn't
> available, download the repo ZIP from GitHub and extract it instead.
>
> Note: on Windows, `cd` to another drive needs the `/d` switch
> (`cd /d D:\...`), and use `copy` rather than the Linux `cp`.

## Setup (manual)

```bash
cd LIFETECH
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # Windows: python -m pip install -r requirements.txt

cp .env.example .env               # Windows: copy .env.example .env
```

Edit `.env` and set at least `ORACLE_USER`, `ORACLE_PASSWORD` and `ORACLE_DSN`
(e.g. `192.168.1.50:1521/ORCLPDB1`).

## Run

**Quick / development**

```bash
python app.py
```

**Production (recommended for hosting)** &mdash; use a WSGI server bound to all
interfaces so other machines on the network can reach it:

```bash
# Cross-platform, no PATH issues (uses waitress under the hood)
python serve.py

# Or the waitress console script (Linux/Windows)
waitress-serve --host=0.0.0.0 --port=8080 app:app

# Linux only (gunicorn)
gunicorn -w 2 -b 0.0.0.0:8080 app:app
```

Then management opens **`http://<server-ip>:8080/`** from their browser
(e.g. `http://192.168.1.50:8080/`).

> If a firewall is enabled on the host, allow inbound TCP on the chosen port.

## Share on the network (let others open it from their PCs)

1. **Keep the app running** on the server (`run.bat` / `python serve.py`). It already
   listens on all interfaces (`0.0.0.0:8080`).
2. **Open the firewall once:** right-click **`open-firewall.bat`** → *Run as administrator*
   (adds an inbound rule for TCP 8080 and prints this machine's IP).
3. **Find the server IP:** run `ipconfig` and note the **IPv4 Address** (e.g. `192.168.129.x`).
4. **Share the URL:** anyone on the same network opens **`http://<server-ip>:8080/`** in a browser.

To always-on it (survive logoff/reboot) run it as a Windows service or a Task
Scheduler task at startup — see "Keep it running 24/7" below.

### Keep it running 24/7
- **Task Scheduler (built-in):** create a task → trigger *At startup* → action
  *Start a program* → `D:\VERDAN-MONITOR\LIFETECH\.venv\Scripts\python.exe` with argument
  `serve.py` and *Start in* `D:\VERDAN-MONITOR\LIFETECH` → check *Run whether user is
  logged on or not* and *Run with highest privileges*.
- **As a service (NSSM):** `nssm install LIFETECH "D:\VERDAN-MONITOR\LIFETECH\.venv\Scripts\python.exe" serve.py`
  then set *Startup directory* to the project folder and start the service.



| Endpoint                       | Description                              |
|--------------------------------|------------------------------------------|
| `GET /`                        | Dashboard page                           |
| `GET /api/health`              | Database connectivity check              |
| `GET /api/summary`             | KPI cards (registrations + encounters)   |
| `GET /api/registrations?period=day\|week\|month` | Trend time series      |
| `GET /api/encounters/today`    | Today's encounter breakdown              |
| `GET /api/doctors/today`       | Today's encounters grouped by provider   |

The page auto-refreshes every 60 seconds.

## Project layout

```
app.py            Flask app + JSON API
config.py         Configuration (env-driven)
db.py             Oracle connection pool (python-oracledb)
queries.py        Dashboard SQL
templates/        dashboard.html
static/css        styling
static/js         chart.js (custom mini chart), dashboard.js
```
